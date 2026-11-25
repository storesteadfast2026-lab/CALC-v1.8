"""Read-only resolution of the rates_all selector chain for one case.

No database access and no tariff activation. Expressions are never executed:
only the patterns listed in ``_evaluate`` are recognised, everything else is
reported as UNKNOWN. Range rule for text filters: ``from < value <= to``.
"""
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field

from apps.imports.services.product_file_adapters import read_product_file
from apps.imports.services.ratecard_source import FIELDS
from apps.imports.services.xlsx_reader import SourceImportError

APPLICABLE = 'APPLICABLE'
NOT_APPLICABLE = 'NOT_APPLICABLE'
UNKNOWN = 'UNKNOWN'

# Roots traced from the file. STEA is a best-known root: its customer selector
# (20) has no confirmed STH line, so the gap must surface as a finding.
SUPPORTED_ROOTS = {
    'TEAMEX': 1135,
    'KTI': 79,
    'TFMX': 55,
    'TEAMTAS': 711,
    'COCHRN': 1509,
    'STEA': 20,
}

_TEXT_FILTERS = {
    'cus_code': 'customer',
    'del_zone': 'zone',
    'del_subz': 'subzone',
    'jobs.del_subz': 'subzone',
    'jobs.del_state': 'state',
}
_OPTION_RE = re.compile(r'^iif\(AT\("([A-Z a-z]+)",')
_OPTIONAL_QUANTITIES = {'job2.qty5', 'jobs.qty5'}
_ZONE_PALLET_RE = re.compile(r'^iif\(jobs\.del_zone="(\w+)",jobs\.pal2,0\)$')
_ZONE_LEVY_RE = re.compile(r'^iif\(inlist\(jobs\.del_zone,([^)]*)\),1,0\)$')
_NOT_STATE_RE = re.compile(r'^iif\(inlist\(jobs\.del_state,([^)]*)\),0,1\)$')
_CUSTOMER_GUARD_RE = re.compile(
    r'^iif\(\(?(?:inlist\(jobs\.cus_code,([^)]*)\)|jobs\.cus_code=("\w+")).*,0,1\)$')
_TONNES = 'iif(cubic*1>(weight/1000)*1,cubic,weight/1000)'
_CARTONS = 'iif(jobs.pal1>0,jobs.pal1,jobs.lift)'
_FAR_NORTH_POSTCODE = "iif((jobs.del_post>='5718' and !inlist(jobs.del_post,'5950')),1,0)"
_LOOSE_CASES = 'iif((jobs.pal1>0 or jobs.pal2>0),0,jobs.lift)'
_LOOSE_PALLETS = 'iif((jobs.pal1>0 or jobs.pal2>0),0,jobs.pallet)'


def _number(value):
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number == int(number) else number


def _quoted(values):
    return {item.strip().strip('"\'') for item in values.split(',')}


def customer_scope(line, customer='STH'):
    """Classify only explicit customer selectors; leave route logic undecided."""
    expression = line.filter_field
    if expression.lower() == 'cus_code':
        return 'MATCHES_CUSTOMER' if line.from_value < customer <= line.to_value else 'OTHER_CUSTOMER'
    match = _CUSTOMER_GUARD_RE.match(expression)
    if match:
        customers = _quoted(match.group(1) or match.group(2))
        return 'CUSTOMER_ROUTE_DEPENDENT' if customer in customers else 'OTHER_CUSTOMER'
    return 'NOT_CUSTOMER_SPECIFIC'


@dataclass(frozen=True)
class CardLine:
    source_row: int
    master: int
    card_name: str
    break_no: int
    item_no: int
    run_rate: int | None
    name: str
    filter_field: str
    from_value: str
    to_value: str
    greater: float
    upto: float
    unit: str
    rate: float
    basic: float
    minimum: float

    @property
    def priced(self):
        return bool(self.rate or self.basic or self.minimum)


