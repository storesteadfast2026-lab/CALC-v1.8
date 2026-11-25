import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.imports.management.commands.validate_sth_rate_sources import validate_sources
from apps.imports.services.ratecard_chain import (
    APPLICABLE, NOT_APPLICABLE, UNKNOWN, CardLine, Catalogue, CaseContext, customer_scope,
    load_catalogue, resolve_case,
)
from apps.imports.services.ratecard_source import FIELDS
from apps.imports.services.xlsx_reader import SourceImportError
from apps.imports.services.zone_source import MAX_BYTES, read_zones, summarise_carrier

HEADER = 'index,index2,carrier,suburb,state,postcode,zone,subzone,area\n'
LEVY = 'iif(inlist(driver_zones.type,"1"),0,1)'
NOT_NT_WA = 'iif(inlist(jobs.del_state,"NT","WA"),0,1)'


def line(master, break_no=1, item=1, run=None, name='Line', expression='', low='', high='',
         greater=0, upto=0, unit='CHG', rate=0.0, basic=0.0, minimum=0.0, row=2):
    return CardLine(source_row=row, master=master, card_name='', break_no=break_no, item_no=item,
                    run_rate=run, name=name, filter_field=expression, from_value=low, to_value=high,
                    greater=greater, upto=upto, unit=unit, rate=rate, basic=basic, minimum=minimum)


def teamex_catalogue():
    """Selector -> customer card -> weight cards, shaped like the native export."""
    guard = 'iif(inlist(jobs.cus_code,"LTU","KBA") and inlist(jobs.del_state,"SA"),0,1)'
    return Catalogue(sha256='x', rows=0, masters={
        1135: [line(1135, item=1, run=1431, expression=guard, low='0', high='1'),
               line(1135, item=2, run=1516, expression='Cus_code', low='STG', high='STH'),
               line(1135, item=3, run=1533, expression='Cus_code', low='AAAA', high='ZZZZ')],
        1431: [line(1431, expression='Del_zone', low='MELA', high='MELB', unit='WTRM', rate=9.0)],
        1533: [line(1533, expression='Del_zone', low='MELA', high='MELB', unit='WTRM', rate=8.0)],
        1516: [line(1516, item=1, run=1517, expression='Weight', greater=0, upto=750),
               line(1516, item=2, run=1518, expression='Weight', greater=750.0001, upto=1500),
               line(1516, break_no=2, run=1115),
               line(1516, break_no=3, run=1524, expression=LEVY, low='0', high='1')],
        1517: [line(1517, expression='Del_zone', low='MELA', high='MELB', unit='WTRM', rate=0.5,
                    row=10)],
        1518: [line(1518, expression='Del_zone', low='MELA', high='MELB', unit='WTRM', rate=0.4,
                    row=20)],
        1115: [line(1115, expression='Price', unit='PRICE', rate=0.44, row=30)],
    })


def rates(ctx_zone='MELB', weight=100):
    return resolve_case(teamex_catalogue(), 'TEAMEX', CaseContext(zone=ctx_zone, state='VIC', weight=weight))


