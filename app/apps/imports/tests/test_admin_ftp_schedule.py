import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.clients.models import Client
from apps.imports.models import ExternalDataFile, FtpImportConfiguration, FtpImportSchedule
from apps.imports.services.ftp_automation import configuration_is_due


class FtpImportScheduleAdminTests(TestCase):
    def setUp(self):
        inbox = tempfile.TemporaryDirectory()
        self.addCleanup(inbox.cleanup)
        inbox_settings = override_settings(FTP_UPLOADED_DATA_DIR=inbox.name)
        inbox_settings.enable()
        self.addCleanup(inbox_settings.disable)
        self.user = get_user_model().objects.create_superuser(
            username='ftp-admin',
            email='ftp-admin@example.com',
            password='test-pass',
        )
        self.client.force_login(self.user)
        self.client_record = Client.objects.create(
            code='STH',
            name='Nexion Oceania',
            active=True,
        )
        self.schedule, _created = FtpImportSchedule.objects.get_or_create()

    def test_schedule_page_shows_file_checkboxes(self):
        response = self.client.get(
            reverse('admin:imports_ftpimportschedule_change', args=[self.schedule.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Scheduled')
        self.assertContains(response, 'Operational status')
        self.assertContains(response, 'Not activated')
        self.assertContains(response, 'Operational database (baseline)')
        self.assertContains(response, 'products.xls')
        self.assertContains(response, 'stock.xls')
        self.assertContains(response, 'fuel.xls')
        self.assertContains(response, 'postcodes.xls')
        self.assertContains(response, 'rates_all.xls')
        self.assertContains(response, 'zones.csv')
        self.assertContains(response, 'Import Centre')
        self.assertContains(response, '>Process from FTP</a>', count=6)
        self.assertContains(response, 'Check inbox now')
        self.assertContains(response, 'Run at the scheduled time today')
        self.assertContains(response, 'Schedule starts')
        self.assertContains(response, 'Recent imports')
        self.assertContains(response, 'Application inbox:')
        self.assertContains(response, 'File not visible', count=6)

    def _save_schedule_at(self, now, **overrides):
        fields = {
            'active': 'on', 'run_time': '14:16:00', 'retry_minutes': '15',
            'monday': 'on', 'tuesday': 'on', 'wednesday': 'on',
            'thursday': 'on', 'friday': 'on', 'enabled_files': ['FUEL|fuel.xls'],
            '_continue': 'Save and continue editing',
        }
        fields.update(overrides)
        with patch('apps.imports.admin_ftp_configuration.timezone.now', return_value=now):
            response = self.client.post(
                reverse('admin:imports_ftpimportschedule_change', args=[self.schedule.pk]), fields,
            )
        self.schedule.refresh_from_db()
        return response

    def _adelaide_time(self, day, hour, minute=0):
        return timezone.make_aware(datetime(2026, 11, day, hour, minute))

    def test_schedule_change_defaults_to_next_enabled_day(self):
        friday = self._adelaide_time(27, 14)
        monday_run = self._adelaide_time(30, 14, 16)

        response = self._save_schedule_at(friday)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.schedule.starts_at, monday_run)
        configuration = FtpImportConfiguration.objects.get(filename='fuel.xls')
        self.assertFalse(configuration_is_due(configuration, now=self._adelaide_time(27, 15)))
        self.assertTrue(configuration_is_due(configuration, now=monday_run))

    def test_run_today_checks_again_at_the_new_time_and_keeps_retry_interval(self):
        now = self._adelaide_time(25, 14, 10)
        run_time = self._adelaide_time(25, 14, 16)
        response = self._save_schedule_at(now, run_today='on')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.schedule.starts_at, run_time)
        confirmation = self.client.get(response.url)
        self.assertContains(confirmation, 'Wed 25 Nov 2026, 14:16:00 ACDT')

        configuration = FtpImportConfiguration.objects.get(filename='fuel.xls')
        configuration.last_success_at = now
        configuration.last_checked_at = now
        self.assertFalse(configuration_is_due(configuration, now=now))
        self.assertTrue(configuration_is_due(configuration, now=run_time))

        configuration.last_checked_at = run_time
        self.assertFalse(configuration_is_due(configuration, now=run_time + timedelta(minutes=5)))
        self.assertTrue(configuration_is_due(configuration, now=run_time + timedelta(minutes=15)))
        configuration.last_success_at = run_time
        self.assertFalse(configuration_is_due(configuration, now=run_time + timedelta(minutes=15)))

        response = self._save_schedule_at(now, retry_minutes='30')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.schedule.starts_at, run_time)

    def test_run_today_requires_a_future_time_on_an_enabled_day(self):
        with self.subTest(reason='past time'):
            response = self._save_schedule_at(self._adelaide_time(25, 15), run_today='on')
            self.assertContains(response, 'Choose a time later than the current Adelaide time.')
            self.assertIsNone(self.schedule.starts_at)

        with self.subTest(reason='disabled day'):
            response = self._save_schedule_at(self._adelaide_time(28, 14), run_today='on')
            self.assertContains(response, 'Activate the schedule and enable today first.')
            self.assertIsNone(self.schedule.starts_at)

    def test_schedule_page_reports_file_visible_in_configured_inbox(self):
        with tempfile.TemporaryDirectory() as temp_root:
            ftp_root = Path(temp_root) / 'ftp_inbox'
            ftp_root.mkdir()
            (ftp_root / 'products.xls').write_bytes(b'product bytes')
            with override_settings(FTP_UPLOADED_DATA_DIR=str(ftp_root)):
                response = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_change',
                        args=[self.schedule.pk],
                    ),
                )

        self.assertContains(response, str(ftp_root))
        self.assertContains(response, 'File visible', count=1)

    def test_recent_file_is_visibly_verifying_and_cannot_be_processed(self):
        with tempfile.TemporaryDirectory() as temp_root:
            ftp_root = Path(temp_root) / 'ftp_inbox'
            ftp_root.mkdir()
            (ftp_root / 'products.xls').write_bytes(b'product bytes')
            FtpImportConfiguration.objects.create(
                client=self.client_record,
                file_type='PRODUCTS',
                filename='products.xls',
                minimum_file_age_seconds=60,
                active=True,
            )
            with override_settings(FTP_UPLOADED_DATA_DIR=str(ftp_root)):
                response = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_change',
                        args=[self.schedule.pk],
                    ),
                )
                status_response = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_file_status',
                        args=['products'],
                    ),
                )

        self.assertContains(response, 'Verifying upload')
        self.assertContains(response, 'Do not process yet.')
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()['code'], 'verifying')
        self.assertFalse(status_response.json()['can_process'])

    def test_stable_file_is_ready_and_process_action_is_enabled(self):
        with tempfile.TemporaryDirectory() as temp_root:
            ftp_root = Path(temp_root) / 'ftp_inbox'
            ftp_root.mkdir()
            (ftp_root / 'products.xls').write_bytes(b'product bytes')
            FtpImportConfiguration.objects.create(
                client=self.client_record,
                file_type='PRODUCTS',
                filename='products.xls',
                minimum_file_age_seconds=0,
                active=True,
            )
            with override_settings(FTP_UPLOADED_DATA_DIR=str(ftp_root)):
                response = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_change',
                        args=[self.schedule.pk],
                    ),
                )
                status_response = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_file_status',
                        args=['products'],
                    ),
                )

        self.assertContains(response, 'Ready to process')
        self.assertContains(response, 'aria-disabled="false"')
        self.assertEqual(status_response.json()['code'], 'ready')
        self.assertTrue(status_response.json()['can_process'])

    def test_missing_scheduled_file_is_clear_and_process_action_is_disabled(self):
        with tempfile.TemporaryDirectory() as temp_root:
            ftp_root = Path(temp_root) / 'ftp_inbox'
            ftp_root.mkdir()
            FtpImportConfiguration.objects.create(
                client=self.client_record,
                file_type='PRODUCTS',
                filename='products.xls',
                minimum_file_age_seconds=60,
                active=True,
            )
            with override_settings(FTP_UPLOADED_DATA_DIR=str(ftp_root)):
                status_response = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_file_status',
                        args=['products'],
                    ),
                )

        self.assertEqual(status_response.json()['code'], 'missing')
        self.assertEqual(status_response.json()['label'], 'File not found')
        self.assertFalse(status_response.json()['can_process'])

    def test_schedule_page_shows_activated_rates_and_zones_as_in_use(self):
        rates = ExternalDataFile.objects.create(
            client=self.client_record,
            file_type='RATES',
            original_filename='rates_all.xls',
            status='ACTIVE',
            import_summary={
                'quotes_use_this_file': True,
                'operational_zones_source_id': 2,
                'operational_validation': {
                    'status': 'PASSED',
                    'warnings': [{'code': 'MISSING_RATE_CARD'}],
                },
            },
        )
        zones = ExternalDataFile.objects.create(
            client=self.client_record,
            file_type='ZONES',
            original_filename='zones.csv',
            status='ACTIVE',
            import_summary={
                'quotes_use_this_file': True,
                'operational_rates_source_id': rates.pk,
                'operational_validation': {
                    'status': 'PASSED',
                    'warnings': [{'code': 'AMBIGUOUS_DESTINATION'}],
                },
            },
        )
        rates.import_summary['operational_zones_source_id'] = zones.pk
        rates.save(update_fields=['import_summary'])

        response = self.client.get(
            reverse('admin:imports_ftpimportschedule_change', args=[self.schedule.pk]),
        )

        self.assertContains(response, 'In use — validation passed', count=2)
        self.assertContains(response, 'active operational source for STH quotes', count=2)
        self.assertNotContains(response, 'Validation required — baseline in use')

    def test_schedule_menu_link_opens_singleton_directly(self):
        response = self.client.get(
            reverse('admin:imports_ftpimportschedule_changelist'),
        )

        self.assertRedirects(
            response,
            reverse(
                'admin:imports_ftpimportschedule_change',
                args=[self.schedule.pk],
            ),
        )

    def test_admin_menu_has_one_import_entry_point(self):
        response = self.client.get(reverse('admin:index'))

        self.assertContains(response, 'Import Centre')
        hidden_import_entries = (
            'External data files',
            'FTP import configurations',
            'Product Masters',
            'Stock Masters',
            'Product source rows',
            'Stock source rows',
            'External data correction memorys',
            'Product reconciliation rules',
            'Import reconciliation exceptions',
        )
        for label in hidden_import_entries:
            with self.subTest(label=label):
                self.assertNotContains(response, label)

    def test_hidden_import_tools_remain_accessible_to_administrator(self):
        contextual_admin_urls = (
            'admin:imports_productmaster_changelist',
            'admin:imports_stockmaster_changelist',
            'admin:imports_productsourcerow_changelist',
            'admin:imports_stocksourcerow_changelist',
            'admin:imports_externaldatacorrectionmemory_changelist',
            'admin:imports_productreconciliationrule_changelist',
            'admin:imports_importreconciliationexception_changelist',
        )
        for url_name in contextual_admin_urls:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_saving_checkboxes_creates_and_disables_configurations(self):
        url = reverse(
            'admin:imports_ftpimportschedule_change',
            args=[self.schedule.pk],
        )
        base_data = {
            'active': 'on',
            'run_time': time(8, 0).strftime('%H:%M:%S'),
            'monday': 'on',
            'tuesday': 'on',
            'wednesday': 'on',
            'thursday': 'on',
            'friday': 'on',
            'retry_minutes': '15',
            '_save': 'Save',
        }

        response = self.client.post(
            url,
            {
                **base_data,
                'enabled_files': ['PRODUCTS|products.xls', 'STOCK|stock.xls'],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertSetEqual(
            set(
                FtpImportConfiguration.objects.filter(active=True).values_list(
                    'file_type', 'filename',
                )
            ),
            {('PRODUCTS', 'products.xls'), ('STOCK', 'stock.xls')},
        )

        response = self.client.post(
            url,
            {**base_data, 'enabled_files': ['FUEL|fuel.xls']},
        )

        self.assertEqual(response.status_code, 302)
        self.assertSetEqual(
            set(
                FtpImportConfiguration.objects.filter(active=True).values_list(
                    'file_type', 'filename',
                )
            ),
            {('FUEL', 'fuel.xls')},
        )
        self.assertFalse(
            FtpImportConfiguration.objects.get(filename='products.xls').active,
        )

    def test_each_file_action_has_no_client_or_local_file_selector(self):
        expected = {
            'products': 'products.xls',
            'stock': 'stock.xls',
            'fuel': 'fuel.xls',
            'suburbs': 'postcodes.xls',
            'rates': 'rates_all.xls',
            'zones': 'zones.csv',
        }
        for key, filename in expected.items():
            with self.subTest(key=key):
                response = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_upload_now',
                        args=[key],
                    ),
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'ftp_inbox/{filename}')
                self.assertContains(response, 'No client or local file selection is required')
                self.assertContains(response, 'Do not close or reload this page')
                self.assertNotContains(response, 'name="client"')
                self.assertNotContains(response, 'type="file"')

    def test_missing_file_reason_and_retry_are_shown_in_import_centre(self):
        with tempfile.TemporaryDirectory() as temp_root:
            ftp_root = Path(temp_root) / 'uploaded_data'
            ftp_root.mkdir()
            FtpImportConfiguration.objects.create(
                client=self.client_record,
                file_type='PRODUCTS',
                filename='products.xls',
                minimum_file_age_seconds=0,
                active=True,
            )
            self.schedule.active = True
            self.schedule.retry_minutes = 15
            self.schedule.save(update_fields=['active', 'retry_minutes', 'updated_at'])

            with override_settings(FTP_UPLOADED_DATA_DIR=str(ftp_root)):
                response = self.client.post(
                    reverse(
                        'admin:imports_ftpimportschedule_upload_now',
                        args=['products'],
                    ),
                )
                message_text = ' '.join(
                    str(message) for message in get_messages(response.wsgi_request)
                )
                page = self.client.get(
                    reverse(
                        'admin:imports_ftpimportschedule_change',
                        args=[self.schedule.pk],
                    ),
                )

        self.assertIn('products.xls was not imported.', message_text)
        self.assertIn('File not found: products.xls.', message_text)
        self.assertIn(
            'Automatic checks will try again every 15 minute(s)',
            message_text,
        )
        self.assertContains(page, 'Waiting for a complete file')
        self.assertContains(page, 'File not found: products.xls.')

        event = AuditEvent.objects.get(event_type='FTP_SCHEDULED_FILE_WAITING')
        audit_page = self.client.get(
            reverse('admin:audit_auditevent_change', args=[event.pk]),
        )
        self.assertContains(audit_page, 'Technical details')
        self.assertContains(audit_page, 'Metadata:', count=1)

    def test_upload_now_registers_products_as_global_master(self):
        with tempfile.TemporaryDirectory() as temp_root:
            ftp_root = Path(temp_root) / 'uploaded_data'
            media_root = Path(temp_root) / 'media'
            ftp_root.mkdir()
            media_root.mkdir()
            (ftp_root / 'products.xls').write_bytes(b'legacy product bytes')
            FtpImportConfiguration.objects.create(
                client=self.client_record,
                file_type='PRODUCTS',
                filename='products.xls',
                minimum_file_age_seconds=0,
                active=True,
            )
            with override_settings(
                FTP_UPLOADED_DATA_DIR=str(ftp_root),
                MEDIA_ROOT=str(media_root),
            ):
                with patch(
                    'apps.imports.services.product_master.read_product_file',
                ) as reader:
                    reader.return_value = SimpleNamespace(
                        headers=['CUSTOMER', 'code'],
                        records=[
                            {'customer': 'STH', 'code': 'A-1', '_row_number': 2},
                            {'customer': '', 'code': 'B-2', '_row_number': 3},
                        ],
                        rejected_rows=[], source_format='CSV', worksheet='',
                        header_row=1, warnings=[],
                    )
                    response = self.client.post(
                        reverse(
                            'admin:imports_ftpimportschedule_upload_now',
                            args=['products'],
                        ),
                    )

                from apps.imports.models import ProductMaster
                master = ProductMaster.objects.get()
                self.assertRedirects(
                    response,
                    reverse(
                        'admin:imports_ftpimportschedule_change',
                        args=[self.schedule.pk],
                    ),
                    fetch_redirect_response=False,
                )
                self.assertEqual(master.status, 'VALIDATED')
                self.assertEqual(master.validation_summary['rows_omitted_without_customer'], 1)
                self.assertEqual(ExternalDataFile.objects.count(), 1)

    def test_upload_now_registers_stock_as_informational_global_master(self):
        with tempfile.TemporaryDirectory() as temp_root:
            ftp_root = Path(temp_root) / 'uploaded_data'
            media_root = Path(temp_root) / 'media'
            ftp_root.mkdir()
            media_root.mkdir()
            (ftp_root / 'stock.xls').write_bytes(b'legacy stock bytes')
            FtpImportConfiguration.objects.create(
                client=self.client_record,
                file_type='STOCK',
                filename='stock.xls',
                minimum_file_age_seconds=0,
                active=True,
            )
            with override_settings(
                FTP_UPLOADED_DATA_DIR=str(ftp_root),
                MEDIA_ROOT=str(media_root),
            ):
                with patch(
                    'apps.imports.services.global_stock_master.read_product_file',
                ) as reader:
                    reader.return_value = SimpleNamespace(
                        headers=[
                            'customer', 'product', 'description', 'quantity',
                            'category', 'serial_no', 'cubic', 'weight',
                        ],
                        records=[{
                            'customer': 'STH', 'product': 'A-1',
                            'description': 'Available stock', 'quantity': 4,
                            'category': 'General', 'serial_no': '',
                            'cubic': 1, 'weight': 10, '_row_number': 2,
                        }],
                        rejected_rows=[], source_format='XLS', worksheet='Stock',
                        header_row=1, warnings=[],
                    )
                    response = self.client.post(
                        reverse(
                            'admin:imports_ftpimportschedule_upload_now',
                            args=['stock'],
                        ),
                    )

                from apps.imports.models import StockMaster
                master = StockMaster.objects.get()
                self.assertRedirects(
                    response,
                    reverse('admin:imports_stockmaster_change', args=[master.pk]),
                    fetch_redirect_response=False,
                )
                self.assertEqual(master.status, 'VALIDATED')
                self.assertTrue(master.validation_summary['reference_only'])
                self.assertFalse(master.validation_summary['operational_tables_updated'])
                self.assertEqual(ExternalDataFile.objects.count(), 1)

    @patch('apps.imports.admin_ftp_configuration.process_ftp_configuration')
    def test_file_action_processes_all_enabled_mappings_for_that_file(self, process):
        process.return_value = {'status': 'UNCHANGED'}
        second_client = Client.objects.create(
            code='NTH',
            name='North client',
            active=True,
        )
        product_configs = [
            FtpImportConfiguration.objects.create(
                client=client,
                file_type='PRODUCTS',
                filename='products.xls',
                active=True,
            )
            for client in (self.client_record, second_client)
        ]
        FtpImportConfiguration.objects.create(
            client=self.client_record,
            file_type='STOCK',
            filename='stock.xls',
            active=True,
        )

        response = self.client.post(
            reverse(
                'admin:imports_ftpimportschedule_upload_now',
                args=['products'],
            ),
        )

        self.assertRedirects(
            response,
            reverse(
                'admin:imports_ftpimportschedule_change',
                args=[self.schedule.pk],
            ),
        )
        self.assertEqual(
            {call.args[0] for call in process.call_args_list},
            {configuration.pk for configuration in product_configs},
        )
        for call in process.call_args_list:
            self.assertEqual(call.kwargs['trigger'], 'MANUAL')
            self.assertTrue(call.kwargs['force'])

    @patch('apps.imports.admin_ftp_configuration.process_ftp_configuration')
    def test_check_inbox_now_processes_every_enabled_mapping(self, process):
        process.return_value = {'status': 'UNCHANGED'}
        second_client = Client.objects.create(
            code='NTH',
            name='North client',
            active=True,
        )
        for client in (self.client_record, second_client):
            FtpImportConfiguration.objects.create(
                client=client,
                file_type='PRODUCTS',
                filename='products.xls',
                active=True,
            )

        response = self.client.post(
            reverse('admin:imports_ftpimportschedule_check_inbox_now'),
        )

        self.assertRedirects(
            response,
            reverse(
                'admin:imports_ftpimportschedule_change',
                args=[self.schedule.pk],
            ),
        )
        self.assertEqual(process.call_count, 2)
        for call in process.call_args_list:
            self.assertEqual(call.kwargs['trigger'], 'MANUAL')
            self.assertTrue(call.kwargs['force'])

