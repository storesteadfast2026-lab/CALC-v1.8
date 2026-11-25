"""Read-only comparison of the rate-card walk with the app calculator (stage 3).

Nothing that quotes imports this module. It measures and explains differences and
never corrects one. A cause is assigned by calculation only, and a pending charge is
never zero: its total stays NO_COMPARABLE.
"""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from apps.carriers.models import ClientCarrierConfig
from apps.clients.models import Client
from apps.freight.services.calculator import FreightCalculatorService, OverlengthNotConfigured, overlength_fee
from apps.freight.services.consolidator import consolidate_lines
from apps.freight.services.dtos import FreightLine, FreightRequest
from apps.freight.services.validators import ValidationError
from apps.imports.services.xlsx_reader import SourceImportError
from apps.imports.services.zone_source import read_zones
from apps.products.models import Product
from apps.rates.models import FreightRate

TOLERANCE = Decimal('0.01')
# The app rounds up three times: freight, fuel and the final estimate.
ROUNDING_LIMIT = TOLERANCE * 3
SERVICES = (('TEAMEX', 'ROAD'), ('KTI', 'GENERAL'), ('TFMX', 'ROAD'), ('TEAMTAS', 'GENERAL'),
            ('COCHRN', 'ROAD'), ('STEA', 'ROAD'))
CARRIERS = frozenset(carrier for carrier, _ in SERVICES)

EQUAL = 'IGUAL'
EXPLAINED = 'EXPLICADA'
UNEXPLAINED = 'SIN_EXPLICAR'
ONLY_APP = 'SOLO_APP'
ONLY_ENGINE = 'SOLO_MOTOR'
NOT_COMPARABLE = 'NO_COMPARABLE'
RESULTS = (EQUAL, EXPLAINED, UNEXPLAINED, ONLY_APP, ONLY_ENGINE, NOT_COMPARABLE)

CURRENT_FUEL = 'COMBUSTIBLE_VIGENTE'
COCHRN_SURCHARGE = 'RECARGO_COCHRN'
UPRATE = 'UPRATE'
CURRENT_RATE = 'TARIFA_VIGENTE'
ROUNDING = 'REDONDEO'

ENGINE_NO_QUOTE = ('SIN_COTIZACION', 'DESCONOCIDO')
CONFIG_SOURCE = 'configuracion'
OLE2_MAGIC = bytes.fromhex('d0cf11e0a1b11ae1')
TRANSLOGIC_COLUMNS = ('case_id', 'carrier', 'service', 'quoted_at', 'freight', 'fuel', 'extras',
                      'total', 'quoted_by', 'note')
APP_EXTRAS = ('tailgate_fee', 'hand_unload', 'overlength', 'remote', 'offshore',
              'teamtas_general_fee', 'handling')


class CompareError(Exception):
    pass


def check_zones(content):
    """Refuse a delivery that cannot cover STH; the 6 Nov file was an Excel file cut at 65,534 rows."""
    if content.startswith(OLE2_MAGIC):
        raise CompareError('zones.csv is an Excel file, not a CSV export. Nothing was compared.')
    try:
        _, rows = read_zones(content)
    except SourceImportError as exc:
        raise CompareError(str(exc)) from exc
    missing = sorted(CARRIERS - {row['carrier'].strip().upper() for row in rows})
    if missing:
        raise CompareError(f'zones.csv has no rows for {", ".join(missing)}. Nothing was compared.')


def _case_from_row(row):
    lines = [{'sku': row[f'sku_{number}'].strip(), 'quantity': row[f'qty_{number}'].strip()}
             for number in (1, 2) if row.get(f'sku_{number}', '').strip()]
    return {'id': row['case_id'].strip(), 'suburb': row['suburb'].strip(), 'state': row['state'].strip(),
            'postcode': row['postcode'].strip(), 'tailgate': row['tailgate'].strip().upper() == 'YES',
            'lines': lines, 'planilla_weight': row['total_weight_kg'].strip(),
            'planilla_cubic': row['total_cubic_m3'].strip()}


def load_cases(path):
    """Read workbook cases: the validated CSV, or JSON with the same shape."""
    source = Path(path)
    if source.suffix.lower() == '.csv':
        text = source.read_bytes().decode('cp1252')
        return [_case_from_row(row) for row in csv.DictReader(io.StringIO(text, newline=''))]
    return with_ids(json.loads(source.read_text(encoding='utf-8')))


def product_map(cases, client_code):
    """A missing SKU stops the run; nothing is ever put in its place."""
    wanted = {line['sku'] for case in cases for line in case['lines']}
    found = {item.sku: item for item in Product.objects.filter(client__code=client_code, sku__in=wanted,
                                                                active=True)}
    missing = sorted(wanted - set(found))
    if missing:
        raise CompareError(f'SKU not in the product table: {", ".join(missing)}.')
    return found


