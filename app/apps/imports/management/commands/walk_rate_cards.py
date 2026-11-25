"""Print the rate-card walk of STH cases as JSON. Reads files only, never the database."""
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.imports.services.ratecard_walk import WalkError, load_sources, walk_all
from apps.imports.services.xlsx_reader import SourceImportError


def _case_fields(raw):
    try:
        return {
            'suburb': raw['suburb'], 'state': raw['state'], 'postcode': str(raw['postcode']),
            'weight': Decimal(str(raw['weight'])), 'cubic': Decimal(str(raw['cubic'])),
            'pallets': int(raw.get('pallets', 0)), 'cartons': int(raw.get('cartons', 0)),
            'tailgate': bool(raw.get('tailgate', False)),
            'hand_unload': bool(raw.get('hand_unload', False)),
        }
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise CommandError(f'Invalid case {raw}: {exc!r}') from exc


class Command(BaseCommand):
    help = 'Walk rate cards for STH cases from files pinned by SHA-256. Changes nothing.'

    def add_arguments(self, parser):
        for name in ('rates', 'zones', 'fuel'):
            parser.add_argument(f'--{name}', required=True)
            parser.add_argument(f'--{name}-sha256', required=True)
        parser.add_argument('--cases', help='JSON file with a list of cases.')
        parser.add_argument('--suburb')
        parser.add_argument('--state')
        parser.add_argument('--postcode')
        parser.add_argument('--weight')
        parser.add_argument('--cubic')
        parser.add_argument('--pallets', type=int, default=0)
        parser.add_argument('--cartons', type=int, default=0)
        parser.add_argument('--tailgate', action='store_true')
        parser.add_argument('--hand-unload', action='store_true')

    def handle(self, *args, **options):
        if options['cases']:
            try:
                cases = json.loads(Path(options['cases']).read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                raise CommandError(f'Cases file: {exc}') from exc
        else:
            cases = [{key: options[key] for key in (
                'suburb', 'state', 'postcode', 'weight', 'cubic', 'pallets', 'cartons',
                'tailgate', 'hand_unload')}]
        parsed = [_case_fields(case) for case in cases]
        try:
            sources = load_sources(
                Path(options['rates']).read_bytes(), Path(options['zones']).read_bytes(),
                Path(options['fuel']).read_bytes(), rates_sha256=options['rates_sha256'],
                zones_sha256=options['zones_sha256'], fuel_sha256=options['fuel_sha256'],
                rates_filename=Path(options['rates']).name)
        except (OSError, WalkError, SourceImportError) as exc:
            raise CommandError(str(exc)) from exc
        output = [{'case': raw, 'results': walk_all(sources, **fields)}
                  for raw, fields in zip(cases, parsed)]
        self.stdout.write(json.dumps(output, indent=2, ensure_ascii=False, default=str))
