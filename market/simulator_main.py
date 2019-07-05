import time
from decimal import Decimal

from .models import sim_market, sim_clients, sim_stocks, sim_trades


def simulator_main_func():
    market = sim_market.SimMarket.objects.get(id=1)
    datetime = market.datetime
    v_clients = sim_clients.BaseClient.objects.filter(driver=None)
    for client in v_clients:
        sim_bid(client, '000009.XSHE', 7.29, 100, datetime)

    a = 1
    b = 2
    result = a + b
    return result


def sim_bid(v_client, symbol, price, vol, datetime):
    """
    虚拟的client在模拟股市中下限价买单，委托给股市环境，将调用相应的处理函数
    :param v_client:虚拟的client
    :param symbol:股票标的代码
    :param price:委托的买价
    :param vol:委托买入的数量
    :param datetime:委托的时间
    """
    new_commission = sim_trades.SimCommissionMsg(stock_symbol=symbol, commit_client=v_client, commit_direction='b',
                                                 commit_price=Decimal(round(price, 2)), commit_vol=vol, commit_date=datetime)
    sim_trades.sim_commission_handler(new_commission)
    return True




