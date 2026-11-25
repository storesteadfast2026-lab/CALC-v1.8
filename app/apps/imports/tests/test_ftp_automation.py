from __future__ import annotations

import tempfile
from datetime import time, timedelta
from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.clients.models import Client
from apps.imports.models import (
    ExternalDataFile,
    FtpImportConfiguration,
    FtpImportSchedule,
    ProductSourceRow,
)
from apps.imports.services.ftp_automation import (
    process_due_ftp_configurations,
    process_ftp_configuration,
)


class FtpImportAutomationTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            code='STH',
            name='Stenhoj Australia',
            active=True,
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'uploaded_data'
        self.media = Path(self.temp.name) / 'media'
        self.root.mkdir()
        self.media.mkdir()
        settings_override = override_settings(
            FTP_UPLOADED_DATA_DIR=str(self.root),
            MEDIA_ROOT=str(self.media),
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.schedule, _ = FtpImportSchedule.objects.get_or_create()
        self.schedule.active = True
        self.schedule.run_time = time(0, 0)
        self.schedule.monday = True
        self.schedule.tuesday = True
        self.schedule.wednesday = True
        self.schedule.thursday = True
        self.schedule.friday = True
        self.schedule.saturday = True
        self.schedule.sunday = True
        self.schedule.retry_minutes = 15
        self.schedule.save()

    def _configuration(self, **overrides):
        values = {
            'client': self.client_obj,
            'file_type': 'PRODUCTS',
            'filename': 'products.xls',
            'minimum_file_age_seconds': 0,
            'active': True,
        }
        values.update(overrides)
        return FtpImportConfiguration.objects.create(**values)

    def test_manual_run_registers_snapshot_without_operational_import(self):
        (self.root / 'products.xls').write_bytes(b'current-product-master')
        configuration = self._configuration()

        result = process_ftp_configuration(configuration.pk, trigger='MANUAL')

        configuration.refresh_from_db()
        self.assertEqual(result['status'], 'NEW_SNAPSHOT')
        self.assertEqual(configuration.last_status, 'NEW_SNAPSHOT')
        self.assertIsNotNone(configuration.last_snapshot_id)
        self.assertEqual(ExternalDataFile.objects.count(), 1)
        self.assertEqual(ProductSourceRow.objects.count(), 0)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type='FTP_SCHEDULED_FILE_REGISTERED',
                client=self.client_obj,
            ).exists()
        )

    def test_automatic_run_waits_until_configured_time(self):
        (self.root / 'products.xls').write_bytes(b'current-product-master')
        configuration = self._configuration()
        self.schedule.run_time = time(23, 59)
        self.schedule.save(update_fields=['run_time', 'updated_at'])
        local_date = timezone.localdate()
        before_schedule = timezone.make_aware(
            timezone.datetime.combine(local_date, time(12, 0)),
            timezone.get_current_timezone(),
        )

        summary = process_due_ftp_configurations(now=before_schedule)

        configuration.refresh_from_db()
        self.assertEqual(summary['processed'], 0)
        self.assertEqual(summary['skipped'], 1)
        self.assertEqual(configuration.last_status, 'NEVER')

    def test_automatic_success_runs_only_once_per_local_day(self):
        (self.root / 'products.xls').write_bytes(b'current-product-master')
        configuration = self._configuration()
        now = timezone.now()

        first = process_due_ftp_configurations(now=now)
        second = process_due_ftp_configurations(now=now + timedelta(minutes=30))

        self.assertEqual(first['new_snapshots'], 1)
        self.assertEqual(second['processed'], 0)
        self.assertEqual(second['skipped'], 1)
        self.assertEqual(ExternalDataFile.objects.count(), 1)
        configuration.refresh_from_db()
        self.assertEqual(timezone.localdate(configuration.last_success_at), timezone.localdate(now))

    def test_inactive_configuration_is_not_processed_by_scheduler(self):
        (self.root / 'products.xls').write_bytes(b'current-product-master')
        self._configuration(active=False)

        summary = process_due_ftp_configurations()

        self.assertEqual(summary['configured'], 0)
        self.assertEqual(ExternalDataFile.objects.count(), 0)

    def test_missing_file_waits_and_respects_retry_interval(self):
        configuration = self._configuration()
        now = timezone.now()

        first = process_due_ftp_configurations(now=now)
        too_soon = process_due_ftp_configurations(now=now + timedelta(minutes=5))
        retry = process_due_ftp_configurations(now=now + timedelta(minutes=16))

        self.assertEqual(first['waiting'], 1)
        self.assertEqual(too_soon['processed'], 0)
        self.assertEqual(retry['waiting'], 1)
        configuration.refresh_from_db()
        self.assertEqual(configuration.last_status, 'WAITING')
        self.assertEqual(
            configuration.last_message,
            'File not found: products.xls. Upload the completed file to the FTP inbox '
            'using this exact filename.',
        )
        event = AuditEvent.objects.filter(
            event_type='FTP_SCHEDULED_FILE_WAITING',
        ).latest('created_at')
        self.assertEqual(event.message, configuration.last_message)

    def test_changed_file_creates_new_snapshot_on_next_day(self):
        source = self.root / 'products.xls'
        source.write_bytes(b'product-master-day-one')
        self._configuration()
        now = timezone.now()
        process_due_ftp_configurations(now=now)
        source.write_bytes(b'product-master-day-two')

        summary = process_due_ftp_configurations(now=now + timedelta(days=1))

        self.assertEqual(summary['new_snapshots'], 1)
        self.assertEqual(ExternalDataFile.objects.count(), 2)

    def test_shared_schedule_skips_disabled_weekday(self):
        (self.root / 'products.xls').write_bytes(b'current-product-master')
        self._configuration()
        now = timezone.now()
        day_field = (
            'monday', 'tuesday', 'wednesday', 'thursday',
            'friday', 'saturday', 'sunday',
        )[timezone.localtime(now).weekday()]
        setattr(self.schedule, day_field, False)
        self.schedule.save(update_fields=[day_field, 'updated_at'])

        summary = process_due_ftp_configurations(now=now)

        self.assertEqual(summary['processed'], 0)
        self.assertEqual(summary['skipped'], 1)
        self.assertEqual(ExternalDataFile.objects.count(), 0)

    def test_shared_run_processes_all_enabled_client_files_together(self):
        second_client = Client.objects.create(code='TWO', name='Second', active=True)
        (self.root / 'products.xls').write_bytes(b'products')
        (self.root / 'stock.xls').write_bytes(b'stock')
        self._configuration()
        self._configuration(
            client=second_client,
            file_type='STOCK',
            filename='stock.xls',
        )

        summary = process_due_ftp_configurations(now=timezone.now())

        self.assertEqual(summary['configured'], 2)
        self.assertEqual(summary['new_snapshots'], 2)
        self.assertEqual(ExternalDataFile.objects.count(), 2)

    def test_configuration_rejects_paths_outside_uploaded_data_root(self):
        configuration = FtpImportConfiguration(
            client=self.client_obj,
            file_type='PRODUCTS',
            filename='../products.xls',
        )

        with self.assertRaises(ValidationError):
            configuration.full_clean()
