from django.db import models
from django.db.models import Max, Min
import uuid
from decimal import Decimal

from .clients import BaseClient
from .sim_market import SimMarket
from .sim_clients import SimHoldingElem, SimCommissionElem, SimTransactionElem
from .sim_stocks import SimStock, SimOrderBook, SimOrderBookEntry, SimOrderBookElem
from .config import *


class SimTradeMsg(models.Model):
    stock_symbol = models.CharField(max_length=12)
    initiator_client = models.ForeignKey(BaseClient, on_delete=models.CASCADE, related_name='sim_initiator')

    trade_direction = models.CharField(max_length=1)
    trade_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    trade_vol = models.IntegerField()
    trade_date = models.DateTimeField(blank=False)
    trade_tick = models.IntegerField(blank=False)

    # 被交易的挂单的ID
    commission_id = models.UUIDField(blank=False, default=uuid.uuid4)
    trade_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    counterpart = models.ForeignKey(BaseClient, on_delete=models.CASCADE, related_name='sim_acceptor')
    tax_charged = models.FloatField(default=0)


def sim_instant_trade(msg):
    """
    client的委托立刻得到了交易，从而不会出现在委托记录中
    :param msg: 交易的相关信息，是一个TradeMsg类
    """
    initiator = msg.initiator_client
    stock_symbol = msg.stock_symbol

    stock_corr = SimStock.objects.get(symbol=stock_symbol)
    new_transaction = SimTransactionElem(owner=initiator, stock_corr=stock_corr, stock_symbol=stock_symbol,
                                         price_traded=msg.trade_price, vol_traded=msg.trade_vol,
                                         counterpart=msg.counterpart, date_traded=msg.trade_date)
    new_transaction.save()
    new_transaction.unique_id = msg.trade_id
    new_transaction.save()

    if msg.trade_direction == 'a':
        # 卖出
        hold_element = initiator.simholdingelem_set.get(stock_symbol=stock_symbol)
        available_shares = hold_element.available_vol
        assert available_shares >= msg.trade_vol
        hold_element.available_vol -= msg.trade_vol
        hold_element.vol -= msg.trade_vol
        if hold_element.vol == 0:
            # 目前为止已全部卖出，不再持有，删除该条数据
            hold_element.delete()
        else:
            hold_element.save()

        earning = float(msg.trade_price * msg.trade_vol - msg.tax_charged)
        initiator.cash += earning
        initiator.flexible_cash += earning

    elif msg.trade_direction == 'b':
        # 买入
        new_holding, cflag = SimHoldingElem.objects.get_or_create(owner=initiator, stock_corr=stock_corr,
                                                                  stock_symbol=stock_symbol, stock_name=stock_corr.name)
        if cflag:
            # 创建了新的对象，即买入新的股票
            new_holding.vol = msg.trade_vol
            new_holding.frozen_vol = 0
            new_holding.available_vol = msg.trade_vol
            new_holding.cost = msg.trade_price
            new_holding.price_guaranteed = msg.trade_price
            new_holding.last_price = stock_corr.last_price
            new_holding.profit = - msg.tax_charged
            new_holding.value = stock_corr.last_price * new_holding.vol
            new_holding.date_bought = msg.trade_date
        else:
            # 之前本就持有该股票
            new_holding.cost = (new_holding.cost * new_holding.vol + msg.trade_price * msg.trade_vol) / \
                               (new_holding.vol + msg.trade_vol)
            new_holding.price_guaranteed = new_holding.cost
            new_holding.last_price = stock_corr.last_price
            new_holding.vol += msg.trade_vol
            new_holding.available_vol += msg.trade_vol
            new_holding.profit -= msg.tax_charged
            new_holding.value = stock_corr.last_price * new_holding.vol
        new_holding.save()

        spending = float(msg.trade_price * msg.trade_vol + msg.tax_charged)
        initiator.cash -= spending
        initiator.flexible_cash -= spending

    initiator.save()
    return True


