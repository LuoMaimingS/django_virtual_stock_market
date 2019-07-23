from django.contrib import admin

from .models import clients, stocks, sim_market, sim_clients, sim_stocks

admin.site.register(clients.BaseClient)
admin.site.register(clients.HoldingElem)
admin.site.register(clients.CommissionElem)
admin.site.register(clients.TransactionElem)
admin.site.register(clients.FocusElem)

admin.site.register(stocks.Stock)
admin.site.register(stocks.OrderBook)
admin.site.register(stocks.OrderBookEntry)
admin.site.register(stocks.OrderBookElem)
admin.site.register(stocks.TradeHistory)

# for simulator
admin.site.register(sim_market.SimMarket)
admin.site.register(sim_clients.SimHoldingElem)
admin.site.register(sim_clients.SimCommissionElem)
admin.site.register(sim_clients.SimTransactionElem)
admin.site.register(sim_stocks.SimStock)
admin.site.register(sim_stocks.SimOrderBookEntry)
admin.site.register(sim_stocks.SimOrderBookElem)
admin.site.register(sim_stocks.SimTradeHistory)
admin.site.register(sim_stocks.SimStockSlice)
admin.site.register(sim_stocks.SimStockDailyInfo)


class BaseClientAdmin(admin.ModelAdmin):
    list_display = ('driver', 'name', 'cash', 'status')
    list_filter = ('status', 'profit')

    fieldsets = (
        (None, {
            'fields': ('name', 'id')
        }),
        ('status', {
            'fields': ('status', 'driver')
        }),
    )
