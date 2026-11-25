"""Coverage of STH destinations with the workbook consignments (stage 5).

Nothing that quotes imports this module. Destinations come from zones.csv and the
consignments from the validated workbook cases. Every row is read-only and rolled back.
"""
from __future__ import annotations

import csv
import gzip
from collections import Counter

from django.db import transaction

from apps.imports.services import ratecard_validate as validate
from apps.imports.services.ratecard_compare import CARRIERS, TOLERANCE
from apps.imports.services.zone_source import read_zones

# Distinct workbook consignments without tailgate; tailgate cases run only at their own destination.
SHAPE_CASES = ('CASE_008', 'CASE_009', 'CASE_010', 'CASE_002', 'CASE_001', 'CASE_012', 'CASE_016',
               'CASE_013', 'CASE_017', 'CASE_018', 'CASE_014', 'CASE_003')
CHUNK = 500
COLUMNS = ('suburb', 'state', 'postcode', 'envio', 'carrier', 'service', 'label', 'reason', 'comparacion',
           'zona_motor', 'zona_app', 'flete', 'combustible', 'total')


def destinations(zones_content):
    """One row per suburb and state of the six services, with its first postcode."""
    _, rows = read_zones(zones_content)
    found = {}
    for row in rows:
        if row['carrier'].strip().upper() in CARRIERS:
            key = (row['suburb'].strip().upper(), row['state'].strip().upper())
            found.setdefault(key, row['postcode'].strip())
    return [(suburb, state, postcode) for (suburb, state), postcode in sorted(found.items())]


def shapes(cases):
    wanted = {case['id']: case for case in cases if case['id'] in SHAPE_CASES}
    missing = [name for name in SHAPE_CASES if name not in wanted]
    if missing:
        raise validate.ValidateError(f'Workbook cases not found: {", ".join(missing)}.')
    return [wanted[name] for name in SHAPE_CASES]


class Summary:
    def __init__(self):
        self.cases = 0
        self.rows = 0
        self.charges = 0
        self.failures = 0
        self.labels = Counter()
        self.by_service = Counter()
        self.by_shape = Counter()
        self.reasons = Counter()
        self.zone_mismatch = Counter()
        self.errors = Counter()
        self.zones = {}

    def add(self, shape, route, compared_row):
        service = f"{route['carrier']}/{route['service']}"
        label = route['label']
        self.rows += 1
        self.charges += route['charges_checked']
        self.failures += len(route['failures'])
        self.labels[label] += 1
        self.by_service[(service, label)] += 1
        self.by_shape[(shape, label)] += 1
        if label in (validate.UNKNOWN, validate.NOT_APPLICABLE):
            self.reasons[(service, label, route['reason'])] += 1
        zone, app_zone = compared_row['engine_zone'], compared_row.get('app_zone')
        if zone and app_zone and zone != app_zone:
            self.zone_mismatch[service] += 1
        if zone:
            self.zones.setdefault(service, {}).setdefault(zone, set()).add(label)


def _csv_row(destination, shape, route, compared_row):
    return (*destination, shape, route['carrier'], route['service'], route['label'], route['reason'],
            compared_row['result'], compared_row['engine_zone'], compared_row.get('app_zone', ''),
            route['freight'] or '', route['fuel'] or '',
            route['engine_total'] if route['label'] == validate.PROVEN else '')


def sweep(sources, cases, places, client, configs, products, lines, fuels, path, progress=None):
    """Walk every destination; an error in one is counted and does not stop the rest."""
    summary = Summary()
    work = [(place, case) for place in places for case in cases]
    with gzip.open(path, 'wt', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for start in range(0, len(work), CHUNK):
            with transaction.atomic():
                for place, shape in work[start:start + CHUNK]:
                    case = {**shape, 'suburb': place[0], 'state': place[1], 'postcode': place[2]}
                    summary.cases += 1
                    try:
                        compared, routes = validate.route_rows(sources, case, client, configs, products,
                                                               lines, fuels)
                    except Exception as exc:  # A sweep must report a failing destination, not die on it.
                        summary.errors[f'{type(exc).__name__}: {str(exc)[:80]}'] += 1
                        continue
                    for row, route in zip(compared['rows'], routes):
                        summary.add(shape['id'], route, row)
                        writer.writerow(_csv_row(place, shape['id'], route, row))
                transaction.set_rollback(True)
            if progress:
                progress(summary.cases, len(work))
    return summary


def render_markdown(meta, summary):
    sources = meta['sources']
    lines = ['# Cobertura de destinos STH', '',
             f"Corrida `{meta['run']}`, cliente {meta['client']}. Fuentes: `rates_all.xls` "
             f"`{sources['rates'][:7]}`, `zones.csv` `{sources['zones'][:7]}`, `fuel.xls` "
             f"`{sources['fuel'][:7]}`. Tolerancia AUD {TOLERANCE}.", '',
             f"Casos: {summary.cases}. Filas: {summary.rows}. Errores: {sum(summary.errors.values())}. "
             f'Cargos recalculados: {summary.charges}. Diferencias: {summary.failures}.', '',
             '## Rutas por servicio', '',
             '| Servicio | ' + ' | '.join(f'`{name}`' for name in validate.LABELS) + ' |',
             '|---|' + '---:|' * len(validate.LABELS)]
    for service in sorted({key[0] for key in summary.by_service}):
        cells = ' | '.join(str(summary.by_service[(service, label)]) for label in validate.LABELS)
        lines.append(f'| {service} | {cells} |')
    lines += ['', '## Rutas por envío', '',
              '| Envío | ' + ' | '.join(f'`{name}`' for name in validate.LABELS) + ' |',
              '|---|' + '---:|' * len(validate.LABELS)]
    for shape in SHAPE_CASES:
        cells = ' | '.join(str(summary.by_shape[(shape, label)]) for label in validate.LABELS)
        lines.append(f'| {shape} | {cells} |')
    lines += ['', '## Motivos', '', '| Servicio | Etiqueta | Motivo | Rutas |', '|---|---|---|---:|']
    for (service, label, reason), value in sorted(summary.reasons.items()):
        lines.append(f'| {service} | `{label}` | {reason or "—"} | {value} |')
    lines += ['', '## Zonas con alguna ruta comprobada', '', '| Servicio | Zonas vistas | Comprobadas |', '|---|---:|---:|']
    for service, zones in sorted(summary.zones.items()):
        proven = sum(1 for labels in zones.values() if labels & {validate.PROVEN, validate.BASE_PROVEN})
        lines.append(f'| {service} | {len(zones)} | {proven} |')
    lines += ['', '## Zona distinta entre motor y app', '', '| Servicio | Rutas |', '|---|---:|']
    lines += [f'| {service} | {value} |' for service, value in sorted(summary.zone_mismatch.items())]
    if summary.errors:
        lines += ['', '## Errores', '', '| Error | Casos |', '|---|---:|']
        lines += [f'| {name} | {value} |' for name, value in summary.errors.most_common()]
    return '\n'.join(lines) + '\n'
