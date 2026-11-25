from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.freight.services.calculator import (
    FreightCalculatorService, _teamex_weight_break, _tfmx_weight_break,
)
from apps.freight.services.dtos import FreightLine, FreightRequest
from apps.rates.models import FreightRate, FreightZone

TEAMEX_BANDS = [(1, '1'), (750, '1'), (751, '2'), (752, '2'), (1500, '2'), (1501, '3'), (1502, '3'),
                (2075, '3'), (3000, '3'), (3001, '4'), (3002, '4'), (5000, '4'), (5001, '5'),
                (5002, '5'), (20000, '5')]
TFMX_BANDS = [(1, '1'), (250, '1'), (251, '2'), (252, '2'), (750, '2'), (751, '3'), (752, '3'),
              (1500, '3'), (1501, '4'), (1502, '4'), (3000, '4'), (3001, '5'), (3002, '5'),
              (4999, '5'), (5000, '5'), (5001, '5'), (5002, '5'), (20000, '5')]


class WeightBandTests(SimpleTestCase):
    def test_teamex_bands_match_cards_1517_to_1521(self):
        for weight, expected in TEAMEX_BANDS:
            with self.subTest(weight=weight):
                self.assertEqual(_teamex_weight_break(Decimal(weight)), expected)

    def test_tfmx_bands_match_cards_1412_to_1416(self):
        for weight, expected in TFMX_BANDS:
            with self.subTest(weight=weight):
                self.assertEqual(_tfmx_weight_break(Decimal(weight)), expected)

    def test_no_whole_kilogram_is_left_without_a_band(self):
        for weight in range(1, 7001):
            with self.subTest(weight=weight):
                self.assertNotEqual(_teamex_weight_break(Decimal(weight)), '')
                self.assertNotEqual(_tfmx_weight_break(Decimal(weight)), '')


class QuotedWeightBandTests(TestCase):
    bands = {
        'TEAMEX': {'1': '1.000000', '2': '0.900000', '3': '0.800000', '4': '0.700000', '5': '0.600000'},
        'TFMX': {'1': '0.500000', '2': '0.400000', '3': '0.300000', '4': '0.200000', '5': '0.100000'},
    }

    def setUp(self):
        self.sth = Client.objects.create(code='STH', name='STH')
        for code, rates in self.bands.items():
            carrier = Carrier.objects.create(code=code)
            service = CarrierService.objects.create(carrier=carrier, service_code='ROAD')
            ClientCarrierConfig.objects.create(client=self.sth, carrier_service=service,
                                               cubic_conversion=Decimal('250'))
            FreightZone.objects.create(client=self.sth, carrier_service=service, suburb='MELBOURNE',
                                       state='VIC', postcode='3000', zone='MEL')
            for band, per_kg in rates.items():
                FreightRate.objects.create(client=self.sth, carrier_service=service, zone='MEL',
                                           weight_break=band, freight_type='C',
                                           per_kg=Decimal(per_kg))

    def quote(self, weight):
        line = FreightLine(sku=None, quantity=Decimal('1'), freight_type='C', length_m=Decimal('1'),
                           width_m=Decimal('1'), height_m=Decimal('1'), weight_kg=Decimal(weight),
                           cubic_m3=Decimal('0.001'))
        request = FreightRequest(client_code='STH', from_address_id=None, suburb='MELBOURNE',
                                 state='VIC', postcode='3000', tailgate=False, preselect_sku=False,
                                 lines=[line])
        return {result.carrier: result for result in FreightCalculatorService().calculate(request)}

    def test_carrier_quotes_on_previously_dropped_weights(self):
        for code, weights in (('TEAMEX', (751, 1501, 3001)), ('TFMX', (251, 751, 1501, 3001, 5000, 6000))):
            for weight in weights:
                with self.subTest(carrier=code, weight=weight):
                    self.assertIn(code, self.quote(weight))

    def test_recovered_weight_uses_the_rate_of_its_band(self):
        self.assertEqual(self.quote(751)['TEAMEX'].estimate_ex_gst, Decimal('675.90'))
        self.assertEqual(self.quote(3001)['TFMX'].estimate_ex_gst, Decimal('300.10'))
        self.assertEqual(self.quote(5000)['TFMX'].estimate_ex_gst, Decimal('500.00'))

    def test_amounts_outside_the_gaps_are_unchanged(self):
        expected = {('TEAMEX', 750): '750.00', ('TEAMEX', 752): '676.80', ('TEAMEX', 2075): '1660.00',
                    ('TEAMEX', 5001): '3000.60', ('TFMX', 250): '125.00', ('TFMX', 752): '225.60',
                    ('TFMX', 3002): '300.20', ('TFMX', 4999): '499.90'}
        for (code, weight), amount in expected.items():
            with self.subTest(carrier=code, weight=weight):
                self.assertEqual(self.quote(weight)[code].estimate_ex_gst, Decimal(amount))

    def test_tfmx_single_band_zone_stays_out_above_250_kg(self):
        """Approved exclusion: zones with only band 1 are not changed by this fix."""
        service = CarrierService.objects.get(carrier__code='TFMX')
        FreightRate.objects.filter(carrier_service=service).exclude(weight_break='1').delete()
        self.assertIn('TFMX', self.quote(250))
        self.assertNotIn('TFMX', self.quote(251))
        self.assertNotIn('TFMX', self.quote(6000))
