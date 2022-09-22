# Generated by Django 4.0.3 on 2022-09-20 09:48

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0006_region_timezone'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservation',
            name='created',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='reservation',
            name='updated',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='reservation',
            name='status',
            field=models.IntegerField(choices=[(0, 'Отказано'), (1, 'Зарезирвировано'), (2, 'В очереди'), (3, 'На приеме'), (4, 'Не пришел'), (5, 'Все ок'), (6, 'Подтвержден')], default=1, verbose_name='Статус'),
        ),
    ]