@dataclass
class Catalogue:
    sha256: str
    rows: int
    masters: dict = field(default_factory=dict)

    def missing_references(self):
        referenced = {line.run_rate for lines in self.masters.values() for line in lines if line.run_rate}
        return sorted(referenced - set(self.masters))

    def structurally_reachable_cards(self, root):
        """Return cards linked from a root without evaluating route conditions."""
        reached = set()
        pending = [root]
        while pending:
            master = pending.pop()
            if master in reached:
                continue
            reached.add(master)
            for line in self.masters.get(master, ()):
                if line.run_rate in self.masters and line.run_rate not in reached:
                    pending.append(line.run_rate)
        return reached

    def missing_reference_details(self):
        """Describe missing targets and structural reachability from STH roots."""
        reachable = {
            carrier: self.structurally_reachable_cards(root)
            for carrier, root in SUPPORTED_ROOTS.items()
        }
        details = {}
        for master, lines in self.masters.items():
            carriers = sorted(
                carrier for carrier, cards in reachable.items() if master in cards
            )
            for line in lines:
                if not line.run_rate or line.run_rate in self.masters:
                    continue
                scope = customer_scope(line)
                issue = expression_issue(line)
                detail = details.setdefault(line.run_rate, {
                    'card': line.run_rate,
                    'reachable_carriers': set(),
                    'references': [],
                })
                detail['reachable_carriers'].update(carriers)
                detail['references'].append({
                    'from_card': master,
                    'row': line.source_row,
                    'name': line.name,
                    'carriers': carriers,
                    'expression': line.filter_field,
                    'from': line.from_value,
                    'to': line.to_value,
                    'customer_scope': scope,
                    'condition_issue': issue,
                })
        result = []
        for card in sorted(details):
            detail = details[card]
            reachable_references = [
                item for item in detail['references'] if item['carriers']
            ]
            relevant_references = [
                item for item in reachable_references
                if item['customer_scope'] != 'OTHER_CUSTOMER'
            ]
            issues = {item['condition_issue'] for item in relevant_references
                      if item['condition_issue']}
            if not detail['reachable_carriers']:
                review_status = 'UNREACHABLE_FROM_STH_ROOTS'
            elif not relevant_references:
                review_status = 'OTHER_CUSTOMER_ONLY'
            elif 'ZONE_TYPE_NOT_IN_ZONES_CSV' in issues:
                review_status = 'SOURCE_FIELD_REQUIRED'
            elif issues:
                review_status = 'EXPRESSION_REVIEW_REQUIRED'
            else:
                review_status = 'CONDITIONALLY_REACHABLE'
            result.append({
                'card': card,
                'structurally_reachable': bool(detail['reachable_carriers']),
                'reachable_carriers': sorted(detail['reachable_carriers']),
                'review_status': review_status,
                'references': sorted(
                    detail['references'], key=lambda item: (item['from_card'], item['row']),
                ),
            })
        return result


@dataclass(frozen=True)
class CaseContext:
    zone: str
    state: str
    postcode: str = ''
    subzone: str = ''
    weight: float = 0
    pallets: int = 1
    cartons: int = 0
    loose_cartons: int = 0
    loose_pallets: int = 0
    cubic: float = 1
    customer: str = 'STH'

    @property
    def tonnes(self):
        return max(self.cubic, self.weight / 1000)


@dataclass
class CaseResult:
    status: str = NOT_APPLICABLE
    base_status: str = NOT_APPLICABLE
    freight: list = field(default_factory=list)
    surcharges: list = field(default_factory=list)
    percent_of_price: list = field(default_factory=list)
    options: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    path: list = field(default_factory=list)


def load_catalogue(content, filename='rates_all.xls'):
    """Parse the native export, keeping every source row number."""
    try:
        result = read_product_file(content, filename, aliases={k: (k,) for k in FIELDS},
                                   required_fields=FIELDS, expected_csv_column_count=len(FIELDS))
    except SourceImportError:
        raise
    except Exception as exc:
        raise SourceImportError('The XLS rate-card file could not be read.') from exc
    masters = defaultdict(list)
    for row in result.records:
        master = _number(row['master_rate'])
        if not isinstance(master, int):
            raise SourceImportError(f"Row {row['_row_number']}: master_rate is not numeric.")
        masters[master].append(CardLine(
            source_row=row['_row_number'], master=master,
            card_name=str(row['rc_name'] or '').strip(),
            break_no=_number(row['break']) or 0, item_no=_number(row['item_no']) or 0,
            run_rate=_number(row['run_rate']) or None,
            name=str(row['name'] or '').strip(),
            filter_field=str(row['filter_field'] or '').strip(),
            from_value=str(row['from'] or '').strip(), to_value=str(row['to'] or '').strip(),
            greater=_number(row['greater']) or 0, upto=_number(row['upto']) or 0,
            unit=str(row['unit'] or '').strip(), rate=_number(row['rate']) or 0,
            basic=_number(row['basic_charge']) or 0, minimum=_number(row['min_charge']) or 0,
        ))
    for lines in masters.values():
        lines.sort(key=lambda line: (line.break_no, line.item_no))
    return Catalogue(sha256=hashlib.sha256(content).hexdigest(), rows=len(result.records),
                     masters=dict(masters))


def _between(line, value):
    return line.greater < value <= line.upto


