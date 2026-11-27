from decimal import Decimal, InvalidOperation

from apps.products.selection import validate_product_selection

from .dtos import FreightLine, FreightRequest
from .validators import ValidationError


def _decimal(value, default='0'):
    try:
        return Decimal(str(value if value not in [None, ''] else default))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError('The calculation contains an invalid number.') from exc


def build_authorized_freight_request(client, payload):
    """Build a request using server-owned Product data and client policy."""
    if not isinstance(payload, dict):
        raise ValidationError('The calculation payload is invalid.')

    preselect_sku = str(payload.get('preselect_sku', 'YES')).upper() == 'YES'
    calculator = client.calculators.filter(active=True, archived_at__isnull=True).first()
    if not preselect_sku and not (calculator and calculator.custom_freight_enabled):
        raise ValidationError('Custom freight is not enabled for this customer.')

    cubic_margin = _decimal(payload.get('cubic_margin_percent'), '0')
    if cubic_margin != cubic_margin.to_integral_value() or not Decimal('0') <= cubic_margin <= Decimal('20'):
        raise ValidationError('Cubic Margin must be a whole number between 0 and 20.')
    if cubic_margin and not (calculator and calculator.cubic_margin_enabled):
        raise ValidationError('Cubic Margin is not enabled for this customer.')

    lines = []
    for line in payload.get('lines', []):
        if not isinstance(line, dict):
            raise ValidationError('A freight item is invalid.')
        quantity = _decimal(line.get('quantity'), '0')
        if preselect_sku:
            product_id = line.get('product_id')
            product = validate_product_selection(
                client,
                line.get('sku'),
                product_id=product_id if product_id not in (None, '') else None,
            )
            lines.append(FreightLine(
                sku=product.sku,
                quantity=quantity,
                freight_type=product.freight_type,
                length_m=product.length_m,
                width_m=product.width_m,
                height_m=product.height_m,
                weight_kg=product.weight_kg,
                cubic_m3=product.cubic_m3,
            ))
        else:
            lines.append(FreightLine(
                sku=line.get('sku') or None,
                quantity=quantity,
                freight_type=line.get('freight_type') or 'P',
                length_m=_decimal(line.get('length_m'), '0'),
                width_m=_decimal(line.get('width_m'), '0'),
                height_m=_decimal(line.get('height_m'), '0'),
                weight_kg=_decimal(line.get('weight_kg'), '0'),
                cubic_m3=_decimal(line.get('cubic_m3'), '0'),
            ))

    return FreightRequest(
        client_code=client.code,
        from_address_id=payload.get('from_address_id'),
        suburb=str(payload.get('suburb', '')),
        state=str(payload.get('state', '')),
        postcode=payload.get('postcode'),
        tailgate=str(payload.get('tailgate', 'NO')).upper() == 'YES',
        preselect_sku=preselect_sku,
        lines=lines,
        cubic_margin_percent=cubic_margin,
    )
