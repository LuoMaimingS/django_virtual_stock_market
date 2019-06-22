# Generated by Django 2.2.2 on 2019-06-22 08:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0006_auto_20190622_1557'),
    ]

    operations = [
        migrations.AddField(
            model_name='commissionelem',
            name='date_traded',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='commissionelem',
            name='opponent_traded',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='oppo_side', to='market.BaseClient'),
        ),
        migrations.AlterField(
            model_name='commissionelem',
            name='owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='self_side', to='market.BaseClient'),
        ),
    ]
