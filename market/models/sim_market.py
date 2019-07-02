from django.db import models

import datetime

from .utils import *
from .config import *

INITIAL_DATETIME = datetime.datetime.strptime('2019-5-4 9:46', '%Y-%m-%d %H:%M')


class SimMarket(models.Model):
    datetime = models.DateTimeField(default=INITIAL_DATETIME)
    tick = models.IntegerField(default=0)


class AddClient(models.Model):
    name = models.CharField(max_length=20, default=generate_random_client_name)
    cash = models.FloatField(default=CASH)

    CLIENT_STRATEGY = (
        ('n', 'No strategy'),
    )
    strategy = models.CharField(max_length=1, choices=CLIENT_STRATEGY, default='n')
    stock_corr = models.ForeignKey('market.SimStock', on_delete=models.CASCADE, blank=True, null=True)
    vol = models.IntegerField(verbose_name='股票总数量', default=0)