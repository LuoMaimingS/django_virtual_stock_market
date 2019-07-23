import time
import random
from decimal import Decimal
import datetime as dt

from .models import clients
from .models import sim_market, sim_clients, sim_stocks
from .models.sim_trades import SimCommissionMsg, sim_commission_handler
from .calculations import calc_tick_action
from .baselines.baselines import logger


def simulator_main_func(user):
    stock = '000009.XSHE'

    calc_actions_without_check(stock)

    # calc_and_check_actions(user, stock)

    # time_point = dt.datetime.strptime('2018-1-2 14:59:06', '%Y-%m-%d %H:%M:%S')
    # super_client, _ = clients.BaseClient.objects.get_or_create(driver=user)
    # calc_and_check_actions_of_one_tick(super_client, stock, time_point, anchored=False)

    return True


def calc_actions_without_check(stock):
    print('Start Calculating Actions(Without Checking)......')
    market, _ = sim_market.SimMarket.objects.get_or_create(id=2)
    market.anchored_datetime = dt.datetime.strptime('2018-1-2 09:30:03', '%Y-%m-%d %H:%M:%S')
    market.datetime = market.anchored_datetime
    market.tick = 0
    market.save()
    calc_length = 1000000
    ticks = 0
    total_count = 0
    ask_count = 0
    bid_count = 0
    cancel_count = 0
    zero2twenty_percent_count = 0
    twenty2forty_percent_count = 0
    forty2sixty_percent_count = 0
    sixty2eighty_percent_count = 0
    eighty2hundred_percent_count = 0
    large_volume_count = 0

    for i in range(calc_length):
        datetime = market.datetime
        if datetime.hour == 14 and datetime.minute >= 57:
            continue
        cur_slice = sim_stocks.SimStockSlice.objects.get(stock_symbol=stock, datetime=datetime)
        next_slice = sim_stocks.SimStockSlice.objects.filter(id=cur_slice.id + 1)

        if next_slice.exists():
            ticks += 1
            assert len(next_slice) == 1
            next_tick = next_slice[0]
            result = calc_tick_action(datetime)

            if result is not None:
                ask_vol, bid_vol = cur_slice.get_level5_volume()
                average_vol = (ask_vol + bid_vol) / 10
                a5_price = cur_slice.a5
                b5_price = cur_slice.b5
                for i in range(len(result) - 1, -1, -1):
                    if (result[i][0] == 'a' and result[i][1] > a5_price) or \
                            (result[i][0] == 'b' and result[i][1] < b5_price):
                        del result[i]
                        continue
                    else:
                        total_count += 1
                        if result[i][0] == 'a':
                            ask_count += 1
                        elif result[i][0] == 'b':
                            bid_count += 1
                        elif result[i][0] == 'c':
                            cancel_count += 1
                        position = float(result[i][2]) / average_vol
                        if position > 1:
                            large_volume_count += 1
                        elif 0.8 < position <= 1:
                            eighty2hundred_percent_count += 1
                        elif 0.6 < position <= 0.8:
                            sixty2eighty_percent_count += 1
                        elif 0.4 < position <= 0.6:
                            forty2sixty_percent_count += 1
                        elif 0.2 < position <= 0.4:
                            twenty2forty_percent_count += 1
                        elif 0 < position <= 0.2:
                            zero2twenty_percent_count += 1
                        else:
                            raise ValueError

            print('Datetime {}, Actions For Learning: {}'.format(market.datetime, result))
            market.datetime = next_tick.datetime
        else:
            break

    print('Actions Calculation Finished.\nAmong {} ticks,\nAsk Takes: {:.2%},\nBid Takes: {:.2%},\nCancel Takes: '
          '{:.2%}'.format(ticks, ask_count / total_count, bid_count / total_count, cancel_count / total_count))
    print('Ratio Of Calculated Volume / Average Level5 Data Volume:')
    print(' 0% - 20%: {:.2%}\n20% - 40%: {:.2%}\n40% - 60%: {:.2%}\n60% - 80%: {:.2%}\n'
          '80% - 100%: {:.2%}\nOver 100%: {:.2%}'.format(zero2twenty_percent_count / total_count,
                                                         twenty2forty_percent_count / total_count,
                                                         forty2sixty_percent_count / total_count,
                                                         sixty2eighty_percent_count / total_count,
                                                         eighty2hundred_percent_count / total_count,
                                                         large_volume_count / total_count))
    return True


