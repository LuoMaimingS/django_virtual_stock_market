from django import forms
from django.core.exceptions import ValidationError

from .clients import BaseClient, HoldingElem, CommissionElem, FocusElem
from .stocks import Stock
from .config import *


class ClientForm(forms.ModelForm):
    class Meta:
        model = BaseClient
        fields = ['name']
        labels = {'name': 'name'}


class BidForm(forms.ModelForm):
    class Meta:
        model = CommissionElem
        fields = ['stock_corr', 'price_committed', 'vol_committed']
    """

    bid_symbol = forms.CharField(max_length=12, help_text="委托买入的股票代码")
    bid_price = forms.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, help_text="委托价格")
    bid_vol = forms.IntegerField(help_text="委托数量")
    bid_type = forms.BooleanField(initial=True, help_text="是否限价", disabled=True)

    def clean_bid_symbol(self):
        data = self.cleaned_data['bid_symbol']
        if not Stock.objects.filter(symbol=data).exists():
            raise ValidationError('错误的股票代码 — 该代码不存在')
        return data
    """




