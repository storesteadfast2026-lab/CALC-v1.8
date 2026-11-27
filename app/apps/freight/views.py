import json
import logging

from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Q
from django.http import Http404, HttpRequest, JsonResponse
from django.http.request import split_domain_port
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.authentication_gateway.decorators import calculator_access_required
from apps.authentication_gateway.services import (
    CalculatorAccessDenied,
    allowed_clients_for,
    resolve_authorized_client,
)
from apps.locations.models import Suburb, FromAddress
from apps.products.models import Product
from apps.imports.services.product_availability import (
    operational_product_contact_message,
    product_contact_notices,
)
from .services.calculator import FreightCalculatorService
from .services.request_builder import build_authorized_freight_request
from .services.validators import ValidationError
from .services.consolidator import PALLET_WEIGHT_KG, PALLET_CUBIC_M3
from apps.authentication_gateway.models import CalculatorUserProfile


logger = logging.getLogger(__name__)


@ensure_csrf_cookie
@calculator_access_required
def calculator_page(request: HttpRequest):
    try:
        client = resolve_authorized_client(
            request.user,
            request.GET.get('client'),
        )
    except CalculatorAccessDenied as exc:
        raise PermissionDenied(str(exc)) from exc

    available_clients = allowed_clients_for(request.user)
    from_addresses = FromAddress.objects.filter(client=client, active=True)
    profile = request.calculator_profile
    calculator = client.calculators.filter(active=True, archived_at__isnull=True).first()
    cubic_margin_options = (
        calculator.allowed_cubic_margins()
        if calculator and calculator.cubic_margin_enabled
        else [0]
    )

    return render(request, 'freight/calculator.html', {
        'client': client,
        'allowed_clients': available_clients,
        'can_select_client': available_clients.count() > 1,
        'user_role_label': profile.get_role_display(),
        'from_addresses': from_addresses,
        'pallet_weight_kg': PALLET_WEIGHT_KG,
        'pallet_cubic_m3': PALLET_CUBIC_M3,
        'saved_estimates_enabled': settings.SAVED_ESTIMATES_ENABLED,
        'can_export_estimates': (
            profile.role == CalculatorUserProfile.Role.INTERNAL_USER
        ),
        'calculator_config': calculator,
        'custom_freight_enabled': bool(calculator and calculator.custom_freight_enabled),
        'cubic_margin_options': cubic_margin_options,
        'app_version': settings.APP_VERSION,
    })


@require_GET
@never_cache
def api_tools_page(request: HttpRequest):
    if not settings.DEBUG or split_domain_port(request.get_host())[0] not in {
        'localhost', '127.0.0.1', '[::1]',
    }:
        raise Http404
    return _render_api_tools(request)


@calculator_access_required
def _render_api_tools(request: HttpRequest):
    codes = list(allowed_clients_for(request.user).values_list('code', flat=True))
    example = {
        'client_code': codes[0] if codes else '',
        'suburb': '',
        'state': '',
        'postcode': '',
        'lines': [{'sku': '', 'quantity': 1}],
    }
    if 'STH' in codes:
        # Local catalogue SKU and destination from acceptance case ACCEPT-001.
        example.update(
            client_code='STH', suburb='ADELAIDE', state='SA', postcode='5000',
            lines=[{'sku': 'CM245-AS-SPKIT', 'quantity': 1}],
        )

    return render(request, 'freight/api_tools.html', {
        'quote_example': json.dumps(example, indent=2),
    })


@require_GET
@calculator_access_required
def suburb_autocomplete(request: HttpRequest):
    q = request.GET.get('q', '').strip()
    qs = Suburb.objects.all()
    if q:
        qs = qs.filter(suburb_name__icontains=q)
    data = [
        {
            'id': s.id,
            'label': f'{s.suburb_name}, {s.state} {s.postcode}',
            'suburb': s.suburb_name,
            'state': s.state,
            'postcode': s.postcode,
        }
        for s in qs[:20]
    ]
    return JsonResponse({'results': data})


@require_GET
@calculator_access_required
def product_autocomplete(request: HttpRequest):
    try:
        client = resolve_authorized_client(request.user, request.GET.get('client'))
    except CalculatorAccessDenied as exc:
        return JsonResponse({'error': str(exc)}, status=403)

    q = request.GET.get('q', '').strip()
    qs = Product.objects.filter(client=client, active=True)
    if q:
        qs = qs.filter(
            Q(sku__icontains=q)
            | Q(name__icontains=q)
            | Q(description__icontains=q)
        )
    data = []
    for product in qs.distinct()[:20]:
        contact_message = operational_product_contact_message(product, client)
        if contact_message:
            data.append({
                'id': None,
                'sku': product.sku,
                'label': f'{product.sku} — Call Steadfast Contact Center / Customer Service',
                'available': False,
                'message': contact_message,
            })
            continue
        data.append({
            'id': product.pk,
            'sku': product.sku,
            'label': f'{product.sku}',
            'length_m': str(product.length_m),
            'width_m': str(product.width_m),
            'height_m': str(product.height_m),
            'weight_kg': str(product.weight_kg),
            'cubic_m3': str(product.cubic_m3),
            'freight_type': product.freight_type,
        })
    if q and len(data) < 20:
        term = q.casefold()
        known_skus = {item['sku'] for item in data}
        for notice in product_contact_notices(client):
            searchable = ' '.join((
                notice['sku'], notice['name'], notice['description'],
            )).casefold()
            if term not in searchable or notice['sku'] in known_skus:
                continue
            data.append({
                'id': None,
                'sku': notice['sku'],
                'label': f'{notice["sku"]} — Call Steadfast Contact Center / Customer Service',
                'available': False,
                'message': notice['message'],
            })
            if len(data) == 20:
                break
    return JsonResponse({'results': data})


@require_POST
@calculator_access_required
def calculate_freight(request: HttpRequest):
    try:
        payload = json.loads(request.body.decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValidationError('The calculation payload must be a JSON object.')
        client_code = payload.get('client_code')
        if client_code is not None and not isinstance(client_code, str):
            raise ValidationError('Client code must be a string.')
        if not isinstance(payload.get('lines', []), list):
            raise ValidationError('Freight lines must be an array.')
        client = resolve_authorized_client(
            request.user,
            client_code,
        )
        req = build_authorized_freight_request(client, payload)
        calculator = FreightCalculatorService()
        results = calculator.calculate(req)
        include_details = (
            request.calculator_profile.role
            == CalculatorUserProfile.Role.INTERNAL_USER
        )
        return JsonResponse({
            'results': [
                {
                    'carrier': result.carrier,
                    'service': result.service,
                    'estimate_ex_gst': result.estimate_ex_gst,
                    'status': result.status,
                    'quote_status': (
                        (result.details or {}).get('operational_status')
                        or 'COMPLETE'
                    ),
                    'details': result.details if include_details else {},
                }
                for result in results
            ],
            'warnings': getattr(calculator, 'last_warnings', []),
        })
    except CalculatorAccessDenied as exc:
        return JsonResponse({'error': str(exc)}, status=403)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON request body.'}, status=400)
    except ValidationError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception:
        logger.exception('Unexpected freight calculation error')
        return JsonResponse({'error': 'Unexpected calculation error'}, status=500)


@require_GET
@calculator_access_required
def freight_accounts(request: HttpRequest):
    accounts = allowed_clients_for(request.user).values('code', 'name')
    return JsonResponse({'results': list(accounts)})
