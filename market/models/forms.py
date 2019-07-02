from django import forms
from django.core.exceptions import ValidationError

from .clients import BaseClient, CommissionElem
from .trades import CommissionMsg
from .sim_clients import SimHoldingElem
from .sim_stocks import SimStock
from .sim_market import AddClient
from .config import *


class BidForm(forms.ModelForm):
    class Meta:
        model = CommissionElem
        fields = ['stock_corr', 'operation', 'price_committed', 'vol_committed']
        labels = {'stock_corr': '股票代码', 'operation': '操作方向'}


class CancelForm(forms.ModelForm):
    class Meta:
        model = CommissionMsg
        fields = ['cancel_cms']
        labels = {'cancel_cms': '取消委托'}


class VClientForm(forms.ModelForm):
    class Meta:
        model = AddClient
        fields = ['name', 'cash', 'strategy', 'stock_corr', 'vol']
        labels = {'name': '名称', 'cash': '初始资金', 'strategy': '初始策略', 'stock_corr': '股票代码', 'vol': '持有数量'}


class VStockForm(forms.ModelForm):
    class Meta:
        model = SimStock
        fields = ['symbol', 'name']
        labels = {'symbol': '股票代码', 'name': '股票名称'}

