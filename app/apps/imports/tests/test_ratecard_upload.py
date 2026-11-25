import os
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from apps.clients.models import Client
from apps.imports.models import ExternalDataFile
from apps.imports.services.ratecard_source import review_ratecard, FIELDS, MAX_BYTES
from apps.imports.services.xlsx_reader import SourceImportError


class RatecardUploadTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.sth = Client.objects.create(code='STH', name='STH')
        self.other = Client.objects.create(code='OTHER', name='Other')
        self.user = get_user_model().objects.create_superuser('rateadmin', 'admin@example.test', 'test')
        self.client.force_login(self.user)
        self.url = reverse('admin:imports_externaldatafile_upload_ratecards')

    def upload(self, content=b'invalid XLS', client=None, name='rates_all.xls'):
        return self.client.post(self.url, {'client': client or self.sth.pk,
                                         'uploaded_file': SimpleUploadedFile(name, content)})

    def test_form_exposes_only_sth_and_post_action(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(r.context['form'].fields['client'].queryset), [self.sth])
        self.assertContains(r, 'Upload and validate structure')

    def test_other_tenant_cannot_be_selected_even_by_superuser(self):
        self.assertEqual(self.upload(client=self.other.pk).status_code, 200)
        self.assertFalse(ExternalDataFile.objects.exists())

    def test_corrupt_source_retains_failed_version_and_review(self):
        r = self.upload()
        obj = ExternalDataFile.objects.get()
        self.assertEqual(obj.status, 'VALIDATION_FAILED')
        self.assertEqual(obj.sha256, hashlib.sha256(b'invalid XLS').hexdigest())
        with obj.uploaded_file.open('rb') as f:
            self.assertEqual(f.read(), b'invalid XLS')
        self.assertEqual(self.client.get(r.url).status_code, 200)
        self.assertContains(self.client.get(r.url), 'Not active for quoting')
        self.assertContains(self.client.get(reverse('admin:imports_externaldatafile_change', args=[obj.pk])),
                            'Not active for quoting')
        self.assertIsNone(obj.activated_at)

    def test_repeated_upload_preserves_previous_source(self):
        self.upload(b'first'); first = ExternalDataFile.objects.get()
        self.upload(b'second')
        self.assertEqual(ExternalDataFile.objects.count(), 2)
        with first.uploaded_file.open('rb') as f:
            self.assertEqual(f.read(), b'first')

    def test_wrong_extension_and_oversized_rejected_before_storage(self):
        self.upload(name='rates.xlsx')
        self.upload(b'x' * (MAX_BYTES + 1))
        self.assertFalse(ExternalDataFile.objects.exists())

    def test_ratecard_review_cannot_read_other_client_source(self):
        obj = ExternalDataFile.objects.create(client=self.other, file_type='RATES', original_filename='other.xls')
        r = self.client.get(reverse('admin:imports_externaldatafile_ratecard_review', args=[obj.pk]))
        self.assertEqual(r.status_code, 404)

    def test_anonymous_has_no_upload_access(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertFalse(ExternalDataFile.objects.exists())

    def test_backend_permission_gate(self):
        from apps.imports.admin import ExternalDataFileAdmin
        with patch.object(ExternalDataFileAdmin, 'has_add_permission', return_value=False):
            self.assertEqual(self.upload().status_code, 403)
        self.assertFalse(ExternalDataFile.objects.exists())

    def test_csrf_required_for_post(self):
        from django.test import Client as HttpClient
        c = HttpClient(enforce_csrf_checks=True)
        c.force_login(self.user)
        self.assertEqual(c.post(self.url, {'client': self.sth.pk}).status_code, 403)

    def test_nonfinite_numeric_and_duplicate_header_rejected(self):
        row = {f: '' for f in FIELDS}
        row.update(master_rate='001', rate_no='0002', rate='NaN', _row_number=2)
        result = SimpleNamespace(headers=list(FIELDS), records=[row], worksheet='rates', header_row=1)
        with patch('apps.imports.services.ratecard_source.read_product_file', return_value=result):
            with self.assertRaises(SourceImportError):
                review_ratecard(b'fixture', 'rates.xls')
            row['rate'] = '1.200000'
            result.headers.append('Master Rate')
            with self.assertRaises(SourceImportError):
                review_ratecard(b'fixture', 'rates.xls')

    def test_no_file_cleanup_orphan_if_audit_transaction_fails(self):
        with patch('apps.imports.admin_ratecards.create_audit_event', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertFalse(ExternalDataFile.objects.exists())
        self.assertFalse(any(p.is_file() for p in Path(self.media.name).rglob('*')))

    def test_real_source_upload_preserves_operational_tables(self):
        path = os.environ.get('RATECARD_TEST_FILE')
        if not path:
            self.skipTest('Set RATECARD_TEST_FILE to the retained actual rates_all.xls source.')
        from apps.products.models import Product
        from apps.rates.models import FreightRate, FreightZone
        from apps.carriers.models import ClientCarrierConfig
        Product.objects.create(client=self.sth, sku='00001', name='Preserve this product',
                               length_m='1', width_m='2', height_m='3', weight_kg='4',
                               cubic_m3='6', freight_type='P')
        models = [Product, FreightRate, FreightZone, ClientCarrierConfig]
        before = [list(m.objects.values()) for m in models]
        content = Path(path).read_bytes()
        response = self.upload(content)
        self.assertEqual(response.status_code, 302)
        obj = ExternalDataFile.objects.get()
        self.assertEqual(obj.status, 'VALIDATED')
        self.assertEqual(obj.validation_summary['rows_read'], 8727)
        self.assertEqual(obj.validation_summary['master_count'], 177)
        self.assertFalse(obj.validation_summary['quotes_use_this_file'])
        self.assertEqual([list(m.objects.values()) for m in models], before)
        self.assertEqual(obj.sha256, hashlib.sha256(content).hexdigest())
        with obj.uploaded_file.open('rb') as f:
            self.assertEqual(f.read(), content)
        self.assertContains(self.client.get(response.url), '8727')
