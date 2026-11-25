"""Preview or explicitly register verified exception evidence; no Product Apply."""
from pathlib import Path
import json
from django.core.management.base import BaseCommand, CommandError
from apps.imports.services.reconciliation_exception_registry import (
    RegistryInputError, persist_exception_evidence,
)


class Command(BaseCommand):
    help = 'Preview verified global import exceptions; --apply persists review-only entries.'

    def add_arguments(self, parser):
        parser.add_argument('--report', required=True, help='REPORT.json from a verified reconciliation')
        parser.add_argument('--csv', required=True, help='EXCEPTIONS.csv from the same run')
        parser.add_argument('--apply', action='store_true', help='Explicitly persist review-only exception entries')

    def handle(self, *args, **options):
        try:
            report = Path(options['report']).read_bytes()
            csv_data = Path(options['csv']).read_bytes()
            result = persist_exception_evidence(report, csv_data, apply=options['apply'])
        except (OSError, RegistryInputError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, sort_keys=True))
