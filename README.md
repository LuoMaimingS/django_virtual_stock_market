# django_virtual_stock_market
使用django框架的虚拟股市环境

## 环境依赖（非部署）

* python3
* django
* bootstrap3

## 配置

首先，进入根目录，迁移数据库

```
$ python manage.py makemigrations
$ python manage.py migrate
```

接着，注册自己的超级用户，填写用户名、邮箱（可不填）、密码

```
$ python manage.py createsuperuser
```

将股票数据（h5格式）放到market/data/目录下

## 运行

进入根目录

```
$ python manage.py runserver
```

点击右上角的登陆，以自己创建的超级用户登陆，然后

* 导入股票数据
* 切入
* 编写主程序并运行

## 使用gail

* 保证data下有对应的原始股票数据，并导入至该环境
* 在股市模拟中运行，先生成专家数据，再设置参数运行

