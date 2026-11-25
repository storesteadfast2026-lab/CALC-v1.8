"""Stage 3 comparison: classification, consignment equivalence, source guards and no writes."""
import hashlib
import json
import tempfile
from decimal import Decimal as D
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.freight.services.consolidator import consolidate_lines
from apps.imports.services import ratecard_compare as compare
from apps.products.models import Product
from apps.rates.models import FreightRate, FreightZone

FIXTURES = Path(__file__).parent / 'fixtures'
HEADER = 'index,index2,carrier,suburb,state,postcode,zone,subzone,area\n'
ALL_CARRIERS = ''.join(f'1,1,{name},MELBOURNE,VIC,3000,MELB,,\n'
                       for name in ('TEAMEX', 'KTI', 'TFMX', 'TEAMTAS', 'COCHRN', 'STEA'))
WORKBOOK_CASES = Path(settings.BASE_DIR) / 'apps/freight/fixtures/sth_excel_validated_cases_0629.1513.csv'
# Weight and cubic from the STH product table, sources of the 20 workbook cases.
PRODUCTS = {'20772': ('70', '0.336'), '20985': ('280', '0.576'), 'SM460': ('2200', '4.782'),
            'SM460-A': ('2200', '4.351'), 'SMC30CABLED': ('2164', '14.43')}


def products():
    return {sku: SimpleNamespace(sku=sku, freight_type='P', length_m=D('1'), width_m=D('1'), height_m=D('1'),
                                 weight_kg=D(weight), cubic_m3=D(cubic))
            for sku, (weight, cubic) in PRODUCTS.items()}


def engine(status='COMPLETO', freight='100', fuel='44', extras=None, fuel_rate='0.44', total='144',
           card=None, carrier='KTI', service='GENERAL'):
    line = {'card': 1, 'row': 2, 'break': 1, 'item': 1, 'name': 'x', 'amount': freight,
            'rate': '0.1', 'basic': '10', 'minimum': '20', **(card or {})}
    quoted = status not in compare.ENGINE_NO_QUOTE
    fuel_line = {'card': 2, 'row': 3, 'name': 'f', 'amount': fuel, 'rate': fuel_rate}
    return {'carrier': carrier, 'service': service, 'status': status, 'zone': 'MELB', 'reasons': [],
            'pending': [{'reason': 'X'}] if status == 'PARCIAL' else [], 'path': [1],
            'freight': [line] if quoted else [],
            'fuel': [fuel_line] if quoted else [],
            'extras': [{'card': 3, 'row': 4, 'name': 'e', 'amount': extras}] if extras else [],
            'known_subtotal': total if quoted else None,
            'total': None if status != 'COMPLETO' else total}


def app(freight='100', fuel='44', total='144', pallets='1'):
    return SimpleNamespace(estimate_ex_gst=D(total), details={
        'zone': 'MELB', 'freight_base': freight, 'fuel': fuel, 'chargeable_weight': '900',
        'pallets': pallets, 'cartons': '0', 'tailgate_fee': '0', 'hand_unload': '0', 'overlength': '0',
        'teamtas_general_fee': '0', 'remote': '0', 'offshore': '0', 'handling': '0'})


def config(levy='0.44', extra='0', uprate='0'):
    return SimpleNamespace(fuel_levy=D(levy), extra_surcharge=D(extra), uprate=D(uprate))


def rate(per_kg='0.1', basic='10', minimum='20', subsequent='0'):
    return SimpleNamespace(per_kg=D(per_kg), basic_charge=D(basic), minimum_charge=D(minimum),
                           per_subsequent_basic=D(subsequent), overweight_charge=D('0'))


