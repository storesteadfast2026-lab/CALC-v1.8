import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import TestCase, override_settings

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.imports.forms import ExternalDataFileAdminForm
from apps.imports.models import ExternalDataFile
from apps.imports.services.ftp_inbox import scan_ftp_inbox
from apps.imports.services.fuel import (
    FuelImportError,
    XLS_SIGNATURE,
    activate_fuel_file,
    calculate_sha256,
    parse_fuel_rows,
    reapply_active_fuel_rates,
    rollback_fuel_file,
    validate_fuel_file,
)
from apps.imports.services.ratecard_chain import Catalogue, CardLine
from apps.imports.services.uploaded_data import (
    default_ftp_fuel_filename,
    snapshot_ftp_fuel_file,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'fuel_sample.xls'
FTP_CSV = b'rate_no,carrier,name,surcharge,type\n1420,TEAMEX,Team Fuel,42.90,PRICE\n'


def card_line(master=1420, rate=0.429, filter_field='Price', unit='PRICE', run_rate=None, item_no=1):
    return CardLine(
        source_row=2, master=master, card_name='Fuel', break_no=1, item_no=item_no,
        run_rate=run_rate, name='Fuel', filter_field=filter_field, from_value='', to_value='',
        greater=0, upto=0, unit=unit, rate=rate, basic=0, minimum=0,
    )


def catalogue(*lines):
    masters = {}
    for line in lines:
        masters.setdefault(line.master, []).append(line)
    return Catalogue(sha256='abc', rows=len(lines), masters=masters)


class XlsParsingTests(TestCase):
    def test_xls_gives_same_rows_as_equivalent_csv(self):
        csv_content = (
            b'rate_no,carrier,name,surcharge,type\n'
            b'1420,TEAMEX,Team Fuel,42.9,PRICE\n'
            b'9999,OTHER,Unused Fuel,15,PRICE\n'
        )
        self.assertEqual(parse_fuel_rows(FIXTURE.read_bytes()), parse_fuel_rows(csv_content))

    def test_percentages_become_decimal_rates(self):
        rows, warnings = parse_fuel_rows(FIXTURE.read_bytes())
        self.assertEqual(warnings, [])
        self.assertEqual([(row.master_rate, row.rate) for row in rows],
                         [('1420', Decimal('0.429')), ('9999', Decimal('0.15'))])

    def test_corrupt_xls_is_rejected(self):
        with self.assertRaisesMessage(FuelImportError, 'could not be read'):
            parse_fuel_rows(XLS_SIGNATURE + b'not a workbook')

    def test_csv_still_parses(self):
        rows, _ = parse_fuel_rows(FTP_CSV)
        self.assertEqual(rows[0].rate, Decimal('0.429'))


class FuelXlsFlowTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.ftp = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.ftp.cleanup)
        override = override_settings(
            MEDIA_ROOT=self.media.name, FTP_UPLOADED_DATA_DIR=self.ftp.name, FUEL_RATE_MAX='1.0',
        )
        override.enable()
        self.addCleanup(override.disable)

        self.user = get_user_model().objects.create_user(
            username='fuel-xls-admin', password='password', is_staff=True, is_superuser=True,
        )
        self.client_obj = Client.objects.create(code='STH', name='Stenhoj Australia', active=True)
        carrier = Carrier.objects.create(code='TEAMEX', name='Team Global Express')
        service = CarrierService.objects.create(carrier=carrier, service_code='ROAD')
        self.config = ClientCarrierConfig.objects.create(
            client=self.client_obj, carrier_service=service, ratecard='1420',
            fuel_levy=Decimal('0.080000'), fuel_levy_source='LEGACY_WORKBOOK',
        )
        other = Carrier.objects.create(code='TEAMTAS', name='Team Tasmania')
        other_service = CarrierService.objects.create(carrier=other, service_code='GENERAL')
        self.unmatched = ClientCarrierConfig.objects.create(
            client=self.client_obj, carrier_service=other_service, ratecard='713',
            fuel_levy=Decimal('0.160000'), fuel_levy_source='LEGACY_WORKBOOK',
        )

    def external_file(self, content=None, filename='fuel.xls'):
        content = FIXTURE.read_bytes() if content is None else content
        external_file = ExternalDataFile.objects.create(
            client=self.client_obj, file_type='FUEL', source_method='FTP_DROP',
            original_filename=filename, status='UPLOADED', uploaded_by=self.user,
            file_size_bytes=len(content), sha256=calculate_sha256(content),
            mime_type='application/vnd.ms-excel',
        )
        external_file.uploaded_file.save(filename, ContentFile(content), save=True)
        external_file.stored_path = external_file.uploaded_file.name
        external_file.save(update_fields=['stored_path'])
        return external_file

    def fuel_values(self):
        return list(ClientCarrierConfig.objects.order_by('pk').values_list('fuel_levy', flat=True))

    def test_validation_changes_nothing_and_lists_unmatched(self):
        external_file = self.external_file()
        summary = validate_fuel_file(external_file, actor=self.user)
        self.assertEqual(self.fuel_values(), [Decimal('0.080000'), Decimal('0.160000')])
        self.assertEqual(summary['configs_to_update'], 1)
        self.assertEqual(summary['unmatched_client_configs'][0]['carrier'], 'TEAMTAS')
        self.assertEqual(summary['unmatched_client_configs'][0]['current_rate'], '0.160000')

    def test_activation_touches_only_matched_and_rollback_restores(self):
        external_file = self.external_file()
        validate_fuel_file(external_file, actor=self.user)
        activate_fuel_file(external_file, actor=self.user)
        self.assertEqual(self.fuel_values(), [Decimal('0.429000'), Decimal('0.160000')])
        external_file.refresh_from_db()
        rollback_fuel_file(external_file, actor=self.user, reason='test')
        self.assertEqual(self.fuel_values(), [Decimal('0.080000'), Decimal('0.160000')])

    def test_active_xls_is_reapplied(self):
        external_file = self.external_file()
        validate_fuel_file(external_file, actor=self.user)
        activate_fuel_file(external_file, actor=self.user)
        ClientCarrierConfig.objects.filter(pk=self.config.pk).update(fuel_levy=Decimal('0.1'))
        self.assertEqual(reapply_active_fuel_rates(self.client_obj)['configs_reapplied'], 1)
        self.config.refresh_from_db()
        self.assertEqual(self.config.fuel_levy, Decimal('0.429000'))

    def test_missing_rates_all_warns_without_blocking(self):
        summary = validate_fuel_file(self.external_file(), actor=self.user)
        self.assertEqual(summary['rates_all_check']['status'], 'NOT_COMPARED')
        self.assertTrue(any('was not compared' in item for item in summary['warnings']))

    def test_matching_rates_all_adds_no_warning(self):
        with patch('apps.imports.services.fuel._load_rates_all',
                   return_value=(catalogue(card_line()), '')):
            summary = validate_fuel_file(self.external_file(), actor=self.user)
        self.assertEqual(summary['rates_all_check']['checks'][0]['result'], 'MATCH')
        self.assertEqual(summary['warnings'], [])

    def test_different_rates_all_warns_without_blocking(self):
        external_file = self.external_file()
        with patch('apps.imports.services.fuel._load_rates_all',
                   return_value=(catalogue(card_line(rate=0.5)), '')):
            summary = validate_fuel_file(external_file, actor=self.user)
        external_file.refresh_from_db()
        self.assertEqual(external_file.status, 'VALIDATED')
        self.assertEqual(summary['rates_all_check']['checks'][0]['result'], 'DIFFERENT')
        self.assertTrue(any('42.90%' in item and '50.00%' in item for item in summary['warnings']))

    def test_pointer_and_zero_lines_are_not_fuel_rates(self):
        lines = catalogue(
            card_line(rate=0, run_rate=1594),
            card_line(rate=0.3, filter_field='iif(x,1,0)', unit='CHG', item_no=2),
        )
        with patch('apps.imports.services.fuel._load_rates_all', return_value=(lines, '')):
            summary = validate_fuel_file(self.external_file(), actor=self.user)
        self.assertEqual(summary['rates_all_check']['checks'][0]['result'], 'NOT_FOUND')

    def test_extra_surcharge_is_flagged(self):
        ClientCarrierConfig.objects.filter(pk=self.config.pk).update(extra_surcharge=Decimal('0.03'))
        summary = validate_fuel_file(self.external_file(), actor=self.user)
        self.assertTrue(any('45.90%' in item for item in summary['warnings']))

    def test_ftp_snapshot_keeps_xls_source_and_mime(self):
        path = Path(self.ftp.name) / 'fuel.xls'
        path.write_bytes(FIXTURE.read_bytes())
        external_file, created = snapshot_ftp_fuel_file(client=self.client_obj, filename='fuel.xls')
        self.assertTrue(created)
        self.assertEqual(external_file.mime_type, 'application/vnd.ms-excel')
        self.assertEqual(path.read_bytes(), FIXTURE.read_bytes())

    def test_default_prefers_xls_and_falls_back_to_csv(self):
        self.assertEqual(default_ftp_fuel_filename(), 'fuel.csv')
        (Path(self.ftp.name) / 'fuel.xls').write_bytes(FIXTURE.read_bytes())
        self.assertEqual(default_ftp_fuel_filename(), 'fuel.xls')

    def test_inbox_registers_xls_without_changing_fuel(self):
        (Path(self.ftp.name) / 'fuel.xls').write_bytes(FIXTURE.read_bytes())
        summary = scan_ftp_inbox(client=self.client_obj, actor=self.user)
        self.assertEqual(summary['new_snapshots'], 1)
        self.assertEqual(ExternalDataFile.objects.get(file_type='FUEL').status, 'UPLOADED')
        self.assertEqual(self.fuel_values(), [Decimal('0.080000'), Decimal('0.160000')])

    def test_command_validates_xls_and_never_activates(self):
        (Path(self.ftp.name) / 'fuel.xls').write_bytes(FIXTURE.read_bytes())
        output = StringIO()
        call_command('process_uploaded_fuel', '--client', 'STH', stdout=output)
        self.assertIn('Fuel source: fuel.xls', output.getvalue())
        self.assertIn('NO FUEL RATES WERE ACTIVATED', output.getvalue())
        self.assertEqual(self.fuel_values(), [Decimal('0.080000'), Decimal('0.160000')])

    def test_admin_form_accepts_xls_and_csv_only(self):
        for filename, valid in (('fuel.xls', True), ('fuel.csv', True), ('fuel.xlsx', False)):
            form = ExternalDataFileAdminForm(
                data={'client': self.client_obj.pk, 'file_type': 'FUEL', 'notes': ''},
                files={'uploaded_file': SimpleUploadedFile(filename, b'x')},
            )
            self.assertEqual(form.is_valid(), valid, filename)

    def test_preview_template_shows_unmatched_and_rates_all(self):
        with patch('apps.imports.services.fuel._load_rates_all',
                   return_value=(catalogue(card_line(rate=0.5)), '')):
            summary = validate_fuel_file(self.external_file(), actor=self.user)
        html = render_to_string('admin/imports/externaldatafile/validation_summary.html', {
            'summary': summary,
            'unmatched_client_configs': summary['unmatched_client_configs'],
            'rates_all_check': summary['rates_all_check'],
        })
        self.assertIn('Client carriers not updated by this file (1)', html)
        self.assertIn('TEAMTAS', html)
        self.assertIn('Comparison with rates_all (1)', html)
        self.assertIn('DIFFERENT', html)
