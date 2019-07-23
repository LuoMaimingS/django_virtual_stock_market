from django.shortcuts import render
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from decimal import Decimal
import datetime
import time
import json

from .models import clients, stocks, forms, sim_market, sim_clients, sim_stocks
from .models import config, utils
from .models.trades import CommissionMsg, commission_handler
from .simulator_main import simulator_main_func, anchor_one_stock
from .baselines.baselines.gail.dataset.generate_expert_data import generate_expert_data


def index(request):
    """
    Main page
    """
    return render(request, 'market/index.html')


def all_stocks(request):
    """
    在股票市场中显示全部股票
    """
    all_the_stocks = stocks.Stock.objects.order_by('symbol')
    context = {'stocks': all_the_stocks}
    return render(request, 'market/all_stocks.html', context)


def stock_detail(request, stock_id):
    """
    具体显示股票市场中某支股票的详细信息
    """
    this_stock = stocks.Stock.objects.get(id=stock_id)
    ask_info, bid_info = this_stock.get_level5_data()
    context = {'stock': this_stock, 'level5_ask': ask_info, 'level5_bid': bid_info}
    return render(request, 'market/stock.html', context)


def register(request):
    """
    注册新用户
    """
    if request.method != 'POST':
        # 刚进入页面，未提交数据，创建一个新表单
        form = UserCreationForm()
    else:
        # POST，提交填写的数据，对数据进行处理
        form = UserCreationForm(data=request.POST)
        if form.is_valid():
            new_user = form.save()

            # 创建相应的用户client
            new_client = clients.BaseClient.objects.create(driver=new_user, name=new_user.username)

            # 默认配置虚拟持仓
            default_stock, created = stocks.Stock.objects.get_or_create(symbol=config.DEFAULT_HOLD_SYMBOL,
                                                                        name=config.DEFAULT_HOLD_NAME,
                                                                        last_price=10, limit_up=11, limit_down=9.1,
                                                                        high=10, low=10)
            if created:
                default_stock.initialize_order_book()
            new_client.holdingelem_set.create(owner=new_client, stock_corr=default_stock, stock_symbol=default_stock.symbol,
                                              stock_name=default_stock.name, vol=config.DEFAULT_HOLD_VOLUME,
                                              available_vol=config.DEFAULT_HOLD_VOLUME, price_guaranteed=10, cost=10)

            # 用户自动登陆，重定向至主页
            authenticated_user = authenticate(username=new_user.username, password=request.POST['password1'])
            login(request, authenticated_user)
            return HttpResponseRedirect(reverse('market:welcome'))

    context = {'form': form}
    return render(request, 'market/register.html', context)


def welcome(request):
    """
    注册或登陆成功的欢迎页面
    """
    user = request.user
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    num_client = clients.BaseClient.objects.count()
    num_stock = stocks.Stock.objects.count()
    from django.utils import timezone
    time = timezone.now()
    context = {'user': user, 'user_agent': user_agent, 'num_client': num_client, 'num_stock': num_stock, 'time': time}

    return render(request, 'market/welcome.html', context)


@login_required
def account_view(request):
    user_client, _ = clients.BaseClient.objects.get_or_create(driver=request.user, name=request.user.username)
    holding = clients.HoldingElem.objects.filter(owner=user_client).order_by('stock_symbol')
    commission = clients.CommissionElem.objects.filter(owner=user_client).order_by('stock_symbol')
    transaction = clients.TransactionElem.objects.filter(owner=user_client).order_by('stock_symbol')
    focusing = clients.FocusElem.objects.filter(owner=user_client).order_by('stock_symbol')

    for hold in holding:
        user_client.profit = 0
        hold.refresh()
        user_client.profit += hold.profit
    user_client.save()
    context = {'client': user_client, 'holding': holding, 'commission': commission, 'transaction': transaction,
               'focusing': focusing}
    return render(request, 'market/my_account.html', context)


