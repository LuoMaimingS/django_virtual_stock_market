"""
遇到的特殊情况
1. 档口数据沉没
2. 买1/卖1交错，gap状态中有负量  e.g. 2018-1-2 09:31:00
3. 分红扩股，导致股票交易出现零头，amount核算难以界定，只能忽略  e.g. 2018-1-2 09:32:06
4. 数据本身有缺陷  e.g. 2018-1-3 10:47:00
"""


import sympy
from decimal import Decimal
from random import shuffle

from .models import sim_market, sim_stocks
from .models.utils import get_int_from_timestamp
from .baselines.baselines import logger


def calc_tick_action(cur_datetime):
    cur_int_datetime = get_int_from_timestamp(cur_datetime)
    if str(cur_int_datetime)[9:11] == '91' or str(cur_int_datetime)[9:11] == '92' or str(cur_int_datetime)[9:12] == '457' \
            or str(cur_int_datetime)[9:12] == '458' or str(cur_int_datetime)[9:12] == '459':
        return None
    actions = []

    # 先读取需要的数据信息
    cur_stick_snap = sim_stocks.SimStockSlice.objects.filter(stock_symbol='000009.XSHE', datetime=cur_datetime)
    if cur_stick_snap.exists():
        cur_stick_snap = cur_stick_snap[0]
    cur_high = cur_stick_snap.high
    cur_low = cur_stick_snap.low
    cur_volume = cur_stick_snap.volume
    cur_amount = cur_stick_snap.amount
    cur_ask5, cur_bid5 = cur_stick_snap.get_level5_data()
    cur_dic_ask5 = {}
    cur_dic_bid5 = {}
    gap_dic_ask5 = {}  # 用于填补挂单和撤单数目，使order book吻合
    gap_dic_bid5 = {}  # 用于填补挂单和撤单数目，使order book吻合
    for i in range(5):
        cur_dic_ask5[cur_ask5[i][0]] = cur_ask5[i][1]
        cur_dic_bid5[cur_bid5[i][0]] = cur_bid5[i][1]
        gap_dic_ask5[cur_ask5[i][0]] = cur_ask5[i][1]
        gap_dic_bid5[cur_bid5[i][0]] = cur_bid5[i][1]

    next_tick_snap = sim_stocks.SimStockSlice.objects.filter(id=cur_stick_snap.id + 1)
    if not next_tick_snap.exists():
        return
    next_tick_snap = next_tick_snap[0]
    next_last = next_tick_snap.last_price
    next_high = next_tick_snap.high
    next_low = next_tick_snap.low
    next_volume = next_tick_snap.volume
    next_amount = next_tick_snap.amount
    next_ask5, next_bid5 = next_tick_snap.get_level5_data()
    next_dic_ask5 = {}
    next_dic_bid5 = {}
    for i in range(5):
        next_dic_ask5[next_ask5[i][0]] = next_ask5[i][1]
        next_dic_bid5[next_bid5[i][0]] = next_bid5[i][1]

    # 再开始计算
    # 先计算交易量，首先确定可能形成交易的level
    delta_volume = next_volume - cur_volume
    delta_amount = next_amount - cur_amount
    coefficients = set()
    # 确认盘口中可能形成交易的价格，加入方程的系数列表，确认方式如下，买方对称处理
    #
    #   current           1)               2)             3)              4)
    #    7.27            7.27            7.28            7.29            7.26
    #    7.26            7.26            7.27            7.28            7.25
    #    7.25            7.25            7.26            7.27            7.24
    #   ------    ->    ------    ->    ------    ->    ------          ------
    #                     25            25, 26        25, 26, 27      24, 25, ×27
    #
    #                                                            盘口边缘level升高，非系数
    # 如果high/low变化，则必然发生high/low价格所对应的交易，加入系数列表
    #
    for ask_price in cur_dic_ask5.keys():
        if ask_price not in next_dic_ask5.keys():
            if ask_price < next_ask5[0][0]:
                coefficients.add(ask_price)
    coefficients.add(cur_ask5[4][0])  # 添加卖1价
    for bid_price in cur_dic_bid5.keys():
        if bid_price not in next_dic_bid5.keys():
            if bid_price > next_bid5[4][0]:
                coefficients.add(bid_price)
    coefficients.add(cur_bid5[0][0])  # 添加买1价
    if next_high != cur_high:
        coefficients.add(next_high)
    if next_low != cur_low:
        coefficients.add(next_low)
    if next_last not in coefficients:
        coefficients.add(next_last)

    logger.debug('Datetime: {}'.format(cur_datetime))
    logger.debug('current:', cur_ask5, cur_bid5, cur_volume)
    logger.debug('next:', next_ask5, next_bid5)
    logger.debug('delta vol:{} delta amount:{} last price:{}'.format(delta_volume, delta_amount, next_last))

    coefficients = list(coefficients)
    coefficients.sort()
    constants_coefficients = [1] * len(coefficients)
    A = sympy.Matrix([coefficients, constants_coefficients])
    B = sympy.Matrix([delta_amount, delta_volume])
    x = sympy.Matrix(sympy.symarray('x', len(coefficients), negative=False))
    # print('寻找actions，正在尝试解出Ax=B... A: {} x: {} B: {} '.format(A, x, B))
    result = sympy.solve(A * x - B)

    # 计算不出结果时，扩展系数重新计算，先扩展大价格方向
    append_direction = 1
    failed = 0
    gap_added = False
    while len(result) == 0:

        failed += 1
        if failed >= 3:
            print('*****当前tick计算失败')
            break
        # print('扩展系数，重新计算')
        # 确定加入买1/卖1价
        if cur_ask5[4][0] not in coefficients:
            coefficients.append(cur_ask5[4][0])
        if cur_bid5[0][0] not in coefficients:
            coefficients.append(cur_bid5[0][0])

        # 买1卖1有gap时，中间可能包含隐藏交易价格，添加系数
        if not gap_added:
            gap_added = True
            steps = int((cur_ask5[4][0] - cur_bid5[0][0]) * 100 - 1)
            if steps != 0:
                for i in range(steps):
                    coefficients.append(Decimal(cur_bid5[0][0] + Decimal(0.01) * (i + 1)).quantize(Decimal('0.00')))
            coefficients.sort()

        if append_direction == 1:
            coefficients.append(Decimal(coefficients[-1] + Decimal(0.01)).quantize(Decimal('0.00')))
            append_direction = -1
        else:
            coefficients.insert(0, Decimal(coefficients[0] - Decimal(0.01)).quantize(Decimal('0.00')))
            append_direction = 1

        constants_coefficients = [1] * len(coefficients)
        A = sympy.Matrix([coefficients, constants_coefficients])
        x = sympy.Matrix(sympy.symarray('x', len(coefficients), integer=True, negative=False))
        # print('寻找actions，正在尝试解出Ax=B... A: {} x: {} B: {}'.format(A, x, B))
        result = sympy.solve(A * x - B)

    if len(coefficients) <= 2:
        # 系数矩阵和增广矩阵秩都为2，可得唯一解
        # print('{} Calculated. Result: {} (prices {})'.format(str(cur_datetime), result, coefficients))
        pass
    elif len(coefficients) == 3:
        # 得到通解，自由变量数目为1
        logger.info('{} Calculated. Result: {} (prices {})'.format(str(cur_datetime), result, coefficients))
        return None
    else:
        # 自由变量数目太多，舍弃
        logger.info('{} Too Much Coefficients. Unable to calculate.'.format(str(cur_datetime)))
        return None
    logger.debug('Actions Calculated: {}'.format(result))

    # 计算出交易动作
    trades = {}
    index = 0
    for key in result:
        if int(result[key]) != 0:
            trades[coefficients[index]] = int(result[key])
        index += 1
    for price in trades.keys():
        if price in cur_dic_ask5.keys():
            actions.append(('b', price, trades[price]))
        elif price in cur_dic_bid5.keys():
            actions.append(('a', price, trades[price]))
        else:
            # 买1卖1间的gap价格
            if price in next_dic_ask5.keys():
                actions.append(('a', price, trades[price]))
            else:
                actions.append(('b', price, trades[price]))

    # 根据交易动作计算出gap的状态
    # actions like [('a', Decimal('7.26'), 900.000000000000), ('b', Decimal('7.27'), 5000.00000000000)]
    #
    #   current           1)               2)             3)
    #    7.28            7.28            7.27            7.29
    #    7.27            7.27            7.26            7.28
    #   ------    ->    ------    ->    ------    ->    ------
    #    7.26            7.26            7.25            7.27
    #    7.25            7.25            7.24            7.26
    #
    for action in actions:
        if action[1] in cur_dic_bid5.keys():
            assert action[0] == 'a'
            gap_dic_bid5[action[1]] -= action[2]
        elif action[1] in cur_dic_ask5.keys():
            assert action[0] == 'b'
            gap_dic_ask5[action[1]] -= action[2]

    # 买1/卖1交错，导致gap中有负量，为该tick瞬时的交易，复原抵消过程
    #    7.28  5000            7.28  5000            7.28  5000
    #    7.27  3000            7.27  -1000              ------
    #      ------        ->      ------       ->     7.27  3000
    #    7.26  2000            7.26  2000            7.26  2000
    #    7.25  1000            7.25  1000            7.25  1000
    #
    for price in list(gap_dic_ask5):
        if gap_dic_ask5[price] == 0:
            del gap_dic_ask5[price]
        elif gap_dic_ask5[price] < 0:
            actions.append(('a', price, -gap_dic_ask5[price]))
    for price in list(gap_dic_bid5):
        if gap_dic_bid5[price] == 0:
            del gap_dic_bid5[price]
        elif gap_dic_bid5[price] < 0:
            actions.append(('b', price, -gap_dic_bid5[price]))

    # 填补挂单和撤单数目，使order book吻合
    # 1. 产生新的卖价
    # 2. 抹除旧的卖价
    # 3. 原有卖价撤单
    # 4. 原有卖价挂单
    #        gap                 next
    # 1)    empty       ->    7.25 54000
    # 2)  7.25 54000    ->      empty
    # 3)  7.25 54000    ->    7.25 44000
    # 4)  7.25 54000    ->    7.25 64000
    #
    # 买的方向对称处理
    #
    for i in range(5):
        # 产生新的卖价，则挂新单
        for next_price in next_dic_ask5.keys():
            if next_price not in gap_dic_ask5.keys():
                # 以该新价格挂入相应数量的卖单，填补order book项
                actions.append(('a', next_price, next_dic_ask5[next_price]))
                gap_dic_ask5[next_price] = next_dic_ask5[next_price]
        # 抹除旧的卖价，则撤回旧单
        for gap_price in gap_dic_ask5.keys():
            if gap_price not in next_dic_ask5.keys():
                # 撤回该旧价格相应的卖单，消除order book项
                if gap_price <= next_ask5[0][0]:
                    # 并非退出盘口
                    actions.append(('c', gap_price, gap_dic_ask5[gap_price]))
                    gap_dic_ask5[gap_price] -= gap_dic_ask5[gap_price]
            else:
                # 盘口价格不变，只是数量变化，则挂或撤，使order book吻合
                delta_temp_vol = next_dic_ask5[gap_price] - gap_dic_ask5[gap_price]
                if delta_temp_vol < 0:
                    # 撤单
                    actions.append(('c', gap_price, -delta_temp_vol))
                elif delta_temp_vol > 0:
                    # 挂单
                    actions.append(('a', gap_price, delta_temp_vol))
                gap_dic_ask5[gap_price] += delta_temp_vol

        # 产生新的买价，则挂新单
        for next_price in next_dic_bid5.keys():
            if next_price not in gap_dic_bid5.keys():
                # 以该新价格挂入相应数量的卖单，填补order book项
                actions.append(('b', next_price, next_dic_bid5[next_price]))
                gap_dic_bid5[next_price] = next_dic_bid5[next_price]
        # 抹除旧的买价，则撤回旧单
        for gap_price in gap_dic_bid5.keys():
            if gap_price not in next_dic_bid5.keys():
                # 撤回该旧价格相应的买单，消除order book项
                if gap_price >= next_bid5[4][0]:
                    actions.append(('c', gap_price, gap_dic_bid5[gap_price]))
                    gap_dic_bid5[gap_price] -= gap_dic_bid5[gap_price]
            else:
                # 盘口价格不变，只是数量变化，则挂或撤，使order book吻合
                delta_temp_vol = next_dic_bid5[gap_price] - gap_dic_bid5[gap_price]
                if delta_temp_vol < 0:
                    # 撤单
                    actions.append(('c', gap_price, -delta_temp_vol))
                elif delta_temp_vol > 0:
                    # 挂单
                    actions.append(('b', gap_price, delta_temp_vol))
                gap_dic_bid5[gap_price] += delta_temp_vol

    # actions重整 聚合
    ask_actions = {}
    bid_actions = {}
    cancel_actions = {}
    for action in actions:
        if action[0] == 'a':
            if action[1] in ask_actions:
                ask_actions[action[1]] += action[2]
            else:
                ask_actions[action[1]] = action[2]
        elif action[0] == 'b':
            if action[1] in bid_actions:
                bid_actions[action[1]] += action[2]
            else:
                bid_actions[action[1]] = action[2]
        else:
            cancel_actions[action[1]] = action[2]
    logger.debug('Actions Before Aggregation: ', ask_actions, bid_actions, cancel_actions)
    actions = []
    last_locked = False
    action_locked = None
    for ask_price in ask_actions.keys():
        if ask_price != next_last or last_locked or ask_price in cur_dic_ask5:
            actions.append(('a', ask_price, ask_actions[ask_price]))
        else:
            action_locked = ('a', ask_price, ask_actions[ask_price])
            last_locked = True
    for bid_price in bid_actions.keys():
        if bid_price != next_last or last_locked or bid_price in cur_dic_bid5:
            actions.append(('b', bid_price, bid_actions[bid_price]))
        else:
            action_locked = ('b', bid_price, bid_actions[bid_price])
            last_locked = True
    for cancel_price in cancel_actions.keys():
        if cancel_actions[cancel_price] != 0:
            actions.append(('c', cancel_price, cancel_actions[cancel_price]))
    shuffle(actions)
    if action_locked is None:
        if delta_volume != 0:
            logger.warn('**********Trade actions Does not cover Last Price.**********')
    else:
        actions.append(action_locked)
    logger.debug('Datetime {}, Finally Returned Actions: {}\n'.format(cur_datetime, actions))
    return actions




