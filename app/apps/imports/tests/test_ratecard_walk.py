"""Stage 2 walker. SimpleTestCase refuses database access, so these also prove it reads none."""
import ast
import hashlib
import json
import tempfile
from decimal import Decimal as D
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from apps.imports.services import ratecard_walk as walk
from apps.imports.services.ratecard_walk import Case, Line, Sources, walk_case

LEVY = 'iif(inlist(driver_zones.type,"1"),0,1)'
FAR = "iif((jobs.del_post>='5718' and !inlist(jobs.del_post,'5950')),1,0)"
NOT_NT_WA = 'iif(inlist(jobs.del_state,"NT","WA"),0,1)'
FIXTURES = Path(__file__).parent / 'fixtures'


def line(master, break_no=1, item=1, run=None, name='Line', expression='', low='', high='', greater='0',
         upto='0', unit='CHG', rate='0', basic='0', minimum='0', cubic='0', row=2, each='1'):
    return Line(source_row=row, master=master, break_no=break_no, item_no=item, run_rate=run, name=name,
                filter_field=expression, from_value=low, to_value=high, greater=D(greater), upto=D(upto),
                unit=unit, rate=D(rate), basic=D(basic), minimum=D(minimum), cubic=D(cubic), each=D(each))


def zone_rows(carrier, zone, suburb='ADELAIDE', state='SA', postcode='5000', subzone=''):
    return {(carrier, suburb, state): [{'zone': zone, 'subzone': subzone, 'postcode': postcode}]}


def sources(cards, zones, fuel=None):
    return Sources('r' * 64, 'z' * 64, 'f' * 64, cards, zones, fuel if fuel is not None else {})


def case(carrier='TEAMEX', service='ROAD', suburb='ADELAIDE', state='SA', postcode='5000', weight='200',
         cubic='0.5', **extra):
    return Case(carrier=carrier, service=service, suburb=suburb, state=state, postcode=postcode,
                weight=D(weight), cubic=D(cubic), **extra)


def teamex_cards():
    """Values copied from rates_all.xls 73b56eb, cards 1135, 1516, 1517, 1518 and 1115."""
    return {
        1135: [line(1135, item=7, run=1533, expression='Cus_code', low='DUL', high='DUN', row=1),
               line(1135, item=8, run=1516, expression='Cus_code', low='STG', high='STH', row=2)],
        1533: [line(1533, expression='Del_zone', low='ADDD', high='ADEL', unit='WTRM', rate='9')],
        1516: [line(1516, item=1, run=1517, expression='Weight', upto='750', cubic='334', row=10),
               line(1516, item=2, run=1518, expression='Weight', greater='750.0001', upto='1500',
                    cubic='334', row=11),
               line(1516, break_no=2, run=1115, name='Freight - Fuel SurChg', row=12),
               line(1516, break_no=3, run=1524, name='Disaster Levy', expression=LEVY, low='0',
                    high='1', row=13)],
        1517: [line(1517, name='ADEL', expression='Del_zone', low='ADDD', high='ADEL', unit='WTRM',
                    rate='0.111', basic='26.88', minimum='54.6', cubic='334', row=20),
               line(1517, item=2, name='MELB', expression='Del_zone', low='MELA', high='MELB',
                    unit='WTRM', rate='0.125', basic='26.88', minimum='58.8', cubic='334', row=21)],
        1518: [line(1518, name='ADEL', expression='Del_zone', low='ADDD', high='ADEL', unit='WTRM',
                    rate='0.1', basic='26.88', minimum='54.6', cubic='334', row=22)],
        1115: [line(1115, name='Freight - Fuel SurChg', expression='Price', upto='999999.9999',
                    unit='PRICE', rate='0.44', row=30)],
    }


def teamex():
    return sources(teamex_cards(), zone_rows('TEAMEX', 'ADEL'), {'1115': D('0.44')})


