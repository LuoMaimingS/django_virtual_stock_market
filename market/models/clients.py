from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
import uuid
import time

from .config import *
from .utils import *


class BaseClient(models.Model):
    """
    Model representing A base class
    """
    # if it is created by a user, we call it is driven by the user.
    driver = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    name = models.CharField(max_length=20)
    cash = models.FloatField(default=CASH)
    frozen_cash = models.FloatField(default=0)
    flexible_cash = models.FloatField(default=CASH)
    profit = models.FloatField(default=0)
    date_reg = models.DateTimeField(auto_now_add=True)

    CLIENT_STATUS = (
        ('a', 'Activate'),
        ('f', 'forbidden'),
        ('i', 'Inactivate'),
    )
    status = models.CharField(max_length=1, choices=CLIENT_STATUS, blank=True, default='a')

    CLIENT_STRATEGY = (
        ('n', 'No strategy'),
    )

    strategy = models.CharField(max_length=1, choices=CLIENT_STRATEGY, default='n')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('market:client', args=[str(self.id)])

    def refresh(self):
        self.profit = 0
        for hold in self.holdingelem_set.all():
            hold.refresh()
        self.save()

    def turn_to_inactive(self):
        """
        转向不活跃状态
        """
        self.status = 'i'
        self.save()
        return True

    def quit(self):
        """
        client推出市场时，删除全部的有关数据（除了交易历史），目前可能导致交易历史指向链接不可得的bug
        """
        time0 = time.time()
        self.holdingelem_set.all().delete()
        self.simholdingelem_set.all().delete()
        self.commissionelem_set.all().delete()
        self.simcommissionelem_set.all().delete()
        self.focuselem_set.all().delete()
        self.orderbookelem_set.all().delete()
        self.simorderbookelem_set.all().delete()
        time1 = time.time()
        print('client:{} id:{} quits, cost {}s.'.format(self.name, self.id, time1 - time0))
        self.delete()
        return True


class HoldingElem(models.Model):
    """
    Client的持仓信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE)

    # stock corresponding
    stock_corr = models.ForeignKey('market.Stock', on_delete=models.CASCADE)
    stock_symbol = models.CharField(max_length=12)
    stock_name = models.CharField(max_length=20)

    # volume info
    vol = models.IntegerField(verbose_name='股票总数量', default=0)
    frozen_vol = models.IntegerField(verbose_name='冻结数量', default=0)
    available_vol = models.IntegerField(verbose_name='可用数量', default=0)

    # price info
    cost = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='成本价', default=0)
    price_guaranteed = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='保本价', default=0)
    last_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name="最新价",
                                     null=True, blank=True, help_text="last price of the stock", default=0)

    # profit info
    profit = models.FloatField(verbose_name='盈亏', default=0)
    value = models.FloatField(verbose_name='市值', default=0)

    # date info
    date_bought = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['owner', '-date_bought']

    def __str__(self):
        return self.stock_symbol + '(' + self.stock_name + ')'

    def refresh(self):
        self.last_price = self.stock_corr.last_price
        self.profit = float((self.last_price - self.cost) * self.vol)
        self.value = self.last_price * self.vol
        self.owner.profit += self.profit
        self.save()

    def get_stock_url(self):
        """
        Returns the url to the stock.
        """
        return reverse('market:stock', args=[str(self.stock_corr.id)])


class CommissionElem(models.Model):
    """
    Client的委托信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE, null=False)
    unique_id = models.UUIDField(blank=False, editable=False)

    # date info
    date_committed = models.DateTimeField(blank=False)

    # stock corresponding
    stock_corr = models.ForeignKey('market.Stock', on_delete=models.CASCADE)
    stock_symbol = models.CharField(max_length=12)
    stock_name = models.CharField(max_length=20)

    # commission info
    CLIENT_OPERATION = (
        ('b', '买入'),
        ('a', '卖出'),
    )
    operation = models.CharField(max_length=1, choices=CLIENT_OPERATION, blank=False, default='b')
    price_committed = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='委托价格')
    vol_committed = models.IntegerField(verbose_name='委托数量')

    # trade info
    price_traded = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='成交均价', default=0)
    vol_traded = models.IntegerField(verbose_name='成交数量', default=0)

    class Meta:
        ordering = ['owner', '-date_committed']

    def __str__(self):
        return self.stock_symbol + '(' + self.stock_name + ')'

    def get_stock_url(self):
        """
        Returns the url to the stock.
        """
        return reverse('market:stock', args=[str(self.stock_corr.id)])


class TransactionElem(models.Model):
    """
    Client的成交信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE, null=False, related_name="self_side")
    unique_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # stock corresponding
    stock_corr = models.ForeignKey('market.Stock', on_delete=models.CASCADE)
    stock_symbol = models.CharField(max_length=12)
    stock_name = models.CharField(max_length=20)

    # commission info
    CLIENT_OPERATION = (
        ('a', 'ASK'),
        ('b', 'BID'),
        ('c', 'CANCEL')
    )
    operation = models.CharField(max_length=1, choices=CLIENT_OPERATION, blank=False, default='b',
                                 help_text='operation')

    # trade info
    price_traded = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='成交价格',
                                       default=0)
    vol_traded = models.IntegerField(verbose_name='成交数量', default=0)
    counterpart = models.ForeignKey(BaseClient, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='counterpart')
    date_traded = models.DateTimeField(blank=False)

    class Meta:
        ordering = ['owner', '-date_traded']

    def __str__(self):
        return self.stock_symbol + '(' + self.stock_name + ')'

    def get_stock_url(self):
        """
        Returns the url to the stock.
        """
        return reverse('market:stock', args=[str(self.stock_corr.id)])


class FocusElem(models.Model):
    """
    Client关注的股票信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE)
    stock_symbol = models.CharField(max_length=12)
    stock_name = models.CharField(max_length=20)

    # stock corresponding
    stock_corr = models.ForeignKey('market.Stock', on_delete=models.CASCADE)

    class Meta:
        ordering = ['owner']

    def __str__(self):
        return self.stock_symbol + '(' + self.stock_name + ')'

    def get_stock_url(self):
        """
        Returns the url to the stock.
        """
        return reverse('market:stock', args=[str(self.stock_corr.id)])

