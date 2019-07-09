from .models import sim_market, sim_stocks


def calc_tick_action():
    stock = sim_stocks.SimStock.objects.get(symbol='000009.XSHE')
    market = sim_market.SimMarket.objects.get(id=1)
    cur_datetime = market.datetime

    cur_stick_snap = sim_stocks.SimStockSlice.objects.filter(stock=stock, datetime=cur_datetime)




