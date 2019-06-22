from django.shortcuts import render
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.views import generic
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import clients, stocks, forms
from .models import config


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
            default_stock, found = stocks.Stock.objects.get_or_create(symbol=config.DEFAULT_HOLD_SYMBOL, name=config.DEFAULT_HOLD_NAME)
            if not found:
                default_stock.initialize_order_book()
            new_client.holdingelem_set.create(owner=new_client, stock_corr=default_stock, stock_symbol=default_stock.symbol,
                                              stock_name=default_stock.name, vol=config.DEFAULT_HOLD_VOLUME,
                                              available_vol=config.DEFAULT_HOLD_VOLUME)

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
    focusing = clients.FocusElem.objects.filter(owner=user_client).order_by('stock_symbol')
    context = {'client': user_client, 'holding': holding, 'commission': commission, 'focusing': focusing}
    return render(request, 'market/my_account.html', context)


@login_required
def bid_view(request):
    user_client, _ = clients.BaseClient.objects.get_or_create(driver=request.user, name=request.user.username)
    form = forms.BidForm()
    if request.method == 'POST':
        form = forms.BidForm(request.POST)

        if form.is_valid():
            bid_stock = form.cleaned_data['stock_corr']
            bid_price = form.cleaned_data['price_committed']
            bid_volume = form.cleaned_data['vol_committed']
            # bid_type = form.cleaned_data['bid_type']
            clients.CommissionElem.objects.create(owner=user_client, stock_corr=bid_stock,
                                                  stock_symbol=bid_stock.symbol, stock_name=bid_stock.name,
                                                  operation='b', price_committed=bid_price, vol_committed=bid_volume)
            return HttpResponseRedirect(reverse('market:my_account'))
    else:
        form = forms.BidForm()

    context = {'client': user_client,'form': form}
    return render(request, 'market/user_bid.html', context)