@login_required
def commit_view(request):
    user_client, _ = clients.BaseClient.objects.get_or_create(driver=request.user, name=request.user.username)
    err_msg = None
    if request.method == 'POST':
        form = forms.BidForm(request.POST)

        if form.is_valid():
            bid_stock = form.cleaned_data['stock_corr']
            bid_price = form.cleaned_data['price_committed']
            bid_volume = form.cleaned_data['vol_committed']
            direction = form.cleaned_data['operation']
            new_commission = CommissionMsg(commit_client=user_client, stock_symbol=bid_stock.symbol,
                                           commit_direction=direction, commit_price=bid_price,
                                           commit_vol=bid_volume)
            if new_commission.is_valid():
                commission_handler(new_commission)
                return HttpResponseRedirect(reverse('market:my_account'))
            else:
                return render(request, 'market/invalid/invalid_form.html')
        else:
            return render(request, 'market/invalid/invalid_form.html')

    else:
        form = forms.BidForm()

    holding = user_client.holdingelem_set.all()
    context = {'client': user_client,'form': form, 'holding': holding}
    return render(request, 'market/user_commit.html', context)


@login_required
def cancel_view(request):
    user_client, _ = clients.BaseClient.objects.get_or_create(driver=request.user, name=request.user.username)
    if request.method == 'POST':
        form = forms.CancelForm(request.POST)

        if form.is_valid():
            cancel = form.cleaned_data['cancel_cms']
            new_commission = CommissionMsg(commit_client=user_client, stock_symbol=cancel.stock_symbol,
                                           commit_direction='c', commit_price=cancel.price_committed,
                                           commit_vol=cancel.vol_committed - cancel.vol_traded, cancel_cms=cancel,
                                           commit_date=cancel.date_committed)
            if new_commission.is_valid():
                commission_handler(new_commission)
                return HttpResponseRedirect(reverse('market:my_account'))
            else:
                return render(request, 'market/invalid/invalid_form.html')
        else:
            return render(request, 'market/invalid/invalid_form.html')

    else:
        form = forms.CancelForm()

    commission = user_client.commissionelem_set.all()
    context = {'client': user_client,'form': form, 'commission': commission}
    return render(request, 'market/user_cancel.html', context)


# 下面的视图用于股市模拟，需要超级用户权限
# 使用虚拟的client，基于真实的股票数据进行模拟


@login_required
def simulator_welcome(request):
    """
    模拟股市的欢迎页面，需要超级用户权限
    """
    # 只有超级用户才有权限进行模拟
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')

    num_clients = clients.BaseClient.objects.count()
    num_v_clients = clients.BaseClient.objects.filter(driver=None).count()
    num_stocks = sim_stocks.SimStock.objects.count()
    market, _ = sim_market.SimMarket.objects.get_or_create(id=1)
    cur_datetime = str(market.datetime)
    tick = market.tick
    context = {'num_clients': num_clients, 'num_stocks': num_stocks, 'num_v_clients': num_v_clients,
               'datetime': cur_datetime, 'tick': tick}
    return render(request, 'market/simulator/simulator_welcome.html', context)


@login_required
def simulator_v_stocks(request):
    """
    在模拟股票市场中显示全部虚拟股票
    """
    # 只有超级用户才有权限进行模拟
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    all_the_v_stocks = sim_stocks.SimStock.objects.order_by('symbol')
    context = {'stocks': all_the_v_stocks}
    return render(request, 'market/simulator/all_v_stocks.html', context)


@login_required
def simulator_stock_detail(request, stock_id):
    """
    具体显示股票市场中某支股票的详细信息
    """
    # 只有超级用户才有权限进行模拟
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    this_stock = sim_stocks.SimStock.objects.get(id=stock_id)
    ask_info, bid_info = this_stock.get_order_book_data(level=5)

    market = sim_market.SimMarket.objects.get(id=1)
    cur_datetime = market.datetime
    cur_day = cur_datetime.day
    stock_slices = sim_stocks.SimStockSlice.objects.filter(stock_symbol=this_stock.symbol,
                                                           datetime__day=cur_day, datetime__lte=cur_datetime)
    time_log = []
    price_log = []
    volume_log = []
    for each_slice in stock_slices:
        time_log.append(str(each_slice.datetime)[-9:-3])
        price_log.append(float(each_slice.last_price))
        volume_log.append(each_slice.volume)

    # 读取生成数据
    generate_trades = sim_stocks.SimTradeHistory.objects.filter(stock_symbol=this_stock.symbol).order_by('tick','id').reverse()
    prev_tick = None
    price_generated = []
    for trade in generate_trades:
        if prev_tick != trade.tick:
            price_generated.append(float(trade.price))
            prev_tick = trade.tick
        else:
            continue
    price_generated.reverse()
    tick = list(range(len(price_generated) + 1))
    tick.remove(0)
    context = {'stock': this_stock, 'level5_ask': ask_info, 'level5_bid': bid_info, 'time': str(cur_datetime),
               'time_log': json.dumps(time_log), 'price_log': json.dumps(price_log), 'volume_log': json.dumps(volume_log),
               'tick': json.dumps(tick), 'price_generated': json.dumps(price_generated)}
    return render(request, 'market/simulator/v_stock.html', context)


