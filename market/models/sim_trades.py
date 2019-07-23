# _*_ coding:UTF-8 _*_

"""
该文件定义了模拟环境中交易动作相关的模型
并非虚拟股市原本的模型，做了一些适应性的调整，取消了全部外键。
"""

from django.db import models
import uuid
from decimal import Decimal
import time

from .clients import BaseClient
from .sim_market import SimMarket
from .sim_clients import SimHoldingElem, SimCommissionElem, SimTransactionElem
from .sim_stocks import SimStock, SimOrderBookEntry, SimOrderBookElem
from .config import *


class SimTradeMsg(models.Model):
    stock_symbol = models.CharField(max_length=12)
    initiator = models.IntegerField(verbose_name='交易的发起方ID')

    trade_direction = models.CharField(max_length=1)
    trade_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    trade_vol = models.IntegerField()
    trade_date = models.DateTimeField(blank=False)
    trade_tick = models.IntegerField(blank=False)

    # 被交易的挂单的ID
    commission_id = models.UUIDField(blank=False, default=uuid.uuid4, verbose_name='原本挂单的uuid')

    acceptor = models.IntegerField(verbose_name='交易的接受方ID')
    tax_charged = models.FloatField(default=0)


def sim_instant_trade(msg):
    """
    client的委托立刻得到了交易，从而不会出现在委托记录中
    :param msg: 交易的相关信息，是一个TradeMsg类
    """
    initiator = msg.initiator
    stock_symbol = msg.stock_symbol

    initiator_object = BaseClient.objects.get(id=initiator)
    stock_object = SimStock.objects.get(symbol=stock_symbol)
    SimTransactionElem.objects.create(one_side=initiator, the_other_side=msg.acceptor,
                                      stock_symbol=stock_symbol, price_traded=msg.trade_price, vol_traded=msg.trade_vol,
                                      date_traded=msg.trade_date, operation=msg.trade_direction)

    if msg.trade_direction == 'a':
        # 卖出
        hold_element = SimHoldingElem.objects.get(owner=initiator, stock_symbol=stock_symbol)
        available_shares = hold_element.available_vol
        assert available_shares >= msg.trade_vol
        hold_element.available_vol -= msg.trade_vol
        hold_element.vol -= msg.trade_vol
        if hold_element.vol == 0:
            # 目前为止已全部卖出，不再持有，删除该条数据
            hold_element.delete()
        else:
            hold_element.save(update_fields=['vol', 'available_vol'])

        earning = float(msg.trade_price * msg.trade_vol - msg.tax_charged)
        initiator_object.cash += earning
        initiator_object.flexible_cash += earning

    elif msg.trade_direction == 'b':
        # 买入
        holding = SimHoldingElem.objects.filter(owner=initiator, stock_symbol=stock_symbol)
        if holding.exists():
            # 之前本就持有该股票
            assert holding.count() == 1
            new_holding = holding[0]
            new_holding.cost = Decimal((new_holding.cost * new_holding.vol + msg.trade_price * msg.trade_vol) /
                                       (new_holding.vol + msg.trade_vol))
            new_holding.price_guaranteed = new_holding.cost
            new_holding.last_price = stock_object.last_price
            new_holding.vol += msg.trade_vol
            new_holding.available_vol += msg.trade_vol
            new_holding.profit -= msg.tax_charged
            new_holding.value = float(stock_object.last_price) * new_holding.vol
            new_holding.save()
        else:
            # 即买入新的股票
            SimHoldingElem.objects.create(owner=initiator, stock_symbol=stock_symbol,
                                          vol=msg.trade_vol, frozen_vol=0, available_vol=msg.trade_vol,
                                          cost=msg.trade_price, price_guaranteed=msg.trade_price,
                                          last_price=stock_object.last_price, profit=- msg.tax_charged,
                                          value=stock_object.last_price * msg.trade_vol, date_bought=msg.trade_date)
        spending = float(msg.trade_price * msg.trade_vol + msg.tax_charged)
        initiator_object.cash -= spending
        initiator_object.flexible_cash -= spending

    initiator_object.save(update_fields=['cash', 'flexible_cash'])
    return True


