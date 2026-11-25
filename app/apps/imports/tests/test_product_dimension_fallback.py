from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from apps.clients.models import Client
from apps.imports.models import ExternalDataFile, ProductSourceRow
from apps.imports.services.product_dimensions import (
    has_large_cubic_dimension_difference,
    resolve_product_dimensions,
)
from apps.imports.services.product_master import new_product_warnings
from apps.imports.services.product_reconciliation_workspace import build_workspace


class ProductDimensionFallbackTests(TestCase):
    @staticmethod
    def source(*, primary=(0, 0, 0), raw=None):
        return SimpleNamespace(
            length_mm=Decimal(str(primary[0])),
            width_mm=Decimal(str(primary[1])),
            height_mm=Decimal(str(primary[2])),
            raw_data=raw or {},
        )

    def test_primary_dimensions_always_take_precedence(self):
        client = SimpleNamespace(dimension_fallback_source='OUTER')
        resolved = resolve_product_dimensions(
            self.source(
                primary=(1200, 800, 350),
                raw={'outer_l': 4700, 'outer_w': 750, 'outer_h': 1050},
            ),
            client,
        )
        self.assertEqual(
            resolved,
            (Decimal('1.2'), Decimal('0.8'), Decimal('0.35'), 'PRIMARY', False),
        )

    def test_tenfold_cubic_dimension_difference_requires_review(self):
        self.assertTrue(has_large_cubic_dimension_difference(10, 1, 1, 1))
        self.assertTrue(has_large_cubic_dimension_difference(1, 1, 1, 10))
        self.assertFalse(has_large_cubic_dimension_difference(9, 1, 1, 1))
        self.assertFalse(has_large_cubic_dimension_difference(0, 1, 1, 1))

    def test_configured_cubic_dimension_factor_controls_review(self):
        self.assertTrue(has_large_cubic_dimension_difference(2, 1, 1, 1, Decimal('2')))
        self.assertFalse(has_large_cubic_dimension_difference(2, 1, 1, 1, Decimal('3')))

    def test_configured_outer_is_used_only_for_fully_missing_primary(self):
        client = SimpleNamespace(dimension_fallback_source='OUTER')
        resolved = resolve_product_dimensions(
            self.source(raw={'OUTER_L': 4700, 'Outer W': 750, 'outer_h': 1050}),
            client,
        )
        self.assertEqual(
            resolved,
            (Decimal('4.7'), Decimal('0.75'), Decimal('1.05'), 'OUTER', True),
        )

    def test_partial_primary_is_not_silently_replaced(self):
        client = SimpleNamespace(dimension_fallback_source='OUTER')
        resolved = resolve_product_dimensions(
            self.source(
                primary=(1200, 0, 350),
                raw={'outer_l': 4700, 'outer_w': 750, 'outer_h': 1050},
            ),
            client,
        )
        self.assertEqual(
            resolved,
            (Decimal('1.2'), Decimal('0'), Decimal('0.35'), 'PRIMARY_PARTIAL', False),
        )

    def test_inner_piece_and_missing_configuration_are_explicit(self):
        raw = {
            'inner_l': 1000, 'inner_w': 600, 'inner_h': 300,
            'piece_l': 500, 'piece_w': 200, 'piece_h': 100,
        }
        self.assertEqual(
            resolve_product_dimensions(
                self.source(raw=raw), SimpleNamespace(dimension_fallback_source='INNER'),
            ),
            (Decimal('1'), Decimal('0.6'), Decimal('0.3'), 'INNER', True),
        )
        self.assertEqual(
            resolve_product_dimensions(
                self.source(raw=raw), SimpleNamespace(dimension_fallback_source='PIECE'),
            ),
            (Decimal('0.5'), Decimal('0.2'), Decimal('0.1'), 'PIECE', True),
        )
        self.assertEqual(
            resolve_product_dimensions(
                self.source(raw=raw), SimpleNamespace(dimension_fallback_source='OUTER'),
            ),
            (Decimal('0'), Decimal('0'), Decimal('0'), 'OUTER_MISSING', False),
        )

    def test_outer_fallback_makes_source_only_product_preview_eligible(self):
        client = Client.objects.create(
            code='STH', name='Stenhoj', dimension_fallback_source='OUTER',
        )
        external_file = ExternalDataFile.objects.create(
            client=client, file_type='PRODUCTS', status='VALIDATED',
            original_filename='products.xls',
        )
        ProductSourceRow.objects.create(
            external_file=external_file,
            source_row_number=19818,
            customer_code='STH',
            product_code_raw='BRH4443',
            product_code_normalized='BRH4443',
            name='Bradbury Hoist H4443 - 3 Parts',
            description='Bradbury Hoist H4443 - 3 Parts',
            length_mm=0,
            width_mm=0,
            height_mm=0,
            weight_kg='1750',
            cubic_m3='3.701',
            quantity=1,
            pallet=3,
            source_status='L',
            raw_data={'outer_l': 4700, 'outer_w': 750, 'outer_h': 1050},
        )

        row = build_workspace(external_file)[0][0]

        self.assertEqual(row['source_values']['dimension_source'], 'OUTER')
        self.assertTrue(row['source_values']['dimension_fallback_used'])
        self.assertEqual(
            tuple(row['source_values'][key] for key in ('length_m', 'width_m', 'height_m')),
            (Decimal('4.7'), Decimal('0.75'), Decimal('1.05')),
        )
        self.assertEqual(new_product_warnings(row, client), [])

    def test_product_warning_uses_client_confirmation_factor(self):
        client = Client.objects.create(
            code='RULE', name='Rule Client', cubic_dimension_confirmation_factor='2',
        )
        row = {
            'status': 'SOURCE_ONLY',
            'sku': 'REVIEW2',
            'source': SimpleNamespace(validation_errors=[]),
            'source_row_number': 1,
            'source_values': {
                'name': 'Review at factor two',
                'description': '',
                'length_m': Decimal('2'),
                'width_m': Decimal('1'),
                'height_m': Decimal('1'),
                'weight_kg': Decimal('1'),
                'cubic_m3': Decimal('1'),
                'pallet': 1,
            },
        }

        self.assertIn(
            'Product dimensions and cubic volume differ by a factor of 2 or more; '
            'Steadfast Contact Center or Customer Service confirmation is required.',
            new_product_warnings(row, client),
        )

    def test_outer_fallback_does_not_hide_zero_weight_or_cubic(self):
        client = Client.objects.create(
            code='STH', name='Stenhoj', dimension_fallback_source='OUTER',
        )
        external_file = ExternalDataFile.objects.create(
            client=client, file_type='PRODUCTS', status='VALIDATED',
            original_filename='products.xls',
        )
        for row_number, sku, weight, cubic in (
            (100, 'ZERO-WEIGHT', '0', '1.2'),
            (101, 'ZERO-CUBIC', '250', '0'),
        ):
            ProductSourceRow.objects.create(
                external_file=external_file,
                source_row_number=row_number,
                customer_code='STH',
                product_code_raw=sku,
                product_code_normalized=sku,
                name=sku,
                description=sku,
                length_mm=0,
                width_mm=0,
                height_mm=0,
                weight_kg=weight,
                cubic_m3=cubic,
                quantity=1,
                pallet=1,
                source_status='L',
                raw_data={'outer_l': 1000, 'outer_w': 800, 'outer_h': 600},
            )

        rows, _ = build_workspace(external_file)

        self.assertEqual(
            [new_product_warnings(row, client) for row in rows],
            [
                ['New Products require positive weight and cubic.'],
                ['New Products require positive weight and cubic.'],
            ],
        )