class ChainResolutionTests(SimpleTestCase):
    def test_sth_takes_its_own_card_not_the_customer_guarded_card(self):
        result = rates()
        self.assertEqual(result.path[:2], [1135, 1516])
        self.assertNotIn(1431, result.path)
        self.assertNotIn(1533, result.path)

    def test_listed_customer_guard_stays_unknown(self):
        ctx = CaseContext(zone='MELB', state='SA', customer='LTU')
        result = resolve_case(teamex_catalogue(), 'TEAMEX', ctx)
        self.assertEqual(result.status, UNKNOWN)
        self.assertEqual(result.unresolved[0]['reason'], 'UNRECOGNISED_EXPRESSION')

    def test_weight_boundaries_follow_the_file(self):
        self.assertIn(1517, rates(weight=750).path)
        self.assertIn(1518, rates(weight=751).path)

    def test_provenance_keeps_source_rows(self):
        self.assertEqual(rates().freight[0]['row'], 10)
        self.assertEqual(rates().percent_of_price[0]['row'], 30)

    def test_missing_levy_card_is_unknown_but_base_is_priced(self):
        result = rates()
        self.assertEqual(result.base_status, APPLICABLE)
        self.assertEqual(result.status, UNKNOWN)
        self.assertEqual(result.unresolved[0]['reason'], 'ZONE_TYPE_NOT_IN_ZONES_CSV')

    def test_zone_without_rate_is_not_applicable(self):
        result = rates(ctx_zone='NOPE')
        self.assertEqual(result.status, NOT_APPLICABLE)
        self.assertEqual(result.base_status, NOT_APPLICABLE)

    def test_zone_range_excludes_lower_bound(self):
        self.assertEqual(rates(ctx_zone='MELA').base_status, NOT_APPLICABLE)

    def test_far_north_postcode_rule_is_resolved_without_comparing_prices(self):
        expression = "iif((jobs.del_post>='5718' and !inlist(jobs.del_post,'5950')),1,0)"
        catalogue = Catalogue(sha256='x', rows=0, masters={
            1509: [line(1509, expression=expression, low='0', high='1', rate=0.66)],
        })

        selected = resolve_case(
            catalogue, 'COCHRN', CaseContext(zone='FNQ', state='QLD', postcode='5718'),
        )
        excluded = resolve_case(
            catalogue, 'COCHRN', CaseContext(zone='FNQ', state='QLD', postcode='5950'),
        )

        self.assertFalse(selected.unresolved)
        self.assertEqual(len(selected.surcharges), 1)
        self.assertFalse(excluded.unresolved)
        self.assertFalse(excluded.surcharges)

    def test_stea_direct_case_and_pallet_quantities_are_resolved(self):
        catalogue = Catalogue(sha256='x', rows=0, masters={
            20: [line(20, run=18)],
            18: [
                line(18, break_no=1, item=1,
                     expression='iif((jobs.pal1>0 or jobs.pal2>0),0,jobs.lift)',
                     greater=.99, upto=999999, unit='CASE', rate=3),
                line(18, break_no=1, item=2, expression='jobs.pal1',
                     greater=.99, upto=999999, unit='TCASE', rate=3),
                line(18, break_no=2, item=1,
                     expression='iif((jobs.pal1>0 or jobs.pal2>0),0,jobs.pallet)',
                     greater=.99, upto=999999, unit='PAL', rate=26),
                line(18, break_no=2, item=2, expression='jobs.pal2',
                     greater=.99, upto=999999, unit='TPAL', rate=26),
            ],
        })

        cases = resolve_case(
            catalogue, 'STEA', CaseContext(zone='ADL', state='SA', cartons=1, pallets=0),
        )
        pallets = resolve_case(
            catalogue, 'STEA', CaseContext(zone='ADL', state='SA', cartons=0, pallets=1),
        )

        self.assertFalse(cases.unresolved)
        self.assertEqual([item['unit'] for item in cases.surcharges], ['TCASE'])
        self.assertFalse(pallets.unresolved)
        self.assertEqual([item['unit'] for item in pallets.surcharges], ['TPAL'])

    def test_chain_stopped_before_a_zone_card_is_unknown_not_unpriced(self):
        catalogue = Catalogue(sha256='x', rows=0, masters={
            1135: [line(1135, run=9999, expression='Cus_code', low='AAAA', high='ZZZZ')]})
        result = resolve_case(catalogue, 'TEAMEX', CaseContext(zone='MELB', state='VIC'))
        self.assertEqual(result.status, UNKNOWN)
        self.assertEqual(result.unresolved[0]['reason'], 'MISSING_MASTER')

    def test_unlisted_expression_is_not_executed(self):
        evil = '__import__("os").system("x")'
        catalogue = Catalogue(sha256='x', rows=0, masters={1135: [line(1135, expression=evil)]})
        with patch('builtins.eval') as evaluated, patch('builtins.exec') as executed:
            result = resolve_case(catalogue, 'TEAMEX', CaseContext(zone='MELB', state='VIC'))
        evaluated.assert_not_called()
        executed.assert_not_called()
        self.assertEqual(result.status, UNKNOWN)

    def test_zero_priced_zone_is_not_a_rate(self):
        catalogue = Catalogue(sha256='x', rows=0, masters={
            1135: [line(1135, name='*** POA ***', expression='Del_zone', low='BOM', high='BON')]})
        result = resolve_case(catalogue, 'TEAMEX', CaseContext(zone='BON', state='VIC'))
        self.assertEqual(result.status, NOT_APPLICABLE)

    def test_circular_reference_stops(self):
        catalogue = Catalogue(sha256='x', rows=0, masters={1135: [line(1135, run=1135)]})
        result = resolve_case(catalogue, 'TEAMEX', CaseContext(zone='MELB', state='VIC'))
        self.assertEqual(result.unresolved[0]['reason'], 'CIRCULAR_REFERENCE')

    def test_missing_references_are_listed(self):
        self.assertEqual(teamex_catalogue().missing_references(), [1524])

    def test_whitelisted_state_exclusion_reaches_missing_card_only_outside_excluded_states(self):
        catalogue = Catalogue(sha256='x', rows=0, masters={
            55: [line(55, run=1594, expression=NOT_NT_WA)],
        })

        vic = resolve_case(catalogue, 'TFMX', CaseContext(zone='MELB', state='VIC'))
        nt = resolve_case(catalogue, 'TFMX', CaseContext(zone='DRW', state='NT'))

        self.assertEqual(vic.unresolved[0]['reason'], 'MISSING_MASTER')
        self.assertEqual(vic.unresolved[0]['card'], 1594)
        self.assertEqual(nt.status, NOT_APPLICABLE)
        self.assertEqual(catalogue.missing_reference_details()[0]['review_status'],
                         'CONDITIONALLY_REACHABLE')

    def test_missing_reference_details_separate_root_reachability(self):
        catalogue = teamex_catalogue()
        catalogue.masters[9000] = [line(9000, run=9999, name='Unrelated missing card', row=99)]

        details = catalogue.missing_reference_details()

        self.assertEqual([item['card'] for item in details], [1524, 9999])
        self.assertTrue(details[0]['structurally_reachable'])
        self.assertEqual(details[0]['reachable_carriers'], ['TEAMEX'])
        self.assertEqual(details[0]['review_status'], 'SOURCE_FIELD_REQUIRED')
        self.assertEqual(details[0]['references'][0]['from_card'], 1516)
        self.assertFalse(details[1]['structurally_reachable'])
        self.assertEqual(details[1]['reachable_carriers'], [])
        self.assertEqual(details[1]['review_status'], 'UNREACHABLE_FROM_STH_ROOTS')

    def test_explicit_customer_selector_can_remove_false_sth_priority(self):
        catalogue = Catalogue(sha256='x', rows=0, masters={
            1135: [line(1135, run=8888, expression='Cus_code', low='AGA', high='AGS')],
        })

        detail = catalogue.missing_reference_details()[0]

        self.assertEqual(customer_scope(catalogue.masters[1135][0]), 'OTHER_CUSTOMER')
        self.assertEqual(detail['review_status'], 'OTHER_CUSTOMER_ONLY')