def sim_delayed_trade(msg):
    """
    client的委托记录中的委托得到了交易，从而改变委托情况
    :param msg: 交易的相关信息，是一个TradeMsg类
    """
    assert isinstance(msg, SimTradeMsg)
    acceptor = msg.acceptor
    stock_symbol = msg.stock_symbol
    if msg.trade_direction == 'a':
        acceptor_direction = 'b'
    else:
        acceptor_direction = 'a'

    acceptor_object = BaseClient.objects.get(id=acceptor)
    stock_object = SimStock.objects.get(symbol=stock_symbol)

    # 先处理委托
    commission_element = SimCommissionElem.objects.get(unique_id=msg.commission_id)
    assert commission_element.stock_symbol == stock_symbol
    assert commission_element.operation == acceptor_direction
    assert commission_element.vol_traded + msg.trade_vol <= commission_element.vol_committed
    new_avg_price = (commission_element.price_traded * commission_element.vol_traded +
                     msg.trade_price * msg.trade_vol) / (commission_element.vol_traded + msg.trade_vol)
    commission_element.price_traded = new_avg_price
    commission_element.vol_traded += msg.trade_vol

    # 委托完成时的操作，目前直接删除，没有委托历史记录，只有历史成交记录
    if commission_element.vol_traded == commission_element.vol_committed:
        commission_element.delete()
    else:
        commission_element.save(update_fields=['price_traded', 'vol_traded'])

    if acceptor_direction == 'a':
        # 卖出，处理持仓
        hold_element = SimHoldingElem.objects.get(owner=acceptor, stock_symbol=stock_symbol)
        frozen_shares = hold_element.frozen_vol
        assert frozen_shares >= msg.trade_vol
        hold_element.frozen_vol -= msg.trade_vol
        hold_element.vol -= msg.trade_vol
        if hold_element.vol == 0:
            # 该持有的股票目前为止已全部卖出，不再持有，删除该条数据
            hold_element.delete()
        else:
            hold_element.save(update_fields=['vol', 'frozen_vol'])

        # 结算收益，成交金额减去收益
        earning = float(msg.trade_price * msg.trade_vol - msg.tax_charged)
        acceptor_object.cash += earning
        acceptor_object.flexible_cash += earning

    elif acceptor_direction == 'b':
        # 买入，建仓
        holding = SimHoldingElem.objects.filter(owner=acceptor, stock_symbol=stock_symbol)
        if holding.exists():
            # 之前本就持有该股票
            assert holding.count() == 1
            new_holding = holding[0]
            new_holding.cost = Decimal((new_holding.cost * new_holding.vol + msg.trade_price * msg.trade_vol) /
                                       (new_holding.vol + msg.trade_vol))
            new_holding.price_guaranteed = new_holding.cost
            new_holding.last_price = stock_object.last_price
            new_holding.vol += msg.trade_vol
            new_holding.available_vol += msg.trade_vol
            new_holding.profit -= msg.tax_charged
            new_holding.value = float(stock_object.last_price) * new_holding.vol
            new_holding.save()
        else:
            # 即买入新的股票
            SimHoldingElem.objects.create(owner=acceptor, stock_symbol=stock_symbol,
                                          vol=msg.trade_vol, frozen_vol=0, available_vol=msg.trade_vol,
                                          cost=msg.trade_price, price_guaranteed=msg.trade_price,
                                          last_price=stock_object.last_price, profit=- msg.tax_charged,
                                          value=stock_object.last_price * msg.trade_vol, date_bought=msg.trade_date)

        # 结算交易成本，扣除冻结资金和资金余额
        spending = float(msg.trade_price * msg.trade_vol + msg.tax_charged)
        acceptor_object.cash -= spending
        acceptor_object.frozen_cash -= spending

    acceptor_object.save(update_fields=['cash', 'frozen_cash', 'flexible_cash'])
    return True


