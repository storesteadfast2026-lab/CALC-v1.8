"""Operational go/no-go decision for an STH Rates/Zones validation report.

The gate deliberately does not compare monetary values with an older source.
Rates are expected to change. It checks only whether the supplied source pair
can be followed deterministically for the configured STH carriers.
"""

from django.db import transaction
from django.utils import timezone

from apps.imports.models import ExternalDataFile
from apps.imports.services.audit import create_audit_event
from apps.imports.services.ratecard_chain import SUPPORTED_ROOTS, UNKNOWN


WARNING_REFERENCE_STATUSES = {
    'SOURCE_FIELD_REQUIRED',
    'CONDITIONALLY_REACHABLE',
    'EXPRESSION_REVIEW_REQUIRED',
}

OPERATIONAL_FLAG = 'quotes_use_this_file'


def build_operational_gate(report):
    """Return a value-independent operational validation decision."""
    blockers = []
    warnings = []

    for detail in report['rates'].get('missing_reference_details', []):
        if detail['review_status'] not in WARNING_REFERENCE_STATUSES:
            continue
        warnings.append({
            'code': 'MISSING_RATE_CARD',
            'carrier': ', '.join(detail.get('reachable_carriers', [])),
            'detail': (
                f"Card {detail['card']} is referenced by the STH route but is not present "
                f"in the source ({detail['review_status']}). Contact Steadfast Customer "
                "Service if it is required; no rule or value has been assumed."
            ),
        })

    carriers = report.get('carriers', {})
    for carrier in SUPPORTED_ROOTS:
        item = carriers.get(carrier)
        if not item or not item.get('rows') or not item.get('zones_in_csv'):
            blockers.append({
                'code': 'CARRIER_ZONES_MISSING',
                'carrier': carrier,
                'detail': 'No usable destination zones were supplied for this carrier.',
            })
            continue

        conflicts = item.get('conflicts_with_postcode', [])
        if conflicts:
            details = item.get('conflict_details', [])
            destinations = '; '.join(
                f"{conflict['suburb']}, {conflict['state']} {conflict['postcode']} -> "
                f"{', '.join(conflict['zones'])} (CSV rows "
                f"{', '.join(str(row) for row in conflict['rows'])})"
                for conflict in details
            )
            warnings.append({
                'code': 'AMBIGUOUS_DESTINATION',
                'carrier': carrier,
                'count': len(conflicts),
                'detail': (
                    f'{len(conflicts)} suburb/state/postcode destination'
                    f'{"s" if len(conflicts) != 1 else ""} resolve to more than one zone.'
                    + (f' {destinations}.' if destinations else '')
                    + ' No zone will be selected automatically for these destinations. '
                    + 'Contact Steadfast Customer Service by phone to confirm the correct '
                    + 'zone, or leave them unresolved until a later review.'
                ),
            })

        unknown = item.get('case_status', {}).get(UNKNOWN, 0)
        if unknown:
            warnings.append({
                'code': 'UNRESOLVED_STH_ROUTE',
                'carrier': carrier,
                'count': unknown,
                'detail': (
                    f'{unknown} validation case{"s" if unknown != 1 else ""} could not be '
                    'resolved deterministically. Contact Steadfast Customer Service if the '
                    'missing source information is required; no rule or value has been assumed.'
                ),
            })

    return {
        'status': 'PASSED' if not blockers else 'BLOCKED',
        'activation_allowed': not blockers,
        'validation_basis': 'PROCEDURE_AND_ROUTE_RESOLVABILITY',
        'compares_rate_values': False,
        'rate_value_changes_allowed': True,
        'operational_tables_updated': False,
        'quotes_use_these_files': False,
        'blockers': blockers,
        'warnings': warnings,
    }


def get_operational_pair(client):
    """Return the explicitly activated STH Rates/Zones pair, or ``None``."""
    candidates = ExternalDataFile.objects.filter(
        client=client, file_type='RATES', status='ACTIVE',
    ).order_by('-activated_at', '-pk')
    for rates_source in candidates:
        summary = rates_source.import_summary or {}
        if not summary.get(OPERATIONAL_FLAG):
            continue
        zones_id = summary.get('operational_zones_source_id')
        zones_source = ExternalDataFile.objects.filter(
            pk=zones_id, client=client, file_type='ZONES', status='ACTIVE',
        ).first()
        if not zones_source:
            continue
        zones_summary = zones_source.import_summary or {}
        if (zones_summary.get(OPERATIONAL_FLAG)
                and zones_summary.get('operational_rates_source_id') == rates_source.pk):
            return rates_source, zones_source
    return None


@transaction.atomic
def activate_operational_pair(rates_source, zones_source, gate, *, actor=None, request=None):
    """Make one validated STH Rates/Zones pair the calculator source."""
    rates_source = ExternalDataFile.objects.select_for_update().get(pk=rates_source.pk)
    zones_source = ExternalDataFile.objects.select_for_update().get(pk=zones_source.pk)
    if rates_source.client_id != zones_source.client_id or rates_source.client.code.upper() != 'STH':
        raise ValueError('Only a matching STH Rates/Zones pair can be activated.')
    if rates_source.file_type != 'RATES' or zones_source.file_type != 'ZONES':
        raise ValueError('A Rates source and a Zones source are required.')
    if rates_source.status != 'ACTIVE' or zones_source.status != 'ACTIVE':
        raise ValueError('Both sources must be loaded and active.')
    if not gate.get('activation_allowed'):
        raise ValueError('The operational validation is blocked.')
    if not rates_source.rate_card_lines.exists() or not zones_source.zone_source_rows.exists():
        raise ValueError('Both sources must contain loaded operational rows.')

    now = timezone.now()
    for source in ExternalDataFile.objects.select_for_update().filter(
        client=rates_source.client, file_type__in=('RATES', 'ZONES'),
    ):
        summary = dict(source.import_summary or {})
        if summary.pop(OPERATIONAL_FLAG, None) is not None:
            summary.pop('operational_rates_source_id', None)
            summary.pop('operational_zones_source_id', None)
            source.import_summary = summary
            source.save(update_fields=['import_summary'])

    common = {
        OPERATIONAL_FLAG: True,
        'operational_status': 'ENABLED',
        'operational_activated_at': now.isoformat(),
        'operational_validation': gate,
        'complete_quotes_only': True,
    }
    rates_source.import_summary = {
        **(rates_source.import_summary or {}), **common,
        'operational_rates_source_id': rates_source.pk,
        'operational_zones_source_id': zones_source.pk,
    }
    zones_source.import_summary = {
        **(zones_source.import_summary or {}), **common,
        'operational_rates_source_id': rates_source.pk,
        'operational_zones_source_id': zones_source.pk,
    }
    for source in (rates_source, zones_source):
        source.activated_by = actor if getattr(actor, 'is_authenticated', False) else None
        source.activated_at = now
        source.save(update_fields=['import_summary', 'activated_by', 'activated_at'])

    create_audit_event(
        event_type='RATE_SOURCES_ACTIVATED_FOR_QUOTES',
        message='STH Rates and Zones activated as the operational quote source.',
        actor=actor, client=rates_source.client, external_file=rates_source, request=request,
        metadata={'rates_source_id': rates_source.pk, 'zones_source_id': zones_source.pk,
                  'complete_quotes_only': True, 'warning_count': len(gate.get('warnings', []))},
    )
    return rates_source, zones_source
