# _*_ coding:UTF-8 _*_

"""
该文件定义了模拟环境中stock相关的模型，包括自身信息，order book，交易历史等，
并非虚拟股市原本的模型，做了一些适应性的调整，取消了全部外键。
"""

from django.db import models
from django.urls import reverse
import uuid
import time

from .config import *


class SimStock(models.Model):
    """
    Model representing A simulator stock class
    """
    symbol = models.CharField(max_length=12)
    name = models.CharField(max_length=20)

    # Maximum price allowed: 999.99
    last_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最新价", null=True)
    low = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最低价", null=True)
    high = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最高价", null=True)
    limit_up = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="涨停价", null=True)
    limit_down = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="跌停价", null=True)

    volume = models.IntegerField(verbose_name="交易量", default=0)
    amount = models.FloatField(verbose_name="交易额", default=0)

    class Meta:
        ordering = ['symbol']

    def __str__(self):
        """
        String for representing the stock
        """
        return self.symbol + '(' + self.name + ')'

    def get_absolute_url(self):
        """
        Returns the url to access a particular instance of the model.
        """
        return reverse('market:sim_stock', args=[str(self.id)])

    def get_daily_info_url(self):
        return reverse('market:sim_stock_daily', args=[str(self.id)])

    def get_tick_info_url(self):
        return reverse('market:sim_stock_tick', args=[str(self.id)])

    def get_prev_tick_info_url(self):
        return reverse('market:sim_stock_prev_tick', args=[str(self.id)])

    def get_next_tick_info_url(self):
        return reverse('market:sim_stock_next_tick', args=[str(self.id)])

    def trading_behaviour(self, direction, price, vol, datetime, tick):
        """
        发生了一次交易，进行一次更新
        """
        self.last_price = price
        if price < self.low:
            self.low = price
        if price > self.high:
            self.high = price
        self.volume += vol
        self.amount += float(price * vol)
        self.save()

        # 记录交易历史
        # SimTradeHistory.objects.create(stock_symbol=self.symbol, direction=direction, price=price, vol=vol, datetime=datetime, tick=tick)

    def is_order_book_empty(self, direction):
        """
        判断自己的买或卖的order book是否为空
        """
        if SimOrderBookEntry.objects.filter(stock_symbol=self.symbol, entry_direction=direction).exists():
            return False
        else:
            return True

    def get_best_element(self, direction):
        entries = SimOrderBookEntry.objects.filter(stock_symbol=self.symbol, entry_direction=direction)
        if not entries.exists():
            return None
        else:
            if direction == 'a':
                # 得到最早的卖一条目
                best_entry = entries.order_by('entry_price')[0]
                best_element = SimOrderBookElem.objects.filter(entry_belonged=best_entry.id)[0]
                return best_element
            elif direction == 'b':
                # 得到最早的买一条目
                best_entry = entries.order_by('-entry_price')[0]
                best_element = SimOrderBookElem.objects.filter(entry_belonged=best_entry.id)[0]
                return best_element
            else:
                raise NotImplementedError

    def get_order_book_data(self, level=5, to_list=False):
        """
        获得指定level的盘口数据，level为-1时获得全部order book数据，默认获取五档数据
        [(a5, a5_v ... a1, a1_v)], [(b1, b1_v ... b5, b5_v)]
        """
        ask_info = []
        bid_info = []
        order_book_entries = SimOrderBookEntry.objects.filter(stock_symbol=self.symbol).order_by('-entry_price')
        if order_book_entries.exists():
            for entry in order_book_entries:
                if entry.entry_direction == 'a':
                    ask_info.append((entry.entry_price, entry.total_vol))
                elif entry.entry_direction == 'b':
                    bid_info.append((entry.entry_price, entry.total_vol))
                else:
                    raise ValueError('Invalid direction in order book entries!')
        while len(ask_info) < level:
            ask_info.insert(0, (None, None))
        while len(bid_info) < level:
            bid_info.append((None, None))

        if not to_list:
            if level == -1:
                return ask_info, bid_info
            else:
                return ask_info[-level:], bid_info[:level]
        else:
            result_list = []
            ask, bid = ask_info[-level:], bid_info[:level]
            for info in ask:
                if info[0]is not None:
                    result_list.append(info[0])
                    result_list.append(info[1])
                else:
                    result_list.append(0)
                    result_list.append(0)

            for info in bid:
                if info[0]is not None:
                    result_list.append(info[0])
                    result_list.append(info[1])
                else:
                    result_list.append(0)
                    result_list.append(0)
            return result_list

    def get_level5_volume(self):
        level5_data = self.get_order_book_data(level=5, to_list=True)
        volume = 0
        for i in range(len(level5_data)):
            if i % 2 == 0:
                continue
            volume += level5_data[i]
        return volume

    def get_data_imported_datetime_range(self):
        """
        在模拟时得到导入的数据的起止日期
        """
        slices = SimStockSlice.objects.filter(stock_symbol=self.symbol).order_by('datetime')
        num_slices = slices.count()
        return str(slices[0].datetime) + '  --  ' + str(slices[num_slices - 1].datetime)

    def get_slices(self):
        """
        在模拟时得到导入的数据
        """
        slices = SimStockSlice.objects.filter(stock_symbol=self.symbol).order_by('datetime')
        return slices

    def reset(self):
        entries = SimOrderBookEntry.objects.filter(stock_symbol=self.symbol)
        for entry in entries:
            SimOrderBookElem.objects.filter(entry_belonged=entry.id).delete()
        entries.delete()
        SimTradeHistory.objects.filter(stock_symbol=self.symbol).delete()
        self.amount = 0
        self.volume = 0
        self.last_price = None
        self.high = None
        self.low = None
        self.limit_up = None
        self.limit_down = None
        self.save()
        return True

    def quit(self):
        entries = SimOrderBookEntry.objects.filter(stock_symbol=self.symbol)
        for entry in entries:
            SimOrderBookElem.objects.filter(entry_belonged=entry.id).delete()
        entries.delete()
        SimTradeHistory.objects.filter(stock_symbol=self.symbol).delete()
        SimStockSlice.objects.filter(stock_symbol=self.symbol).delete()
        SimStockDailyInfo.objects.filter(stock_symbol=self.symbol).delete()
        self.delete()
        return True