def freight_lines(case, products):
    """One line per SKU with the product values, as the workbook battery builds them."""
    lines = []
    for item in case['lines']:
        product = products[item['sku']]
        lines.append(FreightLine(sku=product.sku, quantity=Decimal(str(item['quantity'])),
                                 freight_type=product.freight_type or 'P', length_m=product.length_m,
                                 width_m=product.width_m, height_m=product.height_m,
                                 weight_kg=product.weight_kg, cubic_m3=product.cubic_m3))
    return lines


def with_totals(case, products):
    """Totals come from consolidate_lines, the workbook rule, so both sides get the same consignment."""
    done = consolidate_lines(freight_lines(case, products), bool(case.get('tailgate')))
    return {**case, 'weight': str(done.weight_total_kg), 'cubic': str(done.cubic_total_m3),
            'pallets': int(done.pallet_count), 'cartons': int(done.carton_count), 'tailgate': done.tailgate}


def freight_request(case, client_code, products):
    return FreightRequest(
        client_code=client_code, from_address_id=None, suburb=case['suburb'], state=case['state'],
        postcode=str(case['postcode']), tailgate=bool(case.get('tailgate')), preselect_sku=False,
        lines=freight_lines(case, products))


def app_quotes(case, client_code, products):
    """Return ({(carrier, service): result}, error). An app refusal is data, not a crash."""
    try:
        results = FreightCalculatorService().calculate(freight_request(case, client_code, products))
    except ValidationError as exc:
        return {}, str(exc)
    return {(str(item.carrier), str(item.service)): item for item in results}, ''


def carrier_configs(client_code):
    return {(cfg.carrier_service.carrier.code, cfg.carrier_service.service_code): cfg
            for cfg in ClientCarrierConfig.objects.select_related('carrier_service__carrier')
            .filter(client__code=client_code)}


def app_rate(client_code, details):
    return FreightRate.objects.filter(client__code=client_code, lookup_key=details['rate_lookup_key'],
                                      source_row=details['rate_source_row']).order_by('id').first()


def _sum(items):
    return sum((Decimal(item['amount']) for item in items), Decimal('0'))


def _differs(first, second):
    return abs(first - second) > TOLERANCE


def _text(value):
    return None if value is None else str(value)


def _app_amounts(result, rate):
    details = result.details
    overweight = rate.overweight_charge if rate is not None else Decimal('0')
    return {'freight': Decimal(details['freight_base']), 'fuel': Decimal(details['fuel']),
            'extras': sum((Decimal(details[name]) for name in APP_EXTRAS), overweight),
            'total': result.estimate_ex_gst}


def _engine_amounts(engine):
    return {'freight': _sum(engine['freight']), 'fuel': _sum(engine['fuel']),
            'extras': _sum(engine['extras']),
            'total': None if engine['total'] is None else Decimal(engine['total'])}


def _freight_cause(engine, result, rate):
    """Current rates explain the gap only if the app formula on the card values gives the engine amount."""
    if rate is None or len(engine['freight']) != 1:
        return None
    card = engine['freight'][0]
    values = {name: Decimal(card[name]) for name in ('rate', 'basic', 'minimum')}
    if (values['rate'], values['basic'], values['minimum']) == (
            rate.per_kg, rate.basic_charge, rate.minimum_charge):
        return None
    details = result.details
    units = Decimal(details['pallets']) + Decimal(details['cartons'])
    extra = (units - 1) * rate.per_subsequent_basic if units > Decimal('1.99') else Decimal('0')
    candidate = max(values['minimum'], values['basic'] + extra
                    + values['rate'] * Decimal(details['chargeable_weight']))
    return CURRENT_RATE if not _differs(candidate, Decimal(card['amount'])) else None


def _fuel_causes(engine, cfg):
    """Compare percentages, because an amount also moves with the base."""
    if not engine['fuel'] or cfg is None:
        return None
    rate = sum((Decimal(item['rate']) for item in engine['fuel']), Decimal('0'))
    if cfg.fuel_levy + cfg.extra_surcharge == rate:
        return []
    causes = []
    if cfg.fuel_levy != rate:
        causes.append(CURRENT_FUEL)
    if cfg.extra_surcharge:
        causes.append(COCHRN_SURCHARGE)
    return causes


def _component(engine_value, app_value, causes):
    difference = engine_value - app_value
    if not _differs(engine_value, app_value):
        return {'result': EQUAL, 'difference': str(difference), 'causes': []}
    return {'result': EXPLAINED if causes else UNEXPLAINED, 'difference': str(difference),
            'causes': causes}


