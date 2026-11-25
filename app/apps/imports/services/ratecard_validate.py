"""Route labels, row-source construction and load proof for STH.

Labels are worked out per route and per part,
so a route can have proven freight and an UNKNOWN total. A pending charge is never zero.
Loading is allowed only against the disposable rehearsal database.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from decimal import ROUND_UP, Decimal

from django.core.files.base import ContentFile
from django.db import connection

from apps.clients.models import Client
from apps.imports.models import ExternalDataFile, RateCardLine, ZoneSourceRow
from apps.imports.services.fuel import normalize_ratecard, parse_fuel_rows
from apps.imports.services.rate_source_load import load_source, parse_rate_lines, prepare_source
from apps.imports.services.ratecard_compare import (
    CONFIG_SOURCE, EQUAL, TOLERANCE, UNEXPLAINED, compare_case, with_overlength,
)
from apps.imports.services.ratecard_walk import (
    OUT_OF_SCOPE, WTR_MINIMUM_UNCONFIRMED, Sources, _cards, _zones, walk_all,
)
from apps.imports.services.xlsx_reader import calculate_sha256

PROVEN = 'PROBADA'
BASE_PROVEN = 'BASE_PROBADA'
UNKNOWN = 'UNKNOWN'
NOT_APPLICABLE = 'NOT_APPLICABLE'
LABELS = (PROVEN, BASE_PROVEN, UNKNOWN, NOT_APPLICABLE)

CONFIRMED_UNITS = frozenset({'WTRM', 'WTR'})
DISPOSABLE_HOST = 'calc_stage4_db'
SINGLE_BAND_CARD = 1412
SINGLE_BAND_LIMIT = Decimal('250')
EXACT = Decimal('0.000001')


class ValidateError(Exception):
    pass


def require_disposable():
    """The load marks a version ACTIVE, so it must never reach the real database."""
    if os.environ.get('CALC_DISPOSABLE_DB') != '1' or connection.settings_dict.get('HOST') != DISPOSABLE_HOST:
        raise ValidateError('Loading is only allowed against the disposable rehearsal database.')


def _stored(client, file_type, filename, content):
    item = ExternalDataFile(client=client, file_type=file_type, source_method='FTP_DROP',
                            original_filename=filename, status='UPLOADED',
                            sha256=calculate_sha256(content), file_size_bytes=len(content))
    item.uploaded_file.save(filename, ContentFile(content), save=True)
    return item


def load_rehearsal(client_code, rates, zones):
    """Load both sources through the real path and return the two stored versions."""
    require_disposable()
    client = Client.objects.get(code=client_code)
    versions = []
    for file_type, filename, content in (('RATES', 'rates_all.xls', rates), ('ZONES', 'zones.csv', zones)):
        item = _stored(client, file_type, filename, content)
        prepare_source(item)
        item.refresh_from_db()
        if item.status != 'VALIDATED':
            raise ValidateError(f'{file_type} did not pass review: {item.error_message}')
        load_source(item)
        versions.append(item)
    return versions


def sources_from_rows(rates_file, zones_file, fuel_content, fuel_sha256):
    """The same sources the walk builds from files, read from stored rows instead."""
    rows, _ = parse_fuel_rows(fuel_content)
    return Sources(
        rates_sha256=rates_file.sha256, zones_sha256=zones_file.sha256, fuel_sha256=fuel_sha256,
        cards=_cards(RateCardLine.objects.filter(external_file=rates_file).order_by('source_row').values()),
        zones=_zones(ZoneSourceRow.objects.filter(external_file=zones_file).order_by('source_row').values()),
        fuel={row.master_rate: row.rate for row in rows if row.rate is not None})


def walk_fields(case):
    return {'suburb': case['suburb'], 'state': case['state'], 'postcode': str(case['postcode']),
            'weight': Decimal(str(case['weight'])), 'cubic': Decimal(str(case['cubic'])),
            'pallets': int(case.get('pallets', 0)), 'cartons': int(case.get('cartons', 0)),
            'tailgate': bool(case.get('tailgate', False)),
            'hand_unload': bool(case.get('hand_unload', False))}


def _canonical(result):
    return json.dumps(result, sort_keys=True, default=str)


def load_proof(file_sources, row_sources, cases):
    """Every charge and source row must match, or the load is not faithful."""
    compared = 0
    different = []
    for case in cases:
        fields = walk_fields(case)
        for from_files, from_rows in zip(walk_all(file_sources, **fields), walk_all(row_sources, **fields)):
            compared += 1
            if _canonical(from_files) != _canonical(from_rows):
                different.append(f"{case['id']} {from_files['carrier']}/{from_files['service']}")
    return {'status': 'IDENTICO' if not different else 'DIFERENTE', 'compared': compared,
            'different': different, 'rate_lines': len(sum(row_sources.cards.values(), [])),
            'zone_rows': sum(len(rows) for rows in row_sources.zones.values())}


def rate_rows(content, filename):
    lines, _ = parse_rate_lines(content, filename)
    return {line['source_row']: line for line in lines}


def fuel_rates(content):
    rows, _ = parse_fuel_rows(content)
    return {normalize_ratecard(row.master_rate): row.rate for row in rows if row.rate is not None}


def _kilos(case, factor):
    weight, cubic = Decimal(str(case['weight'])), Decimal(str(case['cubic']))
    return max(weight, cubic * factor).quantize(Decimal('1'), rounding=ROUND_UP)


def recalculate(line, case, factor):
    """Amount from the source row, worked out apart from the walk. None for an unknown unit."""
    unit, basic, rate = line['unit'], line['basic_charge'], line['rate']
    if unit in ('WTRM', 'WTR'):
        return max(line['min_charge'], basic + rate * _kilos(case, line['cubic'] or factor))
    if unit in ('TPAL', 'PAL'):
        return max(line['min_charge'], basic + rate * int(case.get('pallets', 0)))
    if unit in ('CASE', 'TCASE'):
        return max(line['min_charge'], basic + rate * int(case.get('cartons', 0)))
    if unit == 'CHG':
        return max(line['min_charge'], basic + rate)
    return None


def check_charges(engine, case, lines, fuels, factor):
    """Return (charges checked, failures) for one route."""
    failures = []
    checked = 0
    from_cards = [item for item in engine['extras'] if item.get('source') != CONFIG_SOURCE]
    for item in (*engine['freight'], *from_cards):
        checked += 1
        line = lines.get(item['row'])
        value = None if line is None else recalculate(line, case, factor)
        if value is None or abs(value - Decimal(item['amount'])) > EXACT:
            failures.append(f"fila {item['row']}: motor {item['amount']}, recálculo {value}")
    base = sum((Decimal(item['amount']) for item in engine['freight']), Decimal('0'))
    for item in engine['fuel']:
        checked += 1
        rate = fuels.get(normalize_ratecard(item['card']))
        if rate is None or abs(rate * base - Decimal(item['amount'])) > EXACT:
            failures.append(f"combustible tarjeta {item['card']}: motor {item['amount']}")
    return checked, failures


def _service_enabled(case, cfg):
    if cfg.base_status != 'L' or not cfg.active:
        return False
    return cfg.pallet_enabled if int(case.get('pallets', 0)) else cfg.carton_enabled


def _above_single_band(engine, case, cfg):
    """RATE-004: TFMX zones with only the first band stay unquoted above 250 kg."""
    return (engine['carrier'] == 'TFMX' and SINGLE_BAND_CARD in engine['path']
            and _kilos(case, cfg.cubic_conversion) > SINGLE_BAND_LIMIT)


def _freight_proven(row, engine):
    result = row['components']['freight']['result']
    if result == EQUAL:
        return True
    if result == UNEXPLAINED or WTR_MINIMUM_UNCONFIRMED in engine['reasons']:
        return False
    return bool(engine['freight']) and all(item['unit'] in CONFIRMED_UNITS for item in engine['freight'])


def route_label(row, engine, case, cfg):
    """Return (label, reason). Only a settled walk with proven freight is PROBADA."""
    status = engine['status']
    if cfg is None:
        return NOT_APPLICABLE, 'SIN_CONFIGURACION'
    if not _service_enabled(case, cfg):
        return NOT_APPLICABLE, 'SERVICIO_APAGADO'
    quoted_by_app = row['app'] is not None
    if status == 'SIN_COTIZACION' and not quoted_by_app:
        return NOT_APPLICABLE, (engine['reasons'] or ['SIN_COTIZACION'])[0]
    if status in ('SIN_COTIZACION', 'DESCONOCIDO'):
        return UNKNOWN, status
    if not quoted_by_app:
        if _above_single_band(engine, case, cfg):
            return NOT_APPLICABLE, 'RATE_004'
        return UNKNOWN, 'RUTA_SIN_APP'
    if not engine['fuel'] or not _freight_proven(row, engine):
        return UNKNOWN, 'FLETE_SIN_COMPROBAR'
    if status == 'COMPLETO':
        return PROVEN, ''
    pending = sorted({str(item.get('reason')) for item in engine['pending']} | set(engine['reasons']))
    return BASE_PROVEN, ', '.join(pending)


def validate_route(row, engine, case, cfg, lines, fuels):
    label, reason = route_label(row, engine, case, cfg)
    checked, failures = 0, []
    if label in (PROVEN, BASE_PROVEN):
        checked, failures = check_charges(engine, case, lines, fuels, cfg.cubic_conversion)
        if failures:
            label, reason = UNKNOWN, 'RECALCULO_NO_COINCIDE'
    return {'carrier': row['carrier'], 'service': row['service'], 'label': label, 'reason': reason,
            'total': 'PROBADO' if label == PROVEN else NOT_APPLICABLE if label == NOT_APPLICABLE else UNKNOWN,
            'freight': engine['freight'] and str(sum(Decimal(i['amount']) for i in engine['freight'])) or None,
            'fuel': engine['fuel'] and str(sum(Decimal(i['amount']) for i in engine['fuel'])) or None,
            'engine_total': engine['total'], 'compare_result': row['result'],
            'charges_checked': checked, 'failures': failures}


def carrier_configs_or_fail(client, reader):
    configs = reader(client)
    if not configs:
        raise ValidateError(f'No carrier configuration for client {client}.')
    return configs


def route_rows(sources, case, client, configs, products, lines, fuels):
    """Compare one consignment and label each in-scope route."""
    results = with_overlength(in_scope(walk_all(sources, **walk_fields(case))), case, client, configs, products)
    compared = compare_case(case, {'results': results}, client, configs, products)
    engines = {(item['carrier'], item['service']): item for item in results}
    routes = [validate_route(row, engines[(row['carrier'], row['service'])], case,
                             configs.get((row['carrier'], row['service'])), lines, fuels)
              for row in compared['rows']]
    return compared, routes


def in_scope(results):
    return [item for item in results if item['status'] != OUT_OF_SCOPE]


def counts(report):
    tally = dict.fromkeys(LABELS, 0)
    by_carrier = {}
    for case in report['cases']:
        for route in case['routes']:
            tally[route['label']] += 1
            by_carrier.setdefault(f"{route['carrier']}/{route['service']}", Counter())[route['label']] += 1
    return tally, {name: dict(values) for name, values in by_carrier.items()}


def _money(value):
    if value is None:
        return '—'
    return f'{Decimal(value):,.2f}'.replace(',', ' ').replace('.', ',').replace(' ', '.')


def render_markdown(report):
    sources = report['sources']
    proof = report['load_proof']
    lines = ['# Validación de rutas STH', '',
             f"Corrida `{report['run']}`, cliente {report['client']}. Fuentes: `rates_all.xls` "
             f"`{sources['rates'][:7]}`, `zones.csv` `{sources['zones'][:7]}`, `fuel.xls` "
             f"`{sources['fuel'][:7]}`. Tolerancia AUD {TOLERANCE}.", '',
             f"**Prueba de carga:** `{proof['status']}`.", '',
             '## Conteo', '', '| Etiqueta | Rutas |', '|---|---:|']
    lines += [f'| `{name}` | {value} |' for name, value in report['counts'].items()]
    lines += ['', f"Cargos recalculados desde su fila: {report['charges_checked']}.", '',
              '| Servicio | ' + ' | '.join(f'`{name}`' for name in LABELS) + ' |',
              '|---|' + '---:|' * len(LABELS)]
    for name, values in report['by_carrier'].items():
        lines.append(f'| {name} | ' + ' | '.join(str(values.get(label, 0)) for label in LABELS) + ' |')
    for case in report['cases']:
        data = case['case']
        lines += ['', f"## {data['id']} {data['suburb']} {data['state']} {data['postcode']}: "
                      f"{data['weight']} kg, {data['cubic']} m³", '',
                  '| Servicio | Ruta | Flete | Combustible | Total | Motivo |', '|---|---|---:|---:|---:|---|']
        for route in case['routes']:
            total = _money(route['engine_total']) if route['label'] == PROVEN else route['total']
            lines.append(f"| {route['carrier']}/{route['service']} | `{route['label']}` "
                         f"| {_money(route['freight'])} | {_money(route['fuel'])} | {total} "
                         f"| {route['reason'] or '—'} |")
    return '\n'.join(lines) + '\n'
