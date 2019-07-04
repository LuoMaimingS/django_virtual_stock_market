import numpy as np
import pandas as pd
import h5py
import six
import string
import random


def generate_trade_id():
    """
    采取一定规则生成一个11位的交易号
    """
    import time, random
    trade_id = str(time.time())
    trade_id = trade_id[:3] + str(random.randint(1000, 10000)) + trade_id[7:10] + trade_id[11]
    return trade_id


def generate_random_client_name(name_length=10, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(name_length))


def get_dts_range(dts, st, ed):
    left = np.searchsorted(dts, st, side="left")
    right = np.searchsorted(dts, ed, side="right")
    return left, right


class TickTable:
    def __init__(self, path):
        self.path = path

    @staticmethod
    def get_keys():
        return ['high', 'low', 'last', 'volume', 'amount', 'a1', 'a2', 'a3', 'a4', 'a5', 'b1', 'b2', 'b3', 'b4', 'b5',
                'a1_v', 'a2_v', 'a3_v', 'a4_v', 'a5_v', 'b1_v', 'b2_v', 'b3_v', 'b4_v', 'b5_v']

    def select(self, codes, start_dt, end_dt, keys=None, lookback=0, lookahead=0, verbose=False):
        result = []
        if keys is None:
            keys = self.get_keys()
        is_req_code_list = True
        if isinstance(codes, six.string_types):
            codes = [codes]
            is_req_code_list = False
        for code in codes:
            code_path = self.path
            try:
                h5file = h5py.File(code_path, "r")
            except OSError:
                code_path = code_path + '.h5'
                h5file = h5py.File(code_path, "r")
            grp = h5file.get(code)
            if grp is None:
                continue
            else:
                # get series range
                dts_array = grp["datetime"]
                start_dt_code = start_dt or dts_array[0]
                end_dt_code = end_dt or dts_array[-1]
                left, right = get_dts_range(dts_array, start_dt_code, end_dt_code)
                left = max(0, left - lookback)
                right = min(len(dts_array), right + lookahead)
                dts = dts_array[left: right]
                # read data
                data = {}
                for key in keys:
                    data[key] = grp[key][left: right]
                # to pandas
                if is_req_code_list:
                    index = pd.MultiIndex.from_product([[code], dts], names=["code", "datetime"])
                    df = pd.DataFrame(data=data, index=index)
                else:
                    df = pd.DataFrame(data=data, index=dts)
                    df.index.name = "datetime"
                result.append(df)
        result = pd.concat(result, axis=0)
        return result


def get_timestamp_from_int(cur_time):
    cur_time = str(cur_time)
    cur_timestamp = pd.datetime(year=int(cur_time[0:4]), month=int(cur_time[4:6]), day=int(cur_time[6:8]),
                                hour=int(cur_time[8:10]), minute=int(cur_time[10:12]),
                                second=int(cur_time[12:14]), microsecond=int(cur_time[14:17]))
    return cur_timestamp


def get_int_from_timestamp(cur_timestamp):
    cur_time = str(cur_timestamp.year).zfill(4) + str(cur_timestamp.month).zfill(2) + \
               str(cur_timestamp.day).zfill(2) + str(cur_timestamp.hour).zfill(2) + \
               str(cur_timestamp.minute).zfill(2) + str(cur_timestamp.second).zfill(2) + \
               str(cur_timestamp.microsecond).zfill(3)
    cur_time = int(cur_time)
    return cur_time


def get_next_timestamp(cur_timestamp, interval):
    assert interval % 3 == 0 and interval < 60






