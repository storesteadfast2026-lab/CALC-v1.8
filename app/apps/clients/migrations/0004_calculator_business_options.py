from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('clients', '0003_commercial_customer_sections')]

    operations = [
        migrations.AddField(
            model_name='freightcalculator',
            name='custom_freight_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='freightcalculator',
            name='cubic_margin_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='freightcalculator',
            name='cubic_margin_options',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='freightcalculator',
            name='visible_history_days',
            field=models.PositiveSmallIntegerField(default=14),
        ),
    ]
