"""Global Stock Master validation and read-only reconciliation for Phase 1."""

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.authentication_gateway.services import CalculatorAccessDenied, allowed_clients_for
from apps.clients.models import Client, Customer
from apps.imports.models import GlobalStockSourceRow, StockMaster
from apps.imports.services.product_file_adapters import read_product_file
from apps.imports.services.xlsx_reader import SourceImportError, normalize_product_sku, value_to_text
from apps.products.identity import normalize_customer, valid_customer
from apps.products.models import Product


STOCK_MASTER_ALIASES = {
    'customer': ('customer', 'customer code', 'customer_code'),
    'product': ('product', 'sku', 'product code', 'product_code'),
    'description': ('description',),
    'quantity': ('quantity', 'qty'),
    'category': ('category',),
    'serial_no': ('serial_no', 'serial no', 'serial number'),
    'cubic': ('cubic', 'cubic_m3'),
    'weight': ('weight', 'weight_kg'),
}
STOCK_MASTER_REQUIRED_FIELDS = tuple(STOCK_MASTER_ALIASES)
PREVIEW_LIMIT = 100
STAGING_QUANTUM = Decimal('0.000001')


def register_stock_master_snapshot(content, filename, *, actor=None):
    """Store and validate one company-wide informational Stock snapshot.

    FTP mappings are created per operational Client, but stock.xls is one
    company-wide source. Reuse an immutable snapshot by checksum so the same
    file is not duplicated for every enabled Client.
    """
    digest = sha256(content).hexdigest()
    existing = StockMaster.objects.filter(sha256=digest).order_by('-uploaded_at').first()
    if existing:
        return existing, False

    master = StockMaster(
        original_filename=filename,
        sha256=digest,
        file_size_bytes=len(content),
        uploaded_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )
    master.original_file.save(filename, ContentFile(content), save=False)
    master.save()
    return validate_stock_master(master.pk, actor=actor), True


def _decimal(value, field, *, required=False):
    if value is None or str(value).strip() == '':
        if required:
            raise ValueError(f'{field} is required.')
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f'{field} must be numeric.') from exc
    if not number.is_finite():
        raise ValueError(f'{field} must be finite.')
    if abs(number) >= Decimal('1e14'):
        raise ValueError(f'{field} exceeds staging precision (20 digits, 6 decimal places).')
    return number.quantize(STAGING_QUANTUM)


def _read(master):
    master.original_file.open('rb')
    try:
        content = master.original_file.read()
    finally:
        master.original_file.close()
    if sha256(content).hexdigest() != master.sha256:
        raise SourceImportError('The stored Stock Master does not match its upload checksum.')
    return read_product_file(
        content,
        master.original_filename,
        aliases=STOCK_MASTER_ALIASES,
        required_fields=STOCK_MASTER_REQUIRED_FIELDS,
        expected_csv_column_count=8,
    )


def _safe_raw_data(record):
    return record.get('_raw_data') or {
        key: value_to_text(value)
        for key, value in record.items()
        if not key.startswith('_')
    }


def _parse(master, records):
    rows = []
    rejected = []
    for record in records:
        try:
            sku = normalize_product_sku(record.get('product'))
            if not sku:
                raise ValueError('product is required.')
            row = GlobalStockSourceRow(
                stock_master=master,
                source_row_number=record['_row_number'],
                customer_code=normalize_customer(record.get('customer')),
                product_code_raw=value_to_text(record.get('product')),
                product_code_normalized=sku,
                description=value_to_text(record.get('description')),
                quantity=_decimal(record.get('quantity'), 'quantity', required=True),
                category=value_to_text(record.get('category')),
                serial_no=value_to_text(record.get('serial_no')),
                cubic=_decimal(record.get('cubic'), 'cubic'),
                weight=_decimal(record.get('weight'), 'weight'),
                raw_data=_safe_raw_data(record),
            )
            row.full_clean(validate_unique=False, validate_constraints=False)
            rows.append(row)
        except (KeyError, ValueError, InvalidOperation, ValidationError) as exc:
            rejected.append({
                'row': record.get('_row_number'),
                'errors': str(exc),
                'raw_data': _safe_raw_data(record),
            })
    return rows, rejected


def _customer_map(codes):
    normalised = {normalize_customer(code) for code in codes} - {''}
    return {
        customer.code: customer
        for customer in Customer.objects.filter(code__in=normalised).select_related('linked_client')
    }


