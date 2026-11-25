"""Validate a selected Product against the resolved Client on the server."""
from apps.imports.services.product_availability import operational_product_contact_message
from apps.products.models import Product


def validate_product_selection(client, sku, customer_code='', product_id=None):
    # customer_code is accepted only for existing quotation payload compatibility.
    # It does not select a second Product namespace.
    products = Product.objects.filter(client=client, sku=str(sku or '').strip(), active=True)
    if product_id is not None:
        product = products.filter(pk=product_id).first()
        if product is None:
            raise ValueError('The selected Product does not belong to the authorised Client.')
    else:
        product = products.first()
    if product is None:
        raise ValueError(
            'This product is unavailable for calculation. '
            'For an accurate quote, please call Steadfast Contact Center or Customer Service.'
        )
    contact_message = operational_product_contact_message(product, client)
    if contact_message:
        raise ValueError(contact_message)
    return product
