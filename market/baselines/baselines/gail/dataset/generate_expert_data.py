"""
This file implements the generation of the expert data used in gail
"""

import os
import numpy as np

from market.baselines.baselines import logger
from market.models.sim_stocks import SimStockSlice
from market.models.sim_market import SimMarket
from market.simulator_main import calc_tick_action


def generate_expert_data(stock, traj_length, track_length, traj_num=-1):
    logger.set_level(20)
    file_name = stock + '_traj_length' + str(traj_length) + '.npz'
    save_path = os.path.join(os.path.split(os.path.abspath(os.curdir))[0], 'VirtualStockMarket', 'market',
                             'baselines', 'baselines', 'gail', 'data', file_name)
    market = SimMarket.objects.get(id=1)
    datetime = market.datetime

    trajectory_obs = []
    trajectory_acs = []
    trajectory_trk = []
    trajectory_dts = []
    cur_batch_obs = []
    cur_batch_acs = []
    cur_batch_trk = []
    cur_batch_dts = []

    while True:
        cur_slice = SimStockSlice.objects.get(stock_symbol=stock, datetime=datetime)
        next_slice = SimStockSlice.objects.filter(id=cur_slice.id + 1)

        if (datetime.hour == 9 and datetime.minute <= 30) or (datetime.hour == 14 and datetime.minute >= 57):
            # 开盘和收盘竞价略过
            if next_slice.exists():
                datetime = next_slice[0].datetime
            else:
                break
            cur_batch_obs = []
            cur_batch_acs = []
            cur_batch_trk = []
            continue

        if next_slice.exists():
            assert len(next_slice) == 1
            next_slice = next_slice[0]
            result = calc_tick_action(datetime)

            if result is not None:
                # 获取盘口数据，level 5
                level5_data = cur_slice.get_level5_data(to_list=True)
                # 计算上一tick至当前tick的交易额、交易量
                prev_slice = SimStockSlice.objects.get(id=cur_slice.id - 1)
                tick_volume = cur_slice.volume - prev_slice.volume
                tick_amount = cur_slice.amount - prev_slice.amount
                last_price = cur_slice.last_price
                high = cur_slice.high
                low = cur_slice.low

                # 将order book、最新、最高、最低价、当前tick的交易额、量加入observation
                temp_obs = []
                for piece_info in level5_data:
                    temp_obs.append(piece_info)
                temp_obs.append(last_price)
                temp_obs.append(high)
                temp_obs.append(low)
                temp_obs.append(tick_volume)
                temp_obs.append(tick_amount)

                # 将前n个tick的价格走势加入observation
                cur_batch_trk.append(temp_obs)

                # 获得足够的track tick后，开始记入专家数据
                if len(cur_batch_trk) >= track_length + 1:
                    if len(cur_batch_trk) > track_length + traj_length:
                        del cur_batch_trk[0]
                    cur_batch_obs.append(temp_obs.copy())

                    a5_price = cur_slice.a5
                    b5_price = cur_slice.b5
                    level5_ask, level5_bid = cur_slice.get_level5_volume()
                    level5_vol = level5_ask + level5_bid
                    # 忽略level浮出、沉没造成的巨量action
                    for i in range(len(result) - 1, -1, -1):
                        if (result[i][0] == 'a' and result[i][1] > a5_price) or \
                                (result[i][0] == 'b' and result[i][1] < b5_price):
                            del result[i]
                    actions = trans_actions_form_for_training(result, a5_price, b5_price, level5_vol)
                    cur_batch_acs.append(actions)
                    cur_batch_dts.append(datetime)

                # 达到预定轨迹长度，保存轨迹记录，重新计数, n: traj_length, m: track_length
                if len(cur_batch_obs) == traj_length:
                    trajectory_obs.append(cur_batch_obs)  # shape: (n, 25)
                    trajectory_acs.append(cur_batch_acs)  # shape: (n, )
                    trajectory_dts.append(cur_batch_dts)  # shape: (n, )
                    trajectory_trk.append(cur_batch_trk[0:track_length])  # shape: (n + m - 1, 25)
                    logger.info('trajectory add, number: {1}, datetime: {0},'.format(datetime, len(trajectory_obs)))
                    cur_batch_obs = []
                    cur_batch_acs = []
                    cur_batch_dts = []

                    # 获取了足够的轨迹数目，结束循环
                    if len(trajectory_obs) == traj_num and traj_num != -1:
                        break

            datetime = next_slice.datetime

        else:
            # 遍历完所有记录，结束
            break

    # 存储
    trajectory_obs = np.array(trajectory_obs)
    trajectory_acs = np.array(trajectory_acs)
    trajectory_trk = np.array(trajectory_trk)
    trajectory_dts = np.array(trajectory_dts)
    trajectory_num = trajectory_obs.shape[0]
    ep_rets = np.ones(trajectory_num)
    ep_rets = ep_rets * traj_length
    logger.log('Ready to save trajectories.')
    logger.log("Total trajectories: %d" % trajectory_num)
    logger.log("Observations shape: {}".format(trajectory_obs.shape))
    logger.log("Actions shape: {}".format(trajectory_acs.shape))
    logger.log("Datetime shape: {}".format(trajectory_dts.shape))
    logger.log("Tracks shape: {}".format(trajectory_trk.shape))
    logger.log("EP_RETURNS shape: {}".format(ep_rets.shape))
    logger.log("Total transitions: %d" % (trajectory_num * traj_length))

    np.savez(save_path, obs=trajectory_obs, acs=trajectory_acs, trk=trajectory_trk, dts=trajectory_dts,
             ep_rets=ep_rets)

    return True


def trans_actions_form_for_training(actions, a5, b5, total_level5_volume):
    """
    将计算出来的actions转化成神经网络目标输出格式
    :param actions: e.g. [('a', 7.21, 1000), ('a', 7.22, 3000), ('b', 7.21, 2000), ('c', 7.21, 1000)]
    :param a5: 卖5价
    :param b5: 买5价
    :param total_level5_volume: level5的挂单总量
    :return: new_actions: e.g. [(0.2, 0.1, 0.03), (0.2, 0.2, 0.09), (0.6, 0.1, 0.06), (0.9, 0.1, 0.03)]
    """
    average_vol = total_level5_volume / 10
    new_actions = []
    for origin_action in actions:
        direction = 0.0
        if origin_action[0] == 'a':
            direction = 0.2
        elif origin_action[0] == 'b':
            direction = 0.6
        elif origin_action[0] == 'c':
            direction = 0.9
        else:
            raise ValueError
        price = float((origin_action[1] - b5) / (a5 - b5))
        vol = origin_action[2] / average_vol
        new_actions.append((direction, price, vol))

    # *********** for test
    new_actions = new_actions[-1]

    return new_actions



