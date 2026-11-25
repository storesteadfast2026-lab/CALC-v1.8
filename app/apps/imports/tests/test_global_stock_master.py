"""Global Stock Master Phase 1 regression coverage."""

import os
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client, Customer
from apps.freight.services.calculator import FreightCalculatorService
from apps.freight.services.dtos import FreightLine, FreightRequest
from apps.imports.models import (
    ExternalDataFile,
    GlobalStockSourceRow,
    StockMaster,
    ProductMaster,
    StockSourceRow,
)
from apps.imports.services.global_stock_master import (
    stock_master_comparison,
    validate_stock_master,
)
from apps.imports.services.xlsx_reader import SourceImportError
from apps.products.models import Product
from apps.rates.models import FreightRate, FreightZone


class GlobalStockMasterTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

        self.client_a = Client.objects.create(code='CALC-A', name='Calculator A')
        self.client_b = Client.objects.create(code='CALC-B', name='Calculator B')
        self.customer_a = Customer.objects.create(
            code='CUSTOM-A',
            name='Commercial A',
            linked_client=self.client_a,
            source_row_number=1,
        )
        Customer.objects.create(
            code='CUSTOM-B',
            name='Commercial B',
            linked_client=self.client_b,
            source_row_number=2,
        )
        Customer.objects.create(
            code='UNLINKED',
            name='Unlinked',
            source_row_number=3,
        )
        self.product = Product.objects.create(
            client=self.client_a,
            sku='A1',
            name='Existing A',
            length_m=1,
            width_m=1,
            height_m=1,
            weight_kg=10,
            cubic_m3=1,
            freight_type='P',
        )
        Product.objects.create(
            client=self.client_b,
            sku='A1',
            name='Existing B',
            weight_kg=40,
            cubic_m3=4,
        )
        Product.objects.create(
            client=self.client_a,
            sku='ABSENT',
            name='Absent from extract',
        )
        self.user = get_user_model().objects.create_superuser(
            'admin', 'admin@example.test', 'pw'
        )
        self.client.force_login(self.user)

    def records(self):
        pairs = [
            ('CUSTOM-A', 'A1', 2, 'SERIAL-A1'),
            ('CUSTOM-A', 'A1', 3, 'SERIAL-A2'),
            ('CUSTOM-B', 'A1', 7, 'SERIAL-B'),
            ('CUSTOM-A', 'NEW', 1, ''),
            ('UNLINKED', 'A1', 1, ''),
            ('UNKNOWN', 'A1', 1, ''),
            ('', 'A1', 1, ''),
        ]
        return [
            {
                'customer': customer,
                'product': product,
                'quantity': quantity,
                'description': f'Stock {customer} {product}',
                'category': 'Category',
                'serial_no': serial,
                'weight': 12,
                'cubic': '1.2',
                '_row_number': row_number,
            }
            for row_number, (customer, product, quantity, serial) in enumerate(pairs, 2)
        ]

    def source(self, records=None):
        return SimpleNamespace(
            records=self.records() if records is None else records,
            rejected_rows=[],
            source_format='XLS',
            worksheet='Stock',
            header_row=1,
            headers=[
                'customer', 'product', 'description', 'quantity',
                'category', 'serial_no', 'cubic', 'weight',
            ],
            warnings=[],
        )

    def master(self, content=b'test XLS bytes', filename='stock.xls'):
        master = StockMaster(
            original_filename=filename,
            sha256=sha256(content).hexdigest(),
            file_size_bytes=len(content),
        )
        master.original_file.save(filename, ContentFile(content), save=False)
        master.save()
        return master

    def validated(self, records=None):
        master = self.master()
        with patch(
            'apps.imports.services.global_stock_master.read_product_file',
            return_value=self.source(records),
        ):
            master = validate_stock_master(master.pk, actor=self.user)
        self.assertEqual(master.status, 'VALIDATED', master.error_message)
        return master

    def details_url(self, master):
        return reverse('admin:imports_stockmaster_global_details', args=[master.pk])

    def test_global_details_all_customers_preserve_serials_and_decimals(self):
        records = self.records()
        records[0]['quantity'] = '-0.125000'
        records[1]['quantity'] = '3.000001'
        records[4]['product'] = '000123'
        master = self.validated(records)
        products_before = list(Product.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.details_url(master))
            body = response.render().content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['row_page'].paginator.count, 7)
        for value in ('SERIAL-A1', 'SERIAL-A2', 'SERIAL-B', 'UNKNOWN', 'UNLINKED', '000123', '-0.125000', '3.000001'):
            self.assertIn(value, body)
        self.assertEqual(
            [q['sql'] for q in queries if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE'))],
            [],
        )
        self.assertNotContains(response, '>Apply<')
        self.assertEqual(list(Product.objects.order_by('pk').values()), products_before)

    def test_global_details_filter_customer_sku_serial_and_empty_customer(self):
        master = self.validated()
        base = self.details_url(master)
        cases = [
            ({'customer': 'CUSTOM-A'}, 3, ['SERIAL-A1', 'SERIAL-A2'], ['SERIAL-B']),
            ({'customer': 'CUSTOM-B', 'sku': 'a1'}, 1, ['SERIAL-B'], ['SERIAL-A1']),
            ({'customer': 'UNLINKED'}, 1, ['UNLINKED'], ['UNKNOWN']),
            ({'customer': 'UNKNOWN'}, 1, ['UNKNOWN'], ['UNLINKED']),
            ({'customer': ''}, 1, ['No Apply action'], ['SERIAL-A1']),
            ({'sku': 'A1', 'serial_no': 'SERIAL-A2'}, 1, ['SERIAL-A2'], ['SERIAL-A1']),
            ({'serial_no': 'SERIAL-ABSENT'}, 0, ['No source rows match'], ['SERIAL-A1']),
        ]
        for filters, count, visible, hidden in cases:
            with self.subTest(filters=filters):
                response = self.client.get(base, filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['row_page'].paginator.count, count)
                for text in visible:
                    self.assertContains(response, text)
                for text in hidden:
                    self.assertNotContains(response, text)

    def test_global_details_paging_is_stable_and_filters_are_preserved(self):
        records = [
            dict(self.records()[0], product='000123', _row_number=i + 2, serial_no=f'LINE-{i:03}')
            for i in range(216)
        ]
        master = self.validated(records)
        response = self.client.get(self.details_url(master), {'customer': 'CUSTOM-A', 'sku': '000123', 'page': '3'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['row_page'].paginator.count, 216)
        self.assertEqual(len(response.context['row_page']), 16)
        self.assertContains(response, 'LINE-215')
        self.assertContains(response, 'customer=CUSTOM-A')
        self.assertContains(response, 'sku=000123')
        self.assertNotContains(response, 'LINE-000</td>')

    def test_global_details_post_is_forbidden_and_unvalidated_is_hidden(self):
        master = self.validated()
        url = self.details_url(master)
        self.assertEqual(self.client.post(url, {'action': 'apply'}).status_code, 405)
        self.assertEqual(self.client.get(self.details_url(self.master())).status_code, 404)
        self.assertEqual(self.client.get(url, {'customer': 'x' * 101}).context['row_page'].paginator.count, 0)
        self.client.logout()
        anonymous = self.client.get(url)
        self.assertNotEqual(anonymous.status_code, 200)
        non_admin = get_user_model().objects.create_user('ordinary', 'ordinary@example.test', 'pw')
        self.client.force_login(non_admin)
        self.assertNotEqual(self.client.get(url).status_code, 200)
        staff = get_user_model().objects.create_user('staff', 'staff@example.test', 'pw', is_staff=True)
        self.client.force_login(staff)
        self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_global_details_overview_links_cover_unlinked_unknown_and_blank(self):
        master = self.validated()
        response = self.client.get(reverse('admin:imports_stockmaster_change', args=[master.pk]))
        self.assertContains(response, 'File rows')
        self.assertContains(response, 'Back to Import Centre')
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, '?customer=UNLINKED')
        self.assertContains(response, '?customer=UNKNOWN')
        self.assertContains(response, '?customer=')
        self.assertContains(response, 'Compare customer products')

    def test_global_details_escapes_customer_filter_in_html(self):
        master = self.validated()
        response = self.client.get(self.details_url(master), {'customer': '<script>alert(1)</script>'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')

    def global_recon_url(self, master):
        return reverse('admin:imports_stockmaster_global_reconciliation', args=[master.pk])

    def validated_product_master(self, records):
        content = b'controlled Product Master fixture'
        obj = ProductMaster(
            original_filename='products.xls', sha256=sha256(content).hexdigest(),
            file_size_bytes=len(content), status='VALIDATED',
        )
        obj.original_file.save('products.xls', ContentFile(content), save=False)
        obj.save()
        return obj, SimpleNamespace(records=records, rejected_rows=[])

    def test_global_reconciliation_informative_statuses_and_source_detail(self):
        stock = self.validated()
        _, fake_source = self.validated_product_master([
            {'customer': 'CUSTOM-A', 'code': 'A1', 'name': 'Matched A'},
            {'customer': 'CUSTOM-B', 'code': 'A1', 'name': 'Matched B'},
            {'customer': 'UNLINKED', 'code': 'A1', 'name': 'Unlinked product'},
            {'customer': 'NTE', 'code': 'ONLY-PM', 'name': 'Product without Stock'},
        ])
        before_products = list(Product.objects.order_by('pk').values())
        before_stock = list(stock.source_rows.order_by('pk').values())
        with patch('apps.imports.services.global_stock_reconciliation.read_product_file', return_value=fake_source):
            with CaptureQueriesContext(connection) as statements:
                response = self.client.get(self.global_recon_url(stock))
                body = response.render().content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['workspace']['totals'], {
            'MATCHED': 3, 'STOCK_ONLY': 3, 'PRODUCT_MASTER_ONLY': 1,
        })
        self.assertEqual(response.context['row_page'].paginator.count, 7)
        self.assertIn('View original rows', body)
        self.assertIn('UNKNOWN_CUSTOMER', body)
        self.assertIn('UNLINKED', body)
        self.assertIn('SERIAL', str(before_stock))
        self.assertEqual(
            [q['sql'] for q in statements if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE'))], [],
        )
        self.assertEqual(list(Product.objects.order_by('pk').values()), before_products)
        self.assertEqual(list(stock.source_rows.order_by('pk').values()), before_stock)
        self.assertNotIn('>Apply<', body)

    def test_global_reconciliation_exact_filters_and_leading_zero_skus(self):
        records = self.records() + [{
            **self.records()[0], 'product': '000123', '_row_number': 99,
            'serial_no': 'SER-ZERO',
        }]
        stock = self.validated(records)
        _, fake_source = self.validated_product_master([
            {'customer': 'CUSTOM-A', 'code': '000123', 'name': 'Leading zero'},
            {'customer': 'CUSTOM-B', 'code': 'A1', 'name': 'Different owner'},
            {'customer': 'CUSTOM-A', 'code': 'ONLY-PM', 'name': 'Master only'},
        ])
        url = self.global_recon_url(stock)
        with patch('apps.imports.services.global_stock_reconciliation.read_product_file', return_value=fake_source):
            response = self.client.get(url, {'customer': 'custom-a', 'sku': '000123', 'status': 'MATCHED'})
            self.assertEqual(response.context['row_page'].paginator.count, 1)
            self.assertContains(response, '000123')
            self.assertContains(response, 'sku=000123')
            self.assertContains(response, 'customer=CUSTOM-A')
            response = self.client.get(url, {'customer': 'CUSTOM-A', 'status': 'PRODUCT_MASTER_ONLY'})
            self.assertEqual(response.context['row_page'].paginator.count, 1)
            self.assertContains(response, 'ONLY-PM')
            response = self.client.get(url, {'customer': ''})
            self.assertEqual(response.context['row_page'].paginator.count, 1)
            response = self.client.get(url, {'status': 'INVALID'})
            self.assertEqual(response.context['row_page'].paginator.count, 0)
            self.assertContains(response, 'Select a valid choice')

    def test_global_reconciliation_product_master_duplicates_are_not_matched(self):
        stock = self.validated()
        _, fake_source = self.validated_product_master([
            {'customer': 'CUSTOM-A', 'code': 'A1', 'name': 'Duplicate 1'},
            {'customer': 'CUSTOM-A', 'code': 'A1', 'name': 'Duplicate 2'},
        ])
        with patch('apps.imports.services.global_stock_reconciliation.read_product_file', return_value=fake_source):
            response = self.client.get(self.global_recon_url(stock), {'status': 'AMBIGUOUS_PRODUCT_MASTER'})
        self.assertEqual(response.context['row_page'].paginator.count, 1)
        self.assertContains(response, '2 duplicates')

    def test_incomplete_product_master_rows_show_original_numbers_and_missing_fields(self):
        stock = self.validated()
        _, fake_source = self.validated_product_master([
            {'customer': '', 'code': '000123', 'name': 'Missing customer',
             'description': 'Keep leading zero', '_row_number': 44},
            {'customer': 'STH', 'code': '', 'name': 'Missing code',
             'description': 'No SKU', '_row_number': 57},
            {'customer': '', 'code': '', 'name': 'Both missing',
             'description': '<script>alert(1)</script>', '_row_number': 91},
            {'customer': 'STH', 'code': '000002', 'name': 'Valid product',
             '_row_number': 100},
        ])
        fake_source.worksheet = 'Products'
        url = self.global_recon_url(stock)
        with patch('apps.imports.services.global_stock_reconciliation.read_product_file', return_value=fake_source):
            default = self.client.get(url)
            self.assertEqual(default.status_code, 200)
            self.assertContains(default, 'View 3 incomplete Product Master rows')
            self.assertNotContains(default, 'Both missing</td>')
            before_products = list(Product.objects.order_by('pk').values())
            before_stock = list(stock.source_rows.order_by('pk').values())
            with CaptureQueriesContext(connection) as statements:
                detail = self.client.get(url, {'incomplete': '1'})
                body = detail.render().content.decode()
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context['workspace']['product_master_incomplete_keys'], 3)
        self.assertEqual(len(detail.context['workspace']['product_master_incomplete_rows']), 3)
        self.assertIn('000123', body)
        self.assertIn('>44</td>', body)
        self.assertIn('>57</td>', body)
        self.assertIn('>91</td>', body)
        self.assertIn('Products', body)
        self.assertIn('CUSTOMER, CODE (SKU)', body)
        self.assertNotIn('<script>alert(1)</script>', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertEqual(
            [q['sql'] for q in statements if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE'))], []
        )
        self.assertEqual(list(Product.objects.order_by('pk').values()), before_products)
        self.assertEqual(list(stock.source_rows.order_by('pk').values()), before_stock)

    def test_incomplete_product_master_rows_are_admin_only_and_get_only(self):
        stock = self.validated()
        url = self.global_recon_url(stock) + '?incomplete=1'
        self.assertEqual(self.client.post(url).status_code, 405)
        self.client.logout()
        self.assertNotEqual(self.client.get(url).status_code, 200)
        non_admin = get_user_model().objects.create_user('incomplete_reader', 'i@example.test', 'pw', is_staff=True)
        self.client.force_login(non_admin)
        self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_global_reconciliation_missing_or_corrupted_master_is_controlled(self):
        stock = self.validated()
        url = self.global_recon_url(stock)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No validated Product Master')
        self.assertEqual(response.context['row_page'].paginator.count, 0)
        obj, _ = self.validated_product_master([])
        obj.sha256 = '0' * 64
        obj.save(update_fields=['sha256'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'checksum does not match')
        self.assertEqual(response.context['row_page'].paginator.count, 0)

    def test_global_reconciliation_restricted_to_admin_get_and_validated_source(self):
        stock = self.validated()
        url = self.global_recon_url(stock)
        self.assertEqual(self.client.post(url, {'action': 'apply'}).status_code, 405)
        self.assertEqual(self.client.get(self.global_recon_url(self.master())).status_code, 404)
        for is_staff in (False, True):
            user = get_user_model().objects.create_user(
                'reader%d' % is_staff, 'reader%d@example.test' % is_staff,
                'pw', is_staff=is_staff,
            )
            self.client.force_login(user)
            self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_global_reconciliation_pagination_and_filter_preservation(self):
        stock = self.validated()
        _, fake_source = self.validated_product_master([
            {'customer': 'CUSTOM-A', 'code': 'PM-%03d' % i, 'name': 'Master product'}
            for i in range(103)
        ])
        with patch('apps.imports.services.global_stock_reconciliation.read_product_file', return_value=fake_source):
            response = self.client.get(self.global_recon_url(stock), {
                'customer': 'CUSTOM-A', 'status': 'PRODUCT_MASTER_ONLY', 'page': 3,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['row_page'].paginator.count, 103)
        self.assertEqual(len(response.context['row_page']), 3)
        self.assertContains(response, 'Page 3 of 3')
        self.assertContains(response, 'status=PRODUCT_MASTER_ONLY')
        self.assertContains(response, 'customer=CUSTOM-A')

    def compare_url(self, master, client=None):
        return reverse(
            'admin:imports_stockmaster_compare',
            args=[master.pk, (client or self.client_a).pk],
        )

    def test_repeated_rows_aggregate_and_preserve_all_serial_detail(self):
        master = self.validated()
        workspace = stock_master_comparison(master, self.client_a)
        row = next(item for item in workspace['rows'] if item['sku'] == 'A1')
        self.assertEqual(
            (row['quantity'], row['raw_row_count'], row['status']),
            (Decimal('5'), 2, 'MATCHED'),
        )
        self.assertEqual(master.source_rows.count(), 7)
        self.assertEqual(
            list(
                master.source_rows.filter(
                    customer_code='CUSTOM-A', product_code_normalized='A1'
                ).values_list('serial_no', flat=True)
            ),
            ['SERIAL-A1', 'SERIAL-A2'],
        )
        self.assertEqual(workspace['summary']['unique_stock_skus'], 2)
        self.assertEqual(workspace['summary']['total_quantity'], Decimal('6'))

    def test_same_sku_in_different_customers_remains_isolated(self):
        master = self.validated()
        workspace_a = stock_master_comparison(master, self.client_a)
        workspace_b = stock_master_comparison(master, self.client_b)
        row_a = next(item for item in workspace_a['rows'] if item['sku'] == 'A1')
        row_b = workspace_b['rows'][0]
        self.assertEqual(row_a['quantity'], 5)
        self.assertEqual(row_b['quantity'], 7)
        self.assertEqual(row_a['product'].client, self.client_a)
        self.assertEqual(row_b['product'].client, self.client_b)
        self.assertEqual(workspace_a['summary']['raw_rows'], 3)
        self.assertEqual(workspace_b['summary']['raw_rows'], 1)

    def test_customer_resolution_uses_existing_four_states(self):
        master = self.validated()
        self.assertEqual(
            master.validation_summary['status_counts'],
            {
                'LINKED': 4,
                'UNLINKED': 1,
                'UNKNOWN_CUSTOMER': 1,
                'EMPTY_CUSTOMER': 1,
            },
        )
        self.assertEqual((Client.objects.count(), Customer.objects.count()), (2, 3))

    def test_stock_without_product_does_not_create_or_change_product(self):
        before = list(Product.objects.order_by('pk').values())
        master = self.validated()
        workspace = stock_master_comparison(master, self.client_a)
        self.assertEqual(workspace['summary']['stock_without_product'], 1)
        self.assertEqual(workspace['summary']['operational_products'], 2)
        self.assertEqual(list(Product.objects.order_by('pk').values()), before)
        self.assertFalse(Product.objects.filter(sku='NEW').exists())
        self.assertEqual(ExternalDataFile.objects.count(), 0)

    def test_preview_performs_no_writes_has_no_apply_and_does_not_zero(self):
        master = self.validated()
        before = list(Product.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.compare_url(master))
            overview = self.client.get(
                reverse('admin:imports_stockmaster_change', args=[master.pk])
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(overview.status_code, 200)
        writes = [
            query['sql']
            for query in queries
            if query['sql'].lstrip().upper().startswith(
                ('INSERT', 'UPDATE', 'DELETE', 'REPLACE')
            )
        ]
        self.assertEqual(writes, [])
        self.assertNotContains(response, '>Apply<')
        self.assertContains(response, 'Absence from this source is not quantity zero')
        self.assertContains(response, 'ABSENT')
        self.assertNotContains(response, 'SERIAL-B')
        self.assertEqual(list(Product.objects.order_by('pk').values()), before)
        self.assertEqual(self.client.post(self.compare_url(master), {'action': 'apply'}).status_code, 405)
        self.assertEqual(
            self.client.post(reverse('admin:imports_stockmaster_change', args=[master.pk])).status_code,
            405,
        )

    def test_upload_is_global_and_does_not_request_client(self):
        url = reverse('admin:imports_stockmaster_add')
        self.assertNotContains(self.client.get(url), 'name="client"')
        for filename in ('stock.xls', 'stock_STH.xls', 'another_customer_extract.xls'):
            response = self.client.post(
                url,
                {'original_file': SimpleUploadedFile(filename, b'xls')},
            )
            self.assertEqual(response.status_code, 302)
        self.assertEqual(StockMaster.objects.count(), 3)
        self.assertFalse(ExternalDataFile._meta.get_field('client').null)

    def test_checksum_failure_and_invalid_workbook_do_not_touch_products(self):
        before = list(Product.objects.order_by('pk').values())
        master = self.master()
        master.original_file.save('tampered.xls', ContentFile(b'tampered'), save=True)
        master = validate_stock_master(master.pk)
        self.assertEqual(master.status, 'VALIDATION_FAILED')
        self.assertIn('checksum', master.error_message)
        self.assertEqual(GlobalStockSourceRow.objects.count(), 0)
        self.assertEqual(list(Product.objects.order_by('pk').values()), before)

        invalid = validate_stock_master(self.master().pk)
        self.assertEqual(invalid.status, 'VALIDATION_FAILED')
        self.assertEqual(list(Product.objects.order_by('pk').values()), before)

    def test_invalid_numeric_rows_are_excluded_and_reported(self):
        records = self.records()
        records[1]['quantity'] = 'not numeric'
        records[2]['weight'] = 'NaN'
        master = self.validated(records)
        self.assertEqual(master.validation_summary['rows_invalid'], 2)
        self.assertEqual(master.source_rows.count(), 5)
        row = next(
            item
            for item in stock_master_comparison(master, self.client_a)['rows']
            if item['sku'] == 'A1'
        )
        self.assertEqual(row['quantity'], 2)
        self.assertEqual(len(master.validation_summary['invalid_rows']), 2)

    def test_reader_rejections_and_all_invalid_rows_are_visible(self):
        master = self.master()
        source = self.source([dict(self.records()[0], quantity='Infinity')])
        source.rejected_rows = [{'row': 3, 'reason': 'Reader rejected row'}]
        with patch(
            'apps.imports.services.global_stock_master.read_product_file',
            return_value=source,
        ):
            master = validate_stock_master(master.pk)
        self.assertEqual(master.status, 'VALIDATION_FAILED')
        self.assertEqual(master.validation_summary['rows_read'], 1)
        self.assertEqual(master.validation_summary['rows_rejected_by_reader'], 1)
        self.assertEqual(master.validation_summary['rows_invalid'], 1)
        self.assertEqual(GlobalStockSourceRow.objects.count(), 0)

    def test_preview_paginates_without_truncating_source(self):
        records = [
            dict(self.records()[0], product=f'SKU-{index:03}', _row_number=index + 2)
            for index in range(121)
        ]
        master = self.validated(records)
        response = self.client.get(self.compare_url(master) + '?page=3&raw_page=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['raw_rows'], 121)
        self.assertEqual(response.context['summary']['unique_stock_skus'], 121)
        self.assertEqual(len(response.context['row_page']), 21)
        self.assertEqual(len(response.context['raw_page']), 21)
        self.assertContains(response, 'SKU-120')

    def test_weight_and_cubic_are_reference_only_until_semantics_confirmed(self):
        master = self.validated()
        row = next(
            item
            for item in stock_master_comparison(master, self.client_a)['rows']
            if item['sku'] == 'A1'
        )
        self.assertEqual(row['product_weight'], Decimal('10'))
        self.assertEqual(row['stock_weight'], Decimal('12'))
        self.assertIsNone(row['weight_difference'])
        self.assertEqual(row['product_cubic'], Decimal('1'))
        self.assertEqual(row['stock_cubic'], Decimal('1.2'))
        self.assertIsNone(row['cubic_difference'])
        self.assertTrue(any('difference unavailable' in warning for warning in row['warnings']))

    def test_conflicting_stock_physical_references_are_not_selected(self):
        records = self.records()
        records[1]['weight'] = 20
        records[1]['cubic'] = 2
        master = self.validated(records)
        row = next(
            item
            for item in stock_master_comparison(master, self.client_a)['rows']
            if item['sku'] == 'A1'
        )
        self.assertIsNone(row['stock_weight'])
        self.assertIsNone(row['weight_difference'])
        self.assertIsNone(row['stock_cubic'])
        self.assertIsNone(row['cubic_difference'])
        self.assertEqual(row['quantity'], 5)

    def test_ambiguous_normalized_product_is_not_matched(self):
        Product.objects.create(client=self.client_a, sku='a1', name='Case variant')
        master = self.validated()
        row = next(
            item
            for item in stock_master_comparison(master, self.client_a)['rows']
            if item['sku'] == 'A1'
        )
        self.assertEqual(row['status'], 'AMBIGUOUS OPERATIONAL PRODUCT')
        self.assertIsNone(row['product'])
        self.assertEqual(
            stock_master_comparison(master, self.client_a)['summary']['ambiguous_products'],
            1,
        )

    def test_signed_quantity_is_retained_as_reference(self):
        records = self.records()
        records[0]['quantity'] = -2
        master = self.validated(records)
        row = next(
            item
            for item in stock_master_comparison(master, self.client_a)['rows']
            if item['sku'] == 'A1'
        )
        self.assertEqual(row['quantity'], 1)
        self.assertTrue(any('Signed negative' in warning for warning in row['warnings']))

    def test_revalidation_is_blocked_and_current_customer_link_is_resolved(self):
        master = self.validated()
        with self.assertRaises(SourceImportError):
            validate_stock_master(master.pk)
        self.customer_a.linked_client = None
        self.customer_a.save(update_fields=['linked_client'])
        overview = self.client.get(
            reverse('admin:imports_stockmaster_change', args=[master.pk])
        )
        self.assertEqual(overview.context['summary']['status_counts']['UNLINKED'], 4)
        self.assertEqual(master.source_rows.count(), 7)

    def test_validation_endpoint_is_post_only(self):
        master = self.master()
        url = reverse('admin:imports_stockmaster_validate', args=[master.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        with patch(
            'apps.imports.services.global_stock_master.read_product_file',
            return_value=self.source(),
        ):
            self.assertEqual(self.client.post(url).status_code, 302)
        master.refresh_from_db()
        self.assertEqual(master.status, 'VALIDATED')

    def test_new_staging_does_not_change_historical_stock_schema(self):
        legacy_fk = StockSourceRow._meta.get_field('external_file')
        self.assertFalse(legacy_fk.null)
        self.assertEqual(legacy_fk.related_model, ExternalDataFile)
        global_fk = GlobalStockSourceRow._meta.get_field('stock_master')
        self.assertFalse(global_fk.null)
        self.assertEqual(global_fk.related_model, StockMaster)

    def test_existing_freight_result_is_exactly_unchanged_after_preview(self):
        carrier = Carrier.objects.create(code='TEST', name='Test carrier')
        service = CarrierService.objects.create(carrier=carrier, service_code='ROAD')
        ClientCarrierConfig.objects.create(
            client=self.client_a,
            carrier_service=service,
            customer_code=self.client_a.code,
            fuel_levy=Decimal('0.2'),
        )
        FreightZone.objects.create(
            client=self.client_a,
            carrier_service=service,
            suburb='ADELAIDE',
            state='SA',
            postcode='5000',
            zone='A',
        )
        FreightRate.objects.create(
            client=self.client_a,
            carrier_service=service,
            zone='A',
            customer_code=self.client_a.code,
            freight_type='P',
            minimum_charge=50,
            basic_charge=40,
            per_kg=1,
        )

        def calculate():
            product = Product.objects.get(pk=self.product.pk)
            request = FreightRequest(
                client_code=self.client_a.code,
                from_address_id=None,
                suburb='ADELAIDE',
                state='SA',
                postcode='5000',
                tailgate=False,
                preselect_sku=True,
                lines=[
                    FreightLine(
                        product.sku,
                        Decimal('1'),
                        product.freight_type,
                        product.length_m,
                        product.width_m,
                        product.height_m,
                        product.weight_kg,
                        product.cubic_m3,
                    )
                ],
            )
            return FreightCalculatorService().calculate(request)

        before = calculate()
        self.assertTrue(before)
        master = self.validated()
        self.assertEqual(self.client.get(self.compare_url(master)).status_code, 200)
        self.assertEqual(calculate(), before)
        self.assertEqual(Product.objects.count(), 3)

    def test_real_controlled_xls_extract_when_supplied(self):
        filename = os.environ.get('STOCK_MASTER_TEST_FILE')
        if not filename:
            self.skipTest('Set STOCK_MASTER_TEST_FILE to stock_STH.xls.')
        path = Path(filename)
        master = validate_stock_master(self.master(path.read_bytes(), path.name).pk)
        self.assertEqual(master.status, 'VALIDATED', master.error_message)
        self.assertEqual(master.validation_summary['rows_read'], 913)
        self.assertEqual(master.source_rows.count(), 913)
        self.assertEqual(master.validation_summary['rows_invalid'], 0)
        self.assertEqual(master.validation_summary['rows_rejected_by_reader'], 0)
        customer = Customer.objects.create(
            code='STH',
            name='Test extract',
            linked_client=Client.objects.create(code='STH-TEST', name='Extract'),
            source_row_number=4,
        )
        workspace = stock_master_comparison(master, customer.linked_client)
        self.assertEqual(workspace['summary']['unique_stock_skus'], 136)
        self.assertEqual(workspace['summary']['total_quantity'], Decimal('2178'))
        self.assertEqual(Product.objects.count(), 3)

    def test_real_global_xls_when_supplied(self):
        filename = os.environ.get('STOCK_MASTER_GLOBAL_TEST_FILE')
        if not filename:
            self.skipTest('Set STOCK_MASTER_GLOBAL_TEST_FILE to the global stock.xls.')
        path = Path(filename)
        master = validate_stock_master(self.master(path.read_bytes(), path.name).pk)
        self.assertEqual(master.status, 'VALIDATED', master.error_message)
        self.assertEqual(master.validation_summary['rows_read'], 21411)
        self.assertEqual(master.source_rows.count(), 21411)
        self.assertEqual(master.validation_summary['rows_rejected_by_reader'], 0)
        self.assertEqual(len(master.validation_summary['customer_counts']), 90)
        self.assertEqual(master.validation_summary['unique_customer_skus'], 16098)
        self.assertEqual(master.validation_summary['repeated_detail_rows'], 5313)
