"""Overlength table, seeded for STH and TEAMEX from the workbook.

Charges: SettingFlags!C22:D29. Limits: BrokerTotals!BF19:BJ19, without their gaps (contract stage 6, D3).
"""
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion

BANDS = (
    (1, '0', '2.5', '0'),
    (2, '2.5', '3.7', '60'),
    (3, '3.7', '6', '170'),
    (4, '6', '7.3', '240'),
    (5, '7.3', None, '850'),
)


def seed(apps, schema_editor):
    client = apps.get_model('clients', 'Client').objects.filter(code='STH').first()
    carrier = apps.get_model('carriers', 'Carrier').objects.filter(code='TEAMEX').first()
    if client is None or carrier is None:
        return  # Empty databases, such as the test one, have nothing to seed.
    table = apps.get_model('rates', 'CarrierOverlengthBreak')
    for tier, start, end, charge in BANDS:
        table.objects.create(client=client, carrier=carrier, tier=tier, length_from_m=Decimal(start),
                             length_to_m=Decimal(end) if end else None, charge=Decimal(charge))


class Migration(migrations.Migration):

    dependencies = [
        ('carriers', '0003_fuel_provenance'),
        ('clients', '0003_commercial_customer_sections'),
        ('rates', '0002_increase_freightrate_precision'),
    ]

    operations = [
        migrations.CreateModel(
            name='CarrierOverlengthBreak',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tier', models.PositiveSmallIntegerField()),
                ('length_from_m', models.DecimalField(decimal_places=3, max_digits=6)),
                ('length_to_m', models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True)),
                ('charge', models.DecimalField(decimal_places=4, max_digits=12)),
                ('carrier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='carriers.carrier')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='overlength_breaks', to='clients.client')),
            ],
            options={
                'ordering': ['client', 'carrier', 'length_from_m'],
                'unique_together': {('client', 'carrier', 'tier')},
            },
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
