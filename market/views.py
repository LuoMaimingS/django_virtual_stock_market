from django.shortcuts import render
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from decimal import Decimal
import time

from .models import clients, stocks, forms, sim_market, sim_clients, sim_stocks
from .models import config, utils
from .models.trades import CommissionMsg, commission_handler


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
    if sim_market.SimMarket.objects.filter(id=0).exists():
        sim_market.SimMarket.objects.filter(id=0).delete()
    market, _ = sim_market.SimMarket.objects.get_or_create(id=0)
    datetime = market.datetime
    tick = market.tick
    context = {'num_clients': num_clients, 'num_stocks': num_stocks, 'num_v_clients': num_v_clients,
               'datetime': datetime, 'tick': tick}
    return render(request, 'market/simulator/simulator_welcome.html', context)


@login_required
def all_v_stocks(request):
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
def sim_stock_detail(request, stock_id):
    """
    具体显示股票市场中某支股票的详细信息
    """
    # 只有超级用户才有权限进行模拟
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    this_stock = sim_stocks.SimStock.objects.get(id=stock_id)
    ask_info, bid_info = this_stock.get_level5_data()
    context = {'stock': this_stock, 'level5_ask': ask_info, 'level5_bid': bid_info}
    return render(request, 'market/simulator/v_stock.html', context)


@login_required
def simulator_main(request):
    """
    模拟股市的主页面
    """
    # 只有超级用户才有权限进行模拟
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')

    v_clients = clients.BaseClient.objects.filter(driver=None)
    if request.method == 'POST':
        client_form = forms.VClientForm(request.POST)
        stock_form = forms.VStockForm(request.POST)

        if 'sim_client' in request.POST:

            if client_form.is_valid():
                name = client_form.cleaned_data['name']
                cash = client_form.cleaned_data['cash']
                strategy = client_form.cleaned_data['strategy']
                new_client = clients.BaseClient(name=name, cash=cash, frozen_cash=0, flexible_cash=cash,
                                                strategy=strategy)
                new_client.save()
                stock_corr = client_form.cleaned_data['stock_corr']
                vol = client_form.cleaned_data['vol']
                market = sim_market.SimMarket.objects.get(id=0)
                if vol != 0:
                    new_holding = sim_clients.SimHoldingElem(owner=new_client, stock_corr=stock_corr,
                                                             stock_symbol=stock_corr.symbol, stock_name=stock_corr.name,
                                                             vol=vol, frozen_vol=0, available_vol=vol,
                                                             date_bought=market.datetime)
                    new_holding.save()
                market.num_v_clients += 1
                market.save()
                return HttpResponseRedirect(reverse('market:sim_main'))
            else:
                return render(request, 'market/invalid/invalid_form.html')

        elif 'sim_stock' in request.POST:
            if stock_form.is_valid():
                stock_symbol = stock_form.cleaned_data['symbol']
                stock_name = stock_form.cleaned_data['name']
                new_stock = sim_stocks.SimStock(symbol=stock_symbol, name=stock_name, simulating=True)
                new_stock.save()
                new_stock.initialize_order_book()
                return HttpResponseRedirect(reverse('market:sim_welcome'))
            else:
                return render(request, 'market/invalid/invalid_form.html')
    else:
        client_form = forms.VClientForm()
        stock_form = forms.VStockForm()

    context = {'v_clients': v_clients, 'client_form': client_form, 'stock_form': stock_form}
    return render(request, 'market/simulator/simulator_main.html', context)


@login_required
def simulator_client_detail(request, client_id):
    """
    模拟股市的client信息界面
    """
    # 只有超级用户才有权限进行查看
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')

    this_client = clients.BaseClient.objects.get(id=client_id)
    holding = sim_clients.SimHoldingElem.objects.filter(owner=this_client).order_by('stock_symbol')
    commission = sim_clients.SimCommissionElem.objects.filter(owner=this_client).order_by('stock_symbol')
    transaction = sim_clients.SimTransactionElem.objects.filter(owner=this_client).order_by('stock_symbol')

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
    重置模拟的股市
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    market = sim_market.SimMarket.objects.get(id=0)
    sim_clients.SimTransactionElem.objects.all().delete()
    v_clients = clients.BaseClient.objects.filter(driver=None)
    for v_client in v_clients:
        v_client.quit()
        market.num_v_clients -= 1
    market.save()
    v_stocks = sim_stocks.SimStock.objects.filter(simulating=True)
    for v_stock in v_stocks:
        v_stock.quit()
    return HttpResponseRedirect(reverse('market:sim_welcome'))


