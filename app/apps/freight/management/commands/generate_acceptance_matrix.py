"""Generate read-only business acceptance candidates from current live data."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Client
from apps.freight.services.calculator import (
    FreightCalculatorService,
    apply_cubic_margin,
)
from apps.freight.services.consolidator import consolidate_lines
from apps.freight.services.dtos import FreightLine, FreightRequest
from apps.freight.services.validators import ValidationError
from apps.products.models import Product


LOCAL_TIME = ZoneInfo('Australia/Adelaide')
DEFAULT_CLIENT = 'STH'


class Command(BaseCommand):
    help = (
        'Generate a read-only acceptance matrix using active Products and current '
        'operational rates. This command does not approve prices or change data.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--client', default=DEFAULT_CLIENT)
        parser.add_argument(
            '--out-dir',
            default='',
            help='Output directory. Default: /app/reports/acceptance.',
        )

    def handle(self, *args, **options):
        client_code = str(options['client']).strip().upper()
        try:
            client = Client.objects.get(code__iexact=client_code, active=True)
        except Client.DoesNotExist as exc:
            raise CommandError(f'Active client {client_code} does not exist.') from exc

        products = list(
            Product.objects.filter(client=client, active=True, weight_kg__gt=0)
            .order_by('sku')
        )
        if not products:
            raise CommandError(f'{client.code} has no active products with positive weight.')

        selected = _representative_products(products)
        cases = _candidate_cases(selected)
        engine = FreightCalculatorService()
        report_cases = [
            _run_case(engine, client, case)
            for case in cases
        ]
        generated_at = datetime.now(LOCAL_TIME)
        report = {
            'report_type': 'BUSINESS_ACCEPTANCE_CANDIDATES',
            'scope': 'READ_ONLY',
            'software_version': settings.APP_VERSION,
            'generated_at': generated_at.isoformat(),
            'client': {'code': client.code, 'name': client.name},
            'approval_status': 'PENDING_BUSINESS_ACCEPTANCE',
            'notice': (
                'These are reproducible current-system outputs, not approved prices. '
                'A process owner must approve each case.'
            ),
            'summary': _summary(report_cases),
            'cases': report_cases,
        }

        out_dir = Path(
            options['out_dir']
            or Path(settings.BASE_DIR) / 'reports' / 'acceptance'
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = generated_at.strftime('%Y%m%d_%H%M%S')
        stem = f'{client.code.lower()}_acceptance_matrix_{stamp}'
        json_path = out_dir / f'{stem}.json'
        markdown_path = out_dir / f'{stem}.md'
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        markdown_path.write_text(_render_markdown(report), encoding='utf-8')
        self.stdout.write(str(json_path))
        self.stdout.write(str(markdown_path))
        self.stdout.write(json.dumps(report['summary']))


def _representative_products(products):
    by_weight = sorted(products, key=lambda product: (product.weight_kg, product.sku))
    return {
        'light': by_weight[0],
        'median': by_weight[len(by_weight) // 2],
        'heavy': by_weight[-1],
        'cubic': max(products, key=lambda product: (product.cubic_m3, product.sku)),
        'long': max(
            products,
            key=lambda product: (
                max(product.length_m, product.width_m, product.height_m),
                product.sku,
            ),
        ),
    }


def _candidate_cases(products):
    return [
        _case('ACCEPT-001', 'Local minimum / light item', 'ADELAIDE', 'SA', '5000', False,
              [(products['light'], Decimal('1'))]),
        _case('ACCEPT-002', 'Local heavy item with tailgate', 'BLAIR ATHOL', 'SA', '5084', True,
              [(products['heavy'], Decimal('1'))]),
        _case('ACCEPT-003', 'Interstate high-cubic item', 'MELBOURNE', 'VIC', '3000', False,
              [(products['cubic'], Decimal('1'))]),
        _case('ACCEPT-004', 'Interstate quantity and tailgate', 'SYDNEY', 'NSW', '2000', True,
              [(products['median'], Decimal('2'))]),
        _case('ACCEPT-005', 'Interstate overlength candidate', 'BRISBANE', 'QLD', '4000', False,
              [(products['long'], Decimal('1'))]),
        _case('ACCEPT-006', 'Long-distance mixed shipment', 'PERTH', 'WA', '6000', False,
              [(products['light'], Decimal('5')), (products['median'], Decimal('1'))]),
        _case('ACCEPT-007', 'Offshore high-cubic with tailgate', 'HOBART', 'TAS', '7000', True,
              [(products['cubic'], Decimal('1'))]),
    ]


def _case(case_id, purpose, suburb, state, postcode, tailgate, product_lines):
    return {
        'case_id': case_id,
        'purpose': purpose,
        'destination': {'suburb': suburb, 'state': state, 'postcode': postcode},
        'tailgate': tailgate,
        'product_lines': product_lines,
    }


def _run_case(engine, client, case):
    lines = [_freight_line(product, quantity) for product, quantity in case['product_lines']]
    request = FreightRequest(
        client_code=client.code,
        from_address_id=None,
        suburb=case['destination']['suburb'],
        state=case['destination']['state'],
        postcode=case['destination']['postcode'],
        tailgate=case['tailgate'],
        preselect_sku=True,
        lines=lines,
        cubic_margin_percent=Decimal('0'),
    )
    error = ''
    try:
        results = engine.calculate(request)
    except ValidationError as exc:
        results = []
        error = str(exc)

    diagnostics = (
        [] if results or error else _diagnose_no_quote(engine, client, request)
    )

    status = 'PENDING_BUSINESS_ACCEPTANCE' if results else 'UNRESOLVED_NO_QUOTE'
    return {
        'case_id': case['case_id'],
        'purpose': case['purpose'],
        'destination': case['destination'],
        'tailgate': case['tailgate'],
        'cubic_margin_percent': '0',
        'products': [
            _product_snapshot(product, quantity)
            for product, quantity in case['product_lines']
        ],
        'system_status': status,
        'error': error,
        'diagnostics': diagnostics,
        'results': [
            _result_snapshot(result, rank)
            for rank, result in enumerate(results, start=1)
        ],
        'business_decision': 'PENDING',
        'approved_by': '',
        'approved_at': '',
        'business_notes': '',
    }


def _diagnose_no_quote(engine, client, request):
    """Explain why each configured carrier produced no result, without writes."""
    consolidated = apply_cubic_margin(
        consolidate_lines(request.lines, request.tailgate),
        request.cubic_margin_percent,
    )
    diagnostics = []
    configs = (
        client.carrier_configs
        .select_related('carrier_service__carrier')
        .order_by('carrier_service__carrier__code', 'carrier_service__service_code')
    )
    for config in configs:
        carrier = config.carrier_service.carrier.code
        service = config.carrier_service.service_code
        label = f'{carrier} {service}'
        status = engine._carrier_status(config, request, consolidated)
        if status != 'L':
            if not config.active or config.base_status != 'L':
                reason = 'Configuration is inactive.'
            elif consolidated.tailgate and not config.tailgate_enabled:
                reason = 'Tailgate is not enabled for this carrier configuration.'
            elif consolidated.pallet_count > Decimal('0.99') and not config.pallet_enabled:
                reason = 'Pallet freight is not enabled.'
            elif consolidated.carton_count > Decimal('0.99') and not config.carton_enabled:
                reason = 'Carton freight is not enabled.'
            else:
                reason = 'Carrier eligibility rule rejected the shipment.'
            diagnostics.append({'carrier_service': label, 'stage': 'ELIGIBILITY', 'reason': reason})
            continue

        zone = engine._resolve_zone_for_config(client, config, request)
        if zone is None:
            diagnostics.append({
                'carrier_service': label,
                'stage': 'ZONE',
                'reason': 'No applicable destination zone was found.',
            })
            continue

        weight = engine._chargeable_weight_for_config(config, consolidated)
        rate = engine._resolve_rate_for_config(
            client,
            config,
            zone,
            consolidated.freight_type_for_rate,
            weight,
        )
        if rate is None:
            diagnostics.append({
                'carrier_service': label,
                'stage': 'RATE',
                'reason': (
                    f"No rate matched zone {zone['zone'] or '(blank)'}, "
                    f"chargeable weight {weight} kg and freight type "
                    f"{consolidated.freight_type_for_rate}."
                ),
            })
            continue

        diagnostics.append({
            'carrier_service': label,
            'stage': 'SURCHARGE',
            'reason': 'Base rate matched; review surcharge or overlength configuration.',
        })
    return diagnostics


def _freight_line(product, quantity):
    return FreightLine(
        sku=product.sku,
        quantity=quantity,
        freight_type=product.freight_type,
        length_m=product.length_m,
        width_m=product.width_m,
        height_m=product.height_m,
        weight_kg=product.weight_kg,
        cubic_m3=product.cubic_m3,
    )


def _product_snapshot(product, quantity):
    return {
        'sku': product.sku,
        'name': product.name,
        'quantity': str(quantity),
        'freight_type': product.freight_type,
        'length_m': str(product.length_m),
        'width_m': str(product.width_m),
        'height_m': str(product.height_m),
        'weight_kg': str(product.weight_kg),
        'cubic_m3': str(product.cubic_m3),
    }


def _result_snapshot(result, rank):
    details = result.details or {}
    return {
        'rank': rank,
        'carrier': result.carrier,
        'service': result.service,
        'estimate_ex_gst': str(result.estimate_ex_gst),
        'status': result.status,
        'explanation': {
            'zone': details.get('zone', ''),
            'chargeable_weight': details.get('chargeable_weight', ''),
            'actual_weight': details.get('actual_weight', ''),
            'cubic_total': details.get('cubic_total', ''),
            'freight_base': details.get('freight_base', ''),
            'fuel': details.get('fuel', ''),
            'tailgate_fee': details.get('tailgate_fee', ''),
            'overlength': details.get('overlength', ''),
            'source_versions': details.get('source_versions', {}),
        },
    }


def _summary(cases):
    quoted = sum(bool(case['results']) for case in cases)
    return {
        'total_cases': len(cases),
        'quoted_cases': quoted,
        'unresolved_cases': len(cases) - quoted,
        'pending_business_acceptance': len(cases),
    }


def _render_markdown(report):
    lines = [
        f"# {report['client']['code']} {report['software_version']} business acceptance candidates",
        '',
        f"Generated: {report['generated_at']}",
        '',
        '> These outputs are generated from current operational data. They are not approved prices.',
        '',
        '| Case | Purpose | Destination | Products | Tailgate | System result | Business decision |',
        '|---|---|---|---|---|---|---|',
    ]
    for case in report['cases']:
        products = '<br>'.join(
            f"{item['sku']} × {item['quantity']}"
            for item in case['products']
        )
        results = '<br>'.join(
            f"{result['carrier']} {result['service']} ${result['estimate_ex_gst']} ex GST"
            for result in case['results']
        ) or f"UNRESOLVED: {case['error'] or 'No eligible carrier result'}"
        destination = case['destination']
        lines.append(
            f"| {case['case_id']} | {case['purpose']} | "
            f"{destination['suburb']} {destination['state']} {destination['postcode']} | "
            f"{products} | {'YES' if case['tailgate'] else 'NO'} | {results} | PENDING |"
        )

    lines.extend(['', '## Approval record', ''])
    for case in report['cases']:
        lines.extend([
            f"### {case['case_id']} — {case['purpose']}",
            '',
            '- Decision: PENDING',
            '- Approved by:',
            '- Approved at:',
            '- Business notes:',
        ])
        if case['diagnostics']:
            lines.append('- System diagnostics:')
            lines.extend(
                f"  - {item['carrier_service']} [{item['stage']}]: {item['reason']}"
                for item in case['diagnostics']
            )
        lines.append('')
    return '\n'.join(lines)

