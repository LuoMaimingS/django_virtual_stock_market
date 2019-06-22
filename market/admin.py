from django.contrib import admin

from .models import clients, stocks

admin.site.register(clients.BaseClient)
admin.site.register(clients.HoldingElem)
admin.site.register(clients.CommissionElem)
admin.site.register(clients.FocusElem)

admin.site.register(stocks.Stock)
admin.site.register(stocks.OrderBook)
admin.site.register(stocks.OrderBookEntry)
admin.site.register(stocks.OrderBookElem)


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
