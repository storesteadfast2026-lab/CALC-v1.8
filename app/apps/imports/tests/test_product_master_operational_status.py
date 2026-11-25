"""Product Master detail defers its memory-heavy comparison until requested."""

from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.clients.models import Client, Customer
from apps.imports.models import ProductMaster
from apps.imports.tests import test_product_master_reconciliation_bridge as bridge_tests
from apps.products.models import Product


class ProductMasterOperationalStatusTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.sth = Client.objects.create(code='STH', name='Steadfast')
        self.pon = Client.objects.create(code='PON', name='Pon Bike')
        self.sth_customer = Customer.objects.create(
            code='STH', name='Steadfast', linked_client=self.sth, source_row_number=1)
        Customer.objects.create(
            code='PON', name='Pon Bike', linked_client=self.pon, source_row_number=2)
        Customer.objects.create(code='ABC', name='Unlinked', source_row_number=3)
        Product.objects.create(client=self.sth, sku='A1', name='Old STH')
        Product.objects.create(client=self.pon, sku='A1', name='Old PON')
        content = b'example product master bytes'
        self.master = ProductMaster(
            original_filename='products.xls', sha256=sha256(content).hexdigest(),
            file_size_bytes=len(content), status='VALIDATED',
            validation_summary={'rows_read': 124, 'customer_counts': {
                'STH': 123, 'PON': 1, 'ABC': 1}, 'status_counts': {'LINKED': 124}},
        )
        self.master.original_file.save('products.xls', ContentFile(content), save=False)
        self.master.save()
        self.client.force_login(get_user_model().objects.create_superuser(
            'admin', 'admin@example.test', 'password'))

    def detail(self):
        return self.client.get(reverse('admin:imports_productmaster_change',
                                       args=[self.master.pk]))

    def comparison(self, calculator_customer):
        return self.client.get(reverse('admin:imports_productmaster_compare',
                                       args=[self.master.pk, calculator_customer.pk]))

    def test_detail_lists_linked_customers_without_reading_workbook(self):
        with patch('apps.imports.services.product_master.read_product_file',
                   side_effect=bridge_tests.ProductMasterReadOnlyBridgeTests.staged_workbook) as reader:
            detail = self.detail()
            self.assertEqual(detail.status_code, 200)
            self.assertContains(detail, 'LINKED: 124')
            detail = self.client.get(reverse('admin:imports_productmaster_change',
                                            args=[self.master.pk]), {'section': 'compare'})
            html = detail.content.decode()
            self.assertIn('Compare STH', html)
            self.assertIn('Compare PON', html)
            self.assertNotIn('Compare ABC', html)
            self.assertIn('is not re-read automatically', html)
            reader.assert_not_called()

    def test_comparison_reads_workbook_only_when_selected(self):
        with patch('apps.imports.services.product_master.read_product_file',
                   side_effect=bridge_tests.ProductMasterReadOnlyBridgeTests.import_workbook) as reader:
            compare = self.comparison(self.sth)
            self.assertEqual(compare.status_code, 200)
            self.assertEqual(compare.context['summary']['source_rows'], 3)
            reader.assert_called_once()
            self.assertEqual(Product.objects.get(client=self.pon, sku='A1').name, 'Old PON')