def _evaluate(line, ctx):
    """Return (outcome, reason); outcome is True, False, 'OPTION' or UNKNOWN."""
    expression = line.filter_field
    key = expression.lower()
    if not expression:
        return True, ''
    if key in _TEXT_FILTERS:
        return line.from_value < getattr(ctx, _TEXT_FILTERS[key]) <= line.to_value, ''
    if key == 'price':
        return True, ''
    if key == 'weight':
        return _between(line, ctx.weight), ''
    if key == 'cubic':
        return _between(line, ctx.cubic), ''
    if key == 'jobs.pal1':
        return _between(line, ctx.cartons), ''
    if key == 'jobs.pal2':
        return _between(line, ctx.pallets), ''
    if expression == _CARTONS:
        return _between(line, ctx.cartons), ''
    if expression == _TONNES:
        return _between(line, ctx.tonnes), ''
    if expression == _LOOSE_CASES:
        value = 0 if ctx.cartons or ctx.pallets else ctx.loose_cartons
        return _between(line, value), ''
    if expression == _LOOSE_PALLETS:
        value = 0 if ctx.cartons or ctx.pallets else ctx.loose_pallets
        return _between(line, value), ''
    if expression == _FAR_NORTH_POSTCODE:
        selected = bool(ctx.postcode and ctx.postcode >= '5718' and ctx.postcode != '5950')
        value = '1' if selected else '0'
        return line.from_value < value <= line.to_value, ''
    if key in _OPTIONAL_QUANTITIES or _OPTION_RE.match(expression):
        return 'OPTION', ''
    match = _ZONE_PALLET_RE.match(expression)
    if match:
        return (ctx.zone == match.group(1) and _between(line, ctx.pallets)), ''
    match = _ZONE_LEVY_RE.match(expression)
    if match and line.upto > 0:
        return ctx.zone in _quoted(match.group(1)), ''
    match = _NOT_STATE_RE.match(expression)
    if match:
        return ctx.state not in _quoted(match.group(1)), ''
    match = _CUSTOMER_GUARD_RE.match(expression)
    if match and ctx.customer not in _quoted(match.group(1) or match.group(2)):
        # Read literally, (0, 1] would send every other customer to this card.
        # Current TEAMEX rows equal cards 1517/1518, so STH does not take it.
        return False, ''
    if 'driver_zones.type' in expression:
        return UNKNOWN, 'ZONE_TYPE_NOT_IN_ZONES_CSV'
    return UNKNOWN, 'UNRECOGNISED_EXPRESSION'


def expression_issue(line, customer='STH'):
    """Return the parser limitation for one catalogue line, if any.

    This is a structural inventory only. It does not prove that the line is
    reachable for a carrier route or that it affects an operational quote.
    """
    _, reason = _evaluate(line, CaseContext(zone='', state='', customer=customer))
    return reason


def _reference(line):
    return {'card': line.master, 'row': line.source_row, 'break': line.break_no,
            'item': line.item_no, 'name': line.name}


def _is_freight(line):
    """Base freight is a priced line selected by destination zone."""
    key = line.filter_field.lower()
    return key == 'del_zone' or bool(_ZONE_PALLET_RE.match(line.filter_field))


def _record_terminal(line, result):
    item = {**_reference(line), 'unit': line.unit, 'rate': line.rate,
            'basic': line.basic, 'minimum': line.minimum}
    if line.filter_field.lower() == 'price' or line.unit == 'PRICE':
        result.percent_of_price.append(item)
    elif _is_freight(line):
        result.freight.append(item)
    else:
        result.surcharges.append(item)


def _walk(catalogue, master, ctx, result, trail):
    if master in trail:
        result.unresolved.append({'card': master, 'reason': 'CIRCULAR_REFERENCE'})
        return
    lines = catalogue.masters.get(master)
    if lines is None:
        result.unresolved.append({'card': master, 'reason': 'MISSING_MASTER'})
        return
    result.path.append(master)
    breaks = defaultdict(list)
    for line in lines:
        breaks[line.break_no].append(line)
    for number in sorted(breaks):
        for line in breaks[number]:
            outcome, reason = _evaluate(line, ctx)
            if outcome is False:
                continue
            if outcome == 'OPTION':
                result.options.append(_reference(line))
                continue
            if outcome == UNKNOWN:
                result.unresolved.append({**_reference(line), 'reason': reason})
                break
            if line.run_rate:
                _walk(catalogue, line.run_rate, ctx, result, trail + [master])
            else:
                _record_terminal(line, result)
            break


def resolve_case(catalogue, carrier, ctx):
    """Walk one carrier chain; base_status ignores unresolved surcharges."""
    result = CaseResult()
    _walk(catalogue, SUPPORTED_ROOTS[carrier], ctx, result, [])
    if any(item['rate'] or item['basic'] or item['minimum'] for item in result.freight):
        result.base_status = APPLICABLE
        result.status = UNKNOWN if result.unresolved else APPLICABLE
    elif result.unresolved and not priced_zones(catalogue, result.path):
        # The chain stopped before any zone card: absence of price is unproven.
        result.base_status = result.status = UNKNOWN
    return result


def priced_zones(catalogue, masters):
    """Zones priced on terminal Del_zone lines of the given cards."""
    zones = set()
    for master in masters:
        for line in catalogue.masters.get(master, ()):
            if line.filter_field.lower() == 'del_zone' and not line.run_rate and line.priced:
                zones.add(line.to_value)
    return zones
