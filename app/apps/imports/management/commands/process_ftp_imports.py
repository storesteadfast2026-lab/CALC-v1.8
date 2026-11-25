from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.imports.services.ftp_automation import process_due_ftp_configurations


class Command(BaseCommand):
    help = (
        'Register all enabled FTP files due under the shared schedule as immutable snapshots. '
        'This command never activates operational data.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--watch',
            action='store_true',
            help='Keep checking due configurations instead of running one cycle.',
        )
        parser.add_argument(
            '--poll-seconds',
            type=int,
            default=60,
            help='Seconds between checks in watch mode (10 to 3600).',
        )

    def handle(self, *args, **options):
        poll_seconds = options['poll_seconds']
        if not 10 <= poll_seconds <= 3600:
            raise CommandError('--poll-seconds must be between 10 and 3600.')

        if not options['watch']:
            self._run_cycle(always_report=True)
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'FTP import scheduler started; checking every {poll_seconds} seconds. '
                'Operational data activation is disabled.'
            )
        )
        try:
            while True:
                try:
                    self._run_cycle(always_report=False)
                except Exception as exc:  # Keep the scheduler alive after infrastructure errors.
                    self.stderr.write(self.style.ERROR(f'FTP scheduler cycle failed: {exc}'))
                finally:
                    close_old_connections()
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('FTP import scheduler stopped.'))

    def _run_cycle(self, *, always_report):
        summary = process_due_ftp_configurations()
        if always_report or summary['processed'] or summary['errors']:
            self.stdout.write(
                'FTP import cycle: '
                f'{summary["configured"]} enabled file(s), '
                f'{summary["processed"]} processed, '
                f'{summary["new_snapshots"]} new snapshot(s), '
                f'{summary["unchanged"]} unchanged, '
                f'{summary["waiting"]} waiting, '
                f'{summary["errors"]} error(s), '
                f'{summary["skipped"]} not due. '
                'No operational data was activated.'
            )
