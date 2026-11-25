"""Stage 6: overlength comes from the configured table, with the workbook bands and values."""
import importlib
import logging
from decimal import Decimal as D

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.freight.services.calculator import (
    FreightCalculatorService, OverlengthNotConfigured, overlength_fee,
)
from apps.freight.services.dtos import FreightLine, FreightRequest
from apps.imports.services import ratecard_compare as compare
from apps.imports.services import ratecard_validate as validate
from apps.rates.models import CarrierOverlengthBreak, FreightRate, FreightZone

migration = importlib.import_module('apps.rates.migrations.0003_carrier_overlength_break')
# SettingFlags!C22:D29 with BrokerTotals!BF19:BJ19; each band ends where the next one starts.
EXPECTED = ((0, 2.5, 0), (2.5, 3.7, 60), (3.7, 6, 170), (6, 7.3, 240), (7.3, None, 850))
FEES = (('0', '0'), ('2.499', '0'), ('2.5', '60'), ('3.699', '60'), ('3.7', '170'), ('5.99', '170'),
        ('5.995', '170'), ('6', '240'), ('7.299', '240'), ('7.3', '850'), ('12', '850'))


def seed(client, carrier):
    for tier, start, end, charge in migration.BANDS:
        CarrierOverlengthBreak.objects.create(client=client, carrier=carrier, tier=tier, length_from_m=D(start),
                                              length_to_m=D(end) if end else None, charge=D(charge))


class SeedValuesTests(SimpleTestCase):
    def test_seed_is_the_workbook_table_without_gaps(self):
        bands = [(float(start), float(end) if end else None, float(charge))
                 for _, start, end, charge in migration.BANDS]
        self.assertEqual(bands, [(float(a), float(b) if b else None, float(c)) for a, b, c in EXPECTED])


class BandTests(TestCase):
    def setUp(self):
        self.client_row = Client.objects.create(code='STH', name='STH')
        self.carrier = Carrier.objects.create(code='TEAMEX')
        seed(self.client_row, self.carrier)

    def test_every_band_limit_and_former_gap(self):
        for length, charge in FEES:
            with self.subTest(length=length):
                self.assertEqual(overlength_fee(self.client_row, self.carrier, D(length)), D(charge))

    def test_a_changed_row_changes_the_fee(self):
        CarrierOverlengthBreak.objects.filter(tier=2).update(charge=D('75'))
        self.assertEqual(overlength_fee(self.client_row, self.carrier, D('3')), D('75'))

    def test_a_length_without_a_band_is_an_error_not_a_value(self):
        CarrierOverlengthBreak.objects.filter(tier=3).delete()
        with self.assertRaises(OverlengthNotConfigured):
            overlength_fee(self.client_row, self.carrier, D('4'))

    def test_another_carrier_has_no_table_of_its_own(self):
        other = Carrier.objects.create(code='KTI')
        with self.assertRaises(OverlengthNotConfigured):
            overlength_fee(self.client_row, other, D('1'))

    def test_overlapping_band_is_refused(self):
        row = CarrierOverlengthBreak(client=self.client_row, carrier=self.carrier, tier=6,
                                     length_from_m=D('3'), length_to_m=D('4'), charge=D('1'))
        with self.assertRaisesMessage(ValidationError, 'overlaps band 2'):
            row.clean()

    def test_band_ending_before_its_start_is_refused(self):
        row = CarrierOverlengthBreak(client=self.client_row, carrier=self.carrier, tier=6,
                                     length_from_m=D('9'), length_to_m=D('8'), charge=D('1'))
        with self.assertRaisesMessage(ValidationError, 'greater than its start'):
            row.clean()

    def test_admin_registers_the_table(self):
        from django.contrib import admin
        self.assertIn(django_apps.get_model('rates', 'CarrierOverlengthBreak'), admin.site._registry)


