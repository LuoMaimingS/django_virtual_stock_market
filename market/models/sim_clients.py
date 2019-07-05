from django.db import models
from django.urls import reverse
import uuid

from .clients import BaseClient
from .config import *


class SimHoldingElem(models.Model):
    """
    Client的持仓信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE)

    # stock corresponding
    stock_corr = models.ForeignKey('market.SimStock', on_delete=models.CASCADE)
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
    date_bought = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['owner', '-date_bought']

    def __str__(self):
        return self.stock_symbol + '(' + self.stock_name + ')' + str(self.vol)

    def refresh(self):
        self.last_price = self.stock_corr.last_price
        self.profit = (self.last_price - self.cost) * self.vol
        self.value = self.last_price * self.vol
        self.save()

    def get_stock_url(self):
        """
        Returns the url to the stock.
        """
        return reverse('market:sim_stock', args=[str(self.stock_corr.id)])


class SimCommissionElem(models.Model):
    """
    Client的委托信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE, null=False)
    unique_id = models.UUIDField(blank=False, editable=False)

    # date info
    date_committed = models.DateTimeField(blank=False)

    # stock corresponding
    stock_corr = models.ForeignKey('market.SimStock', on_delete=models.CASCADE)
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
        return reverse('market:sim_stock', args=[str(self.stock_corr.id)])


class SimTransactionElem(models.Model):
    """
    Client的成交信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE, null=False, related_name="sim_self_side")
    unique_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # stock corresponding
    stock_corr = models.ForeignKey('market.SimStock', on_delete=models.CASCADE)
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
                                    related_name='sim_counterpart')
    date_traded = models.DateTimeField(blank=False)

    class Meta:
        ordering = ['owner', '-date_traded']

    def __str__(self):
        return self.stock_symbol + '(' + self.stock_name + ')'

    def get_stock_url(self):
        """
        Returns the url to the stock.
        """
        return reverse('market:sim_stock', args=[str(self.stock_corr.id)])
