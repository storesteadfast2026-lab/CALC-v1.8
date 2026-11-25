from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.clients.models import Client, Customer
from apps.imports.models import ProductMaster
from apps.imports.services.product_availability import (
    INCOMPLETE_PHYSICAL_DATA_MESSAGE,
    LARGE_DIMENSION_DIFFERENCE_MESSAGE,
    UNKNOWN_DIMENSIONS_MESSAGE,
    product_contact_notices,
)


class UnknownDimensionProductNoticeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_record = Client.objects.create(
            code='STH',
            name='Steadfast',
            dimension_fallback_source='OUTER',
        )
        Customer.objects.create(
            code='STH',
            name='Steadfast',
            source_row_number=1,
            linked_client=self.client_record,
        )
        ProductMaster.objects.create(
            original_file='product_master/products.xls',
            original_filename='products.xls',
            sha256='a' * 64,
            file_size_bytes=1,
            status='VALIDATED',
        )

    @patch('apps.imports.services.product_availability.build_workspace')
    @patch('apps.imports.services.product_availability.reconciliation_rows_for_customer')
    def test_returns_products_with_unknown_or_highly_inconsistent_dimensions(
        self, reconciliation_rows, build_workspace,
    ):
        reconciliation_rows.return_value = ([object()], [])
        build_workspace.return_value = ([
            {
                'status': 'SOURCE_ONLY',
                'sku': 'BRH4443',
                'source_values': {
                    'name': 'Blocked Product',
                    'description': '',
                    'length_m': 0,
                    'width_m': 0,
                    'height_m': 0,
                    'cubic_m3': 1,
                },
            },
            {
                'status': 'SOURCE_ONLY',
                'sku': 'READY1',
                'source_values': {
                    'name': 'Ready Product',
                    'description': '',
                    'length_m': 1,
                    'width_m': 1,
                    'height_m': 1,
                    'cubic_m3': 1,
                    'weight_kg': 1,
                },
            },
            {
                'status': 'SOURCE_ONLY',
                'sku': 'MISSINGKG',
                'source_values': {
                    'name': 'Missing Weight',
                    'description': '',
                    'length_m': 1,
                    'width_m': 1,
                    'height_m': 1,
                    'cubic_m3': 1,
                    'weight_kg': 0,
                },
            },
            {
                'status': 'SOURCE_ONLY',
                'sku': 'REVIEW10',
                'source_values': {
                    'name': 'Review Product',
                    'description': '',
                    'length_m': 10,
                    'width_m': 1,
                    'height_m': 1,
                    'cubic_m3': 1,
                    'weight_kg': 1,
                },
            },
            {
                'status': 'SAME',
                'sku': 'EXISTING1',
                'source_values': {
                    'name': '',
                    'description': '',
                    'length_m': 0,
                    'width_m': 0,
                    'height_m': 0,
                    'cubic_m3': 0,
                    'weight_kg': 0,
                },
            },
        ], {})

        self.assertEqual(product_contact_notices(self.client_record), [
            {
                'sku': 'BRH4443',
                'name': 'Blocked Product',
                'description': '',
                'message': UNKNOWN_DIMENSIONS_MESSAGE,
            },
            {
                'sku': 'MISSINGKG',
                'name': 'Missing Weight',
                'description': '',
                'message': INCOMPLETE_PHYSICAL_DATA_MESSAGE,
            },
            {
                'sku': 'REVIEW10',
                'name': 'Review Product',
                'description': '',
                'message': LARGE_DIMENSION_DIFFERENCE_MESSAGE,
            },
        ])

    @patch('apps.imports.services.product_availability.build_workspace')
    @patch('apps.imports.services.product_availability.reconciliation_rows_for_customer')
    def test_uses_client_confirmation_factor_and_refreshes_cached_result(
        self, reconciliation_rows, build_workspace,
    ):
        reconciliation_rows.return_value = ([object()], [])
        build_workspace.return_value = ([{
            'status': 'SOURCE_ONLY',
            'sku': 'REVIEW2',
            'source_values': {
                'name': 'Review Product',
                'description': '',
                'length_m': 2,
                'width_m': 1,
                'height_m': 1,
                'cubic_m3': 1,
                'weight_kg': 1,
            },
        }], {})

        self.assertEqual(product_contact_notices(self.client_record), [])
        self.client_record.cubic_dimension_confirmation_factor = 2
        self.client_record.save(update_fields=['cubic_dimension_confirmation_factor'])

        self.assertEqual(product_contact_notices(self.client_record), [{
            'sku': 'REVIEW2',
            'name': 'Review Product',
            'description': '',
            'message': LARGE_DIMENSION_DIFFERENCE_MESSAGE,
        }])