def calc_and_check_actions(user, stock):
    print('Start Calculating And Checking Actions......')
    super_client, _ = clients.BaseClient.objects.get_or_create(driver=user)
    simulator_resetter(super_client)
    market = sim_market.SimMarket.objects.get(id=1)
    market.anchored_datetime = dt.datetime.strptime('2018-1-2 09:30:03', '%Y-%m-%d %H:%M:%S')
    market.datetime = market.anchored_datetime
    market.tick = 0
    market.save()
    anchor_one_stock(stock, market.datetime, super_client)
    cur_slice = sim_stocks.SimStockSlice.objects.get(stock_symbol=stock, datetime=market.datetime)
    if check_act_consistency(stock, cur_slice):
        print('Anchored Successfully, Status Synchronous.')
    else:
        print('Anchored Failed.')
    ticks = 4000
    valid_count = 0
    total_count = 0
    consistent_count = 0
    failed_tick = []

    for i in range(ticks):
        datetime = market.datetime
        next_tick, calculated, consistent = calc_and_check_actions_of_one_tick(super_client, stock, datetime)
        if next_tick is not None:
            total_count += 1
            market.datetime = next_tick.datetime
            market.tick += 1
            market.save()
            valid_count += calculated
            consistent_count += consistent
            if not calculated or not consistent:
                if not calculated:
                    print('Tick: {} Can not be calculated. Skip. Anchor to next slice.'.format(str(datetime)))
                else:
                    print('Tick: {} Consistency failed.'.format(str(datetime)))
                    failed_tick.append(str(datetime))
                simulator_resetter(super_client)
                anchor_one_stock(stock, next_tick.datetime, super_client)
                if check_act_consistency(stock, next_tick):
                    print('Anchored Successfully, Status Synchronous.')
                else:
                    print('Anchored Failed.')
        else:
            break
        print(failed_tick)
        print('Actions Checking, valid(consistent) ticks: {}({})/{}'.format(valid_count, consistent_count,
                                                                                  total_count))
    print('Actions Check Finished, valid(consistent) ticks: {}({})/{}'.format(valid_count, consistent_count, total_count))

    return True


def calc_and_check_actions_of_one_tick(super_client, stock, datetime, anchored=True):
    """

    :param super_client: 超级用户
    :param stock: 股票代码
    :param datetime: 时间日期
    :param anchored: 是否已经设置好环境
    :return:下一tick是否存在，若存在是否可计算，若可计算是否吻合
    """

    if datetime.hour == 14 and datetime.minute >= 57:
        return None, False, False
    cur_slice = sim_stocks.SimStockSlice.objects.get(stock_symbol=stock, datetime=datetime)
    next_slice = sim_stocks.SimStockSlice.objects.filter(id=cur_slice.id + 1)
    next_tick = None
    calculated = False
    consistent = False

    if not anchored:
        simulator_resetter(super_client)
        anchor_one_stock(stock, datetime, super_client)
        if check_act_consistency(stock, cur_slice):
            logger.info('Anchored Successfully, Status Synchronous.')
        else:
            logger.info('Anchored Failed.')

    if next_slice.exists():
        assert len(next_slice) == 1
        next_tick = next_slice[0]
        result = calc_tick_action(datetime)
        if result is not None:
            calculated = True
            act_according_to_calculated_actions(super_client, result)
            ok = check_act_consistency(stock, next_slice[0])
            if ok:
                consistent = True
            else:
                print('Tick: {} Consistency failed.'.format(str(datetime)))
        else:
           logger.info('Tick Actions can not be calculated.')

    return next_tick, calculated, consistent


def act_according_to_calculated_actions(v_client, actions):
    market = sim_market.SimMarket.objects.get(id=1)
    stock_symbol = '000009.XSHE'

    sim_erase_data_out_of_level(v_client, stock_symbol, market.datetime)
    for action in actions:
        logger.debug('Processing Action... {}'.format(action))
        if action[0] == 'a':
            inventory = sim_clients.SimHoldingElem.objects.filter(owner=v_client.id, stock_symbol=stock_symbol)
            if not inventory.exists():
                inventory = sim_clients.SimHoldingElem.objects.create(owner=v_client.id, stock_symbol=stock_symbol,
                                                                      date_bought=market.datetime)
            else:
                inventory = inventory[0]
            inventory.vol += action[2]
            inventory.available_vol += action[2]
            inventory.save()
            sim_ask(v_client, stock_symbol, action[1], action[2], market.datetime)

        elif action[0] == 'b':
            v_client.cash += float(action[1]) * action[2]
            v_client.flexible_cash += float(action[1]) * action[2]
            v_client.save()
            sim_bid(v_client, stock_symbol, action[1], action[2], market.datetime)

        elif action[0] == 'c':
            sim_cancel(v_client, '000009.XSHE', action[1], action[2], market.datetime)
        else:
            raise ValueError('Invalid Actions in function: act_according_to_calculated_actions()!')


