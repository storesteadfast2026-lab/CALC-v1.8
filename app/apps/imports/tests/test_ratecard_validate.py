"""Stage 4: route labels, independent recalculation, load proof and the disposable-only guard."""
import hashlib
import json
import tempfile
from decimal import Decimal as D
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.imports.models import RateCardLine, ZoneSourceRow
from apps.imports.services import ratecard_validate as validate
from apps.products.models import Product
from apps.imports.services.ratecard_walk import load_sources

FIXTURES = Path(__file__).parent / 'fixtures'
HEADER = 'index,index2,carrier,suburb,state,postcode,zone,subzone,area\n'
ALL_CARRIERS = ''.join(f'1,1,{name},MELBOURNE,VIC,3000,MELB,,\n'
                       for name in ('TEAMEX', 'KTI', 'TFMX', 'TEAMTAS', 'COCHRN', 'STEA'))
PALLET = {'id': 'C01', 'suburb': 'MELBOURNE', 'state': 'VIC', 'postcode': '3000', 'weight': '100',
          'cubic': '0.1', 'pallets': 1}
CARTON = {**PALLET, 'pallets': 0, 'cartons': 1}


def config(pallet=True, carton=True, status='L', active=True, factor='250'):
    return SimpleNamespace(base_status=status, active=active, pallet_enabled=pallet, carton_enabled=carton,
                           cubic_conversion=D(factor))


def engine(status='COMPLETO', unit='WTRM', reasons=(), pending=(), carrier='KTI', path=(83,), fuel=True):
    return {'carrier': carrier, 'service': 'ROAD', 'status': status, 'reasons': list(reasons),
            'pending': [{'reason': item} for item in pending], 'path': list(path), 'total': '144',
            'freight': [{'row': 10, 'unit': unit, 'amount': '100'}] if status != 'SIN_COTIZACION' else [],
            'fuel': [{'card': 7, 'amount': '44', 'rate': '0.44'}] if fuel and status != 'SIN_COTIZACION' else [],
            'extras': []}


def row(freight='EXPLICADA', app=True):
    return {'carrier': 'KTI', 'service': 'ROAD', 'result': 'EXPLICADA', 'app': {'total': '1'} if app else None,
            'components': {'freight': {'result': freight}} if app else {}}


class LabelTests(SimpleTestCase):
    def label(self, the_row, the_engine, case=PALLET, cfg=None):
        return validate.route_label(the_row, the_engine, case, cfg or config())

    def test_settled_walk_with_confirmed_unit_is_proven(self):
        self.assertEqual(self.label(row(), engine()), (validate.PROVEN, ''))

    def test_pending_charge_keeps_the_base_and_leaves_the_total_unknown(self):
        label, reason = self.label(row('IGUAL'), engine('PARCIAL', pending=['MISSING_CARD']))
        self.assertEqual((label, reason), (validate.BASE_PROVEN, 'MISSING_CARD'))

    def test_unconfirmed_unit_is_proven_only_when_it_matches_the_app(self):
        self.assertEqual(self.label(row('IGUAL'), engine('PARCIAL', 'TPAL'))[0], validate.BASE_PROVEN)
        self.assertEqual(self.label(row(), engine('PARCIAL', 'TPAL'))[0], validate.UNKNOWN)

    def test_unexplained_freight_is_unknown_even_with_a_confirmed_unit(self):
        self.assertEqual(self.label(row('SIN_EXPLICAR'), engine())[0], validate.UNKNOWN)

    def test_wtr_decided_by_the_minimum_is_unknown(self):
        result = self.label(row(), engine('PARCIAL', 'WTR', reasons=[validate.WTR_MINIMUM_UNCONFIRMED]))
        self.assertEqual(result[0], validate.UNKNOWN)

    def test_missing_fuel_is_unknown(self):
        self.assertEqual(self.label(row('IGUAL'), engine('PARCIAL', fuel=False))[0], validate.UNKNOWN)

    def test_no_zone_is_not_applicable(self):
        result = self.label(row(app=False), engine('SIN_COTIZACION', reasons=['NO_ZONE']))
        self.assertEqual(result, (validate.NOT_APPLICABLE, 'NO_ZONE'))

    def test_engine_refusing_what_the_app_quotes_is_unknown(self):
        self.assertEqual(self.label(row(), engine('SIN_COTIZACION'))[0], validate.UNKNOWN)

    def test_switched_off_service_is_not_applicable_even_when_complete(self):
        result = self.label(row(app=False), engine(), CARTON, config(carton=False))
        self.assertEqual(result, (validate.NOT_APPLICABLE, 'SERVICIO_APAGADO'))

    def test_inactive_service_is_not_applicable(self):
        self.assertEqual(self.label(row(), engine(), cfg=config(active=False))[0], validate.NOT_APPLICABLE)

    def test_tfmx_above_the_first_band_is_not_applicable(self):
        heavy = {**PALLET, 'weight': '300'}
        result = self.label(row(app=False), engine('PARCIAL', carrier='TFMX', path=[1412]), heavy)
        self.assertEqual(result, (validate.NOT_APPLICABLE, 'RATE_004'))

    def test_tfmx_exactly_on_the_limit_stays_a_route_without_app(self):
        limit = {**PALLET, 'weight': '250', 'cubic': '0.1'}
        result = self.label(row(app=False), engine('PARCIAL', carrier='TFMX', path=[1412]), limit)
        self.assertEqual(result, (validate.UNKNOWN, 'RUTA_SIN_APP'))

    def test_other_route_only_the_engine_quotes_is_unknown(self):
        self.assertEqual(self.label(row(app=False), engine('PARCIAL')), (validate.UNKNOWN, 'RUTA_SIN_APP'))