def _resolve_customer(code, customers):
    code = normalize_customer(code)
    customer = customers.get(code)
    if not code:
        return 'EMPTY_CUSTOMER', None
    if not valid_customer(code) or customer is None:
        return 'UNKNOWN_CUSTOMER', None
    return ('LINKED' if customer.linked_client_id else 'UNLINKED'), customer


def customer_resolution_summary(rows):
    """Apply the established Product Master Customer resolution statuses."""
    customers = _customer_map(row.customer_code for row in rows)
    counts = Counter({
        'LINKED': 0,
        'UNLINKED': 0,
        'UNKNOWN_CUSTOMER': 0,
        'EMPTY_CUSTOMER': 0,
    })
    per_customer = Counter()
    preview = []
    for row in rows:
        status, customer = _resolve_customer(row.customer_code, customers)
        counts[status] += 1
        per_customer[row.customer_code or '(empty)'] += 1
        if len(preview) < PREVIEW_LIMIT:
            preview.append({
                'row': row.source_row_number,
                'customer_code': row.customer_code,
                'sku': row.product_code_normalized,
                'customer_name': customer.name if customer else '',
                'calculator_customer': (
                    customer.linked_client.code
                    if customer and customer.linked_client_id
                    else ''
                ),
                'status': status,
            })
    return {
        'status_counts': dict(counts),
        'customer_counts': dict(sorted(per_customer.items())),
        'preview': preview,
        'preview_limit': PREVIEW_LIMIT,
    }


@transaction.atomic
def validate_stock_master(master_id, *, actor=None):
    """Validate and stage one immutable snapshot without operational writes."""
    master = StockMaster.objects.select_for_update().get(pk=master_id)
    if master.status == 'VALIDATED':
        raise SourceImportError('This Stock Master is already validated. Upload a new snapshot.')

    try:
        source = _read(master)
        rows, rejected = _parse(master, source.records)
        resolution = customer_resolution_summary(rows)
        identities = Counter(
            (row.customer_code, row.product_code_normalized)
            for row in rows
        )
        summary = {
            'rows_read': len(source.records),
            'rows_rejected_by_reader': len(source.rejected_rows),
            'reader_rejected': source.rejected_rows,
            'rows_valid': len(rows),
            'rows_invalid': len(rejected),
            'invalid_rows': rejected,
            'unique_customer_skus': len(identities),
            'repeated_detail_rows': sum(value - 1 for value in identities.values() if value > 1),
            # JSONField does not encode Decimal by default. Keep the exact
            # decimal text in validation history; reconciliation uses staged
            # Decimal values for arithmetic.
            'total_quantity': str(sum((row.quantity for row in rows), Decimal('0'))),
            'source_format': source.source_format,
            'worksheet': source.worksheet,
            'header_row': source.header_row,
            'warnings': list(source.warnings),
            'operational_tables_updated': False,
            'reference_only': True,
            'physical_comparison_confirmed': False,
            **resolution,
        }
        summary['warnings'].append(
            'Stock weight and cubic are source references. Their units and meaning are not confirmed, '
            'so Phase 1 does not calculate a numeric difference.'
        )
        if rejected:
            summary['warnings'].append(
                f'{len(rejected)} invalid rows were excluded from aggregation; see rejected detail.'
            )
        GlobalStockSourceRow.objects.filter(stock_master=master).delete()
        GlobalStockSourceRow.objects.bulk_create(rows, batch_size=500)
        if rows:
            master.status = 'VALIDATED'
            master.error_message = ''
        else:
            master.status = 'VALIDATION_FAILED'
            details = '; '.join(item['errors'] for item in rejected[:5])
            master.error_message = 'No valid Stock rows were found.' + (f' {details}' if details else '')
    except (SourceImportError, OSError, ValueError) as exc:
        GlobalStockSourceRow.objects.filter(stock_master=master).delete()
        master.status = 'VALIDATION_FAILED'
        master.error_message = str(exc)
        summary = {
            'operational_tables_updated': False,
            'reference_only': True,
            'physical_comparison_confirmed': False,
        }

    master.validation_summary = summary
    master.validated_at = timezone.now()
    master.validated_by = actor if getattr(actor, 'is_authenticated', False) else None
    master.save(update_fields=[
        'status',
        'error_message',
        'validation_summary',
        'validated_at',
        'validated_by',
    ])
    return master