class SimStockSlice(models.Model):
    """
    股市模拟过程中的股票一个切片信息
    """
    stock_symbol = models.CharField(max_length=12)
    datetime = models.DateTimeField()

    last_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="当前价", default=0)
    low = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最低价", default=0)
    high = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最高价", default=0)
    open = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="开盘价", default=0)

    a1 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    a2 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    a3 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    a4 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    a5 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    b1 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    b2 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    b3 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    b4 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    b5 = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    a1_v = models.IntegerField(default=0)
    a2_v = models.IntegerField(default=0)
    a3_v = models.IntegerField(default=0)
    a4_v = models.IntegerField(default=0)
    a5_v = models.IntegerField(default=0)
    b1_v = models.IntegerField(default=0)
    b2_v = models.IntegerField(default=0)
    b3_v = models.IntegerField(default=0)
    b4_v = models.IntegerField(default=0)
    b5_v = models.IntegerField(default=0)

    volume = models.IntegerField(verbose_name="交易量", default=0)
    amount = models.FloatField(verbose_name="交易额", default=0)

    class Meta:
        ordering = ['stock_symbol', 'datetime']

    def __str__(self):
        return self.stock_symbol + str(self.datetime)

    def get_level5_data(self, to_list=False):
        if not to_list:
            ask_info = [(self.a5, self.a5_v), (self.a4, self.a4_v), (self.a3, self.a3_v), (self.a2, self.a2_v),
                        (self.a1, self.a1_v)]
            bid_info = [(self.b1, self.b1_v), (self.b2, self.b2_v), (self.b3, self.b3_v), (self.b4, self.b4_v),
                        (self.b5, self.b5_v)]
            return ask_info, bid_info
        else:
            return [self.a5, self.a5_v, self.a4, self.a4_v, self.a3, self.a3_v, self.a2, self.a2_v, self.a1, self.a1_v,
                    self.b1, self.b1_v, self.b2, self.b2_v, self.b3, self.b3_v, self.b4, self.b4_v, self.b5, self.b5_v]

    def get_level5_volume(self):
        return (self.a5_v + self.a4_v + self.a3_v + self.a2_v + self.a1_v,
                self.b1_v + self.b2_v + self.b3_v + self.b4_v + self.b5_v)


class SimStockDailyInfo(models.Model):
    """
    股市模拟过程中的股票日级别信息
    """
    stock_symbol = models.CharField(max_length=12)
    date = models.DateField()

    low = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最低价", default=0)
    high = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最高价", default=0)
    open = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="开盘价", default=0)
    close = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="收盘价", default=0)

    volume = models.IntegerField(verbose_name="交易量", default=0)
    amount = models.FloatField(verbose_name="交易额", default=0)

    def __str__(self):
        return self.stock_symbol + str(self.date)


class SimOrderBookEntry(models.Model):
    """
    Order Book Entry, i.e. an entry of a specific price. contains (\d+) elements
    """
    stock_symbol = models.CharField(max_length=12)
    entry_direction = models.CharField(max_length=1, default='b')
    entry_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='价格')
    total_vol = models.IntegerField(default=0)

    class Meta:
        ordering = ['stock_symbol', 'entry_direction', 'entry_price']

    def __str__(self):
        return self.stock_symbol + '-(' + str(self.entry_price) + ',' + str(self.entry_direction) + ')'


class SimOrderBookElem(models.Model):
    """
    Order Book Entry
    """
    entry_belonged = models.IntegerField()  # 所属的order book条目
    unique_id = models.UUIDField(blank=False, default=uuid.uuid4)  # 用于和委托一一对应
    client = models.IntegerField()  # 挂单的client的id
    date_committed = models.DateTimeField()  # 委托提交被挂起的时间
    OPERATION_DIRECTION = (
        ('a', 'ASK'),
        ('b', 'BID'),
    )
    direction_committed = models.CharField(max_length=1, choices=OPERATION_DIRECTION, verbose_name='方向')
    price_committed = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='价格')
    vol_committed = models.IntegerField(verbose_name='数量')

    class Meta:
        ordering = ['entry_belonged', 'date_committed']

    def __str__(self):
        return str(self.client) + '-(' + str(self.price_committed) + ',' + str(self.vol_committed) + ')'


class SimTradeHistory(models.Model):
    """
    记录股票的模拟交易历史
    """
    stock_symbol = models.CharField(max_length=12)
    TRADE_DIRECTION = (
        ('a', 'ASK'),
        ('b', 'BID'),
    )
    direction = models.CharField(max_length=1, choices=TRADE_DIRECTION, verbose_name='交易方向')
    price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="价格", blank=False)
    vol = models.IntegerField(blank=False)
    datetime = models.DateTimeField(blank=False)
    tick = models.IntegerField(blank=False)

    class Meta:
        ordering = ['stock_symbol', 'tick', 'id']

    def __str__(self):
        return self.stock_symbol + str(self.direction) + '-(' + str(self.price) + ',' + str(self.vol) + ')'

