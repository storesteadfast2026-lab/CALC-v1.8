"""Admin upload/preview/confirm integration against disposable test PostgreSQL."""
from pathlib import Path
import re
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from apps.audit.models import AuditEvent
from apps.clients.models import Client
from apps.imports.models import ImportReconciliationException
from apps.products.models import Product

FIXTURES = Path(__file__).parent / 'fixtures' / 'reconciliation_20261014'


class ExceptionAdminImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username='registry_admin', email='admin@example.invalid', password='isolated-secret',
        )
        cls.regular = get_user_model().objects.create_user(
            username='registry_regular', password='isolated-secret', is_staff=True,
        )

    def setUp(self):
        self.url = reverse('admin:imports_importreconciliationexception_register_evidence')
        self.client.force_login(self.admin)

    def uploads(self, csv_blob=None, report_blob=None):
        if csv_blob is None:
            csv_blob = (FIXTURES / 'EXCEPTIONS.csv').read_bytes()
        if report_blob is None:
            report_blob = (FIXTURES / 'REPORT.json').read_bytes()
        return {
            'preview': '1',
            'report': SimpleUploadedFile('REPORT.json', report_blob, content_type='application/json'),
            'exceptions': SimpleUploadedFile('EXCEPTIONS.csv', csv_blob, content_type='text/csv'),
        }

    def proof(self, response):
        raw = response.content.decode('utf-8')
        match = re.search(r'name="proof" value="([^"]+)"', raw)
        self.assertIsNotNone(match, raw[:500])
        return match.group(1)

    def test_admin_list_links_to_evidence_workflow(self):
        response = self.client.get(reverse('admin:imports_importreconciliationexception_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register verified exceptions')

    def test_authorised_preview_does_not_write(self):
        response = self.client.post(self.url, self.uploads())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Exception groups:')
        self.assertContains(response, '1151')
        self.assertEqual(ImportReconciliationException.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_admin_confirmation_is_idempotent_and_audited(self):
        token = self.proof(self.client.post(self.url, self.uploads()))
        response = self.client.post(self.url, {'confirm': '1', 'proof': token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ImportReconciliationException.objects.count(), 1151)
        self.assertEqual(AuditEvent.objects.filter(event_type='IMPORT_EXCEPTIONS_REGISTERED').count(), 1)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Client.objects.count(), 0)
        exception = ImportReconciliationException.objects.first()
        exception.status = 'UNDER_REVIEW'
        exception.review_notes = 'Keep original review decision'
        exception.save()
        repeat = self.client.post(self.url, {'confirm': '1', 'proof': token})
        self.assertEqual(repeat.status_code, 302)
        self.assertEqual(ImportReconciliationException.objects.count(), 1151)
        exception.refresh_from_db()
        self.assertEqual(exception.status, 'UNDER_REVIEW')
        self.assertEqual(exception.review_notes, 'Keep original review decision')
        events = AuditEvent.objects.filter(event_type='IMPORT_EXCEPTIONS_REGISTERED')
        self.assertEqual(events.count(), 2)
        self.assertEqual(events.order_by('-pk').first().metadata['new_rows'], 0)

    def test_invalid_evidence_does_not_register_or_audit(self):
        invalid_csv = (FIXTURES / 'EXCEPTIONS.csv').read_bytes() + b'\nmodified'
        response = self.client.post(self.url, self.uploads(csv_blob=invalid_csv))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'checksum differs')
        self.assertEqual(ImportReconciliationException.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_tampered_or_expired_confirmation_does_not_register(self):
        token = self.proof(self.client.post(self.url, self.uploads()))
        altered = token[:-8] + ('A' if token[-8] != 'A' else 'B') + token[-7:]
        result = self.client.post(self.url, {'confirm': '1', 'proof': altered})
        self.assertContains(result, 'Confirmation rejected')
        self.assertEqual(ImportReconciliationException.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_other_user_and_nonadmin_cannot_confirm(self):
        token = self.proof(self.client.post(self.url, self.uploads()))
        self.client.force_login(self.regular)
        res = self.client.post(self.url, {'confirm': '1', 'proof': token})
        self.assertIn(res.status_code, (302, 403))
        self.assertEqual(ImportReconciliationException.objects.count(), 0)
        self.client.force_login(self.admin)
        other = get_user_model().objects.create_superuser(
            username='other_registry_admin', email='other@example.invalid', password='isolated-secret',
        )
        self.client.force_login(other)
        res = self.client.post(self.url, {'confirm': '1', 'proof': token})
        self.assertContains(res, 'Confirmation rejected')
        self.assertEqual(ImportReconciliationException.objects.count(), 0)
