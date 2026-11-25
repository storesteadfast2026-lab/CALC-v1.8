"""Admin-only global Stock vs Product Master read-only reconciliation."""

from hashlib import sha256

from apps.clients.models import Customer
from apps.imports.models import ProductMaster
from apps.imports.services.global_stock_master import _resolve_customer
from apps.imports.services.global_stock_reconciliation_core import reconcile_source_keys
from apps.imports.services.product_file_adapters import read_product_file
from apps.imports.services.product_source import (
    PRODUCT_ALIASES, PRODUCT_REQUIRED_FIELDS, PRODUCT_CSV_COLUMN_COUNT,
)
from apps.imports.services.xlsx_reader import SourceImportError, normalize_product_sku, value_to_text
from apps.products.identity import normalize_customer


def global_stock_product_reconciliation(master):
    """Compare an immutable validated Stock snapshot to the latest validated Product Master.

    Never selects operational Product values or changes Customer links. The caller
    must have checked Django-administrator authorisation before invoking this.
    """
    if master.status != 'VALIDATED':
        raise SourceImportError('Validate the Stock Master before reconciliation.')

    product_master = (
        ProductMaster.objects.filter(status='VALIDATED')
        .order_by('-uploaded_at', '-pk').first()
    )
    if product_master is None:
        raise SourceImportError('No validated Product Master exists for comparison.')

    try:
        product_master.original_file.open('rb')
        try:
            source_bytes = product_master.original_file.read()
        finally:
            product_master.original_file.close()
    except OSError as exc:
        raise SourceImportError('The validated Product Master file cannot be read.') from exc
    if sha256(source_bytes).hexdigest() != product_master.sha256.lower():
        raise SourceImportError('The Product Master source checksum does not match its stored SHA-256.')

    source = read_product_file(
        source_bytes, product_master.original_filename,
        aliases=PRODUCT_ALIASES,
        required_fields=PRODUCT_REQUIRED_FIELDS,
        expected_csv_column_count=PRODUCT_CSV_COLUMN_COUNT,
    )
    # Reuse exactly the identity test used by the core reconciliation. The
    # source adapter provides the original 1-based worksheet row number.
    incomplete_rows = []
    for record in source.records:
        missing = []
        if not normalize_customer(record.get('customer')):
            missing.append('CUSTOMER')
        if not normalize_product_sku(record.get('code')):
            missing.append('CODE (SKU)')
        if missing:
            incomplete_rows.append({
                'source_row_number': record.get('_row_number'),
                'customer': value_to_text(record.get('customer')),
                'code': value_to_text(record.get('code')),
                'name': value_to_text(record.get('name')),
                'description': value_to_text(record.get('description')),
                'missing_fields': ', '.join(missing),
            })

    raw_rows = master.source_rows.all().values(
        'customer_code', 'product_code_normalized', 'serial_no',
        'quantity', 'description',
    ).iterator(chunk_size=2000)
    entries, totals, incomplete = reconcile_source_keys(
        raw_rows, source.records,
        normalise_customer=normalize_customer,
        normalise_sku=normalize_product_sku,
    )
    codes = {row['customer'] for row in entries if row['customer']}
    customers = {
        obj.code: obj
        for obj in Customer.objects.filter(code__in=codes).select_related('linked_client')
    }
    for entry in entries:
        status, customer = _resolve_customer(entry['customer'], customers)
        entry['customer_resolution'] = status
        entry['calculator_customer'] = (
            customer.linked_client.code if customer and customer.linked_client_id else ''
        )

    return {
        'product_master': product_master,
        'entries': entries,
        'totals': totals,
        'product_master_incomplete_keys': incomplete,
        'product_master_incomplete_rows': incomplete_rows,
        'product_master_worksheet': getattr(source, 'worksheet', ''),
        'product_master_reader_rejected': len(source.rejected_rows),
        'source_rows': sum(row['source_rows'] for row in entries),
        'stock_keys': sum(bool(row['source_rows']) for row in entries),
    }