def check_act_consistency(stock_symbol, target_slice):
    assert isinstance(target_slice, sim_stocks.SimStockSlice)
    print('Checking Act Result\'s Consistency With Slice {}...'.format(str(target_slice.datetime)), end='    ')
    stock = sim_stocks.SimStock.objects.get(symbol=stock_symbol)
    try:
        assert stock.volume == target_slice.volume
        assert stock.amount == target_slice.amount
        assert stock.last_price == target_slice.last_price
        assert stock.high == target_slice.high
        assert stock.low == target_slice.low
        ask5, bid5 = stock.get_order_book_data(level=5)
        assert ask5[0][0] == target_slice.a5
        assert ask5[0][1] == target_slice.a5_v
        assert ask5[1][0] == target_slice.a4
        assert ask5[1][1] == target_slice.a4_v
        assert ask5[2][0] == target_slice.a3
        assert ask5[2][1] == target_slice.a3_v
        assert ask5[3][0] == target_slice.a2
        assert ask5[3][1] == target_slice.a2_v
        assert ask5[4][0] == target_slice.a1
        assert ask5[4][1] == target_slice.a1_v
        assert bid5[0][0] == target_slice.b1
        assert bid5[0][1] == target_slice.b1_v
        assert bid5[1][0] == target_slice.b2
        assert bid5[1][1] == target_slice.b2_v
        assert bid5[2][0] == target_slice.b3
        assert bid5[2][1] == target_slice.b3_v
        assert bid5[3][0] == target_slice.b4
        assert bid5[3][1] == target_slice.b4_v
        assert bid5[4][0] == target_slice.b5
        assert bid5[4][1] == target_slice.b5_v
    except AssertionError:
        print('Not Satisfied.')
        return False

    print('Consistency Satisfied.')
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
    new_commission = SimCommissionMsg(stock_symbol=symbol, commit_client=v_client.id, commit_direction='b',
                                      commit_price=price, commit_vol=vol, commit_date=datetime)
    sim_commission_handler(new_commission)
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
    new_commission = SimCommissionMsg(stock_symbol=symbol, commit_client=v_client.id, commit_direction='a',
                                      commit_price=price, commit_vol=vol, commit_date=datetime)
    sim_commission_handler(new_commission)
    return True


def sim_cancel(v_client, symbol, price, vol, datetime):
    """
    虚拟的client（必须是超级用户）在模拟股市中撤单，委托给股市环境，将调用相应的处理函数
    :param v_client:虚拟的client
    :param symbol:股票标的代码
    :param price:撤去的价格
    :param vol:撤去的数量
    :param datetime:委托的时间
    """
    origin_commissions = sim_clients.SimCommissionElem.objects.filter(owner=v_client.id, stock_symbol=symbol,
                                                                      price_committed=price)
    remaining_vol = vol
    for commission in origin_commissions:
        if remaining_vol == 0:
            break
        rest_vol = commission.vol_committed - commission.vol_traded
        if rest_vol <= remaining_vol:
            new_commission = SimCommissionMsg(stock_symbol=symbol, commit_client=v_client.id, commit_direction='c',
                                              commit_price=price, commit_vol=rest_vol,
                                              commission_to_cancel=commission.unique_id, commit_date=datetime)
            sim_commission_handler(new_commission)
            remaining_vol -= rest_vol
        else:
            new_commission = SimCommissionMsg(stock_symbol=symbol, commit_client=v_client.id, commit_direction='c',
                                              commit_price=price, commit_vol=remaining_vol,
                                              commission_to_cancel=commission.unique_id, commit_date=datetime)
            sim_commission_handler(new_commission)
            remaining_vol = 0

    return True


def sim_erase_data_out_of_level(v_client, symbol, datetime):
    stock = sim_stocks.SimStock.objects.get(symbol=symbol)
    level5_ask, level5_bid = stock.get_order_book_data(level=5)
    level5_prices = []
    for level_data in level5_ask:
        level5_prices.append(level_data[0])
    for level_data in level5_bid:
        level5_prices.append(level_data[0])
    all_ask, all_bid = stock.get_order_book_data(level=-1)
    for level_data in all_ask:
        if level_data[0] not in level5_prices:
            sim_cancel(v_client, symbol, level_data[0], level_data[1], datetime)
    for level_data in all_bid:
        if level_data[0] not in level5_prices:
            sim_cancel(v_client, symbol, level_data[0], level_data[1], datetime)
    return True