def _total_causes(engine_amounts, app_amounts, components, cfg):
    """A total gap inherits component causes; only clean components can point at uprate or rounding."""
    settled = [components[name] for name in ('freight', 'fuel', 'extras')]
    if any(part['result'] == UNEXPLAINED for part in settled):
        return []
    causes = sorted({cause for part in settled for cause in part['causes']})
    if causes:
        return causes
    known = app_amounts['freight'] + app_amounts['fuel'] + app_amounts['extras']
    if cfg is not None and cfg.uprate and not _differs(app_amounts['total'] - known, known * cfg.uprate):
        return [UPRATE]
    return [ROUNDING] if abs(engine_amounts['total'] - app_amounts['total']) <= ROUNDING_LIMIT else []


def classify(engine, result, cfg, rate):
    """One engine result against one app result, by component."""
    row = {'carrier': engine['carrier'], 'service': engine['service'],
           'engine_status': engine['status'], 'engine_zone': engine['zone'],
           'engine_reasons': engine['reasons'], 'engine_pending': engine['pending'],
           'engine_path': engine['path'], 'engine': None, 'app': None, 'components': {},
           'uprate': None if cfg is None else str(cfg.uprate)}
    engine_quoted = engine['status'] not in ENGINE_NO_QUOTE
    if engine_quoted:
        row['engine'] = {key: _text(value) for key, value in _engine_amounts(engine).items()}
        row['engine']['known_subtotal'] = engine['known_subtotal']
        row['engine_sources'] = [
            {key: item.get(key) for key in ('card', 'row', 'break', 'item', 'name', 'amount')}
            for item in (*engine['freight'], *engine['fuel'], *engine['extras'])]
    if result is not None:
        row['app'] = {key: str(value) for key, value in _app_amounts(result, rate).items()}
        row['app_zone'] = result.details['zone']
    if result is None and not engine_quoted:
        row['result'] = EQUAL
        row['note'] = 'Ninguno cotiza.'
        return row
    if result is None:
        row['result'] = ONLY_ENGINE
        return row
    if not engine_quoted:
        row['result'] = ONLY_APP
        return row

    engine_amounts, app_amounts = _engine_amounts(engine), _app_amounts(result, rate)
    freight_cause = None
    if _differs(engine_amounts['freight'], app_amounts['freight']):
        freight_cause = _freight_cause(engine, result, rate)
    freight = _component(engine_amounts['freight'], app_amounts['freight'],
                         [freight_cause] if freight_cause else [])
    fuel_causes = _fuel_causes(engine, cfg)
    if fuel_causes == []:
        fuel_causes = freight['causes']
    fuel = _component(engine_amounts['fuel'], app_amounts['fuel'], fuel_causes or [])
    extras = _component(engine_amounts['extras'], app_amounts['extras'], [])
    components = {'freight': freight, 'fuel': fuel, 'extras': extras}
    if engine_amounts['total'] is None:
        components['total'] = {'result': NOT_COMPARABLE, 'difference': None, 'causes': []}
    else:
        components['total'] = _component(engine_amounts['total'], app_amounts['total'],
                                         _total_causes(engine_amounts, app_amounts, components, cfg))
    row['components'] = components
    seen = {part['result'] for part in components.values()}
    row['result'] = next(name for name in (UNEXPLAINED, EXPLAINED, NOT_COMPARABLE, EQUAL) if name in seen)
    return row


def _plus(value, amount):
    return None if value is None else str(Decimal(value) + amount)


def _with_charge(engine, amount):
    """Overlength goes into the total and pays no fuel (BrokerTotals!X, Z)."""
    extra = {'card': None, 'row': None, 'break': None, 'item': 'OVERLENGTH', 'name': 'Sobrelargo',
             'amount': str(amount), 'source': CONFIG_SOURCE}
    return {**engine, 'extras': [*engine['extras'], extra],
            'known_subtotal': _plus(engine['known_subtotal'], amount), 'total': _plus(engine['total'], amount)}


def with_overlength(results, case, client_code, configs, products):
    """Add the configured overlength to the walk, which has no such charge."""
    length = consolidate_lines(freight_lines(case, products), bool(case.get('tailgate'))).max_length_m
    client = Client.objects.get(code=client_code)
    priced = []
    for engine in results:
        cfg = configs.get((engine['carrier'], engine['service']))
        if engine['status'] in ENGINE_NO_QUOTE or cfg is None or not cfg.overlength_enabled:
            priced.append(engine)
            continue
        try:
            amount = overlength_fee(client, cfg.carrier_service.carrier, length)
        except OverlengthNotConfigured as exc:
            pending = {'reason': 'OVERLENGTH_SIN_CONFIGURACION', 'detail': str(exc)}
            priced.append({**engine, 'status': 'PARCIAL', 'total': None, 'pending': [*engine['pending'], pending]})
            continue
        priced.append(_with_charge(engine, amount))
    return priced


