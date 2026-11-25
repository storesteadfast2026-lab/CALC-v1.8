"""Run read-only operational procedure tests from historical dispatch data."""

import json
from pathlib import Path

import xlrd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Client
from apps.freight.services.operational_test_runner import run_operational_tests


class Command(BaseCommand):
    help = (
        'Test the operational quote procedure against unique historical destinations. '
        'This command is read-only and does not compare historical prices.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--client', default='STH')
        parser.add_argument(
            '--source',
            default='/app/uploaded_data/Aditional Data for check/_current.xls',
        )
        parser.add_argument('--locations', type=int, default=100)
        parser.add_argument(
            '--out-dir', default=str(Path(settings.BASE_DIR) / 'reports' / 'operational_tests')
        )

    def handle(self, *args, **options):
        client_code = str(options['client']).strip().upper()
        if options['locations'] < 1:
            raise CommandError('--locations must be at least 1.')
        if not Client.objects.filter(code__iexact=client_code, active=True).exists():
            raise CommandError(f'Active client {client_code} does not exist.')
        try:
            report, paths = run_operational_tests(
                Path(options['source']), client_code, options['locations'], Path(options['out_dir'])
            )
        except (OSError, ValueError, xlrd.XLRDError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS('Operational procedure test completed.'))
        for name, path in paths.items():
            self.stdout.write(f'{name}: {path}')
        self.stdout.write(json.dumps(report['summary'], sort_keys=True))
