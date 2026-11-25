import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.clients.models import Client
from apps.freight.services.dtos import FreightResult
from apps.products.models import Product


@override_settings(APP_VERSION='v1.8.0')
class AcceptanceMatrixCommandTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(code='STH', name='STH')
        for index, values in enumerate([
            ('1', '0.01', '0.20'),
            ('50', '1.00', '1.00'),
            ('100', '2.00', '2.00'),
            ('500', '10.00', '4.00'),
            ('1000', '15.00', '7.00'),
        ], start=1):
            weight, cubic, length = values
            Product.objects.create(
                client=self.client_record,
                sku=f'SKU-{index}',
                name=f'Product {index}',
                freight_type='P',
                length_m=length,
                width_m='1',
                height_m='1',
                weight_kg=weight,
                cubic_m3=cubic,
                active=True,
            )

    @patch(
        'apps.freight.management.commands.generate_acceptance_matrix.'
        'FreightCalculatorService.calculate'
    )
    def test_generates_read_only_json_and_markdown_pending_business_approval(self, calculate):
        calculate.return_value = [FreightResult(
            carrier='TEST',
            service='ROAD',
            estimate_ex_gst=Decimal('123.45'),
            status='L',
            details={
                'zone': 'Z1',
                'chargeable_weight': '100',
                'source_versions': {
                    'operational_workbook': {'sha256': 'abc'},
                    'fuel': {'sha256': 'def'},
                },
            },
        )]

        with TemporaryDirectory() as folder:
            call_command('generate_acceptance_matrix', out_dir=folder, verbosity=0)
            json_path = next(Path(folder).glob('*.json'))
            markdown_path = next(Path(folder).glob('*.md'))
            report = json.loads(json_path.read_text(encoding='utf-8'))

        self.assertEqual(report['scope'], 'READ_ONLY')
        self.assertEqual(report['approval_status'], 'PENDING_BUSINESS_ACCEPTANCE')
        self.assertEqual(report['summary'], {
            'total_cases': 7,
            'quoted_cases': 7,
            'unresolved_cases': 0,
            'pending_business_acceptance': 7,
        })
        self.assertEqual(report['cases'][0]['business_decision'], 'PENDING')
        self.assertEqual(report['cases'][0]['results'][0]['estimate_ex_gst'], '123.45')
        self.assertTrue(markdown_path.name.startswith('sth_acceptance_matrix_'))
        self.assertEqual(Product.objects.count(), 5)