@login_required
def simulator_reset_all(request):
    """
    重置模拟股市的全部数据（包括导入的）
    """
    if not request.user.is_superuser:
        return render(request, 'market/invalid/no_permission.html')
    market = sim_market.SimMarket.objects.get(id=0)
    sim_clients.SimTransactionElem.objects.all().delete()
    v_clients = clients.BaseClient.objects.filter(driver=None)
    for v_client in v_clients:
        v_client.quit()
        market.num_v_clients -= 1
    market.save()
    v_stocks = sim_stocks.SimStock.objects.all()
    for v_stock in v_stocks:
        v_stock.quit()
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
            # interval = form.cleaned_data['interval']
            ok = import_stock_data(stock, start_date, end_date)
            if ok:
                return HttpResponseRedirect(reverse('market:sim_welcome'))
            else:
                return render(request, 'market/invalid/import_data_failed.html')
    else:
        form = forms.ImportStockDataForm()
    context = {'form': form}
    return render(request, 'market/simulator/import_data.html', context)


def import_stock_data(symbol, start_date, end_date):
    import os
    abs_path = os.path.abspath('utils.py')
    abs_path = abs_path[:-9]
    path = os.path.join(abs_path, 'market', 'data', symbol)
    tb = utils.TickTable(path)
    data = tb.select(symbol, 10180101093000000, 30191231153000000)
    num_record = len(data)
    start_datetime = utils.get_int_from_timestamp(start_date)
    end_datetime = utils.get_int_from_timestamp(end_date)
    for i in range(num_record):
        cur_datetime = data.index[i]
        if cur_datetime < start_datetime:
            continue
        if cur_datetime > end_datetime:
            break
        if str(cur_datetime)[9:11] == '92':
            # 集合竞价阶段不导入
            continue
        if str(cur_datetime)[12:14] != '00':
            # 导入每分钟数据
            continue

        time0 = time.time()
        data_slice = data.loc[cur_datetime]
        cur_timestamp = utils.get_timestamp_from_int(cur_datetime)
        new_sim_stock = sim_stocks.SimStock(symbol=symbol, simulating=False, datetime=cur_timestamp,
                                            last_price=data_slice['last'], high=data_slice.high,
                                            low=data_slice.low, limit_up=999, limit_down=0,
                                            volume=data_slice.volume, amount=data_slice.amount)
        new_sim_stock.save()
        order_book = new_sim_stock.initialize_order_book()
        # 这里的处理有点特殊，感觉循环不太好写……
        if data_slice.a1 == 0 and data_slice.b1 == 0:
            continue
        if data_slice.a1 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='a',
                                                                entry_price=data_slice.a1, total_vol=data_slice.a1_v)
            new_order_book_entry.save()
        if data_slice.a2 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='a',
                                                                entry_price=data_slice.a2, total_vol=data_slice.a2_v)
            new_order_book_entry.save()
        if data_slice.a3 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='a',
                                                                entry_price=data_slice.a3, total_vol=data_slice.a3_v)
            new_order_book_entry.save()
        if data_slice.a4 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='a',
                                                                entry_price=data_slice.a4, total_vol=data_slice.a4_v)
            new_order_book_entry.save()
        if data_slice.a5 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='a',
                                                                entry_price=data_slice.a5, total_vol=data_slice.a5_v)
            new_order_book_entry.save()

        if data_slice.b1 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='b',
                                                                entry_price=data_slice.b1, total_vol=data_slice.b1_v)
            new_order_book_entry.save()
        if data_slice.b2 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='b',
                                                                entry_price=data_slice.b2, total_vol=data_slice.b2_v)
            new_order_book_entry.save()
        if data_slice.b3 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='b',
                                                                entry_price=data_slice.b3, total_vol=data_slice.b3_v)
            new_order_book_entry.save()
        if data_slice.b4 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='b',
                                                                entry_price=data_slice.b4, total_vol=data_slice.b4_v)
            new_order_book_entry.save()
        if data_slice.b5 != 0:
            new_order_book_entry = sim_stocks.SimOrderBookEntry(order_book=order_book, entry_direction='b',
                                                                entry_price=data_slice.b5, total_vol=data_slice.b5_v)
            new_order_book_entry.save()
        time1 = time.time()
        print('time {} saved, cost {:.2f}s.'.format(cur_datetime, time1 - time0))

    return True