class LoadCatalogueTests(SimpleTestCase):
    def read(self, **overrides):
        record = {key: '' for key in FIELDS}
        record.update({'_row_number': 7, 'master_rate': '1516', 'break': 1.0, 'item_no': 2.0,
                       'name': ' Line ', 'greater': 750.0001, 'upto': 1500.0, 'rate': 0.5})
        record.update(overrides)
        result = type('Result', (), {'records': [record]})()
        with patch('apps.imports.services.ratecard_chain.read_product_file', return_value=result):
            return load_catalogue(b'content')

    def test_keeps_row_number_precision_and_hash(self):
        catalogue = self.read()
        loaded = catalogue.masters[1516][0]
        self.assertEqual((loaded.source_row, loaded.item_no, loaded.greater), (7, 2, 750.0001))
        self.assertEqual(loaded.name, 'Line')
        self.assertEqual(len(catalogue.sha256), 64)

    def test_rejects_non_numeric_master(self):
        with self.assertRaises(SourceImportError):
            self.read(master_rate='ABC')


class ZoneSourceTests(SimpleTestCase):
    def rows(self, *lines):
        return read_zones((HEADER + ''.join(lines)).encode())[1]

    def test_postcode_keeps_leading_zero(self):
        rows = self.rows('"a","b","TEAMEX","DARWIN","NT","0800","DRW","",""\n')
        self.assertEqual(rows[0]['postcode'], '0800')
        self.assertEqual(rows[0]['_row_number'], 2)

    def test_rejects_changed_columns(self):
        with self.assertRaises(SourceImportError):
            read_zones(b'carrier,suburb\nA,B\n')

    def test_rejects_short_row(self):
        with self.assertRaises(SourceImportError):
            read_zones((HEADER + 'a,b,TEAMEX\n').encode())

    def test_rejects_empty_and_oversize(self):
        with self.assertRaises(SourceImportError):
            read_zones(b'')
        with self.assertRaises(SourceImportError):
            read_zones(b'x' * (MAX_BYTES + 1))

    def test_reads_latin1_export(self):
        content = (HEADER + 'a,b,TEAMEX,CAF\xc9,SA,5000,ADL,,\n').encode('latin-1')
        self.assertEqual(read_zones(content)[1][0]['suburb'], 'CAF\xc9')

    def test_duplicates_and_conflicts_are_reported_not_resolved(self):
        summary = summarise_carrier(self.rows(
            'a,b,TFMX,NAMBOUR,QLD,4560,BNE,,\n', 'a,b,TFMX,Nambour,QLD,4560,NS2,,\n',
            'a,b,TFMX,ABERDEEN,NSW,2336,NS2,,\n', 'a,b,TFMX,ABERDEEN,NSW,2359,NS3,,\n',
            'a,b,TFMX,ABERDEEN,NSW,2359,NS3,,\n'))
        self.assertEqual(summary['duplicates_case_sensitive'], 1)
        self.assertEqual(summary['duplicates_case_insensitive'], 2)
        self.assertEqual(summary['ambiguous_suburb_state'], 2)
        self.assertEqual(summary['conflicts_with_postcode'], [['NAMBOUR', 'QLD', '4560']])


