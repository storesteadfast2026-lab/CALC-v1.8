import csv
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.imports.models import ExternalDataFile, RateCardLine, ZoneSourceRow
from apps.imports.services import rate_source_load as service
from apps.imports.services.ftp_inbox import scan_ftp_inbox
from apps.imports.services.rate_source_load import (
    RateSourceError,
    load_source,
    parse_rate_lines,
    prepare_source,
    rate_expression_diagnostics,
    rollback_source,
)
from apps.imports.services.xlsx_reader import calculate_sha256
from apps.rates.models import FreightRate, FreightZone

FIXTURES = Path(__file__).parent / 'fixtures'
RATES_V1 = (FIXTURES / 'rates_sample.xls').read_bytes()
RATES_V2 = (FIXTURES / 'rates_sample_v2.xls').read_bytes()
ZONE_HEADER = b'index,index2,carrier,suburb,state,postcode,zone,subzone,area\n'
ZONES_V1 = (ZONE_HEADER
            + b'a,b,TEAMEX,MELBOURNE,VIC,3000,MELB,,\n'
            + b'a,b,TEAMEX,DARWIN,NT,0800,DRW,RM1,\n'
            + b'a,b,OTHER,MELBOURNE,VIC,3000,M1,,\n')
ZONES_V2 = ZONES_V1 + b'a,b,TEAMEX,HOBART,TAS,7000,HBA,,\n'


