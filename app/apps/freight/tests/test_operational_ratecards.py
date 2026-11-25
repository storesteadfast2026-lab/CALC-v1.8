from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.freight.services.operational_ratecards import OperationalRateEngine
from apps.imports.services.ratecard_walk import NO_QUOTE, PARTIAL


class OperationalRateEngineQuoteTests(SimpleTestCase):
    def setUp(self):
        self.engine = object.__new__(OperationalRateEngine)
        self.engine.sources = object()
        self.cfg = SimpleNamespace(
            carrier_service=SimpleNamespace(
                carrier=SimpleNamespace(code='TEAMEX'),
                service_code='ROAD',
            ),
            hand_unload_enabled=False,
        )
        self.request = SimpleNamespace(
            suburb='ACTON', state='ACT', postcode='2601',
        )
        self.consolidated = SimpleNamespace(
            weight_total_kg=Decimal('300.5'),
            cubic_total_m3=Decimal('2.687'),
            pallet_count=Decimal('1'),
            carton_count=Decimal('0'),
            tailgate=False,
        )

    @patch('apps.freight.services.operational_ratecards.walk_case')
    def test_partial_path_returns_confirmed_subtotal_with_warning(self, walk_case):
        partial = {
            'status': PARTIAL,
            'total': None,
            'known_subtotal': Decimal('455.09184000'),
            'reasons': [],
            'pending': [{
                'name': 'Disaster Levy S/Chg',
                'reason': 'ZONE_TYPE_NOT_IN_ZONES_CSV',
            }],
        }
        walk_case.return_value = partial

        result, warning = self.engine.quote(self.cfg, self.request, self.consolidated)

        self.assertIs(result, partial)
        self.assertEqual(warning['status'], 'PARTIAL')
        self.assertIn('provisional operational estimate', warning['message'])
        self.assertIn('Disaster Levy S/Chg', warning['message'])
        self.assertIn('ZONE_TYPE_NOT_IN_ZONES_CSV', warning['message'])
        self.assertNotIn('No automatic quote was produced', warning['message'])

    @patch('apps.freight.services.operational_ratecards.walk_case')
    def test_no_zone_remains_warning_only(self, walk_case):
        walk_case.return_value = {
            'status': NO_QUOTE,
            'total': None,
            'known_subtotal': None,
            'reasons': ['NO_ZONE'],
            'pending': [],
        }

        result, warning = self.engine.quote(self.cfg, self.request, self.consolidated)

        self.assertIsNone(result)
        self.assertEqual(warning['status'], 'NO_QUOTE')
        self.assertIn('NO_ZONE', warning['message'])
        self.assertIn('No automatic quote was produced', warning['message'])
