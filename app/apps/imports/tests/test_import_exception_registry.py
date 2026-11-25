from django.test import TestCase
from django.db import IntegrityError, transaction
from apps.imports.models import ImportReconciliationException


class ImportExceptionRegistryTests(TestCase):
    def test_open_exception_does_not_create_operational_product(self):
        from apps.products.models import Product
        before = Product.objects.count()
        exc = ImportReconciliationException.objects.create(
            source_stock_sha256='a'*64, source_product_sha256='b'*64,
            section_code='GSM', sku='CBLOCK103GCRSKTSW',
            kind='MISSING_PRODUCT', stock_row_count=1)
        self.assertEqual(exc.status, 'OPEN')
        self.assertEqual(Product.objects.count(), before)

    def test_same_source_exception_is_unique(self):
        fields = dict(source_stock_sha256='a'*64, source_product_sha256='b'*64,
                      section_code='GSM', sku='X', kind='MISSING_PRODUCT')
        ImportReconciliationException.objects.create(**fields)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImportReconciliationException.objects.create(**fields)

    def test_different_import_versions_preserve_history(self):
        common = dict(section_code='GSM', sku='X', kind='MISSING_PRODUCT')
        ImportReconciliationException.objects.create(source_stock_sha256='a'*64, source_product_sha256='b'*64, **common)
        ImportReconciliationException.objects.create(source_stock_sha256='c'*64, source_product_sha256='b'*64, **common)
        self.assertEqual(ImportReconciliationException.objects.count(), 2)
