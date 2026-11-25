"""Label STH routes and prove the load path. Changes no data outside the disposable database."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.imports.services import ratecard_validate as validate
from apps.imports.services.ratecard_compare import (
    CompareError, carrier_configs, check_zones, load_cases, product_map, with_totals,
)
from apps.imports.services.ratecard_walk import WalkError, load_sources
from apps.imports.services.xlsx_reader import SourceImportError

SOURCES = ('rates', 'zones', 'fuel')
LOCAL_TIME = ZoneInfo('Australia/Adelaide')


def _pinned(path, expected, label):
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        raise CommandError(f'{label}: {exc}') from exc
    if hashlib.sha256(content).hexdigest() != expected.strip().lower():
        raise CommandError(f'{label}: the file does not match the expected SHA-256.')
    return content


class Command(BaseCommand):
    help = 'Label STH routes and recalculate their charges. Changes no data.'

    def add_arguments(self, parser):
        for name in SOURCES:
            parser.add_argument(f'--{name}', required=True)
            parser.add_argument(f'--{name}-sha256', required=True)
        parser.add_argument('--cases', required=True, help='Workbook cases, CSV or JSON.')
        parser.add_argument('--client', default='STH')
        parser.add_argument('--out-root', help='Default: uploaded_data/rate_compare.')
        parser.add_argument('--rehearse-load', action='store_true',
                            help='Load the sources first. Disposable rehearsal database only.')

    def _routes(self, sources, cases, client, products, lines, fuels):
        """Everything reads; the rollback makes that a guarantee."""
        report_cases = []
        with transaction.atomic():
            configs = validate.carrier_configs_or_fail(client, carrier_configs)
            for case in cases:
                compared, routes = validate.route_rows(sources, case, client, configs, products, lines, fuels)
                report_cases.append({'id': case['id'], 'case': case, 'app_error': compared['app_error'],
                                     'routes': routes})
            transaction.set_rollback(True)
        return report_cases

    def handle(self, *args, **options):
        client = options['client']
        contents = {name: _pinned(options[name], options[f'{name}_sha256'], name) for name in SOURCES}
        rates_name = Path(options['rates']).name
        try:
            if options['rehearse_load']:
                validate.require_disposable()
            check_zones(contents['zones'])
            cases = load_cases(options['cases'])
            products = product_map(cases, client)
            cases = [with_totals(case, products) for case in cases]
            sources = load_sources(contents['rates'], contents['zones'], contents['fuel'],
                                   rates_sha256=options['rates_sha256'], zones_sha256=options['zones_sha256'],
                                   fuel_sha256=options['fuel_sha256'], rates_filename=rates_name)
            lines = validate.rate_rows(contents['rates'], rates_name)
            fuels = validate.fuel_rates(contents['fuel'])
        except (CompareError, validate.ValidateError, WalkError, SourceImportError) as exc:
            raise CommandError(str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise CommandError(f'Cases file: {exc}') from exc

        run = datetime.now(LOCAL_TIME).strftime('%Y%m%d.%H%M')
        root = Path(options['out_root'] or Path(settings.BASE_DIR) / 'uploaded_data' / 'rate_compare')
        folder = root / run
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise CommandError(f'{folder} already exists. Run it again in a minute.') from exc
        for name in SOURCES:
            (folder / Path(options[name]).name).write_bytes(contents[name])
        (folder / 'cases.json').write_text(json.dumps(cases, indent=1, ensure_ascii=False), encoding='utf-8')

        proof = {'status': 'NO_EJECUTADA'}
        try:
            if options['rehearse_load']:
                rates_file, zones_file = validate.load_rehearsal(client, contents['rates'], contents['zones'])
                row_sources = validate.sources_from_rows(rates_file, zones_file, contents['fuel'],
                                                         options['fuel_sha256'].strip().lower())
                proof = validate.load_proof(sources, row_sources, cases)
            report_cases = self._routes(sources, cases, client, products, lines, fuels)
        except (CompareError, validate.ValidateError, SourceImportError) as exc:
            raise CommandError(str(exc)) from exc

        report = {'run': run, 'client': client, 'load_proof': proof, 'cases': report_cases,
                  'sources': {name: options[f'{name}_sha256'].strip().lower() for name in SOURCES}}
        report['counts'], report['by_carrier'] = validate.counts(report)
        report['charges_checked'] = sum(route['charges_checked'] for case in report_cases
                                        for route in case['routes'])
        (folder / 'routes.json').write_text(
            json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
        (folder / 'routes.md').write_text(validate.render_markdown(report), encoding='utf-8')
        self.stdout.write(f"{folder}\n{json.dumps(report['counts'])}\n{proof['status']}")