def line(unit='WTRM', rate='0.1', basic='10', minimum='20', cubic='0'):
    return {'unit': unit, 'rate': D(rate), 'basic_charge': D(basic), 'min_charge': D(minimum), 'cubic': D(cubic)}


class RecalculationTests(SimpleTestCase):
    def test_weight_uses_the_larger_of_real_and_cubic_rounded_up(self):
        self.assertEqual(validate.recalculate(line(), {**PALLET, 'weight': '100.2', 'cubic': '0.1'}, D('250')),
                         D('20.1'))
        self.assertEqual(validate.recalculate(line(), {**PALLET, 'weight': '10', 'cubic': '1'}, D('250')), D('35'))

    def test_line_cubic_wins_over_the_inherited_factor(self):
        self.assertEqual(validate.recalculate(line(cubic='334'), {**PALLET, 'weight': '1', 'cubic': '1'}, D('250')),
                         D('43.4'))

    def test_minimum_decides_when_it_is_higher(self):
        self.assertEqual(validate.recalculate(line(), {**PALLET, 'weight': '10', 'cubic': '0.01'}, D('250')), D('20'))

    def test_pallet_case_and_charge_units(self):
        self.assertEqual(validate.recalculate(line('TPAL', '5', '10', '0'), {**PALLET, 'pallets': 3}, D('1')), D('25'))
        self.assertEqual(validate.recalculate(line('CASE', '2', '1', '0'), {**CARTON, 'cartons': 4}, D('1')), D('9'))
        self.assertEqual(validate.recalculate(line('CHG', '3', '4', '0'), PALLET, D('1')), D('7'))

    def test_unknown_unit_gives_nothing(self):
        self.assertIsNone(validate.recalculate(line('ZZZ'), PALLET, D('1')))

    def test_matching_charges_pass_and_a_wrong_amount_is_reported(self):
        base = engine()
        base['freight'][0].update(row=10, amount='20.0')
        base['fuel'][0].update(card=7, amount='8.8')
        lines = {10: line()}
        checked, failures = validate.check_charges(base, PALLET, lines, {'7': D('0.44')}, D('250'))
        self.assertEqual((checked, failures), (2, []))
        base['freight'][0]['amount'] = '21'
        self.assertTrue(validate.check_charges(base, PALLET, lines, {'7': D('0.44')}, D('250'))[1])

    def test_failed_recalculation_drops_the_route_to_unknown(self):
        result = validate.validate_route(row(), engine(), PALLET, config(), {10: line()}, {'7': D('0.44')})
        self.assertEqual((result['label'], result['reason']), (validate.UNKNOWN, 'RECALCULO_NO_COINCIDE'))
        self.assertEqual(result['total'], validate.UNKNOWN)

    def test_base_proven_never_reports_a_total(self):
        base = engine('PARCIAL', pending=['MISSING_CARD'])
        base['freight'][0]['amount'] = '20.0'
        base['fuel'][0]['amount'] = '8.8'
        result = validate.validate_route(row(), base, PALLET, config(), {10: line()}, {'7': D('0.44')})
        self.assertEqual((result['label'], result['total']), (validate.BASE_PROVEN, validate.UNKNOWN))


class GuardTests(TestCase):
    def test_load_is_refused_outside_the_disposable_database(self):
        with self.assertRaisesMessage(validate.ValidateError, 'disposable'):
            validate.load_rehearsal('STH', b'x', b'y')
        self.assertFalse(RateCardLine.objects.exists())

    def test_flag_alone_is_not_enough(self):
        with mock.patch.dict('os.environ', {'CALC_DISPOSABLE_DB': '1'}):
            with self.assertRaisesMessage(validate.ValidateError, 'disposable'):
                validate.require_disposable()


class SourcesMixin:
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client_record = Client.objects.create(code='STH', name='Test client')
        for code, service_code in (('KTI', 'GENERAL'), ('TEAMEX', 'ROAD'), ('TFMX', 'ROAD'),
                                   ('TEAMTAS', 'GENERAL'), ('COCHRN', 'ROAD'), ('STEA', 'ROAD')):
            service = CarrierService.objects.create(carrier=Carrier.objects.create(code=code),
                                                    service_code=service_code)
            ClientCarrierConfig.objects.create(client=self.client_record, carrier_service=service, ratecard='1',
                                               base_status='L', active=True, pallet_enabled=True,
                                               cubic_conversion=D('250'))
        Product.objects.create(client=self.client_record, sku='20772', weight_kg=D('70'), cubic_m3=D('0.336'),
                               freight_type='P', length_m=D('1.2'), width_m=D('0.8'), height_m=D('0.35'))

    def contents(self):
        return {'rates': (FIXTURES / 'rates_sample.xls').read_bytes(), 'zones': (HEADER + ALL_CARRIERS).encode(),
                'fuel': (FIXTURES / 'fuel_sample.xls').read_bytes()}


