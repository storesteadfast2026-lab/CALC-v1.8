"""Compare the rate-card walk with the app calculator and write a report. Changes no data."""
import hashlib
import json
import shutil
from datetime import datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.imports.services.ratecard_compare import (
    CompareError, attach_translogic, carrier_configs, check_zones, compare_case, counts, load_cases, with_overlength,
    product_map, read_translogic, render_markdown, with_totals,
)

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
    help = 'Compare the rate-card walk with the app for STH cases. Changes no data.'

    def add_arguments(self, parser):
        for name in SOURCES:
            parser.add_argument(f'--{name}', required=True)
            parser.add_argument(f'--{name}-sha256', required=True)
        parser.add_argument('--cases', required=True, help='Workbook cases, CSV or JSON.')
        parser.add_argument('--client', default='STH')
        parser.add_argument('--translogic', help='Optional CSV of TransLogic quotes.')
        parser.add_argument('--translogic-sha256')
        parser.add_argument('--source-date', help='Date of the sources, AAAA-MM-DD. Required with --translogic.')
        parser.add_argument('--out-root', help='Default: uploaded_data/rate_compare.')

    def handle(self, *args, **options):
        if options['translogic'] and not (options['translogic_sha256'] and options['source_date']):
            raise CommandError('--translogic needs --translogic-sha256 and --source-date.')
        contents = {name: _pinned(options[name], options[f'{name}_sha256'], name) for name in SOURCES}
        try:
            check_zones(contents['zones'])
            cases = load_cases(options['cases'])
            products = product_map(cases, options['client'])
            cases = [with_totals(case, products) for case in cases]
            translogic = None
            if options['translogic']:
                translogic = _pinned(options['translogic'], options['translogic_sha256'], 'translogic')
                rows = read_translogic(translogic)
        except CompareError as exc:
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

        copies = {name: folder / Path(options[name]).name for name in SOURCES}
        for name, target in copies.items():
            target.write_bytes(contents[name])
        cases_path = folder / 'cases.json'
        cases_path.write_text(json.dumps(cases, indent=1, ensure_ascii=False), encoding='utf-8')
        if translogic is not None:
            shutil.copyfile(options['translogic'], folder / Path(options['translogic']).name)

        walked = StringIO()
        call_command('walk_rate_cards', stdout=walked, cases=str(cases_path),
                     **{name: str(path) for name, path in copies.items()},
                     **{f'{name}_sha256': options[f'{name}_sha256'] for name in SOURCES})
        report = {'run': run, 'client': options['client'],
                  'sources': {name: options[f'{name}_sha256'].strip().lower() for name in SOURCES}}
        try:
            # Nothing here should write; the rollback makes that a guarantee.
            with transaction.atomic():
                configs = carrier_configs(options['client'])
                if not configs:
                    raise CompareError(f"No carrier configuration for client {options['client']}.")
                report['cases'] = [compare_case(case, {'results': with_overlength(item['results'], case,
                                                                                  options['client'], configs, products)},
                                                options['client'], configs, products)
                                   for case, item in zip(cases, json.loads(walked.getvalue()))]
                transaction.set_rollback(True)
        except CompareError as exc:
            raise CommandError(str(exc)) from exc
        if translogic is not None:
            attach_translogic(report, rows, options['source_date'])
        report['counts'] = counts(report)
        (folder / 'compare.json').write_text(
            json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
        (folder / 'compare.md').write_text(render_markdown(report), encoding='utf-8')
        self.stdout.write(f'{folder}\n{json.dumps(report["counts"])}')
