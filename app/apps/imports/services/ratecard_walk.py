"""Deterministic walk of rates_all.xls for one STH case.

The operational adapter uses this pure module after explicit activation. It reads three
source files identified by hash and reports each charge, its source row and
what it could not resolve. Expressions are never executed: only the patterns in
``_evaluate`` are recognised. A pending item is never zero and never in a total.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal
from itertools import groupby

from apps.imports.services.fuel import FuelImportError, normalize_ratecard, parse_fuel_rows
from apps.imports.services.rate_source_load import parse_rate_lines
from apps.imports.services.ratecard_chain import (
    _CARTONS, _CUSTOMER_GUARD_RE, _OPTION_RE, _OPTIONAL_QUANTITIES, _TONNES, _ZONE_LEVY_RE,
    _ZONE_PALLET_RE, SUPPORTED_ROOTS, _quoted,
)
from apps.imports.services.xlsx_reader import SourceImportError, calculate_sha256
from apps.imports.services.zone_source import read_zones

COMPLETE = 'COMPLETO'
PARTIAL = 'PARCIAL'
NO_QUOTE = 'SIN_COTIZACION'
UNKNOWN = 'DESCONOCIDO'
OUT_OF_SCOPE = 'FUERA_DE_ALCANCE'

ROOTS = {
    ('TEAMEX', 'ROAD'): SUPPORTED_ROOTS['TEAMEX'],
    ('KTI', 'GENERAL'): SUPPORTED_ROOTS['KTI'],
    ('TFMX', 'ROAD'): SUPPORTED_ROOTS['TFMX'],
    ('TEAMTAS', 'GENERAL'): SUPPORTED_ROOTS['TEAMTAS'],
    # Card 10 runs 1506 directly; no card points at the selector 1509.
    ('COCHRN', 'ROAD'): 1506,
    ('STEA', 'ROAD'): SUPPORTED_ROOTS['STEA'],
}
EXCLUDED = (('TEAMEX', 'GENERAL'), ('CUST', 'COLLECT'), ('MACHIPE', 'ROAD'), ('MIPEC', 'ROAD'))

# These cards charge per consignment, case and pallet instead of by zone line.
PER_CONSIGNMENT_CARDS = {18, 21}
OPEN_LIMIT = Decimal('999999')

YES, NO, OPTION, PENDING = 'YES', 'NO', 'OPTION', 'PENDING'
UNIT_UNCONFIRMED = 'UNIT_RULE_UNCONFIRMED'
JOB_FIELD_UNCONFIRMED = 'JOB_FIELD_MAPPING_UNCONFIRMED'
WTR_MINIMUM_UNCONFIRMED = 'WTR_MINIMUM_UNCONFIRMED'

_TEXT_FILTERS = {
    'cus_code': 'customer', 'del_zone': 'zone', 'jobs.del_zone': 'zone', 'del_subz': 'subzone',
    'jobs.del_subz': 'subzone', 'del_state': 'state', 'jobs.del_state': 'state',
}
_ZONE_FILTERS = {'del_zone', 'jobs.del_zone'}
_ZONE_LIST_PALLET_RE = re.compile(r'^iif\(inlist\(jobs\.del_zone,([^)]*)\),jobs\.pal2,0\)$')
_NOT_STATE_RE = re.compile(r'^iif\(inlist\(jobs\.del_state,([^)]*)\),0,1\)$')
_FAR_POSTCODE = "iif((jobs.del_post>='5718' and !inlist(jobs.del_post,'5950')),1,0)"
_NO_CASES = 'iif((jobs.pal1>0 or jobs.pal2>0),0,jobs.lift)'
_NO_PALLETS = 'iif((jobs.pal1>0 or jobs.pal2>0),0,jobs.pallet)'
_PENDING_FIELDS = {'col_zone': 'COLLECTION_ZONE_UNAVAILABLE', 'work_code': 'WORK_CODE_UNAVAILABLE'}


class WalkError(SourceImportError):
    """Raised when the sources cannot be trusted or read."""


@dataclass(frozen=True)
class Line:
    source_row: int
    master: int
    break_no: int
    item_no: int
    run_rate: int | None
    name: str
    filter_field: str
    from_value: str
    to_value: str
    greater: Decimal
    upto: Decimal
    unit: str
    rate: Decimal
    basic: Decimal
    minimum: Decimal
    cubic: Decimal
    each: Decimal = Decimal('1')


@dataclass(frozen=True)
class Case:
    carrier: str
    service: str
    suburb: str
    state: str
    postcode: str
    weight: Decimal
    cubic: Decimal
    pallets: int = 0
    cartons: int = 0
    tailgate: bool = False
    hand_unload: bool = False
    customer: str = 'STH'
    zone: str = ''
    subzone: str = ''

    @property
    def tonnes(self):
        return max(self.cubic, self.weight / 1000)

    def chargeable(self, factor):
        return max(self.weight, self.cubic * factor).quantize(Decimal('1'), rounding=ROUND_UP)


@dataclass
class Sources:
    rates_sha256: str
    zones_sha256: str
    fuel_sha256: str
    cards: dict
    zones: dict
    fuel: dict


def require_hash(content, expected, label):
    actual = calculate_sha256(content)
    if not re.fullmatch(r'[0-9a-f]{64}', (expected or '').lower()):
        raise WalkError(f'{label}: the expected SHA-256 must have 64 hexadecimal characters.')
    if actual != expected.lower():
        raise WalkError(f'{label}: hash {actual} does not match the expected {expected}.')
    return actual


def _cards(lines):
    cards = defaultdict(list)
    for item in lines:
        cards[item['master_rate']].append(Line(
            source_row=item['source_row'], master=item['master_rate'], break_no=item['break_no'],
            item_no=item['item_no'], run_rate=item['run_rate'], name=item['name'],
            filter_field=item['filter_field'], from_value=item['from_value'],
            to_value=item['to_value'], greater=item['greater'], upto=item['upto'],
            unit=item['unit'], rate=item['rate'], basic=item['basic_charge'],
            minimum=item['min_charge'], cubic=item['cubic'], each=item['each'],
        ))
    for lines_of_card in cards.values():
        lines_of_card.sort(key=lambda line: (line.break_no, line.item_no, line.source_row))
    return dict(cards)


def _zones(rows):
    zones = defaultdict(list)
    for row in rows:
        key = (row['carrier'].upper(), row['suburb'].strip().upper(), row['state'].strip().upper())
        zones[key].append(row)
    return dict(zones)


def load_sources(rates, zones, fuel, *, rates_sha256, zones_sha256, fuel_sha256,
                 rates_filename='rates_all.xls'):
    """Verify the three hashes before reading anything."""
    rates_hash = require_hash(rates, rates_sha256, 'rates')
    zones_hash = require_hash(zones, zones_sha256, 'zones')
    fuel_hash = require_hash(fuel, fuel_sha256, 'fuel')
    lines, _ = parse_rate_lines(rates, rates_filename)
    _, zone_rows = read_zones(zones)
    try:
        fuel_rows, _ = parse_fuel_rows(fuel)
    except FuelImportError as exc:
        raise WalkError(f'fuel: {exc}') from exc
    return Sources(rates_sha256=rates_hash, zones_sha256=zones_hash, fuel_sha256=fuel_hash,
                   cards=_cards(lines), zones=_zones(zone_rows),
                   fuel={row.master_rate: row.rate for row in fuel_rows if row.rate is not None})


def resolve_zone(sources, case):
    """Suburb and state first; the postcode only separates duplicates (RATE-002)."""
    key = (case.carrier, case.suburb.strip().upper(), case.state.strip().upper())
    rows = sources.zones.get(key, [])
    if not rows:
        return None, 'NO_ZONE'
    found = {(row['zone'], row['subzone']) for row in rows}
    if len(found) > 1:
        found = {(row['zone'], row['subzone']) for row in rows if row['postcode'] == case.postcode}
    if len(found) != 1:
        return None, 'ZONE_AMBIGUOUS'
    return found.pop(), ''


def _between(line, value):
    return line.greater < value <= line.upto


def _range(line, value):
    """Guards yield 0 or 1 and compare with the numeric text in from/to."""
    try:
        return Decimal(line.from_value) < value <= Decimal(line.to_value)
    except ArithmeticError:
        return False


def _yes(condition, caveat=''):
    return (YES, caveat) if condition else (NO, '')


def _evaluate(line, case, factor):
    """Return (outcome, reason). The reason on YES is a caveat on the result."""
    expression = line.filter_field
    key = expression.lower()
    if not expression:
        return YES, ''
    if key in _TEXT_FILTERS:
        return _yes(line.from_value < getattr(case, _TEXT_FILTERS[key]) <= line.to_value)
    if key == 'price':
        if line.upto == 0 or line.upto >= OPEN_LIMIT:
            return YES, ''
        return PENDING, 'PRICE_LIMIT_UNCONFIRMED'
    if key == 'weight':
        if not factor:
            return PENDING, 'NO_CUBIC_FACTOR'
        return _yes(_between(line, case.chargeable(factor)))
    if key == 'cubic':
        return _yes(_between(line, case.cubic))
    if key == 'jobs.pal2':
        return _yes(_between(line, case.pallets))
    if key == 'jobs.pal':
        return _yes(_between(line, case.pallets), JOB_FIELD_UNCONFIRMED)
    if key == 'jobs.pal1':
        return _yes(_between(line, case.cartons), JOB_FIELD_UNCONFIRMED)
    if expression in (_NO_CASES, _NO_PALLETS):
        return _yes(_between(line, Decimal('0')), JOB_FIELD_UNCONFIRMED)
    if expression == _CARTONS:
        return _yes(_between(line, case.cartons), JOB_FIELD_UNCONFIRMED)
    if expression == _TONNES:
        return _yes(_between(line, case.tonnes))
    if key in _OPTIONAL_QUANTITIES or key == 'jobs.ins_code':
        return OPTION, ''
    option = _OPTION_RE.match(expression)
    if option:
        word = option.group(1).upper()
        return (YES, '') if (case.tailgate and 'TAIL' in word) or (
            case.hand_unload and 'HAND' in word) else (OPTION, '')
    match = _ZONE_PALLET_RE.match(expression)
    if match:
        return _yes(case.zone == match.group(1) and _between(line, case.pallets))
    match = _ZONE_LIST_PALLET_RE.match(expression)
    if match:
        return _yes(case.zone in _quoted(match.group(1)) and _between(line, case.pallets))
    match = _ZONE_LEVY_RE.match(expression)
    if match and line.upto > 0:
        return _yes(case.zone in _quoted(match.group(1)))
    match = _NOT_STATE_RE.match(expression)
    if match:
        return _yes(_range(line, Decimal(int(case.state not in _quoted(match.group(1))))))
    if expression == _FAR_POSTCODE:
        far = case.postcode >= '5718' and case.postcode != '5950'
        return _yes(_range(line, Decimal(int(far))))
    match = _CUSTOMER_GUARD_RE.match(expression)
    if match and case.customer not in _quoted(match.group(1) or match.group(2)):
        return NO, ''
    if 'driver_zones.type' in expression:
        return PENDING, 'ZONE_TYPE_NOT_IN_ZONES_CSV'
    return PENDING, _PENDING_FIELDS.get(key, 'UNRECOGNISED_EXPRESSION')


def _amount(line, case, factor):
    """Return (amount, caveat), or (None, reason) for an unknown unit."""
    unit = line.unit
    if line.each != 1:
        return None, 'EACH_NOT_ONE'
    if unit in ('WTRM', 'WTR'):
        if not factor:
            return None, 'NO_CUBIC_FACTOR'
        kilos = case.chargeable(factor)
        candidate = line.basic + line.rate * kilos
        caveat = WTR_MINIMUM_UNCONFIRMED if unit == 'WTR' and line.minimum > candidate else ''
        return max(line.minimum, candidate), caveat
    if unit in ('TPAL', 'PAL'):
        return max(line.minimum, line.basic + line.rate * case.pallets), UNIT_UNCONFIRMED
    if unit in ('CASE', 'TCASE'):
        return max(line.minimum, line.basic + line.rate * case.cartons), UNIT_UNCONFIRMED
    if unit == 'CUB':
        return max(line.minimum, line.basic + line.rate * case.cubic), UNIT_UNCONFIRMED
    if unit == 'CUBT':
        whole = case.tonnes.quantize(Decimal('1'), rounding=ROUND_UP)
        return max(line.minimum, line.basic * case.cubic + line.rate * whole), UNIT_UNCONFIRMED
    if unit == 'CHG':
        return max(line.minimum, line.basic + line.rate), UNIT_UNCONFIRMED
    return None, 'UNIT_UNKNOWN'


def _reference(line):
    return {'card': line.master, 'row': line.source_row, 'break': line.break_no,
            'item': line.item_no, 'name': line.name}


def _is_zone_line(line):
    key = line.filter_field.lower()
    return (key in _ZONE_FILTERS or bool(_ZONE_PALLET_RE.match(line.filter_field))
            or bool(_ZONE_LIST_PALLET_RE.match(line.filter_field)))


def _is_freight(line):
    return line.master in PER_CONSIGNMENT_CARDS or (_is_zone_line(line) and line.unit != 'CHG')


class _Run:
    def __init__(self, sources, case):
        self.sources = sources
        self.case = case
        self.path = []
        self.freight = []
        self.extras = []
        self.fuel_lines = []
        self.pending = []
        self.options = []
        self.caveats = set()
        self.warnings = []
        self.zero_lines = []
        self.zone_card_seen = False
        self.freight_blocked = False

    def hold(self, line, reason, card=None):
        item = {**(_reference(line) if line else {}), 'reason': reason}
        if card is not None:
            item['target_card'] = card
        self.pending.append(item)

    def charge(self, line, factor):
        if line.unit == 'PRICE':
            if 'FUEL' in line.name.upper():
                self.fuel_lines.append(line)
            else:
                self.hold(line, 'PRICE_RULE_UNCONFIRMED')
            return
        if not (line.rate or line.basic or line.minimum):
            if _is_freight(line) or _is_zone_line(line):
                self.zero_lines.append(_reference(line))
            else:
                self.hold(line, 'ZERO_PRICE_LINE')
            return
        amount, note = _amount(line, self.case, factor)
        if amount is None:
            self.freight_blocked = self.freight_blocked or _is_freight(line)
            self.hold(line, note)
            return
        if amount <= 0:
            self.zero_lines.append(_reference(line))
            return
        if note:
            self.caveats.add(note)
        target = self.freight if _is_freight(line) else self.extras
        target.append({**_reference(line), 'unit': line.unit, 'rate': line.rate, 'basic': line.basic,
                       'minimum': line.minimum, 'amount': amount})


def _walk(card, run, trail, factor, via=None):
    if card in trail:
        run.hold(via, 'CIRCULAR_REFERENCE', card)
        return
    lines = run.sources.cards.get(card)
    if lines is None:
        run.hold(via, 'MISSING_CARD', card)
        return
    run.path.append(card)
    for _, group in groupby(lines, key=lambda line: line.break_no):
        group = list(group)
        for line in group:
            inherited = line.cubic or factor
            if _is_zone_line(line) and not line.run_rate:
                run.zone_card_seen = True
            outcome, reason = _evaluate(line, run.case, inherited)
            if outcome == NO:
                continue
            if outcome == OPTION:
                run.options.append(_reference(line))
                continue
            if outcome == PENDING:
                run.hold(line, reason)
                if any(_is_zone_line(item) and not item.run_rate for item in group):
                    run.freight_blocked = True
                break
            if reason:
                run.caveats.add(reason)
            if line.run_rate:
                _walk(line.run_rate, run, trail + [card], inherited, via=line)
            else:
                run.charge(line, inherited)
            break


def _apply_fuel(run, base):
    fuel = []
    for line in run.fuel_lines:
        rate = run.sources.fuel.get(normalize_ratecard(str(line.master)))
        if rate is None:
            run.hold(line, 'FUEL_NOT_IN_FILE')
            continue
        if rate != line.rate:
            run.warnings.append({'card': line.master, 'reason': 'FUEL_DIFFERS_FROM_RATES_ALL',
                                 'fuel_file': rate, 'rates_all': line.rate})
        fuel.append({**_reference(line), 'unit': line.unit, 'rate': rate, 'amount': rate * base})
    return fuel


def _money(item):
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in item.items()}


def _result(sources, case, status, *, reasons=(), run=None, fuel=(), total=None, known=None):
    run = run or _Run(sources, case)
    return {
        'carrier': case.carrier, 'service': case.service, 'status': status,
        'zone': case.zone, 'subzone': case.subzone, 'reasons': list(reasons),
        'hashes': {'rates_all': sources.rates_sha256, 'zones': sources.zones_sha256,
                   'fuel': sources.fuel_sha256},
        'path': run.path,
        'freight': [_money(item) for item in run.freight],
        'fuel': [_money(item) for item in fuel],
        'extras': [_money(item) for item in run.extras],
        'pending': run.pending,
        'options_not_requested': run.options,
        'zero_price_lines': run.zero_lines,
        'warnings': [_money(item) for item in run.warnings],
        'known_subtotal': None if known is None else str(known),
        'total': None if total is None else str(total),
    }


def walk_case(sources, case):
    """Walk one carrier. ``total`` is only given when every charge is settled."""
    key = (case.carrier, case.service)
    root = ROOTS.get(key)
    if root is None:
        return _result(sources, case, OUT_OF_SCOPE)
    found, reason = resolve_zone(sources, case)
    if found is None:
        return _result(sources, case, NO_QUOTE, reasons=[reason])
    case = Case(**{**case.__dict__, 'zone': found[0], 'subzone': found[1]})
    run = _Run(sources, case)
    _walk(root, run, [], Decimal('0'))
    base = sum((item['amount'] for item in run.freight), Decimal('0'))
    if base <= 0:
        if run.zero_lines:
            return _result(sources, case, NO_QUOTE, reasons=['ZERO_PRICE'], run=run)
        if run.pending and (run.freight_blocked or not run.zone_card_seen):
            return _result(sources, case, UNKNOWN, reasons=['CHAIN_STOPPED_BEFORE_FREIGHT'], run=run)
        return _result(sources, case, NO_QUOTE, reasons=['NO_RATE'], run=run)
    fuel = _apply_fuel(run, base)
    known = base + sum((item['amount'] for item in fuel), Decimal('0'))
    known += sum((item['amount'] for item in run.extras), Decimal('0'))
    if run.pending or run.caveats:
        return _result(sources, case, PARTIAL, reasons=sorted(run.caveats), run=run, fuel=fuel, known=known)
    return _result(sources, case, COMPLETE, run=run, fuel=fuel, known=known, total=known)


def walk_all(sources, **fields):
    """Every carrier in this stage, then the services it leaves out."""
    return [walk_case(sources, Case(carrier=carrier, service=service, **fields))
            for carrier, service in (*ROOTS, *EXCLUDED)]
