"""Run the workbook consignments through every STH destination. Changes no data."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.imports.services import ratecard_coverage as coverage
from apps.imports.services import ratecard_validate as validate
from apps.imports.services.ratecard_compare import (
    CompareError, carrier_configs, check_zones, load_cases, product_map, with_totals,
)
from apps.imports.services.ratecard_walk import WalkError, load_sources
from apps.imports.services.xlsx_reader import SourceImportError

SOURCES = ('rates', 'zones', 'fuel')
LOCAL_TIME = ZoneInfo('Australia/Adelaide')
WORKBOOK_CASES = 'apps/freight/fixtures/sth_excel_validated_cases_0629.1513.csv'
PROGRESS_EVERY = 10000


def _pinned(path, expected, label):
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        raise CommandError(f'{label}: {exc}') from exc
    if hashlib.sha256(content).hexdigest() != expected.strip().lower():
        raise CommandError(f'{label}: the file does not match the expected SHA-256.')
    return content


class Command(BaseCommand):
    help = 'Walk the workbook consignments through every STH destination. Changes no data.'

    def add_arguments(self, parser):
        for name in SOURCES:
            parser.add_argument(f'--{name}', required=True)
            parser.add_argument(f'--{name}-sha256', required=True)
        parser.add_argument('--cases', default=str(Path(settings.BASE_DIR) / WORKBOOK_CASES))
        parser.add_argument('--client', default='STH')
        parser.add_argument('--out-root', help='Default: uploaded_data/rate_compare.')
        parser.add_argument('--limit', type=int, help='Only the first N destinations, for a trial.')

    def handle(self, *args, **options):
        client = options['client']
        contents = {name: _pinned(options[name], options[f'{name}_sha256'], name) for name in SOURCES}
        rates_name = Path(options['rates']).name
        try:
            check_zones(contents['zones'])
            cases = load_cases(options['cases'])
            products = product_map(cases, client)
            cases = [with_totals(case, products) for case in coverage.shapes(cases)]
            places = coverage.destinations(contents['zones'])[:options['limit']]
            sources = load_sources(contents['rates'], contents['zones'], contents['fuel'],
                                   rates_sha256=options['rates_sha256'], zones_sha256=options['zones_sha256'],
                                   fuel_sha256=options['fuel_sha256'], rates_filename=rates_name)
            lines = validate.rate_rows(contents['rates'], rates_name)
            fuels = validate.fuel_rates(contents['fuel'])
            configs = validate.carrier_configs_or_fail(client, carrier_configs)
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

        def progress(done, total):
            if done % PROGRESS_EVERY < coverage.CHUNK:
                self.stdout.write(f'{done} de {total}')
                self.stdout.flush()

        self.stdout.write(f'{len(places)} destinos, {len(cases)} envíos')
        summary = coverage.sweep(sources, cases, places, client, configs, products, lines, fuels,
                                 folder / 'coverage.csv.gz', progress)
        meta = {'run': run, 'client': client,
                'sources': {name: options[f'{name}_sha256'].strip().lower() for name in SOURCES}}
        (folder / 'coverage.md').write_text(coverage.render_markdown(meta, summary), encoding='utf-8')
        self.stdout.write(f'{folder}\n{json.dumps(summary.labels)}\nerrores {sum(summary.errors.values())}')
