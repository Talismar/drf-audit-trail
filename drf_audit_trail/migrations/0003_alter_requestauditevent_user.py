# Generated by Django 5.0.7 on 2024-08-05 22:50

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("drf_audit_trail", "0002_alter_loginauditevent_request"),
    ]

    operations = [
        migrations.AlterField(
            model_name="requestauditevent",
            name="user",
            field=models.CharField(
                blank=True, max_length=120, null=True, verbose_name="User identifier"
            ),
        ),
    ]
