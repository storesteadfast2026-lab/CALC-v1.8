"""Operational STH quoting from the explicitly activated Rates/Zones pair."""
from functools import lru_cache

from apps.imports.models import ExternalDataFile, RateCardLine, ZoneSourceRow
from apps.imports.services.fuel import parse_fuel_rows, read_file_bytes
from apps.imports.services.ratecard_operational import get_operational_pair
from apps.imports.services.ratecard_walk import (
    ROOTS, Case, COMPLETE, PARTIAL, Sources, _cards, _zones, walk_case,
)


@lru_cache(maxsize=8)
def _sources(rates_id, zones_id, fuel_id, rates_hash, zones_hash, fuel_hash):
    rates_source = ExternalDataFile.objects.get(pk=rates_id, sha256=rates_hash)
    zones_source = ExternalDataFile.objects.get(pk=zones_id, sha256=zones_hash)
    fuel_source = ExternalDataFile.objects.get(pk=fuel_id, sha256=fuel_hash)
    fuel_rows, _ = parse_fuel_rows(read_file_bytes(fuel_source))
    return Sources(
        rates_sha256=rates_source.sha256,
        zones_sha256=zones_source.sha256,
        fuel_sha256=fuel_source.sha256,
        cards=_cards(RateCardLine.objects.filter(
            external_file=rates_source,
        ).order_by('source_row').values()),
        zones=_zones(ZoneSourceRow.objects.filter(
            external_file=zones_source,
        ).order_by('source_row').values()),
        fuel={row.master_rate: row.rate for row in fuel_rows if row.rate is not None},
    )


class OperationalRateEngine:
    def __init__(self, client):
        self.pair = get_operational_pair(client)
        self.fuel_source = None
        self.sources = None
        if not self.pair:
            return
        self.fuel_source = (
            ExternalDataFile.objects
            .filter(client=client, file_type='FUEL', status='ACTIVE')
            .order_by('-activated_at', '-pk')
            .first()
        )
        if self.fuel_source:
            rates_source, zones_source = self.pair
            self.sources = _sources(
                rates_source.pk, zones_source.pk, self.fuel_source.pk,
                rates_source.sha256, zones_source.sha256, self.fuel_source.sha256,
            )

    @property
    def active(self):
        return self.pair is not None

    @staticmethod
    def supports(cfg):
        """Return whether the validated operational walker covers this service."""
        carrier = (cfg.carrier_service.carrier.code or '').strip().upper()
        service = (cfg.carrier_service.service_code or '').strip().upper()
        return (carrier, service) in ROOTS

    def quote(self, cfg, request, consolidated):
        carrier = (cfg.carrier_service.carrier.code or '').strip().upper()
        service = (cfg.carrier_service.service_code or '').strip().upper()
        if self.sources is None:
            return None, {
                'carrier': carrier, 'service': service, 'status': 'SOURCE_UNAVAILABLE',
                'message': 'The active fuel source is unavailable; no operational quote was produced.',
            }
        result = walk_case(self.sources, Case(
            carrier=carrier,
            service=service,
            suburb=request.suburb,
            state=request.state,
            postcode=str(request.postcode or ''),
            weight=consolidated.weight_total_kg,
            cubic=consolidated.cubic_total_m3,
            pallets=int(consolidated.pallet_count),
            cartons=int(consolidated.carton_count),
            tailgate=consolidated.tailgate,
            hand_unload=bool(cfg.hand_unload_enabled),
        ))
        if result['status'] == COMPLETE and result.get('total') is not None:
            return result, None
        public_status = {
            'COMPLETO': 'COMPLETE',
            'PARCIAL': 'PARTIAL',
            'SIN_COTIZACION': 'NO_QUOTE',
            'DESCONOCIDO': 'UNKNOWN',
            'FUERA_DE_ALCANCE': 'OUT_OF_SCOPE',
        }.get(result['status'], result['status'])
        pending = result.get('pending') or []
        reason_values = list(result.get('reasons') or [])
        reason_values.extend(item.get('reason') for item in pending if item.get('reason'))
        reason_values = list(dict.fromkeys(reason_values))
        reasons = ', '.join(reason_values) or public_status
        if result['status'] == PARTIAL and result.get('known_subtotal') is not None:
            unresolved = []
            for item in pending:
                name = (item.get('name') or '').strip()
                reason = (item.get('reason') or '').strip()
                label = f'{name} ({reason})' if name and reason else name or reason
                if label and label not in unresolved:
                    unresolved.append(label)
            unresolved_text = ', '.join(unresolved) or reasons
            message = (
                'A provisional operational estimate was produced from confirmed charges only. '
                f'These unresolved source charges are not included: {unresolved_text}. '
                'Please contact Steadfast Customer Service if required.'
            )
            return result, {
                'carrier': carrier,
                'service': service,
                'status': public_status,
                'message': message,
            }
        if 'ZONE_AMBIGUOUS' in reasons:
            message = (
                'The destination matches more than one zone. No automatic quote was produced. '
                'Please contact Steadfast Customer Service by phone to confirm the correct zone.'
            )
        else:
            message = (
                f'The operational rate procedure is incomplete ({reasons}). '
                'No automatic quote was produced; please contact Steadfast Customer Service if required.'
            )
        return None, {'carrier': carrier, 'service': service,
                      'status': public_status, 'message': message}

