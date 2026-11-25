"""Round-trip tests for the exportable Product physical-data issue report."""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from apps.clients.models import Client
from apps.imports.models import (
    ExternalDataFile,
    ProductCorrectionDecision,
    ProductSourceRow,
)
from apps.imports.services.product_correction_rounds import (
    apply_correction_round,
    correction_preview,
    start_correction_round,
)
from apps.imports.services.product_issue_report import (
    HEADER_ROW,
    ProductIssueReportError,
    build_product_issue_rows,
    export_product_issue_workbook,
    preview_product_issue_workbook,
    save_product_issue_report_drafts,
)
from apps.imports.services.product_reconciliation_apply import (
    apply_product_reconciliation,
    create_recommended_product_drafts,
)
from apps.products.models import Product


class ProductIssueReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='product-issue-report-admin', password='password',
            is_staff=True, is_superuser=True,
        )
        self.client_obj = Client.objects.create(code='STH', name='STH', active=True)
        self.source = ExternalDataFile.objects.create(
            client=self.client_obj, file_type='PRODUCTS', status='VALIDATED',
            source_method='ADMIN_UPLOAD', original_filename='products.xls',
            sha256='a' * 64, uploaded_by=self.user,
        )
        Product.objects.create(
            client=self.client_obj, sku='A1', name='Operational product',
            description='Same', length_m=Decimal('1'), width_m=Decimal('1'),
            height_m=Decimal('1'), weight_kg=Decimal('10'),
            cubic_m3=Decimal('1'), freight_type='P',
        )
        ProductSourceRow.objects.create(
            external_file=self.source, source_row_number=2,
            product_code_raw='A1', product_code_normalized='A1',
            name='Source product', description='Same',
            length_mm=1000, width_mm=1000, height_mm=1000,
            weight_kg=Decimal('12'), cubic_m3=Decimal('1'),
            quantity=1, pallet=1,
        )
        create_recommended_product_drafts(self.source, actor=self.user)
        apply_product_reconciliation(self.source.pk, actor=self.user)
        ProductSourceRow.objects.create(
            external_file=self.source, source_row_number=3,
            product_code_raw='NEW-1', product_code_normalized='NEW-1',
            name='Source-only problem', description='Needs confirmation',
            length_mm=0, width_mm=0, height_mm=0,
            weight_kg=Decimal('10'), cubic_m3=Decimal('0'),
            quantity=1, pallet=1,
        )
        self.round = start_correction_round(self.source.pk, actor=self.user)
        self.url = reverse(
            'admin:imports_externaldatafile_product_reconciliation',
            args=[self.source.pk],
        )

    def _corrected_report(self):
        content, _rows = export_product_issue_workbook(self.source)
        workbook = load_workbook(BytesIO(content))
        sheet = workbook['Product issues']
        row = HEADER_ROW + 1
        self.assertEqual(sheet.cell(row=row, column=8).value, 'NEW-1')
        sheet.cell(row=row, column=23, value='YES')
        for column, value in enumerate(
            (Decimal('1'), Decimal('1'), Decimal('1'), Decimal('10'), Decimal('1')),
            start=24,
        ):
            sheet.cell(row=row, column=column, value=value)
        sheet.cell(row=row, column=29, value='Confirmed by Steadfast Customer Service.')
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output

    def test_export_contains_only_current_product_master_issue(self):
        rows = build_product_issue_rows(self.source)
        self.assertEqual([row['sku'] for row in rows], ['NEW-1'])
        self.assertEqual(rows[0]['scope'], 'SOURCE_ONLY')
        self.assertEqual(rows[0]['issue_code'], 'UNKNOWN_DIMENSIONS')
        content, exported_rows = export_product_issue_workbook(self.source)
        self.assertEqual(exported_rows, rows)
        workbook = load_workbook(BytesIO(content), read_only=True)
        sheet = workbook['Product issues']
        self.assertEqual(sheet.cell(row=HEADER_ROW + 1, column=8).value, 'NEW-1')
        self.assertEqual(
            sheet.cell(row=3, column=1).value,
            'The Product Master values below are the only source reference. Do not use another file.',
        )

    def test_corrected_report_saves_draft_then_apply_creates_product(self):
        preview = preview_product_issue_workbook(self.source, self._corrected_report())
        self.assertTrue(preview['can_save'])
        self.assertEqual([item['sku'] for item in preview['items']], ['NEW-1'])
        self.assertFalse(Product.objects.filter(client=self.client_obj, sku='NEW-1').exists())

        saved = save_product_issue_report_drafts(
            self.round.pk, items=preview['items'], actor=self.user,
        )
        self.assertEqual([decision.sku for decision in saved], ['NEW-1'])
        self.assertFalse(Product.objects.filter(client=self.client_obj, sku='NEW-1').exists())

        plan = correction_preview(self.round)
        self.assertTrue(plan['can_apply'], plan['blockers'])
        self.assertEqual(plan['items'][0]['operation'], 'CREATE')
        apply_correction_round(self.round.pk, actor=self.user)
        product = Product.objects.get(client=self.client_obj, sku='NEW-1')
        self.assertEqual(product.length_m, Decimal('1'))
        self.assertEqual(product.width_m, Decimal('1'))
        self.assertEqual(product.height_m, Decimal('1'))
        self.assertEqual(product.weight_kg, Decimal('10'))
        self.assertEqual(product.cubic_m3, Decimal('1'))

    def test_import_rejects_changed_identity_and_does_not_save_draft(self):
        upload = self._corrected_report()
        workbook = load_workbook(upload)
        workbook['Product issues'].cell(row=HEADER_ROW + 1, column=2, value=999)
        changed = BytesIO()
        workbook.save(changed)
        changed.seek(0)
        preview = preview_product_issue_workbook(self.source, changed)
        self.assertFalse(preview['can_save'])
        self.assertIn('immutable Source ID changed', preview['errors'][0])
        self.assertFalse(ProductCorrectionDecision.objects.filter(round=self.round).exists())

    def test_admin_export_preview_and_save_keep_products_unchanged(self):
        self.client.force_login(self.user)
        response = self.client.post(
            f'{self.url}?mode=correction&round={self.round.pk}',
            {'correction_action': 'export_issue_report', 'round_id': self.round.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        upload = SimpleUploadedFile(
            'product-issues.xlsx', self._corrected_report().getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response = self.client.post(
            f'{self.url}?mode=correction&round={self.round.pk}',
            {
                'correction_action': 'preview_issue_report',
                'round_id': self.round.pk,
                'issue_report': upload,
            },
        )
        self.assertEqual(response.status_code, 200)
        preview = response.context['issue_report_preview']
        self.assertTrue(preview['can_save'], preview['errors'])
        self.assertContains(response, '1 row(s) ready for draft')
        self.assertFalse(Product.objects.filter(client=self.client_obj, sku='NEW-1').exists())

        response = self.client.post(
            f'{self.url}?mode=correction&round={self.round.pk}',
            {
                'correction_action': 'save_issue_report_drafts',
                'round_id': self.round.pk,
                'preview_token': preview['token'],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProductCorrectionDecision.objects.filter(
            round=self.round, sku='NEW-1',
        ).exists())
        self.assertFalse(Product.objects.filter(client=self.client_obj, sku='NEW-1').exists())

