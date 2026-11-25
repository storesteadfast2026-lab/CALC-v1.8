from django.test import TestCase

from apps.carriers.models import Carrier, CarrierService, ClientCarrierConfig
from apps.clients.models import Client
from apps.imports.management.commands.import_sth_excel import Command
from apps.imports.models import ExternalDataFile
from apps.products.models import Product
from apps.rates.models import (
    CarrierOverlengthBreak,
    CarrierTailgateCharge,
    FreightRate,
    FreightZone,
)


class OperationalOnlyWorkbookImportTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(code='STH', name='STH')
        carrier = Carrier.objects.create(code='TEAMEX')
        service = CarrierService.objects.create(carrier=carrier, service_code='ROAD')
        ClientCarrierConfig.objects.create(client=self.client_record, carrier_service=service)
        self.product = Product.objects.create(client=self.client_record, sku='KEEP-ME')
        self.source = ExternalDataFile.objects.create(
            client=self.client_record,
            file_type='PRODUCTS',
            original_filename='products.xls',
            stored_path='uploaded_data/products.xls',
            sha256='a' * 64,
            status='VALIDATED',
        )
        FreightZone.objects.create(
            client=self.client_record,
            carrier_service=service,
            suburb='ADELAIDE',
            state='SA',
            postcode='5000',
        )
        FreightRate.objects.create(client=self.client_record, carrier_service=service)
        CarrierTailgateCharge.objects.create(
            client=self.client_record,
            carrier=carrier,
        )
        CarrierOverlengthBreak.objects.create(
            client=self.client_record,
            carrier=carrier,
            tier=99,
            length_from_m='0',
            length_to_m=None,
            charge='1',
        )

    def test_operational_replace_preserves_products_and_source_history(self):
        Command().replace_client_data(self.client_record, operational_only=True)

        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertTrue(ExternalDataFile.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(ClientCarrierConfig.objects.filter(client=self.client_record).exists())
        self.assertFalse(FreightZone.objects.filter(client=self.client_record).exists())
        self.assertFalse(FreightRate.objects.filter(client=self.client_record).exists())
        self.assertFalse(CarrierTailgateCharge.objects.filter(client=self.client_record).exists())
        self.assertFalse(CarrierOverlengthBreak.objects.filter(client=self.client_record).exists())

    def test_overlength_import_is_idempotent_and_uses_approved_bands(self):
        command = Command()
        command.import_overlength(self.client_record)
        command.import_overlength(self.client_record)

        rows = list(
            CarrierOverlengthBreak.objects.filter(client=self.client_record)
            .order_by('tier')
            .values_list('tier', 'length_from_m', 'length_to_m', 'charge')
        )
        self.assertEqual(len(rows), 6)  # Existing unrelated tier is preserved without --replace.
        approved = [row for row in rows if row[0] != 99]
        self.assertEqual([str(row[1]) for row in approved], ['0.000', '2.500', '3.700', '6.000', '7.300'])
        self.assertEqual([str(row[3]) for row in approved], ['0.0000', '60.0000', '170.0000', '240.0000', '850.0000'])
