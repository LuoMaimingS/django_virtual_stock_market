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

    # 全部虚拟客户页面
    path('simulator/all_v_clients', views.simulator_v_clients, name='sim_clients'),

    # 全部虚拟股票页面
    path('simulator/all_v_stocks', views.simulator_v_stocks, name='sim_stocks'),

    # 客户信息页面
    path('simulator/v_clients/<int:client_id>', views.simulator_client_detail, name='sim_client'),

    # 单支股票页面
    path('simulator/v_stocks/<int:stock_id>', views.simulator_stock_detail, name='sim_stock'),

    # 单支股票历史信息页面
    path('simulator/v_stocks/daily_info/<int:stock_id>', views.simulator_stock_daily, name='sim_stock_daily'),

    # 单支股票tick截面页面
    path('simulator/v_stocks/tick_info/<int:stock_id>', views.simulator_stock_tick, name='sim_stock_tick'),
    path('simulator/v_stocks/prev_tick_info/<int:stock_id>', views.simulator_stock_prev_tick, name='sim_stock_prev_tick'),
    path('simulator/v_stocks/next_tick_info/<int:stock_id>', views.simulator_stock_next_tick, name='sim_stock_next_tick'),

    # 重置股市模拟系统
    path('simulator/reset', views.simulator_reset, name='sim_reset'),

    # 重置全部数据
    path('simulator/reset_all', views.simulator_reset_all, name='sim_reset_all'),

    # 导入股票数据
    path('simulator/import_data', views.simulator_import_stock_data, name='sim_import'),

    # 切入股市历史截面
    path('simulator/anchor_in_time_point', views.anchor_in_time_point, name='sim_anchor'),

    # gail主页面
    path('gail/main', views.gail_main, name='gail_main'),

    # 生成gail专家数据页面
    path('gail/generate_expert_data', views.gail_generate_expert_data, name='gail_gen_expert_data'),

    # gail训练页面
    path('gail/train', views.gail_train, name='gail_train')
]