class QuoteTests(TestCase):
    def setUp(self):
        self.client_row = Client.objects.create(code='STH', name='STH')
        self.carrier = Carrier.objects.create(code='TEAMEX')
        service = CarrierService.objects.create(carrier=self.carrier, service_code='ROAD')
        self.config = ClientCarrierConfig.objects.create(
            client=self.client_row, carrier_service=service, cubic_conversion=D('250'),
            overlength_enabled=True, fuel_levy=D('0.30'))
        FreightZone.objects.create(client=self.client_row, carrier_service=service, suburb='MELBOURNE',
                                   state='VIC', postcode='3000', zone='MEL')
        FreightRate.objects.create(client=self.client_row, carrier_service=service, zone='MEL', weight_break='1',
                                   freight_type='C', per_kg=D('1'))
        seed(self.client_row, self.carrier)

    def quote(self, length='3'):
        line = FreightLine(sku=None, quantity=D('1'), freight_type='C', length_m=D(length), width_m=D('1'),
                           height_m=D('1'), weight_kg=D('100'), cubic_m3=D('0.001'))
        request = FreightRequest(client_code='STH', from_address_id=None, suburb='MELBOURNE', state='VIC',
                                 postcode='3000', tailgate=False, preselect_sku=False, lines=[line])
        return FreightCalculatorService().calculate(request)

    def test_fee_goes_into_the_total_without_fuel(self):
        result = self.quote()[0]
        self.assertEqual(result.details['overlength'], '60.00')
        self.assertEqual(result.details['fuel'], '30.00')
        self.assertEqual(result.estimate_ex_gst, D('190.00'))

    def test_switch_off_means_zero_with_or_without_rows(self):
        ClientCarrierConfig.objects.update(overlength_enabled=False)
        self.assertEqual(self.quote()[0].details['overlength'], '0.00')
        CarrierOverlengthBreak.objects.all().delete()
        self.assertEqual(self.quote()[0].details['overlength'], '0.00')

    def test_missing_row_drops_that_service_and_logs_it(self):
        CarrierOverlengthBreak.objects.all().delete()
        with self.assertLogs('apps.freight.services.calculator', logging.ERROR) as seen:
            self.assertEqual(self.quote(), [])
        self.assertIn('TEAMEX', seen.output[0])

    def test_engine_gets_the_same_fee_without_fuel(self):
        case = {'id': 'X', 'tailgate': False, 'lines': [{'sku': 'LONG', 'quantity': '1'}]}
        products = {'LONG': type('P', (), dict(sku='LONG', freight_type='C', length_m=D('3'), width_m=D('1'),
                                               height_m=D('1'), weight_kg=D('100'), cubic_m3=D('0.001')))}
        engine = {'carrier': 'TEAMEX', 'service': 'ROAD', 'status': 'COMPLETO', 'pending': [], 'reasons': [],
                  'freight': [], 'fuel': [{'amount': '30'}], 'extras': [], 'known_subtotal': '130', 'total': '130'}
        configs = compare.carrier_configs('STH')
        priced = compare.with_overlength([engine], case, 'STH', configs, products)[0]
        self.assertEqual(D(priced['total']), D('190'))
        self.assertEqual(priced['fuel'], [{'amount': '30'}])
        self.assertEqual(priced['extras'][0]['source'], compare.CONFIG_SOURCE)
        self.assertEqual(engine['extras'], [])

    def test_engine_without_a_row_has_no_total_and_no_assumed_value(self):
        CarrierOverlengthBreak.objects.all().delete()
        case = {'id': 'X', 'tailgate': False, 'lines': [{'sku': 'LONG', 'quantity': '1'}]}
        products = {'LONG': type('P', (), dict(sku='LONG', freight_type='C', length_m=D('3'), width_m=D('1'),
                                               height_m=D('1'), weight_kg=D('100'), cubic_m3=D('0.001')))}
        engine = {'carrier': 'TEAMEX', 'service': 'ROAD', 'status': 'COMPLETO', 'pending': [], 'reasons': [],
                  'freight': [], 'fuel': [], 'extras': [], 'known_subtotal': '130', 'total': '130'}
        priced = compare.with_overlength([engine], case, 'STH', compare.carrier_configs('STH'), products)[0]
        self.assertIsNone(priced['total'])
        self.assertEqual(priced['status'], 'PARCIAL')
        self.assertEqual(priced['pending'][0]['reason'], 'OVERLENGTH_SIN_CONFIGURACION')

    def test_recalculation_skips_the_configured_charge(self):
        engine = {'freight': [], 'fuel': [],
                  'extras': [{'row': None, 'amount': '60', 'source': compare.CONFIG_SOURCE}]}
        self.assertEqual(validate.check_charges(engine, {}, {}, {}, D('250')), (0, []))