class SimCommissionMsg(models.Model):
    stock_symbol = models.CharField(max_length=12)
    commit_client = models.IntegerField(verbose_name='委托的client的ID')

    commit_direction = models.CharField(max_length=1, default='b')
    commit_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    commit_vol = models.IntegerField(default=0)
    commit_date = models.DateTimeField(blank=True, default=None)

    # used for cancel a commission
    commission_to_cancel = models.UUIDField(verbose_name='委托取消的目标委托本身的uuid', default=uuid.uuid4)

    # Confirm the commission
    confirmed = models.BooleanField(default=False)

    def is_valid(self):
        """
        判断委托信息是否合法
        :return: 合法则返回True
        """
        if not SimStock.objects.filter(symbol=self.stock_symbol).exists():
            # 委托的股票标的不存在
            print('The STOCK COMMITTED DOES NOT EXIST!')
            return False
        else:
            stock_corr = SimStock.objects.get(symbol=self.stock_symbol)
        if stock_corr.limit_up != 0 and stock_corr.limit_down != 0:
            if self.commit_price > stock_corr.limit_up or self.commit_price < stock_corr.limit_down:
                # 委托价格，需要在涨跌停价之间
                print('COMMIT PRICE MUST BE BETWEEN THE LIMIT UP AND THE LIMIT DOWN!')
                return False
        if self.commit_direction not in ['a', 'b', 'c']:
            # 委托方向，需要是买/卖/撤，三者其一
            print('COMMIT DIRECTION INVALID!')
            return False

        commit_client_object = BaseClient.objects.get(id=self.commit_client)
        if self.commit_direction == 'a':
            # 委卖，则委托的股票必须有合理的持仓和充足的可用余额
            if not SimHoldingElem.objects.filter(owner=self.commit_client, stock_symbol=self.stock_symbol).exists():
                print('DOES NOT HOLD THE STOCK!')
                return False
            holding_element = SimHoldingElem.objects.get(owner=self.commit_client, stock_symbol=self.stock_symbol)
            if holding_element.available_vol < self.commit_vol:
                print('DOES NOT HOLD ENOUGH STOCK SHARES!')
                return False
        elif self.commit_direction == 'b':
            # 委买，则必须有充足的可用余额，能够负担税费的冻结资金
            if commit_client_object.flexible_cash < self.commit_price * self.commit_vol * Decimal(1 + TAX_RATE):
                print('CAN NOT AFFORD THE FROZEN CASH!')
                return False
        elif self.commit_direction == 'c':
            # 委托撤单，则必须有合理的委托，撤单即撤销该委托
            if self.commission_to_cancel is None:
                print('COMMISSION CANCELED IS NONE!')
                return False

        return True


def sim_add_commission(msg):
    """
    client成功提交了一个委托，且部分或全部没有被交易，将更新client的委托信息和相应股票的order book
    :param msg:委托的相关信息，是一个CommissionMsg类
    """
    assert isinstance(msg, SimCommissionMsg)
    assert msg.confirmed is True
    principle = msg.commit_client
    stock_symbol = msg.stock_symbol
    market  = SimMarket.objects.get(id=1)

    order_book_entry, created = SimOrderBookEntry.objects.get_or_create(stock_symbol=stock_symbol,
                                                                        entry_price=msg.commit_price,
                                                                        entry_direction=msg.commit_direction)

    order_book_entry.total_vol += msg.commit_vol
    order_book_entry.save(update_fields=['total_vol'])
    new_order_book_element = SimOrderBookElem.objects.create(entry_belonged=order_book_entry.id,
                                                             client=principle,
                                                             direction_committed=msg.commit_direction,
                                                             price_committed=msg.commit_price,
                                                             vol_committed=msg.commit_vol,
                                                             date_committed=market.datetime)

    SimCommissionElem.objects.create(owner=principle, stock_symbol=stock_symbol, operation=msg.commit_direction,
                                     price_committed=msg.commit_price, vol_committed=msg.commit_vol,
                                     date_committed=market.datetime, unique_id=new_order_book_element.unique_id)

    if msg.commit_direction == 'a':
        # 卖出委托
        holding = SimHoldingElem.objects.get(owner=principle, stock_symbol=stock_symbol)
        assert msg.commit_vol <= holding.available_vol
        holding.frozen_vol += msg.commit_vol
        holding.available_vol -= msg.commit_vol
        holding.save(update_fields=['frozen_vol', 'available_vol'])

    elif msg.commit_direction == 'b':
        # 买入委托
        principle_object = BaseClient.objects.get(id=principle)
        freeze = float(msg.commit_price * msg.commit_vol)
        assert freeze <= principle_object.flexible_cash
        principle_object.frozen_cash += freeze
        principle_object.flexible_cash -= freeze
        principle_object.save(update_fields=['frozen_cash', 'flexible_cash'])

    return True


