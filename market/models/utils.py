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
