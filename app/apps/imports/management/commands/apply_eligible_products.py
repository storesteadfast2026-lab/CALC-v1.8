from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Customer
from apps.imports.models import ExternalDataFile, ProductMaster
from apps.imports.services.product_master import (
    import_new_products_from_master,
    new_product_warnings,
    reconciliation_rows_for_customer,
)
from apps.imports.services.product_reconciliation_workspace import build_workspace


class Command(BaseCommand):
    help = (
        'Preview or apply only fully eligible Source-only products from the latest '
        'validated Product Master for one linked customer.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--customer', default='STH')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        customer_code = options['customer'].strip().upper()
        customer = Customer.objects.filter(
            code=customer_code,
            linked_client__isnull=False,
            is_special=False,
        ).select_related('linked_client').first()
        if customer is None:
            raise CommandError(f'Linked customer not found: {customer_code}')

        master = ProductMaster.objects.filter(status='VALIDATED').order_by(
            '-uploaded_at', '-pk'
        ).first()
        if master is None:
            raise CommandError('No validated Product Master is available.')

        source_rows, invalid = reconciliation_rows_for_customer(
            master, customer, include_invalid=True,
        )
        source = ExternalDataFile(
            client=customer.linked_client,
            file_type='PRODUCTS',
            status='VALIDATED',
            original_filename=master.original_filename,
        )
        rows, summary = build_workspace(
            source,
            source_rows=source_rows,
            pending_rejected=0,
            include_decisions=False,
        )
        invalid_skus = {row['product_code_normalized'] for row in invalid}
        eligible = sorted({
            row['sku']
            for row in rows
            if row['status'] == 'SOURCE_ONLY'
            and row['sku'] not in invalid_skus
            and not new_product_warnings(row, customer.linked_client)
        })
        blocked = summary['source_only'] - len(eligible)
        self.stdout.write(
            f'Customer {customer.code}; master #{master.pk}; '
            f'source-only={summary["source_only"]}; eligible={len(eligible)}; blocked={blocked}.'
        )
        if not options['apply']:
            self.stdout.write('Preview only. Use --apply to create eligible operational Products.')
            return
        if not eligible:
            self.stdout.write('No eligible Source-only products remain.')
            return

        external_file, batch = import_new_products_from_master(
            master,
            customer,
            eligible,
        )
        batch_id = batch.get('batch_id') if isinstance(batch, dict) else getattr(batch, 'pk', None)
        self.stdout.write(self.style.SUCCESS(
            f'Applied {len(eligible)} products through ExternalDataFile '
            f'#{external_file.pk}; reconciliation batch {batch_id or "completed"}.'
        ))
