"""Acceptance tests for verified import reconciliation persistence."""
import copy
import hashlib
import json
from pathlib import Path
from django.test import TestCase
from apps.imports.models import ImportReconciliationException
from apps.imports.services.reconciliation_exception_registry import (
    RegistryInputError, inspect_exception_evidence, persist_exception_evidence,
)
from apps.products.models import Product
from apps.clients.models import Client, Customer

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'reconciliation_20261014'


def source():
    return (FIXTURE_DIR / 'REPORT.json').read_bytes(), (FIXTURE_DIR / 'EXCEPTIONS.csv').read_bytes()


class ExceptionIngestionTests(TestCase):
    def test_real_1151_groups_are_verified_and_preview_is_read_only(self):
        report, csv_data = source()
        before = (ImportReconciliationException.objects.count(), Product.objects.count(), Client.objects.count())
        parsed = inspect_exception_evidence(report, csv_data)
        self.assertEqual(len(parsed['entries']), 1151)
        self.assertEqual(parsed['stock_rows'], 2068)
        self.assertEqual(parsed['counts']['MISSING_PRODUCT'], 2036)
        self.assertEqual(parsed['counts']['UNKNOWN_CUSTOMER'], 32)
        self.assertTrue(persist_exception_evidence(report, csv_data)['preview_only'])
        self.assertEqual(before, (ImportReconciliationException.objects.count(), Product.objects.count(), Client.objects.count()))

    def test_explicit_persist_keeps_original_sections_and_is_idempotent(self):
        report, csv_data = source()
        result = persist_exception_evidence(report, csv_data, apply=True)
        self.assertEqual(result['new_rows'], 1151)
        self.assertEqual(ImportReconciliationException.objects.count(), 1151)
        self.assertEqual(ImportReconciliationException.objects.filter(section_code='GSM', kind='MISSING_PRODUCT').count(), 397)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Client.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        record = ImportReconciliationException.objects.get(section_code='GSM', sku='CBLOCK103GCRSKTSW')
        record.status = 'ACCEPTED_EXCEPTION'
        record.review_notes = 'Test review retained across identical import'
        record.save()
        second = persist_exception_evidence(report, csv_data, apply=True)
        self.assertEqual(second['new_rows'], 0)
        self.assertEqual(second['existing_rows'], 1151)
        record.refresh_from_db()
        self.assertEqual(record.status, 'ACCEPTED_EXCEPTION')
        self.assertEqual(record.review_notes, 'Test review retained across identical import')

    def test_checksum_change_fails_before_any_write(self):
        report, csv_data = source()
        tampered = csv_data.replace(b'CBLOCK103GCRSKTSW', b'CBLOCK103GCRSKTSX')
        self.assertNotEqual(tampered, csv_data)
        with self.assertRaisesMessage(RegistryInputError, 'checksum differs'):
            persist_exception_evidence(report, tampered, apply=True)
        self.assertEqual(ImportReconciliationException.objects.count(), 0)

    def test_report_count_change_fails_before_any_write(self):
        report, csv_data = source()
        obj = json.loads(report.decode('utf-8-sig'))
        obj['stock_missing_product_rows'] += 1
        with self.assertRaisesMessage(RegistryInputError, 'counts differ'):
            persist_exception_evidence(json.dumps(obj).encode(), csv_data, apply=True)
        self.assertEqual(ImportReconciliationException.objects.count(), 0)

    def test_separate_import_versions_keep_independent_reviews(self):
        report, csv_data = source()
        first = json.loads(report.decode('utf-8-sig'))
        persist_exception_evidence(report, csv_data, apply=True)
        first_count = ImportReconciliationException.objects.count()
        first['product_sha256'] = '0' * 64  # synthetic different source version
        next_report = json.dumps(first).encode()
        persist_exception_evidence(next_report, csv_data, apply=True)
        self.assertEqual(ImportReconciliationException.objects.count(), first_count * 2)
