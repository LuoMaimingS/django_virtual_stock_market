"""
定义market的url模式
"""

from django.urls import path

from . import views

app_name = "market"
urlpatterns = [
    # 主页
    path('', views.index, name='index'),

    # 全部股票页面
    path('all_stocks/', views.all_stocks, name='all_stocks'),

    # 单支股票页面
    path('stocks/<int:stock_id>/', views.stock_detail, name='stock'),

    # 用户注册页面
    path('register/', views.register, name='register'),

    # 注册成功页面
    path('welcome/', views.welcome, name='welcome'),

    # 用户信息页面
    path('my_account/', views.account_view, name='my_account'),

    # 交易页面：买入
    path('my_account/bid', views.bid_view, name='bid'),
]