@login_required
def simulator_stock_daily(request, stock_id):
    """
    显示股票市场中某支股票的历史信息
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    this_stock = sim_stocks.SimStock.objects.get(id=stock_id)
    market = sim_market.SimMarket.objects.get(id=1)
    cur_datetime = market.datetime
    cur_date = cur_datetime.date()

    stock_daily_info = sim_stocks.SimStockDailyInfo.objects.filter(stock_symbol=this_stock.symbol, date__lt=cur_date)
    candles = []
    volume = []
    for info in stock_daily_info:
        candles.append([str(info.date), float(info.open), float(info.high), float(info.low), float(info.close)])
        volume.append([str(info.date), info.volume])

    context = {'stock': this_stock, 'time': str(cur_datetime),
               'candles': json.dumps(candles), 'volume': json.dumps(volume)}
    return render(request, 'market/simulator/v_stock_daily.html', context)


@login_required
def simulator_stock_tick(request, stock_id):
    """
    显示股票市场中某支股票的tick截面信息
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    this_stock = sim_stocks.SimStock.objects.get(id=stock_id)
    market, created = sim_market.SimMarket.objects.get_or_create(id=2)  # 用于浏览截面
    if created:
        origin_market = sim_market.SimMarket.objects.get(id=1)
        market.anchored_datetime = origin_market.anchored_datetime
        market.datetime = origin_market.anchored_datetime
        market.save()
    cur_datetime = market.datetime
    stock_tick_info = sim_stocks.SimStockSlice.objects.filter(stock_symbol=this_stock.symbol, datetime=cur_datetime)
    ask_info = None
    bid_info = None
    tick_info = None
    if stock_tick_info.exists():
        ask_info, bid_info = stock_tick_info[0].get_level5_data()
        tick_info = stock_tick_info[0]

    context = {'stock': this_stock, 'info': tick_info, 'level5_ask': ask_info, 'level5_bid': bid_info, 'time': str(cur_datetime)}
    return render(request, 'market/simulator/v_stock_tick.html', context)


@login_required
def simulator_stock_prev_tick(request, stock_id):
    """
    显示股票市场中某支股票上一个的tick截面信息
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    this_stock = sim_stocks.SimStock.objects.get(id=stock_id)
    market = sim_market.SimMarket.objects.get(id=2)
    cur_datetime = market.datetime
    stock_tick_info = sim_stocks.SimStockSlice.objects.get(stock_symbol=this_stock.symbol, datetime=cur_datetime)
    prev_info = sim_stocks.SimStockSlice.objects.filter(id=stock_tick_info.id - 1)
    ask_info = None
    bid_info = None
    tick_info = None
    if prev_info.exists():
        tick_info = prev_info[0]
        ask_info, bid_info = prev_info[0].get_level5_data()
        market.datetime = prev_info[0].datetime
        market.save()
        cur_datetime = market.datetime

    context = {'stock': this_stock, 'info': tick_info, 'level5_ask': ask_info, 'level5_bid': bid_info, 'time': str(cur_datetime)}
    return render(request, 'market/simulator/v_stock_tick.html', context)


@login_required
def simulator_stock_next_tick(request, stock_id):
    """
    显示股票市场中某支股票的tick截面信息
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    this_stock = sim_stocks.SimStock.objects.get(id=stock_id)
    market = sim_market.SimMarket.objects.get(id=2)
    cur_datetime = market.datetime
    stock_tick_info = sim_stocks.SimStockSlice.objects.get(stock_symbol=this_stock.symbol, datetime=cur_datetime)
    next_info = sim_stocks.SimStockSlice.objects.filter(id=stock_tick_info.id + 1)
    ask_info = None
    bid_info = None
    tick_info = None
    if next_info.exists():
        tick_info = next_info[0]
        ask_info, bid_info = next_info[0].get_level5_data()
        market.datetime = next_info[0].datetime
        market.save()
        cur_datetime = market.datetime

    context = {'stock': this_stock, 'info': tick_info, 'level5_ask': ask_info, 'level5_bid': bid_info, 'time': str(cur_datetime)}
    return render(request, 'market/simulator/v_stock_tick.html', context)