def sim_delayed_trade(msg):
    """
    client的委托记录中的委托得到了交易，从而改变委托情况
    :param msg: 交易的相关信息，是一个TradeMsg类
    """
    assert isinstance(msg, SimTradeMsg)
    acceptor = msg.counterpart
    stock_symbol = msg.stock_symbol
    if msg.trade_direction == 'a':
        acceptor_direction = 'b'
    else:
        acceptor_direction = 'a'

    stock_corr = SimStock.objects.get(symbol=stock_symbol)
    new_transaction = SimTransactionElem(owner=acceptor, stock_corr=stock_corr, stock_symbol=stock_symbol,
                                         stock_name=stock_corr.name, operation=acceptor_direction,
                                         price_traded=msg.trade_price, vol_traded=msg.trade_vol,
                                         counterpart=msg.initiator_client, date_traded=msg.trade_date)
    new_transaction.save()
    new_transaction.unique_id = msg.trade_id
    new_transaction.save()

    # 先处理委托
    commission_element = acceptor.simcommissionelem_set.get(unique_id=msg.commission_id)
    assert commission_element.stock_symbol == msg.stock_symbol
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
        commission_element.save()

    if acceptor_direction == 'a':
        # 卖出，处理持仓
        hold_element = acceptor.simholdingelem_set.get(stock_symbol=stock_symbol)
        frozen_shares = hold_element.frozen_vol
        assert frozen_shares >= msg.trade_vol
        hold_element.frozen_vol -= msg.trade_vol
        hold_element.vol -= msg.trade_vol
        if hold_element.vol == 0:
            # 该持有的股票目前为止已全部卖出，不再持有，删除该条数据
            hold_element.delete()
        else:
            hold_element.save()

        # 结算收益，成交金额减去收益
        earning = float(msg.trade_price * msg.trade_vol - msg.tax_charged)
        acceptor.cash += earning
        acceptor.flexible_cash += earning

    elif acceptor_direction == 'b':
        # 买入，建仓
        new_holding, cflag = SimHoldingElem.objects.get_or_create(owner=acceptor, stock_corr=stock_corr,
                                                               stock_symbol=stock_symbol, stock_name=stock_corr.name)
        if cflag:
            # 创建了新的对象，即买入新的股票
            new_holding.vol = msg.trade_vol
            new_holding.frozen_vol = 0
            new_holding.available_vol = msg.trade_vol
            new_holding.cost = msg.trade_price
            new_holding.price_guaranteed = msg.trade_price
            new_holding.last_price = stock_corr.last_price
            new_holding.profit = - msg.tax_charged
            new_holding.value = stock_corr.last_price * new_holding.vol
            new_holding.date_bought = msg.trade_date
        else:
            # 之前本就持有该股票
            new_holding.cost = (new_holding.cost * new_holding.vol + msg.trade_price * msg.trade_vol) / \
                               (new_holding.vol + msg.trade_vol)
            new_holding.price_guaranteed = new_holding.cost
            new_holding.last_price = stock_corr.last_price
            new_holding.vol += msg.trade_vol
            new_holding.available_vol += msg.trade_vol
            new_holding.profit -= msg.tax_charged
            new_holding.value = stock_corr.last_price * new_holding.vol

        new_holding.save()

        # 结算交易成本，扣除冻结资金和资金余额
        spending = float(msg.trade_price * msg.trade_vol + msg.tax_charged)
        acceptor.cash -= spending
        acceptor.frozen_cash -= spending

    acceptor.save()
    return True


class SimCommissionMsg(models.Model):
    stock_symbol = models.CharField(max_length=12)
    commit_client = models.ForeignKey(BaseClient, on_delete=models.CASCADE, related_name='sim_principle')

    commit_direction = models.CharField(max_length=1, default='b')
    commit_price = models.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0)
    commit_vol = models.IntegerField(default=0)
    commit_date = models.DateTimeField(blank=True, default=None)

    # used for cancel a commission
    cancel_cms = models.ForeignKey(SimCommissionElem, on_delete=models.CASCADE, blank=True, null=True, default=None)

    # Confirm the commission
    confirmed = models.BooleanField(default=False)

    def is_valid(self):
        """
        判断委托信息是否合法
        :return: 合法则返回True
        """
        if not SimStock.objects.filter(symbol=self.stock_symbol).exists():
            # 委托的股票标的不存在
            return False
        else:
            stock_corr = SimStock.objects.get(symbol=self.stock_symbol)
        if self.commit_price > stock_corr.limit_up or self.commit_price < stock_corr.limit_down:
            # 委托价格，需要在涨跌停价之间
            return False
        if self.commit_direction not in ['a', 'b', 'c']:
            # 委托方向，需要是买/卖/撤，三者其一
            return False

        if self.commit_direction == 'a':
            # 委卖，则委托的股票必须有合理的持仓和充足的可用余额
            if not SimHoldingElem.objects.filter(owner=self.commit_client, stock_symbol=self.stock_symbol).exists():
                return False
            holding_element = SimHoldingElem.objects.get(owner=self.commit_client, stock_symbol=self.stock_symbol)
            if holding_element.available_vol < self.commit_vol:
                return False
        elif self.commit_direction == 'b':
            # 委买，则必须有充足的可用余额，能够负担税费的冻结资金
            if self.commit_client.flexible_cash < self.commit_price * self.commit_vol * Decimal(1 + TAX_RATE):
                return False
        elif self.commit_direction == 'c':
            # 委托撤单，则必须有合理的委托，撤单即撤销该委托
            if self.cancel_cms is None:
                return False

        return True


