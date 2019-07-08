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
    last_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最新价",
                                     null=True, blank=True, help_text="last price of the stock", default=0)
    low = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最低价",
                              null=True, blank=True, help_text="lowest price of the stock till now today", default=0)
    high = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最高价",
                               null=True, blank=True, help_text="highest price of the stock till now today", default=0)
    limit_up = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="涨停价",
                                   null=True, blank=True, help_text="limit up of the stock today", default=0)
    limit_down = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="跌停价",
                                     null=True, blank=True, help_text="limit down of the stock today", default=0)

    volume = models.IntegerField(verbose_name="交易量", null=True, blank=True,
                                 help_text="Total traded volume of this stock today", default=0)
    amount = models.FloatField(verbose_name="交易额", null=True, blank=True,
                               help_text="Total traded amount of this stock today", default=0)

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

    def get_daily_absolute_url(self):
        return reverse('market:sim_stock_daily', args=[str(self.id)])

    def initialize_order_book(self):
        """
        初始化stock的order book
        """
        order_book, ok = SimOrderBook.objects.get_or_create(stock=self)
        return order_book

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

        SimTradeHistory.objects.create(stock=self, direction=direction, price=price, vol=vol, datetime=datetime, tick=tick)

    def is_order_book_empty(self, direction):
        """
        判断自己的买或卖的order book是否为空
        """
        order_book, _ = SimOrderBook.objects.get_or_create(stock=self)
        entries = SimOrderBookEntry.objects.filter(order_book=order_book, entry_direction=direction)
        if entries.exists():
            return True
        else:
            return False

    def get_order_book_info(self):
        ask_info = []
        bid_info = []
        order_book, _ = SimOrderBook.objects.get_or_create(stock=self)
        order_book_entries = SimOrderBookEntry.objects.filter(order_book=order_book).order_by('entry_price')
        if order_book_entries is not None:
            for entry in order_book_entries:
                if entry.entry_direction == 'a':
                    ask_info.append((entry.entry_price, entry.total_vol))
                elif entry.entry_direction == 'b':
                    bid_info.append((entry.entry_price, entry.total_vol))
                else:
                    raise ValueError('Invalid direction in order book entries!')

        return ask_info, bid_info

    def get_level1_data(self):
        order_book = SimOrderBook.objects.get(stock=self)
        best_ask_price = SimOrderBookEntry.objects.filter(order_book=order_book, entry_direction='a').order_by(
            'entry_price')[0].entry_price
        best_bid_price = SimOrderBookEntry.objects.filter(order_book=order_book, entry_direction='b').order_by(
            '-entry_price')[0].entry_price
        return best_ask_price, best_bid_price

    def get_level5_data(self):
        ask_info = []
        bid_info = []
        order_book, _ = SimOrderBook.objects.get_or_create(stock=self)
        ask_entries = SimOrderBookEntry.objects.filter(order_book=order_book, entry_direction='a').order_by('entry_price')
        if ask_entries is not None:
            for entry in ask_entries:
                ask_info.append((entry.entry_price, entry.total_vol))
                if len(ask_info) >= 5:
                    break
        while len(ask_info) < 5:
            ask_info.insert(0, (None, None))

        bid_entries = SimOrderBookEntry.objects.filter(order_book=order_book, entry_direction='b').order_by('-entry_price')
        if bid_entries is not None:
            for entry in bid_entries:
                bid_info.append((entry.entry_price, entry.total_vol))
                if len(bid_info) >= 5:
                    break
        while len(bid_info) < 5:
            bid_info.append((None, None))

        return ask_info, bid_info

    def get_datetime_bound(self):
        """
        在模拟时得到导入的数据的起止日期
        """
        slices = SimStockSlice.objects.filter(stock=self).order_by('datetime')
        r_slices = slices.reverse()
        return str(slices[0].datetime) + '  --  ' + str(r_slices[0].datetime)

    def get_slices(self):
        slices = SimStockSlice.objects.filter(stock=self).order_by('datetime')
        return slices

    def reset(self):
        order_book, _ = SimOrderBook.objects.get_or_create(stock=self)
        order_book_entries = SimOrderBookEntry.objects.filter(order_book=order_book)
        for entry in order_book_entries:
            entry.simorderbookelem_set.all().delete()
            entry.delete()
        self.amount = 0
        self.volume = 0
        self.last_price = 0
        self.high = 0
        self.low = 0
        self.limit_up = 0
        self.limit_down = 0
        self.save()
        return True

    def quit(self):
        time0 = time.time()
        order_book, _ = SimOrderBook.objects.get_or_create(stock=self)
        order_book_entries = SimOrderBookEntry.objects.filter(order_book=order_book)
        for entry in order_book_entries:
            entry.simorderbookelem_set.all().delete()
            entry.delete()
        order_book.delete()
        time1 = time.time()
        self.simstockslice_set.all().delete()
        print('stock:{} id:{} quit, cost {}s.'.format(self.symbol, self.id, time1 - time0))
        self.delete()
        return True


