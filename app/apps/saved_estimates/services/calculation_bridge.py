from decimal import Decimal

from apps.freight.services.calculator import FreightCalculatorService
from apps.freight.services.request_builder import build_authorized_freight_request
from apps.freight.services.validators import ValidationError
from apps.locations.models import FromAddress


class SnapshotValidationError(ValueError):
    pass


def build_freight_request(payload, client):
    """Build the same authorised DTO used by the live calculation endpoint."""
    try:
        return build_authorized_freight_request(client, payload)
    except (ValidationError, ValueError) as exc:
        raise SnapshotValidationError(str(exc)) from exc


def serialise_results(results):
    return [
        {
            'carrier': str(result.carrier),
            'service': str(result.service),
            'estimate_ex_gst': str(result.estimate_ex_gst),
            'status': str(result.status),
            'details': _json_safe(result.details),
        }
        for result in results
    ]


def normalise_displayed_results(results):
    if not isinstance(results, list):
        raise SnapshotValidationError('The displayed freight results are invalid.')
    normalised = []
    for result in results:
        if not isinstance(result, dict):
            raise SnapshotValidationError('A displayed freight result is invalid.')
        normalised.append({
            'carrier': str(result.get('carrier', '')),
            'service': str(result.get('service', '')),
            'estimate_ex_gst': str(result.get('estimate_ex_gst', '')),
            'status': str(result.get('status', '')),
            'details': _json_safe(result.get('details') or {}),
        })
    return normalised


def serialise_request(request_dto, client):
    from_address = None
    if request_dto.from_address_id:
        address = FromAddress.objects.filter(
            pk=request_dto.from_address_id,
            client=client,
        ).first()
        if address:
            from_address = {
                'id': address.id,
                'name': address.name,
                'address_line_1': address.address_line_1,
                'suburb': address.suburb,
                'state': address.state,
                'postcode': address.postcode,
            }

    return {
        'client_code': client.code,
        'from_address_id': request_dto.from_address_id,
        'from_address': from_address,
        'suburb': request_dto.suburb,
        'state': request_dto.state,
        'postcode': request_dto.postcode,
        'tailgate': 'YES' if request_dto.tailgate else 'NO',
        'preselect_sku': 'YES' if request_dto.preselect_sku else 'NO',
        'cubic_margin_percent': str(request_dto.cubic_margin_percent),
        'lines': [
            {
                'sku': line.sku or '',
                'quantity': str(line.quantity),
                'freight_type': line.freight_type,
                'length_m': str(line.length_m),
                'width_m': str(line.width_m),
                'height_m': str(line.height_m),
                'weight_kg': str(line.weight_kg),
                'cubic_m3': str(line.cubic_m3),
            }
            for line in request_dto.lines
        ],
    }


def recalculate_snapshot(payload, client):
    request_dto = build_freight_request(payload, client)
    results = FreightCalculatorService().calculate(request_dto)
    return (
        serialise_request(request_dto, client),
        serialise_results(results),
    )


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)