def anchor_one_stock(stock, ach, client):
    """
    将stock锚定到anchor位置的状态，并初始化client的信息
    """
    if isinstance(stock, str):
        stock_object = sim_stocks.SimStock.objects.get(symbol=stock)
    else:
        stock_object = stock
    if not isinstance(ach, sim_stocks.SimStockSlice):
        anchor = sim_stocks.SimStockSlice.objects.get(datetime=ach)
    else:
        anchor = ach
    assert isinstance(client, clients.BaseClient)
    assert isinstance(stock_object, sim_stocks.SimStock)
    assert isinstance(anchor, sim_stocks.SimStockSlice)

    print('Simulator Anchoring... datetime: {}'.format(anchor.datetime))

    stock_object.last_price = anchor.last_price
    stock_object.high = anchor.high
    stock_object.low = anchor.low
    stock_object.limit_up = anchor.open * Decimal(1.1)
    stock_object.limit_down = anchor.open * Decimal(0.9)
    stock_object.amount = anchor.amount
    stock_object.volume = anchor.volume
    stock_object.save()

    if anchor.a1 == 0 and anchor.b1 == 0:
        # anchor位置可能是集合竞价时段或其他特殊情况，没有盘口，判断为无法交易
        return True

    stock_symbol = stock_object.symbol
    if anchor.a5 != 0:
        superuser_build_position(client, stock_symbol, anchor.a5, anchor.a5_v, anchor.datetime)
    if anchor.a4 != 0:
        superuser_build_position(client, stock_symbol, anchor.a4, anchor.a4_v, anchor.datetime)
    if anchor.a3 != 0:
        superuser_build_position(client, stock_symbol, anchor.a3, anchor.a3_v, anchor.datetime)
    if anchor.a2 != 0:
        superuser_build_position(client, stock_symbol, anchor.a2, anchor.a2_v, anchor.datetime)
    if anchor.a1 != 0:
        superuser_build_position(client, stock_symbol, anchor.a1, anchor.a1_v, anchor.datetime)

    if anchor.b1 != 0:
        super_user_enter_market(client, stock_symbol, anchor.b1, anchor.b1_v, anchor.datetime)
    if anchor.b2 != 0:
        super_user_enter_market(client, stock_symbol, anchor.b2, anchor.b2_v, anchor.datetime)
    if anchor.b3 != 0:
        super_user_enter_market(client, stock_symbol, anchor.b3, anchor.b3_v, anchor.datetime)
    if anchor.b4 != 0:
        super_user_enter_market(client, stock_symbol, anchor.b4, anchor.b4_v, anchor.datetime)
    if anchor.b5 != 0:
        super_user_enter_market(client, stock_symbol, anchor.b5, anchor.b5_v, anchor.datetime)

    return True


def superuser_build_position(user, stock_symbol, price, vol, date):
    assert isinstance(user, clients.BaseClient)
    inventory, created = sim_clients.SimHoldingElem.objects.get_or_create(owner=user.id,
                                                                          stock_symbol=stock_symbol, date_bought=date)
    inventory.vol += vol
    inventory.available_vol += vol
    inventory.save()
    new_commission = SimCommissionMsg.objects.create(stock_symbol=stock_symbol, commit_client=user.id,
                                                     commit_direction='a',
                                                     commit_price=price, commit_vol=vol, commit_date=date)
    ok = sim_commission_handler(new_commission)
    return ok


def super_user_enter_market(user, stock_symbol, price, vol, date):
    assert isinstance(user, clients.BaseClient)
    user.cash += float(price * vol)
    user.flexible_cash += float(price * vol)
    user.save()
    new_commission = SimCommissionMsg.objects.create(stock_symbol=stock_symbol, commit_client=user.id,
                                                     commit_direction='b',
                                                     commit_price=price, commit_vol=vol, commit_date=date)
    ok = sim_commission_handler(new_commission)
    return ok


def simulator_resetter(superuser_client):
    assert isinstance(superuser_client, clients.BaseClient)
    clients.BaseClient.objects.filter(driver=None).delete()
    sim_clients.SimTransactionElem.objects.all().delete()
    sim_clients.SimHoldingElem.objects.all().delete()
    sim_clients.SimCommissionElem.objects.all().delete()
    v_stocks = sim_stocks.SimStock.objects.all()
    for v_stock in v_stocks:
        v_stock.reset()
    superuser_client.cash = 100000000
    superuser_client.flexible_cash = 100000000
    superuser_client.frozen_cash = 0
    superuser_client.save()
    return True




