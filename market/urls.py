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
    path('all_stocks', views.all_stocks, name='all_stocks'),

    # 单支股票页面
    path('stocks/<int:stock_id>', views.stock_detail, name='stock'),

    # 用户注册页面
    path('register', views.register, name='register'),

    # 注册成功页面
    path('welcome', views.welcome, name='welcome'),

    # 用户信息页面
    path('my_account', views.account_view, name='my_account'),

    # 交易页面
    path('my_account/commit', views.commit_view, name='commit'),

    # 撤销委托页面
    path('my_account/cancel', views.cancel_view, name='cancel'),


    # 股市模拟欢迎页面
    path('simulator/welcome', views.simulator_welcome, name='sim_welcome'),

    # 股市模拟主页面
    path('simulator/main', views.simulator_main, name='sim_main'),

    # 客户信息页面
    path('simulator/clients/<int:client_id>', views.simulator_client_detail, name='client'),

    # 全部虚拟股票页面
    path('simulator/all_v_stocks', views.all_v_stocks, name='all_v_stocks'),

    # 单支股票页面
    path('simulator/v_stocks/<int:stock_id>', views.sim_stock_detail, name='sim_stock'),
]