class Base(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.ftp = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.ftp.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name, FTP_UPLOADED_DATA_DIR=self.ftp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.sth = Client.objects.create(code='STH', name='STH')
        self.other = Client.objects.create(code='OTHER', name='Other')
        carrier = Carrier.objects.create(code='TEAMEX', name='Team')
        self.service = CarrierService.objects.create(carrier=carrier, service_code='ROAD')
        ClientCarrierConfig.objects.create(client=self.sth, carrier_service=self.service, ratecard='1115')
        self.user = get_user_model().objects.create_superuser('sourceadmin', 'admin@example.test', 'test')

    def source(self, content, file_type='RATES', filename=None, client=None):
        filename = filename or ('rates_all.xls' if file_type == 'RATES' else 'zones.csv')
        obj = ExternalDataFile(client=client or self.sth, file_type=file_type, source_method='FTP_DROP',
                               original_filename=filename, status='UPLOADED', sha256=calculate_sha256(content),
                               file_size_bytes=len(content))
        obj.uploaded_file.save(filename, ContentFile(content), save=True)
        return obj

    def prepared(self, content, file_type='RATES'):
        obj = self.source(content, file_type)
        prepare_source(obj, actor=self.user)
        return obj

    def loaded(self, content, file_type='RATES'):
        obj = self.prepared(content, file_type)
        load_source(obj, actor=self.user)
        obj.refresh_from_db()
        return obj


class ParsingTests(TestCase):
    def test_every_column_and_row_is_kept(self):
        lines, rounded = parse_rate_lines(RATES_V1, 'rates_all.xls')
        self.assertEqual(len(lines), 4)
        self.assertEqual(rounded, 0)
        freight = lines[3]
        self.assertEqual((freight['source_row'], freight['master_rate'], freight['item_no']), (5, 1517, 154))
        self.assertEqual(freight['to_value'], 'MELB')
        self.assertEqual(freight['unit'], 'WTRM')
        self.assertEqual(freight['rc_name'], 'TeamExp < 750kg 40%')

    def test_float_noise_becomes_six_decimals(self):
        freight = parse_rate_lines(RATES_V1, 'rates_all.xls')[0][3]
        self.assertEqual(freight['basic_charge'], Decimal('26.880000'))
        self.assertEqual(freight['min_charge'], Decimal('58.800000'))

    def test_pointer_is_separate_from_blank_run_rate(self):
        lines = parse_rate_lines(RATES_V1, 'rates_all.xls')[0]
        self.assertEqual(lines[0]['run_rate'], 1516)
        self.assertIsNone(lines[3]['run_rate'])

    def test_expression_is_stored_as_text(self):
        line = parse_rate_lines(RATES_V1, 'rates_all.xls')[0][2]
        self.assertEqual(line['filter_field'], 'iif(inlist(driver_zones.type,"1"),0,1)')


class PrepareTests(Base):
    def test_preview_reports_missing_pointer_without_storing_rows(self):
        obj = self.prepared(RATES_V1)
        preview = obj.validation_summary['load_preview']
        self.assertEqual(obj.status, 'VALIDATED')
        self.assertEqual((preview['rows'], preview['cards']), (4, 3))
        self.assertEqual(preview['missing_references'], [1524])
        self.assertTrue(preview['carrier_roots']['TEAMEX'])
        self.assertFalse(preview['carrier_roots']['KTI'])
        diagnostics = preview['expression_diagnostics']
        self.assertEqual(diagnostics['scope'], 'CATALOGUE_WIDE_STRUCTURE_ONLY')
        self.assertFalse(diagnostics['route_impact_proven'])
        self.assertFalse(diagnostics['quotes_changed'])
        self.assertEqual(diagnostics['issue_rows'], 1)
        self.assertEqual(diagnostics['reason_counts'], {'ZONE_TYPE_NOT_IN_ZONES_CSV': 1})
        self.assertEqual(diagnostics['groups'][0]['reason'], 'ZONE_TYPE_NOT_IN_ZONES_CSV')
        self.assertFalse(RateCardLine.objects.exists())

    def test_expression_diagnostics_include_source_examples(self):
        diagnostics = rate_expression_diagnostics(RATES_V1, 'rates_all.xls')

        self.assertEqual(diagnostics['issue_groups'], 1)
        self.assertEqual(diagnostics['groups'][0]['examples'], [{'card': 1516, 'row': 4}])

    def test_preview_compares_with_loaded_version(self):
        self.loaded(RATES_V1)
        preview = self.prepared(RATES_V2).validation_summary['load_preview']
        self.assertEqual(preview['cards_added']['first'], [1518])
        self.assertEqual(preview['cards_changed']['first'], [1517])
        self.assertEqual(preview['cards_removed']['count'], 0)

    def test_corrupt_rates_are_rejected(self):
        obj = self.source(b'invalid XLS')
        prepare_source(obj, actor=self.user)
        self.assertEqual(obj.status, 'VALIDATION_FAILED')
        with self.assertRaises(RateSourceError):
            load_source(obj, actor=self.user)

    def test_wrong_zone_columns_are_rejected(self):
        obj = self.source(b'carrier,suburb\nTEAMEX,MELBOURNE\n', 'ZONES')
        prepare_source(obj, actor=self.user)
        self.assertEqual(obj.status, 'VALIDATION_FAILED')
        self.assertIn('columns must be exactly', obj.error_message)

    def test_tampered_file_is_rejected(self):
        obj = self.prepared(RATES_V1)
        ExternalDataFile.objects.filter(pk=obj.pk).update(sha256='0' * 64)
        obj.refresh_from_db()
        with self.assertRaisesMessage(RateSourceError, 'does not match'):
            load_source(obj, actor=self.user)
        self.assertFalse(RateCardLine.objects.exists())

    def test_only_sth_is_supported(self):
        with self.assertRaisesMessage(RateSourceError, 'Only STH'):
            prepare_source(self.source(RATES_V1, client=self.other), actor=self.user)


class LoadTests(Base):
    def test_rate_load_keeps_all_lines_and_values(self):
        obj = self.loaded(RATES_V1)
        self.assertEqual(obj.status, 'ACTIVE')
        self.assertEqual(obj.rate_card_lines.count(), 4)
        line = obj.rate_card_lines.get(master_rate=1517)
        self.assertEqual(line.rate, Decimal('0.125000'))
        self.assertEqual(line.source_row, 5)

    def test_zones_keep_leading_zeros_and_only_client_carriers(self):
        obj = self.loaded(ZONES_V1, 'ZONES')
        self.assertEqual(obj.zone_source_rows.count(), 2)
        self.assertEqual(obj.zone_source_rows.get(suburb='DARWIN').postcode, '0800')
        self.assertEqual(obj.validation_summary['load_preview']['rows_in_file'], 3)

    def test_same_content_is_not_loaded_twice(self):
        self.loaded(RATES_V1)
        duplicate = self.prepared(RATES_V1)
        with self.assertRaisesMessage(RateSourceError, 'already loaded'):
            load_source(duplicate, actor=self.user)
        self.assertEqual(RateCardLine.objects.count(), 4)

    def test_load_requires_review(self):
        with self.assertRaisesMessage(RateSourceError, 'Review the source'):
            load_source(self.source(RATES_V1), actor=self.user)

    def test_new_version_archives_previous(self):
        first = self.loaded(RATES_V1)
        second = self.loaded(RATES_V2)
        first.refresh_from_db()
        self.assertEqual(first.status, 'ARCHIVED')
        self.assertEqual(second.previous_active_file, first)
        self.assertEqual(first.rate_card_lines.count(), 4)

    def test_failure_during_load_leaves_previous_version(self):
        first = self.loaded(RATES_V1)
        second = self.prepared(RATES_V2)
        with patch('apps.imports.services.rate_source_load.create_audit_event', side_effect=RuntimeError('x')):
            with self.assertRaises(RuntimeError):
                load_source(second, actor=self.user)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ('ACTIVE', 'VALIDATED'))
        self.assertFalse(second.rate_card_lines.exists())

    def test_rollback_restores_previous_version(self):
        first = self.loaded(RATES_V1)
        second = self.loaded(RATES_V2)
        rollback_source(second, reason='test', actor=self.user)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ('ACTIVE', 'ROLLED_BACK'))
        self.assertFalse(second.rate_card_lines.exists())
        self.assertEqual(first.rate_card_lines.count(), 4)

    def test_rollback_of_first_version_leaves_none_in_use(self):
        first = self.loaded(RATES_V1)
        rollback_source(first, reason='test', actor=self.user)
        self.assertFalse(ExternalDataFile.objects.filter(status='ACTIVE').exists())
        self.assertFalse(RateCardLine.objects.exists())

    def test_rollback_needs_reason(self):
        with self.assertRaisesMessage(RateSourceError, 'reason'):
            rollback_source(self.loaded(RATES_V1), reason=' ', actor=self.user)

    def test_rows_of_old_versions_are_purged_but_files_stay(self):
        with patch.object(service, 'RETAINED_VERSIONS', 1):
            first = self.loaded(ZONES_V1, 'ZONES')
            second = self.loaded(ZONES_V2, 'ZONES')
        self.assertFalse(first.zone_source_rows.exists())
        self.assertEqual(second.zone_source_rows.count(), 3)
        self.assertTrue(ExternalDataFile.objects.filter(pk=first.pk).exists())
        with self.assertRaisesMessage(RateSourceError, 'no longer has stored rows'):
            rollback_source(second, reason='test', actor=self.user)
        second.refresh_from_db()
        self.assertEqual(second.status, 'ACTIVE')

    def test_operational_tables_do_not_change(self):
        FreightZone.objects.create(client=self.sth, carrier_service=self.service, suburb='MELBOURNE',
                                   state='VIC', postcode='3000', zone='MELB')
        FreightRate.objects.create(client=self.sth, carrier_service=self.service, zone='MELB',
                                   freight_type='P', per_kg=Decimal('0.1'))
        models = (FreightRate, FreightZone, ClientCarrierConfig)
        before = [list(model.objects.order_by('pk').values()) for model in models]
        rollback_source(self.loaded(RATES_V1), reason='test', actor=self.user)
        self.loaded(ZONES_V1, 'ZONES')
        self.assertEqual([list(model.objects.order_by('pk').values()) for model in models], before)