def sim_add_commission(msg):
    """
    client成功提交了一个委托，且部分或全部没有被交易，将更新client的委托信息和相应股票的order book
    :param msg:委托的相关信息，是一个CommissionMsg类
    """
    assert isinstance(msg, SimCommissionMsg)
    assert msg.is_valid()
    assert msg.confirmed is True
    principle = msg.commit_client
    stock_symbol = msg.stock_symbol

    stock_corr = SimStock.objects.get(symbol=stock_symbol)
    order_book = SimOrderBook.objects.get(stock=stock_corr)
    order_book_entry, created = order_book.simorderbookentry_set.get_or_create(order_book=order_book,
                                                                               entry_price=msg.commit_price,
                                                                               entry_direction=msg.commit_direction)
    if created:
        order_book_entry.total_vol = msg.commit_vol
    else:
        order_book_entry.total_vol += msg.commit_vol
    order_book_entry.save()
    new_order_book_element = SimOrderBookElem(order_book_entry=order_book_entry, client=msg.commit_client,
                                              direction_committed=msg.commit_direction, price_committed=msg.commit_price,
                                              vol_committed=msg.commit_vol, date_committed=SimMarket.datetime)
    new_order_book_element.save()

    new_commission = SimCommissionElem(owner=principle, stock_corr=stock_corr, stock_symbol=stock_symbol,
                                       stock_name=stock_corr.name, operation=msg.commit_direction,
                                       price_committed=msg.commit_price, vol_committed=msg.commit_vol,
                                       date_committed=new_order_book_element.date_committed,
                                       unique_id=new_order_book_element.unique_id)
    new_commission.save()

    if msg.commit_direction == 'a':
        # 卖出委托
        holding = principle.simholdingelem_set.get(stock_symbol=stock_symbol)
        assert msg.commit_vol <= holding.available_vol
        holding.frozen_vol += msg.commit_vol
        holding.available_vol -= msg.commit_vol
        holding.save()

    elif msg.commit_direction == 'b':
        # 买入委托
        freeze = float(msg.commit_price * msg.commit_vol)
        assert freeze <= principle.flexible_cash
        principle.frozen_cash += freeze
        principle.flexible_cash -= freeze
        principle.save()

    return True


