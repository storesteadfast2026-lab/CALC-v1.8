"""Read-only Product Master notices for Products that cannot be quoted."""

import logging

from django.core.cache import cache
from django.db.models import Count, Max

from apps.clients.models import Customer
from apps.imports.models import ExternalDataFile, ProductMaster
from apps.imports.services.product_dimensions import (
    cubic_dimension_confirmation_factor,
    has_large_cubic_dimension_difference,
)
from apps.imports.services.product_master import reconciliation_rows_for_customer
from apps.imports.services.product_reconciliation_workspace import build_workspace
from apps.imports.services.xlsx_reader import SourceImportError
from apps.products.models import Product


logger = logging.getLogger(__name__)

UNKNOWN_DIMENSIONS_MESSAGE = (
    'Dimensions are unavailable for this product. '
    'For an accurate quote, please call Steadfast Contact Center or Customer Service.'
)
LARGE_DIMENSION_DIFFERENCE_MESSAGE = (
    'The product dimensions and cubic volume need confirmation. '
    'For an accurate quote, please call Steadfast Contact Center or Customer Service.'
)
INCOMPLETE_PHYSICAL_DATA_MESSAGE = (
    'The product weight or cubic volume is unavailable. '
    'For an accurate quote, please call Steadfast Contact Center or Customer Service.'
)


def operational_product_contact_message(product, client=None):
    """Return the customer-service message when an active Product is unsafe to quote."""
    client = client or product.client
    dimensions_unknown = any(
        getattr(product, field, None) is None or getattr(product, field) <= 0
        for field in ('length_m', 'width_m', 'height_m')
    )
    if dimensions_unknown:
        return UNKNOWN_DIMENSIONS_MESSAGE

    physical_data_incomplete = any(
        getattr(product, field, None) is None or getattr(product, field) <= 0
        for field in ('weight_kg', 'cubic_m3')
    )
    if physical_data_incomplete:
        return INCOMPLETE_PHYSICAL_DATA_MESSAGE

    if has_large_cubic_dimension_difference(
        product.length_m,
        product.width_m,
        product.height_m,
        product.cubic_m3,
        cubic_dimension_confirmation_factor(client),
    ):
        return LARGE_DIMENSION_DIFFERENCE_MESSAGE
    return None


def product_contact_notices(client):
    """Return source-only SKUs that require Steadfast confirmation before quoting.

    The source workbook remains read-only. These rows are notices, not operational
    Products, and therefore cannot enter a freight calculation.
    """
    customer = Customer.objects.filter(
        linked_client=client,
        is_special=False,
    ).first()
    master = ProductMaster.objects.filter(status='VALIDATED').order_by(
        '-uploaded_at', '-pk'
    ).first()
    if not customer or not master:
        return []

    product_state = Product.objects.filter(client=client).aggregate(
        count=Count('pk'),
        max_pk=Max('pk'),
    )
    confirmation_factor = cubic_dimension_confirmation_factor(client)
    cache_key = (
        f'product-contact-notices:v3:{master.pk}:{master.sha256}:'
        f'{customer.pk}:{client.pk}:{client.dimension_fallback_source}:'
        f'{confirmation_factor}:'
        f'{product_state["count"]}:{product_state["max_pk"] or 0}'
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        source_rows, _invalid = reconciliation_rows_for_customer(
            master,
            customer,
            include_invalid=True,
        )
        source = ExternalDataFile(
            client=client,
            file_type='PRODUCTS',
            status='VALIDATED',
            original_filename=master.original_filename,
        )
        rows, _summary = build_workspace(
            source,
            source_rows=source_rows,
            pending_rejected=0,
            include_decisions=False,
        )
    except SourceImportError:
        logger.warning(
            'Could not build unknown-dimension Product notices from Product Master %s.',
            master.pk,
            exc_info=True,
        )
        return []

    notices = []
    for row in rows:
        if row['status'] != 'SOURCE_ONLY':
            continue
        values = row['source_values']
        dimensions_unknown = any(
            values.get(field) is None or values[field] <= 0
            for field in ('length_m', 'width_m', 'height_m')
        )
        large_difference = has_large_cubic_dimension_difference(
            values.get('length_m'), values.get('width_m'), values.get('height_m'),
            values.get('cubic_m3'),
            confirmation_factor,
        )
        physical_data_incomplete = any(
            values.get(field) is None or values[field] <= 0
            for field in ('weight_kg', 'cubic_m3')
        )
        if not dimensions_unknown and not physical_data_incomplete and not large_difference:
            continue
        notices.append({
            'sku': row['sku'],
            'name': values.get('name') or '',
            'description': values.get('description') or '',
            'message': (
                UNKNOWN_DIMENSIONS_MESSAGE
                if dimensions_unknown
                else (
                    INCOMPLETE_PHYSICAL_DATA_MESSAGE
                    if physical_data_incomplete
                    else LARGE_DIMENSION_DIFFERENCE_MESSAGE
                )
            ),
        })

    notices.sort(key=lambda notice: notice['sku'])
    cache.set(cache_key, notices, timeout=300)
    return notices


# Compatibility for callers retained during the Product Master transition.
unknown_dimension_product_notices = product_contact_notices
