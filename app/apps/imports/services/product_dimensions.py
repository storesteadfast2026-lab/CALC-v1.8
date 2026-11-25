"""Resolve configured Product dimensions without altering source records."""

from decimal import Decimal, InvalidOperation

from apps.imports.services.xlsx_reader import normalize_header


ZERO = Decimal('0')
MM_PER_METRE = Decimal('1000')
DEFAULT_CUBIC_DIMENSION_CONFIRMATION_FACTOR = Decimal('10')
FALLBACK_KEYS = {
    'OUTER': ('outer_l', 'outer_w', 'outer_h'),
    'INNER': ('inner_l', 'inner_w', 'inner_h'),
    'PIECE': ('piece_l', 'piece_w', 'piece_h'),
}


def _decimal(value):
    try:
        result = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO
    return result if result.is_finite() else ZERO


def _metres(values):
    return tuple(value / MM_PER_METRE for value in values)


def cubic_dimension_difference_factor(length_m, width_m, height_m, cubic_m3):
    """Return the larger ratio between geometric and recorded cubic volume.

    Invalid or incomplete physical values return ``None`` and are handled by
    the existing required-value validation.
    """
    values = tuple(_decimal(value) for value in (
        length_m, width_m, height_m, cubic_m3,
    ))
    if not all(value > ZERO for value in values):
        return None
    geometric_m3 = values[0] * values[1] * values[2]
    return max(values[3] / geometric_m3, geometric_m3 / values[3])


def cubic_dimension_confirmation_factor(client):
    """Return the client's configured factor, with a safe legacy default."""
    factor = _decimal(getattr(client, 'cubic_dimension_confirmation_factor', None))
    return factor if factor > Decimal('1') else DEFAULT_CUBIC_DIMENSION_CONFIRMATION_FACTOR


def has_large_cubic_dimension_difference(
    length_m,
    width_m,
    height_m,
    cubic_m3,
    confirmation_factor=DEFAULT_CUBIC_DIMENSION_CONFIRMATION_FACTOR,
):
    factor = cubic_dimension_difference_factor(
        length_m, width_m, height_m, cubic_m3,
    )
    threshold = _decimal(confirmation_factor)
    if threshold <= Decimal('1'):
        threshold = DEFAULT_CUBIC_DIMENSION_CONFIRMATION_FACTOR
    return factor is not None and factor >= threshold


def resolve_product_dimensions(source, client):
    """Return effective metres, source label and whether fallback was used.

    A partial primary triplet is never replaced silently. Fallback is used only
    when all three primary dimensions are zero or missing and the configured
    alternative triplet is fully positive.
    """
    primary_mm = tuple(_decimal(getattr(source, field, None)) for field in (
        'length_mm', 'width_mm', 'height_mm',
    ))
    if all(value > ZERO for value in primary_mm):
        return (*_metres(primary_mm), 'PRIMARY', False)
    if any(value > ZERO for value in primary_mm):
        return (*_metres(primary_mm), 'PRIMARY_PARTIAL', False)

    configured = str(getattr(client, 'dimension_fallback_source', 'NONE') or 'NONE').upper()
    keys = FALLBACK_KEYS.get(configured)
    if not keys:
        return (*_metres(primary_mm), 'PRIMARY_MISSING', False)

    raw = {
        normalize_header(key): value
        for key, value in (getattr(source, 'raw_data', None) or {}).items()
    }
    fallback_mm = tuple(_decimal(raw.get(normalize_header(key))) for key in keys)
    if all(value > ZERO for value in fallback_mm):
        return (*_metres(fallback_mm), configured, True)
    return (*_metres(primary_mm), f'{configured}_MISSING', False)