def compare_case(case, walked, client_code, configs, products):
    """Every in-scope service of one case. Services left out of the walk stay out here too."""
    quotes, error = app_quotes(case, client_code, products)
    rows = []
    for engine in walked['results']:
        key = (engine['carrier'], engine['service'])
        if key not in SERVICES:
            continue
        result = quotes.get(key)
        rate = app_rate(client_code, result.details) if result is not None else None
        rows.append(classify(engine, result, configs.get(key), rate))
    return {'id': case['id'], 'case': case, 'app_error': error, 'rows': rows}


def _decimal_or_none(value, label):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise CompareError(f'TransLogic file: {label} is not a number: {value}') from exc


def read_translogic(content):
    """An empty value means no data, never zero."""
    reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline=''))
    if tuple(reader.fieldnames or ()) != TRANSLOGIC_COLUMNS:
        raise CompareError(f'TransLogic file columns must be exactly {", ".join(TRANSLOGIC_COLUMNS)}.')
    rows = {}
    for row in reader:
        key = (row['case_id'].strip(), row['carrier'].strip().upper(), row['service'].strip().upper())
        rows[key] = {**row, **{name: _decimal_or_none(row[name], name)
                               for name in ('freight', 'fuel', 'extras', 'total')}}
    return rows


def attach_translogic(report, rows, source_date):
    """Optional evidence: a value from another day is not comparable, because rates change daily."""
    for case in report['cases']:
        for row in case['rows']:
            item = rows.get((case['id'], row['carrier'], row['service']))
            if item is None:
                continue
            same_day = item['quoted_at'].strip()[:10] == source_date
            row['translogic'] = {
                'status': 'MISMA_FECHA' if same_day else 'FECHA_DISTINTA',
                'quoted_at': item['quoted_at'], 'quoted_by': item['quoted_by'], 'note': item['note'],
                **{name: _text(item[name]) for name in ('freight', 'fuel', 'extras', 'total')}}


def counts(report):
    tally = dict.fromkeys(RESULTS, 0)
    for case in report['cases']:
        for row in case['rows']:
            tally[row['result']] += 1
    return tally


def _cell(value):
    if value is None:
        return '—'
    return f'{Decimal(value):,.2f}'.replace(',', ' ').replace('.', ',').replace(' ', '.')


def _describe(case):
    data = case['case']
    units = [f'{data[name]} {label}' for name, label in (('pallets', 'pallet(s)'), ('cartons', 'caja(s)'))
             if data.get(name)]
    extra = ', tailgate' if data.get('tailgate') else ''
    return (f"{data['id']} {data['suburb']} {data['state']} {data['postcode']}: "
            f"{data['weight']} kg, {data['cubic']} m³, {', '.join(units)}{extra}")


def _pair(row, name):
    return f"{_cell((row['engine'] or {}).get(name))} / {_cell((row['app'] or {}).get(name))}"


def _causes(row):
    found = sorted({cause for part in row['components'].values() for cause in part['causes']})
    return ', '.join(found) or '—'


def render_markdown(report):
    hashes = report['sources']
    lines = ['# Comparación motor y app', '',
             f"Corrida `{report['run']}`, cliente {report['client']}. Fuentes: `rates_all.xls` "
             f"`{hashes['rates'][:7]}`, `zones.csv` `{hashes['zones'][:7]}`, `fuel.xls` "
             f"`{hashes['fuel'][:7]}`. Tolerancia AUD {TOLERANCE} por componente.", '',
             '## Conteo', '', '| Resultado | Filas |', '|---|---:|']
    lines += [f'| `{name}` | {value} |' for name, value in counts(report).items()]
    for case in report['cases']:
        lines += ['', f'## {_describe(case)}', '']
        if case['app_error']:
            lines += [f"La app rechazó el caso: {case['app_error']}", '']
        lines += ['Importes en formato motor / app.', '',
                  '| Transportista | Resultado | Motor | Zona motor / app | Flete | Combustible '
                  '| Extras | Total | Causas |', '|---|---|---|---|---:|---:|---:|---:|---|']
        for row in case['rows']:
            lines.append(
                f"| {row['carrier']}/{row['service']} | `{row['result']}` | `{row['engine_status']}` "
                f"| {row['engine_zone'] or '—'} / {row.get('app_zone') or '—'} "
                f"| {_pair(row, 'freight')} | {_pair(row, 'fuel')} | {_pair(row, 'extras')} "
                f"| {_pair(row, 'total')} | {_causes(row)} |")
    return '\n'.join(lines) + '\n'


def with_ids(cases):
    """Give each case a stable id; the id goes into every report row."""
    return [{**case, 'id': case.get('id') or f'C{number:02d}'} for number, case in enumerate(cases, start=1)]