class ValidateSourcesTests(TestCase):
    zones = (HEADER + 'a,b,TEAMEX,MELBOURNE,VIC,3000,MELB,,\n'
                      'a,b,TEAMEX,NOWHERE,VIC,3999,NOPE,,\n').encode()

    def report(self):
        with patch('apps.imports.management.commands.validate_sth_rate_sources.load_catalogue',
                   return_value=teamex_catalogue()):
            return validate_sources(b'x', self.zones)

    def test_makes_no_database_queries(self):
        with self.assertNumQueries(0):
            report = self.report()
        self.assertEqual(report['scope'], 'VALIDATION_ONLY')
        self.assertFalse(report['operational_tables_updated'])
        self.assertFalse(report['quotes_use_these_files'])

    def test_coverage_and_unresolved_are_reported(self):
        report = self.report()
        teamex = report['carriers']['TEAMEX']
        self.assertEqual(teamex['zones_with_base_price'], 1)
        self.assertEqual(teamex['csv_zones_without_price'], ['NOPE'])
        self.assertIn('ZONE_TYPE_NOT_IN_ZONES_CSV:Line', teamex['unresolved'])
        self.assertEqual(report['rates']['missing_reference_details'][0]['reachable_carriers'],
                         ['TEAMEX'])

    def test_command_writes_only_the_requested_report(self):
        with tempfile.TemporaryDirectory() as folder:
            rates_path, zones_path = Path(folder, 'rates_all.xls'), Path(folder, 'zones.csv')
            out_path = Path(folder, 'report.json')
            rates_path.write_bytes(b'x')
            zones_path.write_bytes(self.zones)
            stdout = StringIO()
            with patch('apps.imports.management.commands.validate_sth_rate_sources.load_catalogue',
                       return_value=teamex_catalogue()), self.assertNumQueries(0):
                call_command('validate_sth_rate_sources', rates=str(rates_path), zones=str(zones_path),
                             json_out=str(out_path), stdout=stdout)
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),
                             ['rates_all.xls', 'report.json', 'zones.csv'])
            self.assertIn('cases', json.loads(out_path.read_text(encoding='utf-8'))['carriers']['TEAMEX'])
            self.assertNotIn('"cases"', stdout.getvalue())


class RealSourceTests(SimpleTestCase):
    def test_real_files_when_supplied(self):
        rates_path = os.environ.get('RATES_ALL_XLS')
        zones_path = os.environ.get('ZONES_CSV')
        if not rates_path or not zones_path:
            self.skipTest('Set RATES_ALL_XLS and ZONES_CSV to run against real exports.')
        report = validate_sources(Path(rates_path).read_bytes(), Path(zones_path).read_bytes())
        self.assertIn(1524, report['rates']['missing_references'])
        teamex = report['carriers']['TEAMEX']
        self.assertGreater(teamex['zones_with_base_price'], 0)
        self.assertTrue(any(key.startswith('ZONE_TYPE_NOT_IN_ZONES_CSV') for key in teamex['unresolved']))
        case = next(case for case in teamex['cases'] if case['status'] != NOT_APPLICABLE)
        self.assertIn(1516, case['path'])
