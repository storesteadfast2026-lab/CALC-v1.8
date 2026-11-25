"""Stage 5: destinations, workbook consignments, a failing destination and no writes."""
import csv
import gzip
import hashlib
import tempfile
from decimal import Decimal as D
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.imports.services import ratecard_compare as compare
from apps.imports.services import ratecard_coverage as coverage
from apps.imports.services import ratecard_validate as validate
from apps.products.models import Product

FIXTURES = Path(__file__).parent / 'fixtures'
WORKBOOK_CASES = Path(settings.BASE_DIR) / 'apps/freight/fixtures/sth_excel_validated_cases_0629.1513.csv'
HEADER = 'index,index2,carrier,suburb,state,postcode,zone,subzone,area\n'
SIX = ('TEAMEX', 'KTI', 'TFMX', 'TEAMTAS', 'COCHRN', 'STEA')
ZONES = HEADER + ''.join(f'1,1,{name},MELBOURNE,VIC,3000,MELB,,\n' for name in SIX)
PRODUCTS = {'20772': ('70', '0.336'), '20985': ('280', '0.576'), 'SM460': ('2200', '4.782'),
            'SM460-A': ('2200', '4.351'), 'SMC30CABLED': ('2164', '14.43')}


class ShapeTests(SimpleTestCase):
    def test_every_consignment_comes_from_the_workbook_without_tailgate(self):
        chosen = coverage.shapes(compare.load_cases(WORKBOOK_CASES))
        self.assertEqual(len(chosen), 12)
        self.assertFalse(any(case['tailgate'] for case in chosen))

    def test_a_missing_case_stops(self):
        with self.assertRaisesMessage(validate.ValidateError, 'CASE_008'):
            coverage.shapes([])


class DestinationTests(SimpleTestCase):
    def content(self, rows):
        return (HEADER + rows).encode()

    def test_one_destination_per_suburb_and_state(self):
        rows = '1,1,TEAMEX,ADELAIDE,SA,5000,ADEL,,\n2,2,KTI,Adelaide,SA,5000,ADEL,,\n3,3,TFMX,ADELAIDE,NT,0800,X,,\n'
        self.assertEqual(coverage.destinations(self.content(rows)),
                         [('ADELAIDE', 'NT', '0800'), ('ADELAIDE', 'SA', '5000')])

    def test_other_carriers_are_left_out(self):
        self.assertEqual(coverage.destinations(self.content('1,1,IPEC,ADELAIDE,SA,5000,X,,\n')), [])

    def test_leading_zero_postcode_survives(self):
        rows = '1,1,TEAMEX,DARWIN,NT,0800,DARW,,\n'
        self.assertEqual(coverage.destinations(self.content(rows))[0][2], '0800')


class SweepTests(TestCase):
    def setUp(self):
        client = Client.objects.create(code='STH', name='Test client')
        for code, service_code in (('KTI', 'GENERAL'), ('TEAMEX', 'ROAD'), ('TFMX', 'ROAD'),
                                   ('TEAMTAS', 'GENERAL'), ('COCHRN', 'ROAD'), ('STEA', 'ROAD')):
            service = CarrierService.objects.create(carrier=Carrier.objects.create(code=code),
                                                    service_code=service_code)
            ClientCarrierConfig.objects.create(client=client, carrier_service=service, ratecard='1', base_status='L',
                                               active=True, pallet_enabled=True, cubic_conversion=D('250'))
        for sku, (weight, cubic) in PRODUCTS.items():
            Product.objects.create(client=client, sku=sku, weight_kg=D(weight), cubic_m3=D(cubic), freight_type='P',
                                   length_m=D('1'), width_m=D('1'), height_m=D('1'))

    def arguments(self, folder):
        files = {'rates': (FIXTURES / 'rates_sample.xls').read_bytes(), 'zones': ZONES.encode(),
                 'fuel': (FIXTURES / 'fuel_sample.xls').read_bytes()}
        arguments = {}
        for name, content in files.items():
            path = Path(folder) / ('rates_sample.xls' if name == 'rates' else f'{name}.bin')
            path.write_bytes(content)
            arguments[name] = str(path)
            arguments[f'{name}_sha256'] = hashlib.sha256(content).hexdigest()
        arguments['out_root'] = str(Path(folder) / 'out')
        return arguments

    def rows(self, run):
        with gzip.open(run / 'coverage.csv.gz', 'rt', encoding='utf-8', newline='') as handle:
            return list(csv.DictReader(handle))

    def test_every_consignment_and_service_gets_a_label(self):
        with tempfile.TemporaryDirectory() as folder:
            call_command('sweep_rate_routes', stdout=StringIO(), **self.arguments(folder))
            run = next((Path(folder) / 'out').iterdir())
            rows = self.rows(run)
            markdown = (run / 'coverage.md').read_text(encoding='utf-8')
        self.assertEqual(len(rows), 12 * 6)
        self.assertLessEqual({row['label'] for row in rows}, set(validate.LABELS))
        self.assertIn('Errores: 0', markdown)

    def test_a_failing_destination_is_counted_and_the_rest_continue(self):
        real = validate.route_rows
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise ValueError('broken row')
            return real(*args, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(validate, 'route_rows', flaky):
                call_command('sweep_rate_routes', stdout=StringIO(), **self.arguments(folder))
            run = next((Path(folder) / 'out').iterdir())
            rows = self.rows(run)
            markdown = (run / 'coverage.md').read_text(encoding='utf-8')
        self.assertEqual(len(rows), 11 * 6)
        self.assertIn('ValueError: broken row', markdown)

    def test_sweep_never_writes_to_the_database(self):
        with tempfile.TemporaryDirectory() as folder:
            with CaptureQueriesContext(connection) as queries:
                call_command('sweep_rate_routes', stdout=StringIO(), **self.arguments(folder))
        self.assertGreater(len(queries), 0)
        written = [item['sql'] for item in queries
                   if item['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(written, [])

    def test_wrong_hash_stops_before_creating_a_run(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            arguments['rates_sha256'] = '0' * 64
            with self.assertRaisesMessage(CommandError, 'does not match'):
                call_command('sweep_rate_routes', stdout=StringIO(), **arguments)
            self.assertFalse((Path(folder) / 'out').exists())


class IsolationTests(SimpleTestCase):
    def test_nothing_that_quotes_imports_the_coverage(self):
        root = Path(settings.BASE_DIR) / 'apps'
        allowed = {root / 'imports/services/ratecard_coverage.py',
                   root / 'imports/management/commands/sweep_rate_routes.py',
                   root / 'imports/tests/test_ratecard_coverage.py',
                   root / 'imports/tests/test_ratecard_walk.py',
                   root / 'imports/tests/test_ratecard_compare.py',
                   root / 'imports/tests/test_ratecard_validate.py'}
        for path in root.rglob('*.py'):
            if path not in allowed:
                self.assertNotIn('ratecard_coverage', path.read_text(encoding='utf-8', errors='ignore'), path)
