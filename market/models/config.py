# PRICE CONFIG
# Maximum price allowed: 999.99
MAX_DIGITS = 5
DECIMAL_PLACES = 2

# Default holding created (virtual stock)
DEFAULT_HOLD_SYMBOL = '009999.XSHG'
DEFAULT_HOLD_NAME = '黄浦地产'
DEFAULT_HOLD_PRICE = 6.22
DEFAULT_HOLD_VOLUME = 1000

# Client default attr
CASH = 100000

# tax
TAX_RATE = 0.002


def generate_trade_id():
    """
    采取一定规则生成一个11位的交易号
    """
    import time, random
    trade_id = str(time.time())
    trade_id = trade_id[:3] + str(random.randint(1000, 10000)) + trade_id[7:10] + trade_id[11]
    return trade_id
