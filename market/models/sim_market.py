from django.db import models

import datetime

from .utils import *
from .config import *

INITIAL_DATETIME = datetime.datetime.strptime('2018-1-2 9:30', '%Y-%m-%d %H:%M')
END_DATETIME = datetime.datetime.strptime('2018-1-3 9:50', '%Y-%m-%d %H:%M')


class SimMarket(models.Model):
    datetime = models.DateTimeField(default=INITIAL_DATETIME)
    anchored_datetime = models.DateTimeField(default=INITIAL_DATETIME)
    tick = models.IntegerField(default=0)
    num_v_clients = models.IntegerField(default=0)

    def reset(self):
        self.datetime = INITIAL_DATETIME
        self.tick = 0
        self.save()


def generate_ordered_client_name():
    market, _ = SimMarket.objects.get_or_create(id=1)
    name = 'SimClient_ID_' + str(market.num_v_clients + 1)
    return name


class AddClient(models.Model):
    name = models.CharField(max_length=20, default=generate_ordered_client_name)
    cash = models.FloatField(default=CASH)

    CLIENT_STRATEGY = (
        ('n', 'No strategy'),
    )
    strategy = models.CharField(max_length=1, choices=CLIENT_STRATEGY, default='n')
    stock_corr = models.ForeignKey('market.SimStock', on_delete=models.CASCADE, blank=True, null=True)
    vol = models.IntegerField(verbose_name='股票总数量', default=0)