class ClassificationTests(SimpleTestCase):
    def test_equal(self):
        row = compare.classify(engine(), app(), config(), rate())
        self.assertEqual(row['result'], compare.EQUAL)

    def test_one_cent_is_inside_the_tolerance_and_two_are_not(self):
        inside = compare.classify(engine(freight='100.01', total='144.01'), app(), config(), rate())
        outside = compare.classify(engine(freight='100.02', total='144.02'), app(), config(), rate())
        self.assertEqual(inside['components']['freight']['result'], compare.EQUAL)
        self.assertEqual(outside['components']['freight']['result'], compare.UNEXPLAINED)

    def test_neither_quoting_is_equal(self):
        row = compare.classify(engine('SIN_COTIZACION'), None, config(), None)
        self.assertEqual(row['result'], compare.EQUAL)

    def test_only_app_and_only_engine(self):
        self.assertEqual(compare.classify(engine('SIN_COTIZACION'), app(), config(), rate())['result'],
                         compare.ONLY_APP)
        self.assertEqual(compare.classify(engine('DESCONOCIDO'), app(), config(), rate())['result'],
                         compare.ONLY_APP)
        self.assertEqual(compare.classify(engine(), None, config(), None)['result'], compare.ONLY_ENGINE)

    def test_current_fuel_explains_the_fuel_gap(self):
        row = compare.classify(engine(), app(fuel='36.4', total='136.4'), config('0.364'), rate())
        self.assertEqual(row['result'], compare.EXPLAINED)
        self.assertEqual(row['components']['fuel']['causes'], [compare.CURRENT_FUEL])
        self.assertEqual(row['components']['total']['causes'], [compare.CURRENT_FUEL])

    def test_cochrn_surcharge_is_named_with_the_fuel_gap(self):
        row = compare.classify(engine(fuel='53', fuel_rate='0.53', total='153'),
                               app(fuel='35', total='135'), config('0.32', '0.03'), rate())
        self.assertEqual(row['components']['fuel']['causes'],
                         [compare.CURRENT_FUEL, compare.COCHRN_SURCHARGE])

    def test_current_rate_needs_the_app_formula_to_give_the_engine_amount(self):
        card = {'rate': '0.1', 'basic': '10', 'minimum': '20'}
        row = compare.classify(engine(freight='100', fuel='44', total='144', card=card),
                               app(freight='91', fuel='40.04', total='131.04'), config(),
                               rate(per_kg='0.09'))
        self.assertEqual(row['components']['freight']['causes'], [compare.CURRENT_RATE])

    def test_changed_rate_with_a_gap_it_does_not_explain_stays_unexplained(self):
        card = {'rate': '0.2', 'basic': '10', 'minimum': '20'}
        row = compare.classify(engine(card=card), app(freight='91', fuel='40.04', total='131.04'),
                               config(), rate(per_kg='0.09'))
        self.assertEqual(row['result'], compare.UNEXPLAINED)

    def test_same_rate_with_a_base_gap_stays_unexplained(self):
        row = compare.classify(engine(), app(freight='90', fuel='39.6', total='129.6'), config(), rate())
        self.assertEqual(row['components']['freight']['result'], compare.UNEXPLAINED)
        self.assertEqual(row['components']['total']['causes'], [])

    def test_uprate_needs_clean_components(self):
        row = compare.classify(engine(), app(total='158.4'), config(uprate='0.1'), rate())
        self.assertEqual(row['components']['total']['causes'], [compare.UPRATE])

    def test_rounding_is_named_on_the_total(self):
        row = compare.classify(engine(total='144.009'), app(total='144.02'), config(), rate())
        self.assertEqual(row['components']['total']['causes'], [compare.ROUNDING])

    def test_gap_above_the_rounding_limit_stays_unexplained(self):
        row = compare.classify(engine(total='144.00'), app(total='144.04'), config(), rate())
        self.assertEqual(row['components']['total']['result'], compare.UNEXPLAINED)

    def test_pending_total_is_not_comparable_and_never_zero(self):
        row = compare.classify(engine('PARCIAL'), app(), config(), rate())
        self.assertEqual(row['result'], compare.NOT_COMPARABLE)
        self.assertIsNone(row['components']['total']['difference'])
        self.assertIsNone(row['engine']['total'])

    def test_extras_gap_has_no_automatic_cause(self):
        row = compare.classify(engine(extras='10', total='154'), app(), config(), rate())
        self.assertEqual(row['components']['extras']['result'], compare.UNEXPLAINED)