def kti(fuel=None):
    cards = {
        79: [line(79, run=83, expression='Cus_code', low='STG', high='STH')],
        83: [line(83, name='Deliver Melbourne', expression='Del_zone', low='MELA', high='MELB', unit='WTRM',
                  rate='0.108', basic='16.1', minimum='106.8', cubic='334', row=40),
             line(83, break_no=2, run=1822, name='Freight - Fuel S/Chg', row=41)],
        1822: [line(1822, name='Freight - Fuel S/Chg', expression='Price', upto='999999.9999',
                    unit='PRICE', rate='0.51', row=42)],
    }
    return sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000'),
                   {'1822': D('0.51')} if fuel is None else fuel)


def kti_case(**extra):
    return case('KTI', 'GENERAL', 'MELBOURNE', 'VIC', '3000', '751', '1.2', **extra)


class WalkRuleTests(SimpleTestCase):
    def test_kti_is_complete_with_the_minimum_and_fuel_on_freight(self):
        result = walk_case(kti(), kti_case(pallets=1))
        self.assertEqual(result['status'], walk.COMPLETE)
        self.assertEqual(result['path'], [79, 83, 1822])
        self.assertEqual(D(result['freight'][0]['amount']), D('106.8'))
        self.assertEqual(D(result['fuel'][0]['amount']), D('54.468'))
        self.assertEqual(D(result['total']), D('161.268'))

    def test_every_charge_cites_card_and_source_row(self):
        result = walk_case(kti(), kti_case())
        self.assertEqual((result['freight'][0]['card'], result['freight'][0]['row']), (83, 40))
        self.assertEqual((result['fuel'][0]['card'], result['fuel'][0]['row']), (1822, 42))
        self.assertEqual(result['hashes']['rates_all'], 'r' * 64)

    def test_first_match_wins_inside_a_break_and_next_break_is_separate(self):
        cards = {79: [line(79, item=1, expression='Del_zone', low='MELA', high='MELB', unit='WTRM',
                           rate='1', cubic='334', row=1),
                      line(79, item=2, expression='Del_zone', low='MELA', high='MELB', unit='WTRM',
                           rate='9', cubic='334', row=2),
                      line(79, break_no=2, name='Toll', unit='CHG', rate='5', row=3)]}
        result = walk_case(sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000')),
                           kti_case())
        self.assertEqual([item['row'] for item in result['freight']], [1])
        self.assertEqual([item['row'] for item in result['extras']], [3])

    def test_run_rate_ignores_values_on_its_own_line(self):
        cards = {79: [line(79, run=80, rate='999', basic='999', minimum='999')],
                 80: [line(80, expression='Del_zone', low='MELA', high='MELB', unit='WTRM', rate='1',
                           cubic='334')]}
        result = walk_case(sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000')),
                           kti_case())
        self.assertEqual(D(result['freight'][0]['amount']), D('751'))

    def test_band_uses_chargeable_weight_not_real_weight(self):
        result = walk_case(teamex(), case(weight='500', cubic='2.5'))
        self.assertIn(1518, result['path'])
        self.assertNotIn(1517, result['path'])

    def test_customer_selector_uses_from_exclusive_to_inclusive(self):
        self.assertNotIn(1533, walk_case(teamex(), case())['path'])

    def test_zero_cubic_inherits_the_factor_from_above(self):
        cards = {79: [line(79, run=80, cubic='334')],
                 80: [line(80, expression='Del_zone', low='MELA', high='MELB', unit='WTRM', rate='1')]}
        result = walk_case(sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000')),
                           case('KTI', 'GENERAL', 'MELBOURNE', 'VIC', '3000', '100', '1'))
        self.assertEqual(D(result['freight'][0]['amount']), D('334'))

    def test_no_cubic_factor_stays_pending(self):
        cards = {79: [line(79, expression='Del_zone', low='MELA', high='MELB', unit='WTRM', rate='1')]}
        result = walk_case(sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000')), kti_case())
        self.assertEqual(result['status'], walk.UNKNOWN)
        self.assertEqual(result['pending'][0]['reason'], 'NO_CUBIC_FACTOR')
        self.assertIsNone(result['total'])

    def test_unreadable_line_in_the_zone_break_is_unknown_not_no_rate(self):
        cards = {20: [line(20, item=1, expression='Del_zone', low='AAA', high='AAB', unit='TPAL', rate='1'),
                      line(20, item=2, expression='Col_zone', low='ADK', high='ADL')]}
        result = walk_case(sources(cards, zone_rows('STEA', 'ADL')), case('STEA', pallets=1))
        self.assertEqual(result['status'], walk.UNKNOWN)

    def test_missing_root_card_is_pending(self):
        result = walk_case(sources({}, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000')), kti_case())
        self.assertEqual((result['status'], result['pending'][0]['target_card']), (walk.UNKNOWN, 79))

    def test_zero_price_is_a_rejection_not_a_price(self):
        cards = {1506: [line(1506, run=1502)],
                 1502: [line(1502, name='*** POA Zone BON ***', expression='Del_zone', low='BOM',
                             high='BON', unit='TPAL')]}
        result = walk_case(sources(cards, zone_rows('COCHRN', 'BON')), case('COCHRN', pallets=1))
        self.assertEqual((result['status'], result['reasons']), (walk.NO_QUOTE, ['ZERO_PRICE']))
        self.assertIsNone(result['known_subtotal'])

    def test_zero_charge_line_chosen_by_zone_is_also_a_rejection(self):
        cards = {20: [line(20, name='Steadfast Regional', expression='Del_zone', low='SA0', high='SA5')]}
        result = walk_case(sources(cards, zone_rows('STEA', 'SA2')), case('STEA', pallets=1))
        self.assertEqual((result['status'], result['reasons']), (walk.NO_QUOTE, ['ZERO_PRICE']))

    def test_zone_without_rate_is_no_quote(self):
        data = sources(teamex_cards(), zone_rows('TEAMEX', 'ZZZZ'), {'1115': D('0.44')})
        result = walk_case(data, case())
        self.assertEqual((result['status'], result['reasons']), (walk.NO_QUOTE, ['NO_RATE']))

    def test_missing_zone_and_conflicting_zone_are_no_quote(self):
        self.assertEqual(walk_case(teamex(), case(suburb='NOWHERE'))['reasons'], ['NO_ZONE'])
        rows = {('TEAMEX', 'ADELAIDE', 'SA'): [{'zone': 'A', 'subzone': '', 'postcode': '5000'},
                                               {'zone': 'B', 'subzone': '', 'postcode': '5000'}]}
        self.assertEqual(walk_case(sources(teamex_cards(), rows), case())['reasons'], ['ZONE_AMBIGUOUS'])

    def test_postcode_separates_duplicates_and_keeps_leading_zero(self):
        rows = {('TFMX', 'DARWIN', 'NT'): [{'zone': 'DRW', 'subzone': '', 'postcode': '0800'},
                                           {'zone': 'OTH', 'subzone': '', 'postcode': '0900'}]}
        found, _ = walk.resolve_zone(sources({}, rows), case('TFMX', suburb='DARWIN', state='NT',
                                                             postcode='0800'))
        self.assertEqual(found, ('DRW', ''))

    def test_circular_reference_is_pending(self):
        cards = {79: [line(79, run=80)], 80: [line(80, run=79)]}
        data = sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000'))
        result = walk_case(data, kti_case())
        self.assertEqual(result['pending'][0]['reason'], 'CIRCULAR_REFERENCE')
        self.assertEqual(result['status'], walk.UNKNOWN)

    def test_unknown_unit_is_pending(self):
        cards = {79: [line(79, name='x', expression='Del_zone', low='MELA', high='MELB', unit='WTRM',
                           rate='1', cubic='334'),
                      line(79, break_no=2, unit='NEW', rate='7')]}
        result = walk_case(sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000')),
                           kti_case())
        self.assertEqual(result['pending'][0]['reason'], 'UNIT_UNKNOWN')
        self.assertIsNone(result['total'])


class PendingNeverZeroTests(SimpleTestCase):
    def test_disaster_levy_keeps_teamex_partial_without_total(self):
        result = walk_case(teamex(), case())
        self.assertEqual(result['status'], walk.PARTIAL)
        self.assertIsNone(result['total'])
        self.assertEqual(result['pending'][0]['reason'], 'ZONE_TYPE_NOT_IN_ZONES_CSV')
        self.assertEqual(D(result['freight'][0]['amount']), D('54.6'))
        self.assertEqual(D(result['known_subtotal']), D('78.624'))

    def test_missing_card_reports_its_number(self):
        cards = teamex_cards()
        cards[1516][-1] = line(1516, break_no=3, run=1524, name='Disaster Levy', row=13)
        data = sources(cards, zone_rows('TEAMEX', 'ADEL'), {'1115': D('0.44')})
        result = walk_case(data, case())
        self.assertEqual((result['pending'][0]['reason'], result['pending'][0]['target_card']),
                         ('MISSING_CARD', 1524))

    def test_price_limit_is_not_ignored_for_card_1466(self):
        cards = {55: [line(55, name='x', expression='Del_zone', low='ADDD', high='ADEL', unit='WTRM',
                           rate='1', cubic='250'),
                      line(55, break_no=2, run=1466, expression='Price', upto='23.44')],
                 1466: [line(1466, name='Force Majeure', expression='Price', upto='999999.9999',
                             unit='PRICE', rate='0.3')]}
        result = walk_case(sources(cards, zone_rows('TFMX', 'ADEL')), case('TFMX'))
        self.assertNotIn(1466, result['path'])
        self.assertEqual(result['pending'][0]['reason'], 'PRICE_LIMIT_UNCONFIRMED')
        self.assertEqual(result['extras'], [])

    def test_non_fuel_price_line_is_pending_and_adds_nothing(self):
        cards = {55: [line(55, name='x', expression='Del_zone', low='ADDD', high='ADEL', unit='WTRM',
                           rate='1', cubic='250'),
                      line(55, break_no=2, name='Force Majeure', expression='Price',
                           upto='999999.9999', unit='PRICE', rate='0.3')]}
        result = walk_case(sources(cards, zone_rows('TFMX', 'ADEL')), case('TFMX'))
        self.assertEqual(result['pending'][0]['reason'], 'PRICE_RULE_UNCONFIRMED')
        self.assertEqual(D(result['known_subtotal']), D('200'))

    def test_wtr_decided_by_minimum_is_partial(self):
        cards = {79: [line(79, name='x', expression='Del_zone', low='MELA', high='MELB', unit='WTR',
                           rate='0.01', minimum='90', cubic='334')]}
        data = sources(cards, zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000'))
        result = walk_case(data, kti_case())
        self.assertEqual((result['status'], result['reasons']),
                         (walk.PARTIAL, [walk.WTR_MINIMUM_UNCONFIRMED]))

    def test_unconfirmed_unit_is_calculated_but_partial(self):
        cards = {1506: [line(1506, name='Pallets', expression='Del_zone', low='RZZ', high='S00',
                             unit='TPAL', rate='41.27')]}
        result = walk_case(sources(cards, zone_rows('COCHRN', 'S00')), case('COCHRN', pallets=1))
        self.assertEqual(result['status'], walk.PARTIAL)
        self.assertEqual(D(result['known_subtotal']), D('41.27'))


class FuelSourceTests(SimpleTestCase):
    def test_fuel_file_governs_and_difference_warns(self):
        result = walk_case(kti({'1822': D('0.40')}), kti_case())
        self.assertEqual(D(result['fuel'][0]['amount']), D('42.72'))
        self.assertEqual(result['warnings'][0]['reason'], 'FUEL_DIFFERS_FROM_RATES_ALL')

    def test_card_absent_from_fuel_file_is_pending_not_the_card_value(self):
        result = walk_case(kti({}), kti_case())
        self.assertEqual(result['fuel'], [])
        self.assertEqual(result['pending'][0]['reason'], 'FUEL_NOT_IN_FILE')
        self.assertIsNone(result['total'])


class ExpressionTests(SimpleTestCase):
    def outcome(self, expression, **fields):
        data = {'low': '0', 'high': '1', **fields}
        target = line(1, expression=expression, low=data.pop('low'), high=data.pop('high'),
                      greater=data.pop('greater', '0'), upto=data.pop('upto', '0'))
        return walk._evaluate(target, case(**data), D('334'))

    def test_expressions_are_never_executed(self):
        payload = '__import__("os").system("echo hacked")'
        self.assertEqual(self.outcome(payload), (walk.PENDING, 'UNRECOGNISED_EXPRESSION'))

    def test_far_postcode_rule_is_text_and_excludes_5950(self):
        self.assertEqual(self.outcome(FAR, postcode='5718')[0], walk.YES)
        self.assertEqual(self.outcome(FAR, postcode='5950')[0], walk.NO)
        self.assertEqual(self.outcome(FAR, postcode='5000')[0], walk.NO)
        self.assertEqual(self.outcome(FAR, postcode='0800')[0], walk.NO)

    def test_state_guard(self):
        self.assertEqual(self.outcome(NOT_NT_WA, state='SA')[0], walk.YES)
        self.assertEqual(self.outcome(NOT_NT_WA, state='NT')[0], walk.NO)

    def test_zone_list_with_pallets(self):
        expression = 'iif(inlist(jobs.del_zone,"MCLA","WILL"),jobs.pal2,0)'
        target = line(1, expression=expression, greater='0.99', upto='999999.9999')
        self.assertEqual(walk._evaluate(target, case(zone='WILL', pallets=1), D('334'))[0], walk.YES)
        self.assertEqual(walk._evaluate(target, case(zone='OTHR', pallets=1), D('334'))[0], walk.NO)

    def test_fields_without_input_stay_pending(self):
        self.assertEqual(self.outcome('Col_zone')[1], 'COLLECTION_ZONE_UNAVAILABLE')
        self.assertEqual(self.outcome('Work_code')[1], 'WORK_CODE_UNAVAILABLE')
        self.assertEqual(self.outcome(LEVY)[1], 'ZONE_TYPE_NOT_IN_ZONES_CSV')

    def test_options_apply_only_when_requested(self):
        tail = 'iif(AT("TAIL",UPPER(jobs.del_comment))=0,\'NO\',\'YES\')'
        self.assertEqual(self.outcome(tail)[0], walk.OPTION)
        self.assertEqual(self.outcome(tail, tailgate=True)[0], walk.YES)
        self.assertEqual(self.outcome('jobs.ins_code')[0], walk.OPTION)

    def test_job_field_mapping_carries_a_caveat(self):
        target = line(1, expression='jobs.pal1', greater='0.99', upto='999999.9999')
        self.assertEqual(walk._evaluate(target, case(cartons=2), D('334')),
                         (walk.YES, walk.JOB_FIELD_UNCONFIRMED))


class SteadfastTests(SimpleTestCase):
    def test_per_consignment_card_counts_as_freight(self):
        cards = {20: [line(20, run=18, expression='Del_zone', low='ADK', high='ADL')],
                 18: [line(18, name='Deliver - Consignment', rate='17', row=50),
                      line(18, break_no=3, name='Deliver Pallets', expression='jobs.pal2',
                           greater='0.99', upto='999999.9999', unit='TPAL', rate='26', row=51)]}
        result = walk_case(sources(cards, zone_rows('STEA', 'ADL')), case('STEA', pallets=1))
        self.assertEqual(sum(D(item['amount']) for item in result['freight']), D('43'))
        self.assertEqual(result['status'], walk.PARTIAL)


class CochranesRootTests(SimpleTestCase):
    def data(self):
        cards = {
            1509: [line(1509, break_no=2, name='Far North Extra fuel S/Chg', expression=FAR, low='0',
                        high='1', rate='0.66')],
            1506: [line(1506, run=1502, expression='jobs.pal2', greater='0.99', upto='999999.9999'),
                   line(1506, break_no=2, name='Freight Fuel S/charge', expression='Price',
                        upto='999999.9999', unit='PRICE', rate='0.53')],
            1502: [line(1502, name='Pallets Zone S07', expression='Del_zone', low='S06', high='S07',
                        unit='TPAL', rate='132.61')],
        }
        return sources(cards, zone_rows('COCHRN', 'S07', 'COOBER PEDY', 'SA', '5723'), {'1506': D('0.53')})

    def test_starts_at_1506_and_skips_the_unreferenced_selector(self):
        result = walk_case(self.data(), case('COCHRN', suburb='COOBER PEDY', postcode='5723', pallets=1))
        self.assertEqual(result['path'], [1506, 1502])
        self.assertEqual(result['extras'], [])
        self.assertEqual(D(result['known_subtotal']), D('202.8933'))


class ScopeTests(SimpleTestCase):
    def test_excluded_services_are_reported_as_out_of_scope(self):
        results = walk.walk_all(teamex(), suburb='ADELAIDE', state='SA', postcode='5000',
                                weight=D('200'), cubic=D('0.5'))
        status = {(item['carrier'], item['service']): item['status'] for item in results}
        self.assertEqual(len(status), 10)
        for key in walk.EXCLUDED:
            self.assertEqual(status[key], walk.OUT_OF_SCOPE)


class HashAndCommandTests(SimpleTestCase):
    ZONES = b'index,index2,carrier,suburb,state,postcode,zone,subzone,area\n1,1,KTI,MELBOURNE,VIC,3000,MELB,,\n'

    def write_sources(self, folder):
        files = {'rates': (FIXTURES / 'rates_sample.xls').read_bytes(), 'zones': self.ZONES,
                 'fuel': (FIXTURES / 'fuel_sample.xls').read_bytes()}
        arguments = {}
        for name, content in files.items():
            path = Path(folder) / ('rates_sample.xls' if name == 'rates' else f'{name}.bin')
            path.write_bytes(content)
            arguments[name] = str(path)
            arguments[f'{name}_sha256'] = hashlib.sha256(content).hexdigest()
        return arguments

    def run_command(self, arguments):
        out = StringIO()
        call_command('walk_rate_cards', stdout=out, suburb='MELBOURNE', state='VIC', postcode='3000',
                     weight='100', cubic='0.1', **arguments)
        return json.loads(out.getvalue())

    def test_command_prints_every_carrier_with_all_three_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.write_sources(folder)
            output = self.run_command(arguments)
        self.assertEqual(len(output[0]['results']), 10)
        self.assertEqual(output[0]['results'][0]['hashes']['fuel'], arguments['fuel_sha256'])

    def test_wrong_hash_stops_without_a_result(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.write_sources(folder)
            arguments['rates_sha256'] = '0' * 64
            with self.assertRaisesMessage(CommandError, 'does not match'):
                self.run_command(arguments)

    def test_short_hash_is_refused(self):
        with self.assertRaisesMessage(walk.WalkError, '64 hexadecimal'):
            walk.require_hash(b'x', 'abc', 'rates')

    def test_money_keeps_six_decimals_as_decimal(self):
        fine = sources({79: [line(79, name='x', expression='Del_zone', low='MELA', high='MELB',
                                  unit='WTRM', rate='0.123456', cubic='334')]},
                       zone_rows('KTI', 'MELB', 'MELBOURNE', 'VIC', '3000'))
        self.assertEqual(D(walk_case(fine, kti_case())['freight'][0]['amount']), D('92.715456'))


class IsolationTests(SimpleTestCase):
    def test_nothing_that_quotes_imports_the_walker(self):
        root = Path(settings.BASE_DIR) / 'apps'
        allowed = {root / 'imports/services/ratecard_walk.py',
                   root / 'imports/management/commands/walk_rate_cards.py',
                   root / 'imports/tests/test_ratecard_walk.py',
                   root / 'imports/services/ratecard_validate.py',
                   root / 'imports/management/commands/validate_rate_routes.py',
                   root / 'imports/tests/test_ratecard_validate.py',
                   root / 'imports/services/ratecard_coverage.py',
                   root / 'freight/services/operational_ratecards.py',
                   root / 'imports/management/commands/sweep_rate_routes.py',
                   root / 'imports/tests/test_ratecard_coverage.py'}
        for path in root.rglob('*.py'):
            if path not in allowed:
                self.assertNotIn('ratecard_walk', path.read_text(encoding='utf-8', errors='ignore'), path)

    def test_walker_never_touches_the_orm_or_executes_text(self):
        for name in ('imports/services/ratecard_walk.py', 'imports/management/commands/walk_rate_cards.py'):
            source = (Path(settings.BASE_DIR) / 'apps' / name).read_text(encoding='utf-8')
            calls = {node.func.id for node in ast.walk(ast.parse(source))
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
            self.assertFalse(calls & {'eval', 'exec', 'compile'})
            for word in ('.objects', '.save(', 'django.db'):
                self.assertNotIn(word, source)