def authorised_stock_client(user, client_id):
    """Apply existing Calculator Customer scope before reading Stock detail."""
    if user.is_superuser:
        clients = Client.objects.all()
    else:
        try:
            clients = allowed_clients_for(user)
        except CalculatorAccessDenied as exc:
            raise PermissionDenied from exc
    return get_object_or_404(clients, pk=client_id)


def _reference_values(rows, field):
    return sorted({getattr(row, field) for row in rows if getattr(row, field) is not None})


def stock_master_comparison(master, client):
    """Build a pure read workspace for one authorised Calculator Customer."""
    if master.status != 'VALIDATED':
        raise SourceImportError('Validate the Stock Master before comparison.')
    customer = get_object_or_404(Customer, linked_client=client, is_special=False)
    raw_rows = list(
        master.source_rows.filter(customer_code=customer.code).order_by('source_row_number')
    )
    groups = defaultdict(list)
    for row in raw_rows:
        groups[(customer.code, row.product_code_normalized)].append(row)

    products = defaultdict(list)
    for product in Product.objects.filter(client=client).order_by('sku', 'pk'):
        products[normalize_product_sku(product.sku)].append(product)

    comparison = []
    comparable = bool((master.validation_summary or {}).get('physical_comparison_confirmed'))
    for (customer_code, sku), detail_rows in sorted(groups.items()):
        matches = products.get(sku, [])
        product = matches[0] if len(matches) == 1 else None
        warnings = []
        if len(matches) > 1:
            status = 'AMBIGUOUS OPERATIONAL PRODUCT'
            warnings.append('Ambiguous operational SKU after normalisation; no Product selected.')
        elif product:
            status = 'MATCHED'
        else:
            status = 'STOCK WITHOUT OPERATIONAL PRODUCT'

        if any(row.quantity < 0 for row in detail_rows):
            warnings.append(
                'Signed negative quantity retained as reference; no availability semantics applied.'
            )

        item = {
            'customer_code': customer_code,
            'sku': sku,
            'description': detail_rows[0].description,
            'raw_row_count': len(detail_rows),
            'quantity': sum((row.quantity for row in detail_rows), Decimal('0')),
            'product': product,
            'status': status,
            'warnings': warnings,
        }
        for source_field, product_field, label in (
            ('weight', 'weight_kg', 'weight'),
            ('cubic', 'cubic_m3', 'cubic'),
        ):
            values = _reference_values(detail_rows, source_field)
            stock_value = values[0] if len(values) == 1 else None
            product_value = getattr(product, product_field) if product else None
            item[f'stock_{label}'] = stock_value
            item[f'stock_{label}_values'] = ', '.join(str(value) for value in values)
            item[f'product_{label}'] = product_value
            item[f'{label}_difference'] = (
                stock_value - product_value
                if comparable and stock_value is not None and product_value is not None
                else None
            )
            if len(values) > 1:
                warnings.append(
                    f'Conflicting Stock {label} references; no single difference calculated.'
                )
            if any(getattr(row, source_field) is None for row in detail_rows):
                warnings.append(
                    f'Missing Stock {label} reference on one or more detail rows.'
                )
            if any(value < 0 for value in values):
                warnings.append(f'Negative Stock {label} reference retained; review the source.')
        if not comparable and product:
            warnings.append(
                'Product and Stock physical values are shown as references; difference unavailable '
                'until source units and meaning are confirmed.'
            )
        comparison.append(item)

    stock_skus = {sku for (_customer, sku) in groups}
    operational_only = [
        product
        for sku, items in products.items()
        if sku not in stock_skus
        for product in items
    ]
    return {
        'customer': customer,
        'client': client,
        'raw_rows': raw_rows,
        'rows': comparison,
        'operational_only': operational_only,
        'summary': {
            'raw_rows': len(raw_rows),
            'unique_stock_skus': len(groups),
            'total_quantity': sum((row.quantity for row in raw_rows), Decimal('0')),
            'operational_products': sum(len(items) for items in products.values()),
            'matched': sum(item['status'] == 'MATCHED' for item in comparison),
            'stock_without_product': sum(
                item['status'] == 'STOCK WITHOUT OPERATIONAL PRODUCT' for item in comparison
            ),
            'ambiguous_products': sum(
                item['status'] == 'AMBIGUOUS OPERATIONAL PRODUCT' for item in comparison
            ),
            'product_without_stock': len(operational_only),
        },
        'warnings': list((master.validation_summary or {}).get('warnings', [])) + [
            'Absence from this source is not quantity zero. No Product, availability, or freight '
            'values changed.'
        ],
    }