class ConsignmentTests(SimpleTestCase):
    def test_all_twenty_workbook_cases_load(self):
        cases = compare.load_cases(WORKBOOK_CASES)
        self.assertEqual(len(cases), 20)
        self.assertEqual(cases[3]['lines'], [{'sku': 'SMC30CABLED', 'quantity': '1'},
                                             {'sku': 'SMC30CABLED', 'quantity': '4'}])
        self.assertEqual(cases[0]['postcode'], '3020')

    def test_totals_reproduce_the_workbook_in_all_twenty_cases(self):
        for case in compare.load_cases(WORKBOOK_CASES):
            done = compare.with_totals(case, products())
            self.assertEqual(D(done['weight']), D(case['planilla_weight']), case['id'])
            visible = D(done['cubic']) - done['pallets'] * D('0.02')
            self.assertEqual(visible, D(case['planilla_cubic']), case['id'])

    def test_quantity_does_not_multiply_the_cubic_as_the_workbook_shows(self):
        case = {'lines': [{'sku': 'SMC30CABLED', 'quantity': '2'}]}
        self.assertEqual(D(compare.with_totals(case, products())['cubic']), D('14.47'))

    def test_engine_and_app_receive_the_same_totals(self):
        case = {'lines': [{'sku': '20772', 'quantity': '4'}, {'sku': '20985', 'quantity': '2'}]}
        done = compare.with_totals(case, products())
        again = consolidate_lines(compare.freight_lines(case, products()), False)
        self.assertEqual((D(done['weight']), D(done['cubic']), done['pallets']),
                         (again.weight_total_kg, again.cubic_total_m3, again.pallet_count))


class ProductTests(TestCase):
    def test_missing_sku_stops_and_is_not_replaced(self):
        with self.assertRaisesMessage(compare.CompareError, 'NOPE'):
            compare.product_map([{'lines': [{'sku': 'NOPE', 'quantity': '1'}]}], 'STH')


class SourceGuardTests(SimpleTestCase):
    def test_excel_file_named_csv_is_refused(self):
        with self.assertRaisesMessage(compare.CompareError, 'Excel file'):
            compare.check_zones(compare.OLE2_MAGIC + b'\0' * 64)

    def test_missing_sth_carrier_is_refused(self):
        content = (HEADER + '1,1,COCHRN,ADELAIDE,SA,5000,S00,,\n').encode()
        with self.assertRaisesMessage(compare.CompareError, 'TEAMEX'):
            compare.check_zones(content)

    def test_all_carriers_pass(self):
        compare.check_zones((HEADER + ALL_CARRIERS).encode())


class TransLogicTests(SimpleTestCase):
    ROWS = (','.join(compare.TRANSLOGIC_COLUMNS) + '\n'
            'C01,KTI,GENERAL,2026-11-06 10:00,100,,,144,Trev,\n'
            'C01,TFMX,ROAD,2026-11-05 10:00,100,44,0,144,Trev,\n').encode()

    def report(self):
        return {'cases': [{'id': 'C01', 'rows': [
            {'carrier': 'KTI', 'service': 'GENERAL'}, {'carrier': 'TFMX', 'service': 'ROAD'},
            {'carrier': 'STEA', 'service': 'ROAD'}]}]}

    def test_empty_value_is_no_data_not_zero(self):
        rows = compare.read_translogic(self.ROWS)
        self.assertIsNone(rows[('C01', 'KTI', 'GENERAL')]['fuel'])

    def test_other_date_is_marked_and_absent_rows_stay_absent(self):
        report = self.report()
        compare.attach_translogic(report, compare.read_translogic(self.ROWS), '2026-11-06')
        kti, tfmx, stea = report['cases'][0]['rows']
        self.assertEqual(kti['translogic']['status'], 'MISMA_FECHA')
        self.assertEqual(tfmx['translogic']['status'], 'FECHA_DISTINTA')
        self.assertNotIn('translogic', stea)

    def test_wrong_columns_are_refused(self):
        with self.assertRaisesMessage(compare.CompareError, 'columns'):
            compare.read_translogic(b'a,b\n1,2\n')

    def test_bad_number_is_refused(self):
        with self.assertRaisesMessage(compare.CompareError, 'not a number'):
            compare.read_translogic(self.ROWS.replace(b',100,,,', b',abc,,,'))


class CommandTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(code='STH', name='Test client')
        carrier = Carrier.objects.create(code='KTI')
        service = CarrierService.objects.create(carrier=carrier, service_code='GENERAL')
        ClientCarrierConfig.objects.create(
            client=self.client_record, carrier_service=service, fuel_levy=D('0.429'), base_status='L',
            active=True, pallet_enabled=True, carton_enabled=True, zone_enabled=True,
            cubic_conversion=D('250'), ratecard='KTI')
        FreightZone.objects.create(client=self.client_record, carrier_service=service, suburb='MELBOURNE',
                                   state='VIC', postcode='3000', zone='MELB')
        FreightRate.objects.create(client=self.client_record, carrier_service=service, zone='MELB',
                                   freight_type='P', basic_charge=D('10'), per_kg=D('0.1'),
                                   minimum_charge=D('20'), source_row=7)
        Product.objects.create(client=self.client_record, sku='20772', weight_kg=D('70'), cubic_m3=D('0.336'),
                               freight_type='P', length_m=D('1.2'), width_m=D('0.8'), height_m=D('0.35'))

    def arguments(self, folder):
        files = {'rates': (FIXTURES / 'rates_sample.xls').read_bytes(),
                 'zones': (HEADER + ALL_CARRIERS).encode(),
                 'fuel': (FIXTURES / 'fuel_sample.xls').read_bytes()}
        arguments = {}
        for name, content in files.items():
            path = Path(folder) / ('rates_sample.xls' if name == 'rates' else f'{name}.bin')
            path.write_bytes(content)
            arguments[name] = str(path)
            arguments[f'{name}_sha256'] = hashlib.sha256(content).hexdigest()
        cases = Path(folder) / 'cases.json'
        cases.write_text(json.dumps([{'suburb': 'MELBOURNE', 'state': 'VIC', 'postcode': '3000',
                                      'tailgate': False, 'lines': [{'sku': '20772', 'quantity': '1'}]}]),
                         encoding='utf-8')
        arguments.update(cases=str(cases), out_root=str(Path(folder) / 'out'))
        return arguments

    def test_run_writes_the_report_and_copies_the_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            call_command('compare_rate_cards', stdout=StringIO(), **arguments)
            run = next((Path(folder) / 'out').iterdir())
            report = json.loads((run / 'compare.json').read_text(encoding='utf-8'))
            names = {path.name for path in run.iterdir()}
            markdown = (run / 'compare.md').read_text(encoding='utf-8')
        self.assertLessEqual({'rates_sample.xls', 'zones.bin', 'fuel.bin', 'cases.json'}, names)
        self.assertEqual(len(report['cases'][0]['rows']), 6)
        self.assertEqual(report['cases'][0]['id'], 'C01')
        self.assertEqual(sum(report['counts'].values()), 6)
        self.assertIn(arguments['rates_sha256'][:7], markdown)

    def test_run_never_writes_to_the_database(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            with CaptureQueriesContext(connection) as queries:
                call_command('compare_rate_cards', stdout=StringIO(), **arguments)
        self.assertGreater(len(queries), 0)
        written = [item['sql'] for item in queries
                   if item['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(written, [])

    def test_wrong_hash_stops_before_creating_a_run(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            arguments['fuel_sha256'] = '0' * 64
            with self.assertRaisesMessage(CommandError, 'does not match'):
                call_command('compare_rate_cards', stdout=StringIO(), **arguments)
            self.assertFalse((Path(folder) / 'out').exists())

    def test_translogic_needs_its_hash_and_date(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            with self.assertRaisesMessage(CommandError, '--translogic-sha256'):
                call_command('compare_rate_cards', stdout=StringIO(), translogic='x.csv', **arguments)


class IsolationTests(SimpleTestCase):
    def test_nothing_that_quotes_imports_the_comparison(self):
        root = Path(settings.BASE_DIR) / 'apps'
        allowed = {root / 'freight/tests/test_overlength.py',
                   root / 'imports/services/ratecard_compare.py',
                   root / 'imports/management/commands/compare_rate_cards.py',
                   root / 'imports/tests/test_ratecard_compare.py',
                   root / 'imports/services/ratecard_validate.py',
                   root / 'imports/management/commands/validate_rate_routes.py',
                   root / 'imports/tests/test_ratecard_validate.py',
                   root / 'imports/services/ratecard_coverage.py',
                   root / 'imports/management/commands/sweep_rate_routes.py',
                   root / 'imports/tests/test_ratecard_coverage.py'}
        for path in root.rglob('*.py'):
            if path not in allowed:
                self.assertNotIn('ratecard_compare', path.read_text(encoding='utf-8', errors='ignore'), path)

    def test_comparison_has_no_write_calls(self):
        for name in ('imports/services/ratecard_compare.py', 'imports/management/commands/compare_rate_cards.py'):
            source = (Path(settings.BASE_DIR) / 'apps' / name).read_text(encoding='utf-8')
            for word in ('.save(', '.delete(', '.update(', '.create(', '.bulk_create(', 'eval(', 'exec('):
                self.assertNotIn(word, source)