def sim_order_book_matching(commission):
    """
    将client给出的委托信息与order book中所有order进行撮合交易
    """
    assert isinstance(commission, SimCommissionMsg)
    assert commission.is_valid()
    assert commission.confirmed is False

    stock_corr = SimStock.objects.get(symbol=commission.stock_symbol)
    direction = commission.commit_direction
    remaining_vol = commission.commit_vol

    if direction == 'a':
        # 卖出委托
        matching_direction = 'b'
        order_book, _ = SimOrderBook.objects.get_or_create(stock=stock_corr)
        while not order_book.is_empty(matching_direction):
            best_element = order_book.get_best_element(matching_direction)
            if best_element.price_committed < commission.commit_price:
                # 价格不符合要求，结束撮合
                break
            if remaining_vol == 0:
                # 交易量达成要求，结束撮合
                break
            if remaining_vol >= best_element.vol_committed:
                # 交易发生，order book中的此条挂单被完全交易
                trade_message = SimTradeMsg(stock_symbol=stock_corr.symbol, initiator_client=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=best_element.vol_committed, counterpart=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=SimMarket.datetime, trade_tick=SimMarket.tick)
                trade_message.save()

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并删除order book中的挂单
                stock_corr.trading_behaviour(direction, best_element.price_committed, best_element.vol_committed,
                                             trade_message.trade_date, trade_message.trade_tick)
                remaining_vol -= best_element.vol_committed
                best_entry = best_element.order_book_entry
                best_entry.total_vol -= best_element.vol_committed
                best_entry.save(update_fields=['total_vol'])

                best_element.delete()
                if best_entry.total_vol == 0:
                    best_entry.delete()

            else:
                # 交易发生，order book中的此条挂单被部分交易
                trade_message = SimTradeMsg(stock_symbol=stock_corr.symbol, initiator_client=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=remaining_vol, counterpart=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=SimMarket.datetime, trade_tick=SimMarket.tick)
                trade_message.save()

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并调整order book中的挂单
                stock_corr.trading_behaviour(direction, best_element.price_committed, remaining_vol,
                                             trade_message.trade_date, trade_message.trade_tick)
                best_element.vol_committed -= remaining_vol
                best_entry = best_element.order_book_entry
                best_entry.total_vol -= remaining_vol
                remaining_vol = 0
                best_element.save()
                best_entry.save()

    elif direction == 'b':
        # 买入委托
        matching_direction = 'a'
        order_book = SimOrderBook.objects.get(stock=stock_corr)
        while not order_book.is_empty(matching_direction):
            best_element = order_book.get_best_element(matching_direction)
            if best_element.price_committed > commission.commit_price:
                # 价格不符合要求，结束撮合
                break
            if remaining_vol == 0:
                # 交易量达成要求，结束撮合
                break
            if remaining_vol >= best_element.vol_committed:
                # 交易发生，order book中的此条挂单被完全交易
                trade_message = SimTradeMsg(stock_symbol=stock_corr.symbol, initiator_client=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=best_element.vol_committed, counterpart=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=SimMarket.datetime, trade_tick=SimMarket.tick)
                trade_message.save()

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并删除order book中的挂单
                stock_corr.trading_behaviour(direction, best_element.price_committed, best_element.vol_committed,
                                             trade_message.trade_date, trade_message.trade_tick)
                remaining_vol -= best_element.vol_committed
                best_entry = best_element.order_book_entry
                best_entry.total_vol -= best_element.vol_committed
                best_entry.save()

                best_element.delete()
                if best_entry.total_vol == 0:
                    best_entry.delete()

            else:
                # 交易发生，order book中的此条挂单被部分交易
                trade_message = SimTradeMsg(stock_symbol=stock_corr.symbol, initiator_client=commission.commit_client,
                                            trade_direction=direction, trade_price=best_element.price_committed,
                                            trade_vol=remaining_vol, counterpart=best_element.client,
                                            commission_id=best_element.unique_id, tax_charged=0,
                                            trade_date=SimMarket.datetime, trade_tick=SimMarket.tick)
                trade_message.save()

                # 这应当是并行的
                sim_instant_trade(trade_message)
                sim_delayed_trade(trade_message)

                # 记录交易，并调整order book中的挂单
                stock_corr.trading_behaviour(direction, best_element.price_committed, remaining_vol,
                                             trade_message.trade_date, trade_message.trade_tick)
                best_element.vol_committed -= remaining_vol
                best_entry = best_element.order_book_entry
                best_entry.total_vol -= remaining_vol
                remaining_vol = 0
                best_element.save()
                best_entry.save()

    elif direction == 'c':
        # 撤单
        assert commission.cancel_cms is not None
        order_book_element_corr = SimOrderBookElem.objects.get(unique_id=commission.cancel_cms.unique_id)
        try:
            assert commission.commit_date == order_book_element_corr.date_committed
            assert commission.commit_client == order_book_element_corr.client
            assert commission.commit_price == order_book_element_corr.price_committed
            assert commission.commit_vol == order_book_element_corr.vol_committed
            order_book_entry = order_book_element_corr.order_book_entry
            order_book_entry.total_vol -= commission.commit_vol

            order_book_element_corr.delete()
            if order_book_entry.total_vol == 0:
                order_book_entry.delete()

            # 确认撤单成功，删除委托信息，解除冻结
            if commission.cancel_cms.operation == 'a':
                holding = commission.commit_client.simholdingelem_set.get(stock_symbol=commission.stock_symbol)
                holding.frozen_vol -= commission.commit_vol
                holding.available_vol += commission.commit_vol
                holding.save()
            else:
                assert commission.cancel_cms.operation == 'b'
                freeze = float(commission.commit_price * commission.commit_vol)
                commission.commit_client.frozen_cash -= freeze
                commission.commit_client.flexible_cash += freeze
                commission.commit_client.save()
            commission.cancel_cms.delete()
            commission.cancel_cms = None

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
        commission.save()
        ok = sim_add_commission(commission)
        assert ok
    else:
        commission.confirmed = True
        commission.save()

    return True


def sim_commission_handler(new_commission):
    """
    委托的处理函数，如果接受的委托message合法，则根据处理情况，在数据库中建立委托项/加入order book/建立成交记录
    :param new_commission:新收到的委托信息
    """
    assert isinstance(new_commission, SimCommissionMsg)
    # 只有模拟的client才可以进行委托，真实的client不被允许
    assert new_commission.commit_client.driver is None
    if not new_commission.is_valid():
        return False
    sim_order_book_matching(new_commission)

    assert new_commission.confirmed
    new_commission.delete()
    return True




