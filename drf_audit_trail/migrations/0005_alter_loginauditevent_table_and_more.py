# Generated by Django 4.2.6 on 2024-09-22 18:01

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('drf_audit_trail', '0004_processauditevent_stepauditevent_and_more'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='loginauditevent',
            table=None,
        ),
        migrations.AlterModelTable(
            name='processauditevent',
            table=None,
        ),
        migrations.AlterModelTable(
            name='registrationauditevent',
            table=None,
        ),
        migrations.AlterModelTable(
            name='requestauditevent',
            table=None,
        ),
        migrations.AlterModelTable(
            name='stepauditevent',
            table=None,
        ),
    ]
