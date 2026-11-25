"""Validate rates_all.xls + zones.csv for STH. Reads files only; writes no data."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.imports.services.ratecard_chain import (
    APPLICABLE, SUPPORTED_ROOTS, CaseContext, load_catalogue, priced_zones, resolve_case,
)
from apps.imports.services.xlsx_reader import SourceImportError
from apps.imports.services.zone_source import read_zones, summarise_carrier

WEIGHTS = {
    'TFMX': (100, 251, 751, 1501, 3001, 6000),
    'TEAMTAS': (4000, 10000, 14000, 17000, 20000),
}
DEFAULT_WEIGHTS = (100, 751, 1501, 3001, 6000)


def validate_sources(rates_content, zones_content, rates_name='rates_all.xls'):
    """Return the full report; separated from the command so tests can call it."""
    catalogue = load_catalogue(rates_content, rates_name)
    zones_sha256, rows = read_zones(zones_content)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['carrier']].append(row)
    report = {
        'scope': 'VALIDATION_ONLY',
        'operational_tables_updated': False,
        'quotes_use_these_files': False,
        'rates': {'sha256': catalogue.sha256, 'rows': catalogue.rows,
                  'masters': len(catalogue.masters),
                  'missing_references': catalogue.missing_references(),
                  'missing_reference_details': catalogue.missing_reference_details()},
        'zones': {'sha256': zones_sha256, 'rows': len(rows), 'carriers': len(grouped)},
        'carriers': {},
    }
    for carrier in SUPPORTED_ROOTS:
        report['carriers'][carrier] = _validate_carrier(catalogue, carrier, grouped.get(carrier, []))
    return report


def _validate_carrier(catalogue, carrier, rows):
    summary = summarise_carrier(rows)
    destinations = {}
    for row in rows:
        destinations.setdefault((row['zone'], row['subzone'], row['state']), row)
    statuses, bases = Counter(), Counter()
    unresolved, cases, price_lines, reached = Counter(), [], {}, set()
    zones_with_price = set()
    for (zone, subzone, state), row in sorted(destinations.items()):
        if not zone:
            continue
        for weight in WEIGHTS.get(carrier, DEFAULT_WEIGHTS):
            for pallets, cartons in ((1, 0), (0, 1)):
                ctx = CaseContext(zone=zone, subzone=subzone, state=state, postcode=row['postcode'],
                                  weight=weight, pallets=pallets, cartons=cartons)
                result = resolve_case(catalogue, carrier, ctx)
                statuses[result.status] += 1
                bases[result.base_status] += 1
                reached.update(result.path)
                if result.base_status == APPLICABLE:
                    zones_with_price.add(zone)
                for item in result.unresolved:
                    unresolved[f"{item['reason']}:{item.get('name') or item.get('card')}"] += 1
                for item in result.percent_of_price:
                    price_lines[(item['card'], item['name'])] = item['rate']
                cases.append({'zone': zone, 'subzone': subzone, 'state': state,
                              'zones_csv_row': row['_row_number'], 'weight': weight,
                              'freight_type': 'P' if pallets else 'C', 'status': result.status,
                              'base_status': result.base_status, 'path': result.path,
                              'freight': result.freight, 'surcharges': result.surcharges,
                              'percent_of_price': result.percent_of_price, 'unresolved': result.unresolved})
    csv_zones = set(summary['zones'])
    card_zones = priced_zones(catalogue, reached)
    return {
        **{key: value for key, value in summary.items() if key != 'zones'},
        'root_card': SUPPORTED_ROOTS[carrier],
        'zones_in_csv': len(csv_zones),
        'zones_with_base_price': len(zones_with_price),
        'csv_zones_without_price': sorted(csv_zones - zones_with_price),
        'priced_zones_missing_from_csv': sorted(card_zones - csv_zones),
        'case_status': dict(statuses),
        'base_status': dict(bases),
        'unresolved': dict(unresolved),
        'percent_of_price_lines': [{'card': card, 'name': name, 'rate': rate}
                                   for (card, name), rate in sorted(price_lines.items())],
        'cases': cases,
    }


class Command(BaseCommand):
    help = 'Validate rates_all.xls and zones.csv for STH without changing any data.'

    def add_arguments(self, parser):
        parser.add_argument('--rates', required=True)
        parser.add_argument('--zones', required=True)
        parser.add_argument('--json-out', help='Optional path for the full report with every case.')

    def handle(self, *args, **options):
        try:
            report = validate_sources(Path(options['rates']).read_bytes(),
                                      Path(options['zones']).read_bytes(),
                                      Path(options['rates']).name)
        except (OSError, SourceImportError) as exc:
            raise CommandError(str(exc)) from exc
        if options.get('json_out'):
            Path(options['json_out']).write_text(json.dumps(report, indent=1), encoding='utf-8')
        brief = {**report, 'carriers': {
            name: {key: value for key, value in data.items()
                   if key not in ('cases', 'conflicts_with_postcode')}
            for name, data in report['carriers'].items()}}
        self.stdout.write(json.dumps(brief, indent=1))