@login_required
def simulator_main(request):
    """
    模拟股市的主页面
    """
    # 只有超级用户才有权限进行模拟
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    result = simulator_main_func(request.user)
    context = {'result': result}
    return render(request, 'market/simulator/simulator_main.html', context)


@login_required
def simulator_v_clients(request):
    """
    模拟股市的主页面
    """
    # 只有超级用户才有权限进行模拟
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    v_clients = clients.BaseClient.objects.filter(driver=None)
    if request.method == 'POST':
        client_form = forms.VClientForm(request.POST)
        if client_form.is_valid():
            name = client_form.cleaned_data['name']
            cash = client_form.cleaned_data['cash']
            strategy = client_form.cleaned_data['strategy']
            new_client = clients.BaseClient(name=name, cash=cash, frozen_cash=0, flexible_cash=cash,
                                            strategy=strategy)
            new_client.save()
            stock_corr = client_form.cleaned_data['stock_corr']
            vol = client_form.cleaned_data['vol']
            market = sim_market.SimMarket.objects.get(id=1)
            if vol != 0:
                new_holding = sim_clients.SimHoldingElem(owner=new_client.id, stock_symbol=stock_corr.symbol,
                                                         stock_name=stock_corr.name, date_bought=market.datetime,
                                                         vol=vol, frozen_vol=0, available_vol=vol)
                new_holding.save()
            market.num_v_clients += 1
            market.save()
            return HttpResponseRedirect(reverse('market:sim_clients'))
        else:
            return render(request, 'market/invalid/invalid_form.html')

    else:
        client_form = forms.VClientForm()

    context = {'v_clients': v_clients, 'client_form': client_form}
    return render(request, 'market/simulator/all_v_clients.html', context)


@login_required
def simulator_client_detail(request, client_id):
    """
    模拟股市的client信息界面
    """
    # 只有超级用户才有权限进行查看
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')

    this_client = clients.BaseClient.objects.get(id=client_id)
    holding = sim_clients.SimHoldingElem.objects.filter(owner=client_id).order_by('stock_symbol')
    commission = sim_clients.SimCommissionElem.objects.filter(owner=client_id).order_by('stock_symbol')
    transaction = sim_clients.SimTransactionElem.objects.filter(one_side=client_id).order_by('stock_symbol')

    for hold in holding:
        this_client.profit = 0
        hold.refresh()
        this_client.profit += hold.profit
    this_client.save()
    context = {'client': this_client, 'holding': holding, 'commission': commission, 'transaction': transaction}
    return render(request, 'market/simulator/client.html', context)


@login_required
def simulator_reset(request):
    """
    重置模拟的股市（还原到切入的点）
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    superuser_client, _ = clients.BaseClient.objects.get_or_create(driver=request.user)
    simulator_reset_handler(request, superuser_client)
    return HttpResponseRedirect(reverse('market:sim_welcome'))


def simulator_reset_handler(request, superuser_client):
    time0 = time.time()
    assert isinstance(superuser_client, clients.BaseClient)
    market = sim_market.SimMarket.objects.get(id=1)
    sim_market.SimMarket.objects.filter(id=2).delete()
    clients.BaseClient.objects.filter(driver=None).delete()
    sim_clients.SimTransactionElem.objects.all().delete()
    sim_clients.SimHoldingElem.objects.all().delete()
    sim_clients.SimCommissionElem.objects.all().delete()

    market.datetime = market.anchored_datetime
    market.num_v_clients = 0
    market.tick = 0
    market.save()
    v_stocks = sim_stocks.SimStock.objects.all()
    for v_stock in v_stocks:
        v_stock.reset()
    superuser_client.cash = 100000000
    superuser_client.flexible_cash = 100000000
    superuser_client.frozen_cash = 0
    superuser_client.save()
    time1 = time.time()
    print('Simulator Reset, Cost {}s'.format(time1 - time0))
    return True


@login_required
def simulator_reset_all(request):
    """
    重置模拟股市的全部数据（包括导入的）
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    superuser_client, _ = clients.BaseClient.objects.get_or_create(driver=request.user)
    simulator_reset_handler(request, superuser_client)
    sim_stocks.SimStockSlice.objects.all().delete()
    sim_stocks.SimTradeHistory.objects.all().delete()
    return HttpResponseRedirect(reverse('market:sim_welcome'))