def sim_order_book_matching(commission):
    """
    将client给出的委托信息与order book中所有order进行撮合交易
    """
    assert isinstance(commission, SimCommissionMsg)
    assert commission.confirmed is False

    stock_symbol = commission.stock_symbol
    stock_object = SimStock.objects.get(symbol=stock_symbol)
    direction = commission.commit_direction
    remaining_vol = commission.commit_vol
    market = SimMarket.objects.get(id=1)

    if direction == 'a':
        # 卖出委托
        matching_direction = 'b'
        while not stock_object.is_order_book_empty(matching_direction):
            best_element = stock_object.get_best_element(matching_direction)
            if best_element.price_committed < commission.commit_price:
                # 价格不符合要求，结束撮合
                break
            if remaining_vol == 0:
                # 交易量达成要求，结束撮合
                break
            if remaining_vol >= best_element.vol_committed:
                # 交易发生，order book中的此条挂单被完全交易
                trade_message = SimTradeMsg(stock_symbol=stock_symbol, initiator=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=best_element.vol_committed, acceptor=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=market.datetime, trade_tick=market.tick)

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并删除order book中的挂单
                stock_object.trading_behaviour(direction, best_element.price_committed, best_element.vol_committed,
                                               trade_message.trade_date, trade_message.trade_tick)
                remaining_vol -= best_element.vol_committed
                best_entry = SimOrderBookEntry.objects.get(id=best_element.entry_belonged)
                best_entry.total_vol -= best_element.vol_committed
                if best_entry.total_vol == 0:
                    best_entry.delete()
                else:
                    best_entry.save(update_fields=['total_vol'])

                best_element.delete()

            else:
                # 交易发生，order book中的此条挂单被部分交易
                trade_message = SimTradeMsg(stock_symbol=stock_symbol, initiator=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=remaining_vol, acceptor=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=market.datetime, trade_tick=market.tick)

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并调整order book中的挂单
                stock_object.trading_behaviour(direction, best_element.price_committed, remaining_vol,
                                               trade_message.trade_date, trade_message.trade_tick)
                best_element.vol_committed -= remaining_vol
                best_entry = SimOrderBookEntry.objects.get(id=best_element.entry_belonged)
                best_entry.total_vol -= remaining_vol
                remaining_vol = 0
                best_element.save(update_fields=['vol_committed'])
                best_entry.save(update_fields=['total_vol'])

    elif direction == 'b':
        # 买入委托
        matching_direction = 'a'
        while not stock_object.is_order_book_empty(matching_direction):
            best_element = stock_object.get_best_element(matching_direction)
            if best_element.price_committed > commission.commit_price:
                # 价格不符合要求，结束撮合
                break
            if remaining_vol == 0:
                # 交易量达成要求，结束撮合
                break
            if remaining_vol >= best_element.vol_committed:
                # 交易发生，order book中的此条挂单被完全交易
                trade_message = SimTradeMsg(stock_symbol=stock_symbol, initiator=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=best_element.vol_committed, acceptor=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=market.datetime, trade_tick=market.tick)

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并删除order book中的挂单
                stock_object.trading_behaviour(direction, best_element.price_committed, best_element.vol_committed,
                                               trade_message.trade_date, trade_message.trade_tick)
                remaining_vol -= best_element.vol_committed
                best_entry = SimOrderBookEntry.objects.get(id=best_element.entry_belonged)
                best_entry.total_vol -= best_element.vol_committed
                if best_entry.total_vol == 0:
                    best_entry.delete()
                else:
                    best_entry.save(update_fields=['total_vol'])

                best_element.delete()

            else:
                # 交易发生，order book中的此条挂单被部分交易
                trade_message = SimTradeMsg(stock_symbol=stock_object.symbol, initiator=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=remaining_vol, acceptor=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=market.datetime, trade_tick=market.tick)

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并调整order book中的挂单
                stock_object.trading_behaviour(direction, best_element.price_committed, remaining_vol,
                                               trade_message.trade_date, trade_message.trade_tick)
                best_element.vol_committed -= remaining_vol
                best_entry = SimOrderBookEntry.objects.get(id=best_element.entry_belonged)
                best_entry.total_vol -= remaining_vol
                remaining_vol = 0
                best_element.save(update_fields=['vol_committed'])
                best_entry.save(update_fields=['total_vol'])

    elif direction == 'c':
        # 撤单
        assert commission.commission_to_cancel is not None
        order_book_element_corr = SimOrderBookElem.objects.get(unique_id=commission.commission_to_cancel)
        try:
            assert commission.commit_client == order_book_element_corr.client
            assert commission.commit_vol <= order_book_element_corr.vol_committed  # 委托撤单的数量
            order_book_entry = SimOrderBookEntry.objects.get(id=order_book_element_corr.entry_belonged)
            order_book_entry.total_vol -= commission.commit_vol

            order_book_element_corr.vol_committed -= commission.commit_vol
            if order_book_element_corr.vol_committed == 0:
                order_book_element_corr.delete()
            else:
                order_book_element_corr.save(update_fields=['vol_committed'])

            if order_book_entry.total_vol == 0:
                order_book_entry.delete()
            else:
                order_book_entry.save(update_fields=['total_vol'])

            # 确认撤单成功，删除委托信息，解除冻结
            origin_commission = SimCommissionElem.objects.get(unique_id=commission.commission_to_cancel)
            if origin_commission.operation == 'a':
                holding = SimHoldingElem.objects.get(owner=commission.commit_client, stock_symbol=stock_symbol)
                holding.frozen_vol -= commission.commit_vol
                holding.available_vol += commission.commit_vol
                holding.save(update_fields=['frozen_vol', 'available_vol'])
            else:
                assert origin_commission.operation == 'b'
                freeze = float(commission.commit_price * commission.commit_vol)
                client_object = BaseClient.objects.get(id=commission.commit_client)
                client_object.frozen_cash -= freeze
                client_object.flexible_cash += freeze
                client_object.save(update_fields=['frozen_cash', 'flexible_cash'])
            origin_commission.vol_committed -= commission.commit_vol
            if origin_commission.vol_traded == origin_commission.vol_committed:
                origin_commission.delete()
            else:
                origin_commission.save(update_fields=['vol_committed'])

        except AssertionError:
            print("撤单失败！")

        commission.confirmed = True
        commission.save()
        return True

    else:
        raise ValueError

    if remaining_vol > 0:
        # 市场上所有的挂单都不够买/卖，或不符合交易条件
        commission.commit_vol = remaining_vol
        commission.confirmed = True
        ok = sim_add_commission(commission)
        assert ok
    else:
        commission.confirmed = True

    return True


def sim_commission_handler(new_commission, handle_info=False):
    """
    委托的处理函数，如果接受的委托message合法，则根据处理情况，在数据库中建立委托项/加入order book/建立成交记录
    :param new_commission:新收到的委托信息
    :param handle_info:是否打印委托信息
    """
    time0 = time.time()
    assert isinstance(new_commission, SimCommissionMsg)
    if not new_commission.is_valid():
        return False

    sim_order_book_matching(new_commission)

    assert new_commission.confirmed
    time1 = time.time()
    if handle_info:
        print('Commission Handled: symbol-{} {} price-{} vol-{}, Cost {} s.'.format(new_commission.stock_symbol,
                                                                                    new_commission.commit_direction,
                                                                                    new_commission.commit_price,
                                                                                    new_commission.commit_vol,
                                                                                    time1 - time0))
    return True




