from django import forms
from django.core.exceptions import ValidationError

from .clients import BaseClient, CommissionElem
from .trades import CommissionMsg
from .sim_clients import SimHoldingElem
from .sim_stocks import SimStock
from .sim_market import INITIAL_DATETIME, END_DATETIME, AddClient
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


class ImportStockDataForm(forms.Form):
    stock_symbol = forms.CharField(max_length=12, label='股票代码')
    start_date = forms.SplitDateTimeField(label='起始时间', initial=INITIAL_DATETIME)
    end_date = forms.SplitDateTimeField(label='截止时间', initial=END_DATETIME)
    INTERVAL = (
        ('t', 'tick'),
        ('m', 'minute'),
    )
    interval = forms.ChoiceField(choices=INTERVAL, label='数据级别')


class AnchorForm(forms.Form):
    anchor_datetime = forms.SplitDateTimeField(label='起始时间', initial=INITIAL_DATETIME)


class GenerateDataForm(forms.Form):
    stock_symbol = forms.CharField(max_length=12, label='股票代码', initial='000009.XSHE')
    traj_length = forms.IntegerField(label='轨迹长度', initial=64)
    traj_num = forms.IntegerField(label='轨迹数目', initial=-1)
    track_length = forms.IntegerField(label='TICK追踪长度', initial=64)


class GailTrainForm(forms.Form):
    stock_symbol = forms.CharField(max_length=12, label='股票代码', initial='000009.XSHE')
    seed = forms.IntegerField(label='随机种子', initial=0)
    task = forms.ChoiceField(choices=(('train', 'train'), ('evaluate', 'evaluate'), ('sample', 'sample')),
                             label='训练任务', initial='train')
    algo = forms.ChoiceField(choices=(('trpo', 'trpo'), ('ppo', 'ppo')), label='算法使用', initial='trpo')
    g_step = forms.IntegerField(initial=3, label='G的步数')
    d_step = forms.IntegerField(initial=1, label='D的步数')