@login_required
def simulator_import_stock_data(request):
    """
    模拟股市导入股票数据
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    if request.method == 'POST':
        form = forms.ImportStockDataForm(request.POST)
        if form.is_valid():
            stock = form.cleaned_data['stock_symbol']
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            interval = form.cleaned_data['interval']
            ok = import_stock_data(stock, start_date, end_date, interval)
            if ok:
                return HttpResponseRedirect(reverse('market:sim_welcome'))
            else:
                return render(request, 'market/invalid/import_data_failed.html')
    else:
        form = forms.ImportStockDataForm()
    context = {'form': form}
    return render(request, 'market/simulator/import_data.html', context)


def import_stock_data(symbol, start_date, end_date, interval):
    import os
    abs_path = os.path.abspath('utils.py')
    abs_path = abs_path[:-9]
    path = os.path.join(abs_path, 'market', 'data', symbol)
    tb = utils.TickTable(path)
    data = tb.select(symbol, 10180101093000000, 30191231153000000)
    num_record = len(data)
    start_datetime = utils.get_int_from_timestamp(start_date)
    end_datetime = utils.get_int_from_timestamp(end_date)
    prev_day = str(data.index[0])[6:8]
    prev_imported_time = None
    open_today = 0.0
    time0 = time.time()
    count = 0

    sim_stocks.SimStock.objects.get_or_create(symbol=symbol)
    for i in range(num_record):
        cur_datetime = data.index[i]
        if cur_datetime < start_datetime:
            continue
        if cur_datetime > end_datetime:
            break

        if str(data.index[i])[6:8] != prev_day:
            # 加入前一天的日间截面信息
            prev_timestamp = utils.get_timestamp_from_int(prev_imported_time)
            prev_record = data.loc[prev_imported_time]
            sim_stocks.SimStockDailyInfo.objects.create(stock_symbol=symbol, date=prev_timestamp.date(), open=open_today,
                                                        high=prev_record.high, low=prev_record.low,
                                                        close=prev_record['last'],
                                                        volume=prev_record.volume, amount=prev_record.amount)
            prev_day = str(data.index[i])[6:8]
            time1 = time.time()
            print('{} imported, cost {:.2f} s.'.format(prev_timestamp.date(), time1 - time0))
            time0 = time.time()

        if str(cur_datetime)[9:11] == '91' or str(cur_datetime)[9:11] == '92':
            # 集合竞价阶段不导入（开盘）
            prev_imported_time = None
            continue

        if interval == 't':
            pass
        elif interval == 'm':
            # 导入每分钟数据，加入偏移，尽量同步每个整分钟
            if (str(prev_imported_time)[12:14] == '03' or str(prev_imported_time)[12:14] == '06') and \
                    str(cur_datetime)[12:14] == '00':
                pass
            else:
                if prev_imported_time is not None and cur_datetime - prev_imported_time < 100000:
                    continue

        data_slice = data.loc[cur_datetime]
        if prev_imported_time is None:
            # 开盘价
            open_today = data_slice['last']
        cur_timestamp = utils.get_timestamp_from_int(cur_datetime)

        if sim_stocks.SimStockSlice.objects.filter(stock_symbol=symbol, datetime=cur_timestamp).exists():
            # 该股票该截面已经导入
            continue

        stick = sim_stocks.SimStockSlice(stock_symbol=symbol, datetime=cur_timestamp, last_price=data_slice['last'],
                                         high=data_slice.high, low=data_slice.low, open=open_today,
                                         a1=data_slice.a1, a1_v=data_slice.a1_v, b1=data_slice.b1, b1_v=data_slice.b1_v,
                                         a2=data_slice.a2, a2_v=data_slice.a2_v, b2=data_slice.b2, b2_v=data_slice.b2_v,
                                         a3=data_slice.a3, a3_v=data_slice.a3_v, b3=data_slice.b3, b3_v=data_slice.b3_v,
                                         a4=data_slice.a4, a4_v=data_slice.a4_v, b4=data_slice.b4, b4_v=data_slice.b4_v,
                                         a5=data_slice.a5, a5_v=data_slice.a5_v, b5=data_slice.b5, b5_v=data_slice.b5_v,
                                         amount=data_slice.amount, volume=data_slice.volume)
        stick.save()
        prev_imported_time = cur_datetime

        # 每导入10条记录，打印下时间
        count += 1
        if count == 10:
            print('{} imported.'.format(cur_timestamp))
            count = 0

    return True


def anchor_in_time_point(request):
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    if request.method == 'POST':
        form = forms.AnchorForm(request.POST)
        if form.is_valid():
            user_client, _ = clients.BaseClient.objects.get_or_create(driver=request.user)
            simulator_reset_handler(request, user_client)

            anchor_datetime = form.cleaned_data['anchor_datetime']
            market, _ = sim_market.SimMarket.objects.get_or_create(id=1)
            market.datetime = anchor_datetime
            market.anchored_datetime = anchor_datetime
            market.save()
            market_for_tick, _ = sim_market.SimMarket.objects.get_or_create(id=2)
            market_for_tick.datetime = anchor_datetime
            market_for_tick.anchored_datetime = anchor_datetime
            market_for_tick.save()
            v_stocks = sim_stocks.SimStock.objects.all()
            for v_stock in v_stocks:
                slices = v_stock.get_slices()
                if not slices.exists():
                    # 股票的slices信息不存在，跳过
                    continue
                start = slices[0].datetime
                end = slices[slices.count() - 1].datetime
                if anchor_datetime < start or anchor_datetime > end:
                    # anchor time不在slices记录之中，跳过
                    continue
                anchor_slice = None
                for anchor_slice in slices:
                    if anchor_slice.datetime >= anchor_datetime:
                        # 找到该股票在anchor time之后的第一个tick截面信息
                        break
                anchor_one_stock(v_stock, anchor_slice, user_client)
            return HttpResponseRedirect(reverse('market:sim_welcome'))
        else:
            return render(request, 'market/invalid/import_data_failed.html')
    else:
        form = forms.AnchorForm()
    context = {'form': form}
    return render(request, 'market/simulator/anchor_in_time_point.html', context)


@login_required
def gail_main(request):
    market, _ = sim_market.SimMarket.objects.get_or_create(id=1)
    cur_datetime = str(market.datetime)
    context = {'datetime': cur_datetime}
    return render(request, 'market/gail/gail_main.html', context)


@login_required
def gail_generate_expert_data(request):
    """
    生成专家数据
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    market, _ = sim_market.SimMarket.objects.get_or_create(id=1)
    cur_datetime = str(market.datetime)
    if request.method == 'POST':
        generate_data_form = forms.GenerateDataForm(request.POST)
        if generate_data_form.is_valid():
            stock_symbol = generate_data_form.cleaned_data['stock_symbol']
            traj_length = generate_data_form.cleaned_data['traj_length']
            traj_num = generate_data_form.cleaned_data['traj_num']
            track_length = generate_data_form.cleaned_data['track_length']
            generate_expert_data(stock_symbol, traj_length, track_length, traj_num)
            return HttpResponseRedirect(reverse('market:gail_main'))
        else:
            return render(request, 'market/invalid/invalid_form.html')

    else:
        generate_data_form = forms.GenerateDataForm()

    context = {'datetime': cur_datetime, 'generate_data_form': generate_data_form}
    return render(request, 'market/gail/generate_expert_data.html', context)


@login_required
def gail_train(request):
    if request.method == 'POST':
        gail_train_form = forms.GailTrainForm(request.POST)
        if gail_train_form.is_valid():
            stock_symbol = gail_train_form.cleaned_data['stock_symbol']
            seed = gail_train_form.cleaned_data['seed']
            task = gail_train_form.cleaned_data['task']
            algo = gail_train_form.cleaned_data['algo']
            g_step = gail_train_form.cleaned_data['g_step']
            d_step = gail_train_form.cleaned_data['d_step']
            from market.baselines.baselines.gail.run_mujoco import GailArgs, main
            args = GailArgs()
            args.set_args(seed=seed, task=task, algo=algo, g_step=g_step, d_step=d_step)
            main(args)
            return HttpResponseRedirect(reverse('market:gail_main'))
        else:
            return render(request, 'market/invalid/invalid_form.html')

    else:
        gail_train_form = forms.GailTrainForm()

    context = {'gail_train_form': gail_train_form}
    return render(request, 'market/gail/gail_train.html', context)




