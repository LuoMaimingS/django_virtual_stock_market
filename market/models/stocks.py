from django.db import models
from django.urls import reverse
import uuid

from .config import *


class Stock(models.Model):
    """
    Model representing A stock class
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
        return reverse('market:stock', args=[str(self.id)])

    def initialize_order_book(self):
        """
        初始化stock的order book
        """
        OrderBook.objects.get_or_create(stock=self)

    def trading_behaviour(self, direction, price, vol, datetime):
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

        new_trade = TradeHistory(stock=self, direction=direction, price=price, vol=vol, datetime=datetime)
        new_trade.save()

    def is_order_book_empty(self, direction):
        """
        判断自己的买或卖的order book是否为空
        """
        order_book = OrderBook.objects.get(stock=self)
        entries = OrderBookEntry.objects.filter(order_book=order_book, entry_direction=direction)
        if entries.exists():
            return True
        else:
            return False

    def get_order_book_info(self):
        ask_info = []
        bid_info = []
        order_book = OrderBook.objects.get(stock=self)
        order_book_entries = OrderBookEntry.objects.filter(order_book=order_book).order_by('entry_price')
        if order_book_entries is not None:
            for entry in order_book_entries:
                if entry.entry_direction == 'a':
                    ask_info.append((entry.entry_price, entry.total_vol))
                elif entry.entry_direction == 'b':
                    bid_info.append((entry.entry_price, entry.total_vol))
                else:
                    raise ValueError('Invalid direction in order book entries!')

        return ask_info, bid_info

    def get_level5_data(self):
        ask_info = []
        bid_info = []
        order_book, _ = OrderBook.objects.get_or_create(stock=self)
        ask_entries = OrderBookEntry.objects.filter(order_book=order_book, entry_direction='a').order_by('entry_price')
        if ask_entries is not None:
            for entry in ask_entries:
                ask_info.append((entry.entry_price, entry.total_vol))
                if len(ask_info) >= 5:
                    break
        while len(ask_info) < 5:
            ask_info.insert(0, (None, None))

        bid_entries = OrderBookEntry.objects.filter(order_book=order_book, entry_direction='b').order_by('-entry_price')
        if bid_entries is not None:
            for entry in bid_entries:
                bid_info.append((entry.entry_price, entry.total_vol))
                if len(bid_info) >= 5:
                    break
        while len(bid_info) < 5:
            bid_info.append((None, None))

        return ask_info, bid_info


class OrderBook(models.Model):
    """
    order book of a stock
    """
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)

    class Meta:
        ordering = ['stock']

    def __str__(self):
        return self.stock.symbol + '(' + self.stock.name + ')'

    def is_empty(self, direction):
        entries = OrderBookEntry.objects.filter(order_book=self, entry_direction=direction)
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
                best_entry = self.orderbookentry_set.filter(entry_direction=direction).order_by('entry_price')[0]
                best_element = best_entry.orderbookelem_set.all().order_by('-date_committed')[0]
                return best_element
            elif direction == 'b':
                # 得到最早的买一条目
                best_entry = self.orderbookentry_set.filter(entry_direction=direction).order_by('-entry_price')[0]
                best_element = best_entry.orderbookelem_set.all().order_by('-date_committed')[0]
                return best_element
            else:
                raise NotImplementedError


class OrderBookEntry(models.Model):
    """
    Order Book Entry, i.e. an entry of a specific price. contains (\d+) elements
    """
    order_book = models.ForeignKey(OrderBook, on_delete=models.CASCADE)
    entry_direction = models.CharField(max_length=1, default='b')
    entry_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='价格')
    total_vol = models.IntegerField(default=0)

    class Meta:
        ordering = ['order_book', 'entry_direction', 'entry_price']

    def __str__(self):
        return self.order_book.__str__() + str(self.entry_price) + str(self.entry_direction)


class OrderBookElem(models.Model):
    """
    Order Book Entry
    """
    order_book_entry = models.ForeignKey(OrderBookEntry, on_delete=models.CASCADE)

    unique_id = models.UUIDField(blank=False, default=uuid.uuid4)
    client = models.ForeignKey('market.BaseClient', on_delete=models.CASCADE)
    date_committed = models.DateTimeField(auto_now_add=True)
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


class TradeHistory(models.Model):
    """
    记录股票的交易历史
    """
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    TRADE_DIRECTION = (
        ('a', 'ASK'),
        ('b', 'BID'),
    )
    direction = models.CharField(max_length=1, choices=TRADE_DIRECTION, verbose_name='交易方向')
    price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="价格", blank=False)
    vol = models.IntegerField(blank=False)
    datetime = models.DateTimeField(blank=False)

    class Meta:
        ordering = ['stock']

    def __str__(self):
        return self.stock.symbol + '(' + self.stock.name + ')'