class LoadProofTests(SourcesMixin, TestCase):
    def load(self, files):
        with mock.patch.object(validate, 'require_disposable'):
            return validate.load_rehearsal('STH', files['rates'], files['zones'])

    def file_sources(self, files):
        hashes = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
        return load_sources(files['rates'], files['zones'], files['fuel'], rates_sha256=hashes['rates'],
                            zones_sha256=hashes['zones'], fuel_sha256=hashes['fuel'],
                            rates_filename='rates_all.xls'), hashes

    def test_loaded_rows_give_the_same_walk_as_the_files(self):
        files = self.contents()
        rates_file, zones_file = self.load(files)
        sources, hashes = self.file_sources(files)
        rows = validate.sources_from_rows(rates_file, zones_file, files['fuel'], hashes['fuel'])
        proof = validate.load_proof(sources, rows, [PALLET])
        self.assertEqual(proof['status'], 'IDENTICO')
        self.assertGreater(proof['compared'], 0)
        self.assertEqual(proof['rate_lines'], RateCardLine.objects.count())
        self.assertEqual(proof['zone_rows'], ZoneSourceRow.objects.count())

    def test_a_changed_zone_is_detected(self):
        files = self.contents()
        rates_file, zones_file = self.load(files)
        sources, hashes = self.file_sources(files)
        ZoneSourceRow.objects.filter(carrier='KTI').update(zone='OTHER')
        rows = validate.sources_from_rows(rates_file, zones_file, files['fuel'], hashes['fuel'])
        proof = validate.load_proof(sources, rows, [PALLET])
        self.assertEqual(proof['status'], 'DIFERENTE')
        self.assertIn('C01 KTI/GENERAL', proof['different'])


class CommandTests(SourcesMixin, TestCase):
    def arguments(self, folder):
        arguments = {}
        for name, content in self.contents().items():
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

    def test_run_labels_every_route_and_writes_the_report(self):
        with tempfile.TemporaryDirectory() as folder:
            call_command('validate_rate_routes', stdout=StringIO(), **self.arguments(folder))
            run = next((Path(folder) / 'out').iterdir())
            report = json.loads((run / 'routes.json').read_text(encoding='utf-8'))
            names = {path.name for path in run.iterdir()}
            markdown = (run / 'routes.md').read_text(encoding='utf-8')
        self.assertLessEqual({'routes.json', 'routes.md', 'cases.json', 'rates_sample.xls'}, names)
        self.assertEqual(sum(report['counts'].values()), 6)
        self.assertEqual(report['load_proof']['status'], 'NO_EJECUTADA')
        self.assertIn('`NO_EJECUTADA`', markdown)

    def test_run_never_writes_to_the_database(self):
        with tempfile.TemporaryDirectory() as folder:
            with CaptureQueriesContext(connection) as queries:
                call_command('validate_rate_routes', stdout=StringIO(), **self.arguments(folder))
        written = [item['sql'] for item in queries
                   if item['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(written, [])

    def test_rehearsal_flag_is_refused_before_creating_a_run(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesMessage(CommandError, 'disposable'):
                call_command('validate_rate_routes', stdout=StringIO(), rehearse_load=True,
                             **self.arguments(folder))
            self.assertFalse((Path(folder) / 'out').exists())
        self.assertFalse(RateCardLine.objects.exists())

    def test_wrong_hash_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            arguments['zones_sha256'] = '0' * 64
            with self.assertRaisesMessage(CommandError, 'does not match'):
                call_command('validate_rate_routes', stdout=StringIO(), **arguments)


class IsolationTests(SimpleTestCase):
    def test_nothing_that_quotes_imports_the_validation(self):
        root = Path(settings.BASE_DIR) / 'apps'
        allowed = {root / 'freight/tests/test_overlength.py',
                   root / 'freight/services/operational_ratecards.py',
                   root / 'imports/services/ratecard_validate.py',
                   root / 'imports/management/commands/validate_rate_routes.py',
                   root / 'imports/tests/test_ratecard_validate.py',
                   root / 'imports/tests/test_ratecard_walk.py',
                   root / 'imports/tests/test_ratecard_compare.py',
                   root / 'imports/services/ratecard_coverage.py',
                   root / 'imports/management/commands/sweep_rate_routes.py',
                   root / 'imports/tests/test_ratecard_coverage.py'}
        for path in root.rglob('*.py'):
            if path not in allowed:
                self.assertNotIn('ratecard_validate', path.read_text(encoding='utf-8', errors='ignore'), path)