class SimStockSlice(models.Model):
    """
    股市模拟过程中的股票一个切片信息
    """
    stock = models.ForeignKey(SimStock, on_delete=models.CASCADE)
    datetime = models.DateTimeField(blank=False)

    last_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="当前价",
                                     null=True, blank=True, help_text="last price of the stock", default=0)
    low = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最低价",
                              null=True, blank=True, help_text="lowest price of the stock till now today", default=0)
    high = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最高价",
                               null=True, blank=True, help_text="highest price of the stock till now today", default=0)
    open = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="开盘价",
                               null=True, blank=True, default=0)

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

    volume = models.IntegerField(verbose_name="交易量", null=True, blank=True, default=0)
    amount = models.FloatField(verbose_name="交易额", null=True, blank=True, default=0)

    def __str__(self):
        return self.stock.symbol + str(self.datetime)


class SimStockDailyInfo(models.Model):
    """
    股市模拟过程中的股票日级别信息
    """
    stock = models.ForeignKey(SimStock, on_delete=models.CASCADE)
    date = models.DateField(blank=False)

    low = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最低价",
                              null=True, blank=True, help_text="lowest price of the stock till now today", default=0)
    high = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最高价",
                               null=True, blank=True, help_text="highest price of the stock till now today", default=0)
    open = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="开盘价",
                               null=True, blank=True, default=0)
    close = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="收盘价",
                                null=True, blank=True, default=0)

    volume = models.IntegerField(verbose_name="交易量", null=True, blank=True, default=0)
    amount = models.FloatField(verbose_name="交易额", null=True, blank=True, default=0)

    def __str__(self):
        return self.stock.symbol + str(self.date)


class SimOrderBook(models.Model):
    """
    order book of a stock
    """
    stock = models.ForeignKey(SimStock, on_delete=models.CASCADE)

    class Meta:
        ordering = ['stock']

    def __str__(self):
        return self.stock.symbol + '(' + self.stock.name + ')'

    def is_empty(self, direction):
        entries = SimOrderBookEntry.objects.filter(order_book=self, entry_direction=direction)
        if entries.exists():
            return False
        else:
            return True

    def get_best_element(self, direction):
        if self.is_empty(direction):
            return None
        else:
            if direction == 'a':
                # 得到最早的卖一条目
                best_entry = self.simorderbookentry_set.filter(entry_direction=direction).select_related().order_by('entry_price')[0]
                best_element = best_entry.simorderbookelem_set.all().order_by('-date_committed')[0]
                return best_element
            elif direction == 'b':
                # 得到最早的买一条目
                best_entry = self.simorderbookentry_set.filter(entry_direction=direction).order_by('-entry_price')[0]
                best_element = best_entry.simorderbookelem_set.all().order_by('-date_committed')[0]
                return best_element
            else:
                raise NotImplementedError


class SimOrderBookEntry(models.Model):
    """
    Order Book Entry, i.e. an entry of a specific price. contains (\d+) elements
    """
    order_book = models.ForeignKey(SimOrderBook, on_delete=models.CASCADE)
    entry_direction = models.CharField(max_length=1, default='b')
    entry_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='价格')
    total_vol = models.IntegerField(default=0)

    class Meta:
        ordering = ['order_book', 'entry_direction', 'entry_price']

    def __str__(self):
        return self.order_book.__str__() + str(self.entry_price) + str(self.entry_direction)


class SimOrderBookElem(models.Model):
    """
    Order Book Entry
    """
    order_book_entry = models.ForeignKey(SimOrderBookEntry, on_delete=models.CASCADE)

    unique_id = models.UUIDField(blank=False, default=uuid.uuid4)
    client = models.ForeignKey('market.BaseClient', on_delete=models.CASCADE)
    date_committed = models.DateTimeField(blank=False)
    OPERATION_DIRECTION = (
        ('a', 'ASK'),
        ('b', 'BID'),
    )
    direction_committed = models.CharField(max_length=1, choices=OPERATION_DIRECTION, verbose_name='方向')
    price_committed = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='价格')
    vol_committed = models.IntegerField(verbose_name='数量')

    class Meta:
        ordering = ['order_book_entry', 'date_committed']

    def __str__(self):
        return self.client.name


class SimTradeHistory(models.Model):
    """
    记录股票的模拟交易历史
    """
    stock = models.ForeignKey(SimStock, on_delete=models.CASCADE)
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
        ordering = ['stock', 'tick', 'id']

    def __str__(self):
        return self.stock.symbol + '(' + self.stock.name + ')' + str(self.direction) + str(self.price) + str(self.id)

