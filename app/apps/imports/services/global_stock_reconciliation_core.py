"""Pure, read-only Customer + SKU comparison; physical data is not authoritative."""

from collections import Counter
from decimal import Decimal


def reconcile_source_keys(stock_rows, product_rows, *, normalise_customer, normalise_sku):
    """Preserve Stock detail identity; report Product Master-only keys separately.

    stock_rows: iterable of dicts with staged quantity and serial_no.
    product_rows: iterable of parsed Product Master dicts (not operational Products).
    No repository access or mutation takes place in this function.
    """
    stock = {}
    for source in stock_rows:
        customer = normalise_customer(source['customer_code'])
        sku = normalise_sku(source['product_code_normalized'])
        key = (customer, sku)
        row = stock.get(key)
        if row is None:
            row = {
                'customer': customer, 'sku': sku, 'source_rows': 0,
                'serial_rows': 0, 'quantity': Decimal('0'),
                'description': source.get('description') or '',
            }
            stock[key] = row
        row['source_rows'] += 1
        row['serial_rows'] += bool(source.get('serial_no'))
        row['quantity'] += source['quantity']

    products = {}
    skipped_incomplete = 0
    for record in product_rows:
        customer = normalise_customer(record.get('customer'))
        sku = normalise_sku(record.get('code'))
        if not customer or not sku:
            skipped_incomplete += 1
            continue
        key = (customer, sku)
        if key not in products:
            products[key] = {'count': 0, 'name': record.get('name') or ''}
        products[key]['count'] += 1

    entries = []
    statuses = Counter()
    for customer, sku in sorted(set(stock) | set(products)):
        item = dict(stock.get((customer, sku)) or {
            'customer': customer, 'sku': sku, 'source_rows': 0,
            'serial_rows': 0, 'quantity': None, 'description': '',
        })
        candidate = products.get((customer, sku))
        if candidate is None:
            status = 'STOCK_ONLY'
        elif candidate['count'] > 1:
            status = 'AMBIGUOUS_PRODUCT_MASTER'
        elif (customer, sku) not in stock:
            status = 'PRODUCT_MASTER_ONLY'
        else:
            status = 'MATCHED'
        item['status'] = status
        item['product_name'] = candidate['name'] if candidate else ''
        item['product_master_count'] = candidate['count'] if candidate else 0
        entries.append(item)
        statuses[status] += 1
    return entries, dict(statuses), skipped_incomplete
