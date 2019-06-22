from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

from .config import *


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
    profit = models.FloatField(help_text="profit made till now", default=0)
    date_reg = models.DateTimeField(auto_now_add=True)

    CLIENT_STATUS = (
        ('a', 'Activate'),
        ('f', 'forbidden'),
        ('i', 'Inactivate'),
    )

    status = models.CharField(max_length=1, choices=CLIENT_STATUS, blank=True, default='a', help_text='client status')

    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
    #                       help_text="Unique ID for a client in the market.")

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


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
    vol = models.IntegerField(verbose_name='股票总数量')
    frozen_vol = models.IntegerField(verbose_name='冻结数量', default=0)
    available_vol = models.IntegerField(verbose_name='可用数量')

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

    def get_stock_url(self):
        """
        Returns the url to the stock.
        """
        return reverse('market:stock', args=[str(self.stock_corr.id)])


class CommissionElem(models.Model):
    """
    Client的委托信息
    """
    owner = models.ForeignKey(BaseClient, on_delete=models.CASCADE, null=False, related_name="self_side")

    # date info
    date_committed = models.DateTimeField(auto_now_add=True)

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
    operation = models.CharField(max_length=1, choices=CLIENT_OPERATION, blank=False, default='b', help_text='operation')
    price_committed = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='委托价格')
    vol_committed = models.IntegerField(verbose_name='委托数量')

    # trade info
    price_traded = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, verbose_name='成交价格', default=0)
    vol_traded = models.IntegerField(verbose_name='成交数量', default=0)
    opponent_traded = models.ForeignKey(BaseClient, on_delete=models.CASCADE, null=True, blank=True, related_name='oppo_side')
    date_traded = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['owner', '-date_committed']

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