class ChannelTests(Base):
    def login(self, user=None):
        self.client.force_login(user or self.user)

    def test_ftp_scan_registers_without_loading(self):
        (Path(self.ftp.name) / 'rates_all.xls').write_bytes(RATES_V1)
        summary = scan_ftp_inbox(client=self.sth, actor=self.user)
        self.assertEqual(summary['new_snapshots'], 1)
        self.assertEqual(ExternalDataFile.objects.get(file_type='RATES').status, 'UPLOADED')
        self.assertFalse(RateCardLine.objects.exists())

    def test_zone_upload_review_and_load_screens(self):
        self.login()
        response = self.client.post(reverse('admin:imports_externaldatafile_upload_zones'), {
            'client': self.sth.pk, 'uploaded_file': SimpleUploadedFile('zones.csv', ZONES_V1),
        })
        obj = ExternalDataFile.objects.get(file_type='ZONES')
        self.assertRedirects(response, reverse('admin:imports_externaldatafile_ratecard_review', args=[obj.pk]))
        page = self.client.get(reverse('admin:imports_externaldatafile_ratecard_review', args=[obj.pk]))
        self.assertContains(page, 'Rows for STH carriers: 2')
        self.assertContains(page, 'Load version')
        self.client.post(reverse('admin:imports_externaldatafile_rate_source_load', args=[obj.pk]))
        self.assertEqual(ZoneSourceRow.objects.count(), 2)

    def test_rate_upload_shows_preview_and_rollback_screen_works(self):
        self.login()
        self.client.post(reverse('admin:imports_externaldatafile_upload_ratecards'), {
            'client': self.sth.pk, 'uploaded_file': SimpleUploadedFile('rates_all.xls', RATES_V1),
        })
        obj = ExternalDataFile.objects.get(file_type='RATES')
        page = self.client.get(reverse('admin:imports_externaldatafile_ratecard_review', args=[obj.pk]))
        self.assertContains(page, 'Pointers to cards not in this file (1)')
        self.assertContains(page, 'Expression diagnostics')
        self.assertContains(page, 'ZONE_TYPE_NOT_IN_ZONES_CSV')
        self.assertContains(page, 'Show all 1 expression findings')
        self.client.post(reverse('admin:imports_externaldatafile_rate_source_load', args=[obj.pk]))
        self.client.post(reverse('admin:imports_externaldatafile_rate_source_rollback', args=[obj.pk]),
                         {'reason': 'test'})
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'ROLLED_BACK')

    def test_review_backfills_diagnostics_for_an_existing_source(self):
        self.login()
        obj = self.prepared(RATES_V1)
        summary = obj.validation_summary
        del summary['load_preview']['expression_diagnostics']
        ExternalDataFile.objects.filter(pk=obj.pk).update(validation_summary=summary)

        page = self.client.get(reverse('admin:imports_externaldatafile_ratecard_review', args=[obj.pk]))

        self.assertContains(page, 'Expression diagnostics')
        self.assertContains(page, 'ZONE_TYPE_NOT_IN_ZONES_CSV')

    def test_paired_diagnostic_is_read_only_and_shows_carrier_coverage(self):
        self.login()
        rates = self.loaded(RATES_V1)
        zones = self.loaded(ZONES_V1, 'ZONES')
        operational_before = [list(model.objects.values()) for model in (FreightRate, FreightZone)]
        report = {
            'scope': 'VALIDATION_ONLY',
            'operational_tables_updated': False,
            'quotes_use_these_files': False,
            'rates': {
                'rows': 4,
                'masters': 3,
                'missing_references': [1524],
                'missing_reference_details': [{
                    'card': 1524,
                    'structurally_reachable': True,
                    'reachable_carriers': ['TEAMEX'],
                    'review_status': 'SOURCE_FIELD_REQUIRED',
                    'references': [{
                        'from_card': 1516,
                        'row': 4,
                        'name': '=Disaster Levy',
                        'carriers': ['TEAMEX'],
                        'expression': 'iif(inlist(driver_zones.type,"1"),0,1)',
                        'from': '0',
                        'to': '1',
                        'customer_scope': 'NOT_CUSTOMER_SPECIFIC',
                        'condition_issue': 'ZONE_TYPE_NOT_IN_ZONES_CSV',
                    }],
                }],
            },
            'zones': {'rows': 3, 'carriers': 2},
            'carriers': {
                'TEAMEX': {
                    'root_card': 1135,
                    'rows': 2,
                    'zones_in_csv': 2,
                    'zones_with_base_price': 1,
                    'csv_zones_without_price': ['DRW'],
                    'priced_zones_missing_from_csv': ['HAST'],
                    'case_status': {'APPLICABLE': 2, 'UNKNOWN': 1},
                    'base_status': {'APPLICABLE': 3},
                    'unresolved': {'ZONE_TYPE_NOT_IN_ZONES_CSV:Disaster Levy': 1},
                },
            },
        }

        url = reverse('admin:imports_externaldatafile_rate_pair_diagnostic', args=[rates.pk])
        with patch('apps.imports.admin_ratecards.validate_sources', return_value=report) as validate:
            page = self.client.get(reverse(
                'admin:imports_externaldatafile_rate_pair_diagnostic', args=[rates.pk],
            ))
            csv_response = self.client.get(f'{url}?format=csv')

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Read-only diagnostic')
        self.assertContains(page, 'TEAMEX')
        self.assertContains(page, 'DRW')
        self.assertContains(page, 'ZONE_TYPE_NOT_IN_ZONES_CSV')
        self.assertContains(page, 'Structural reachability from STH roots')
        self.assertContains(page, 'SOURCE_FIELD_REQUIRED')
        self.assertContains(page, 'Download diagnostic evidence CSV')
        self.assertContains(page, 'Rate values are not compared with the previous file')
        self.assertContains(page, 'BLOCKED')
        self.assertContains(page, '1 priority missing card')
        self.assertContains(page, zones.sha256)
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('sth_rate_diagnostic_rates_', csv_response['Content-Disposition'])
        csv_rows = list(csv.DictReader(StringIO(csv_response.content.decode('utf-8-sig'))))
        missing = next(row for row in csv_rows if row['record_type'] == 'missing_reference')
        self.assertEqual(missing['missing_card'], '1524')
        self.assertEqual(missing['review_status'], 'SOURCE_FIELD_REQUIRED')
        self.assertEqual(missing['rule_name'], "'=Disaster Levy")
        self.assertEqual(missing['rates_sha256'], rates.sha256)
        self.assertEqual(missing['zones_sha256'], zones.sha256)
        self.assertEqual(validate.call_count, 2)
        self.assertEqual([list(model.objects.values()) for model in (FreightRate, FreightZone)],
                         operational_before)

    def test_paired_diagnostic_requires_an_active_zones_source(self):
        self.login()
        rates = self.loaded(RATES_V1)

        page = self.client.get(reverse(
            'admin:imports_externaldatafile_rate_pair_diagnostic', args=[rates.pk],
        ))

        self.assertContains(page, 'No active STH Zones source')

    def test_load_needs_its_own_permission(self):
        obj = self.prepared(RATES_V1)
        staff = get_user_model().objects.create_user('staffer', password='x', is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_externaldatafile', 'validate_external_data_file'],
        ))
        self.login(staff)
        url = reverse('admin:imports_externaldatafile_rate_source_load', args=[obj.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(RateCardLine.objects.exists())

    def test_other_client_source_is_not_reachable(self):
        obj = self.source(RATES_V1, client=self.other)
        self.login()
        url = reverse('admin:imports_externaldatafile_rate_source_load', args=[obj.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
