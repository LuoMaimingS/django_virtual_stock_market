from django.shortcuts import render
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import clients, stocks, forms
from .models import config
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
    all_stocks = stocks.Stock.objects.order_by('symbol')
    context = {'stocks': all_stocks}
    return render(request, 'market/all_stocks.html', context)


def stock_detail(request, stock_id):
    """
    具体显示股票市场中某支股票的详细信息
    """
    this_stock = stocks.Stock.objects.get(id=stock_id)
    ask_info, bid_info = this_stock.get_level5_data()
    context = {'stock': this_stock, 'level5_ask': ask_info, 'level5_bid': bid_info}
    return render(request, 'market/stock.html', context)


def client_detail(request, client_id):
    """
    具体显示某个client的详细信息
    """
    this_client = clients.BaseClient.objects.get(id=client_id)
    context = {'client': this_client}
    return render(request, 'market/client.html', context)


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
                return render(request, 'market/invalid_form.html')
        else:
            return render(request, 'market/invalid_form.html')

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
                return render(request, 'market/invalid_form.html')
        else:
            return render(request, 'market/invalid_form.html')

    else:
        form = forms.CancelForm()

    commission = user_client.commissionelem_set.all()
    context = {'client': user_client,'form': form, 'commission': commission}
    return render(request, 'market/user_cancel.html', context)
