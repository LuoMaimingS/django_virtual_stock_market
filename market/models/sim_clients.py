# _*_ coding:UTF-8 _*_

"""
该文件定义了模拟环境中client相关的模型，包括持仓，委托，交易等，
并非虚拟股市原本的模型，做了一些适应性的调整，取消了全部外键。
"""

from django.db import models
import uuid
from .config import *


class SimHoldingElem(models.Model):
    """
    Client的持仓信息
    """
    owner = models.IntegerField()  # 持有者的ID
    stock_symbol = models.CharField(max_length=12)  # 股票代码

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
    date_bought = models.DateTimeField()

    class Meta:
        ordering = ['owner', '-date_bought', 'id']

    def __str__(self):
        return self.stock_symbol + '-' + str(self.vol) + 'shares'


class SimCommissionElem(models.Model):
    """
    Client的委托信息
    """
    owner = models.IntegerField()  # 委托者的ID
    stock_symbol = models.CharField(max_length=12)  # 股票代码
    unique_id = models.UUIDField(blank=False, default=uuid.uuid4)

    # date info
    date_committed = models.DateTimeField()

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
        return self.stock_symbol + '-' + self.operation + '-' + str(self.vol_committed) + 'shares'


class SimTransactionElem(models.Model):
    """
    Client的成交信息
    """
    one_side = models.IntegerField(verbose_name='交易一方的ID')
    the_other_side = models.IntegerField(verbose_name='交易另一方的ID')
    stock_symbol = models.CharField(max_length=12, verbose_name='股票代码')

    # transaction info
    CLIENT_OPERATION = (
        ('a', 'ASK'),
        ('b', 'BID'),
        ('c', 'CANCEL')
    )
    operation = models.CharField(max_length=1, choices=CLIENT_OPERATION, blank=False, default='b', verbose_name='交易一方的成交方向')

    # trade info
    price_traded = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='成交价格',
                                       default=0)
    vol_traded = models.IntegerField(verbose_name='成交数量', default=0)
    date_traded = models.DateTimeField(blank=False)

    class Meta:
        ordering = ['one_side', '-date_traded']

    def __str__(self):
        return str(self.one_side) + self.operation + '-' + self.stock_symbol + '-' + str(self.vol_traded) + 'shares'
