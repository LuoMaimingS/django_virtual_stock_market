import time
import random
from decimal import Decimal

from .models import sim_market, sim_clients, sim_stocks, sim_trades


def simulator_main_func():

    market = sim_market.SimMarket.objects.get(id=1)
    datetime = market.datetime
    players = []
    v_clients = sim_clients.BaseClient.objects.filter(driver=None)
    r_clients = sim_clients.BaseClient.objects.exclude(driver=None)
    for v_client in v_clients:
        players.append(v_client)
    for r_client in r_clients:
        if r_client.driver.is_superuser:
            players.append(r_client)

    run_tick = 10
    stock = sim_stocks.SimStock.objects.get(symbol='000009.XSHE')

    for i in range(run_tick):
        a1, a1_v, b1, b1_v = stock.get_level1_data()
        random.shuffle(players)
        for player in players:
            temp = random.random()
            if player.driver is None:
                if temp < 0.5:
                    sim_bid(player, '000009.XSHE', a1, a1_v, datetime)
                else:
                    sim_bid(player, '000009.XSHE', a1, 100, datetime)
            else:
                if temp < 0.5:
                    sim_bid(player, '000009.XSHE', a1, a1_v, datetime)
                    sim_ask(player, '000009.XSHE', b1, a1_v, datetime)
                else:
                    sim_bid(player, '000009.XSHE', a1, 100, datetime)
                    sim_ask(player, '000009.XSHE', b1, 100, datetime)

        market.tick += 1
        market.save(update_fields=['tick'])

    return True


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


def sim_ask(v_client, symbol, price, vol, datetime):
    """
    虚拟的client在模拟股市中下限价卖单，委托给股市环境，将调用相应的处理函数
    :param v_client:虚拟的client
    :param symbol:股票标的代码
    :param price:委托的卖价
    :param vol:委托卖出的数量
    :param datetime:委托的时间
    """
    new_commission = sim_trades.SimCommissionMsg(stock_symbol=symbol, commit_client=v_client, commit_direction='a',
                                                 commit_price=Decimal(round(price, 2)), commit_vol=vol, commit_date=datetime)
    sim_trades.sim_commission_handler(new_commission)
    return True


def calc_tick_action():
    market = sim_market.SimMarket.objects.get(id=1)




