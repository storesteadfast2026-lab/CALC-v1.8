"""Read-only operational quote tests built from historical dispatch rows."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import xlrd
from django.conf import settings

from apps.freight.services.calculator import FreightCalculatorService
from apps.freight.services.consolidator import consolidate_lines
from apps.freight.services.dtos import FreightLine, FreightRequest
from apps.freight.services.validators import ValidationError
from apps.locations.models import Suburb


LOCAL_TIME = ZoneInfo('Australia/Adelaide')
REQUIRED_COLUMNS = {
    'jobs_cus_code', 'jobs_del_loc', 'jobs_del_state', 'jobs_weight',
    'jobs_cubic', 'jobs_quantity', 'jobs_pallet',
}


@dataclass(frozen=True)
class DispatchCase:
    source_row: int
    client: str
    suburb: str
    state: str
    historical_zone: str
    historical_carrier: str
    historical_service: str
    job_number: str
    quantity: Decimal
    pallets: Decimal
    weight_kg: Decimal
    cubic_m3: Decimal
    tailgate: bool


def run_operational_tests(source_path: Path, client_code: str, limit: int, out_dir: Path):
    client_code = client_code.strip().upper()
    source_path = source_path.resolve()
    rows, source_sheet, total_source_rows = _read_dispatch_cases(source_path, client_code)
    selected = _select_unique_destinations(rows, limit)
    if len(selected) < limit:
        raise ValueError(
            f'Only {len(selected)} eligible unique destinations were found for '
            f'{client_code}; {limit} were requested.'
        )

    postcode_map = _postcode_map(selected)
    engine = FreightCalculatorService()
    cases = [
        _run_case(engine, case, postcode_map.get((case.suburb, case.state), []), index)
        for index, case in enumerate(selected, start=1)
    ]

    generated_at = datetime.now(LOCAL_TIME)
    report = {
        'report_type': 'OPERATIONAL_PROCEDURE_TEST',
        'scope': 'READ_ONLY_NO_DATABASE_WRITES',
        'software_version': settings.APP_VERSION,
        'generated_at': generated_at.isoformat(),
        'client': client_code,
        'source': {
            'path': str(source_path),
            'filename': source_path.name,
            'sha256': _sha256(source_path),
            'sheet': source_sheet,
            'data_rows': total_source_rows,
            'eligible_rows': len(rows),
            'selection': (
                'One eligible historical row per unique suburb/state, selected '
                'deterministically in a state round-robin.'
            ),
        },
        'rules': {
            'price_comparison': 'NOT_USED_AS_PASS_FAIL_CRITERION',
            'postcode': 'Exact operational Suburb normalized_key; missing or multiple postcodes require review.',
            'cargo': (
                'Historical total weight/cubic are used. Quantity is the historical pallet '
                'count when present, otherwise historical quantity. Normal calculator '
                'pallet tare rules remain active.'
            ),
            'warnings': 'Operational source gaps and provisional charges require review, not silent acceptance.',
        },
        'summary': _summary(cases),
        'cases': cases,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime('%Y%m%d_%H%M%S')
    stem = f'{client_code.lower()}_operational_test_{stamp}'
    paths = {
        'json': out_dir / f'{stem}.json',
        'csv': out_dir / f'{stem}.csv',
        'markdown': out_dir / f'{stem}.md',
    }
    paths['json'].write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    _write_csv(paths['csv'], cases)
    paths['markdown'].write_text(_render_markdown(report), encoding='utf-8')
    return report, paths


def _read_dispatch_cases(path: Path, client_code: str):
    if not path.is_file():
        raise ValueError(f'Source workbook does not exist: {path}')
    workbook = xlrd.open_workbook(str(path), on_demand=True)
    try:
        sheet = workbook.sheet_by_index(0)
        headers = [_text(sheet.cell_value(0, col)).lower() for col in range(sheet.ncols)]
        header_map = {name: index for index, name in enumerate(headers) if name}
        missing = sorted(REQUIRED_COLUMNS - set(header_map))
        if missing:
            raise ValueError(f'Missing required columns: {", ".join(missing)}')

        rows = []
        for row_index in range(1, sheet.nrows):
            value = lambda name: sheet.cell_value(row_index, header_map[name]) if name in header_map else ''
            if _text(value('jobs_cus_code')).upper() != client_code:
                continue
            suburb = _text(value('jobs_del_loc')).upper()
            state = _text(value('jobs_del_state')).upper()
            weight = _decimal(value('jobs_weight'))
            cubic = _decimal(value('jobs_cubic'))
            quantity = _decimal(value('jobs_quantity'))
            pallets = _decimal(value('jobs_pallet'))
            units = pallets if pallets > Decimal('0.99') else quantity
            if not suburb or not state or weight <= 0 or cubic <= 0 or units <= Decimal('0.99'):
                continue
            rows.append(DispatchCase(
                source_row=row_index + 1,
                client=client_code,
                suburb=suburb,
                state=state,
                historical_zone=_text(value('jobs_del_zone')).upper(),
                historical_carrier=_text(value('jobs_drv_code')).upper(),
                historical_service=_text(value('jobs_srv_code')).upper(),
                job_number=_text(value('jobs_job_no')),
                quantity=quantity,
                pallets=pallets,
                weight_kg=weight,
                cubic_m3=cubic,
                tailgate=_decimal(value('jobs_lift')) > 0,
            ))
        return rows, sheet.name, max(sheet.nrows - 1, 0)
    finally:
        workbook.release_resources()


def _select_unique_destinations(rows: list[DispatchCase], limit: int):
    unique = {}
    for row in rows:
        unique.setdefault((row.suburb, row.state), row)
    by_state = defaultdict(list)
    for case in unique.values():
        by_state[case.state].append(case)
    queues = {
        state: deque(sorted(cases, key=lambda item: (item.suburb, item.source_row)))
        for state, cases in sorted(by_state.items())
    }
    selected = []
    while queues and len(selected) < limit:
        for state in list(queues):
            selected.append(queues[state].popleft())
            if not queues[state]:
                del queues[state]
            if len(selected) == limit:
                break
    return selected


def _postcode_map(cases: list[DispatchCase]):
    keys = {f'{case.state}{case.suburb}'.upper().strip() for case in cases}
    found = defaultdict(set)
    for item in Suburb.objects.filter(normalized_key__in=keys).values(
        'normalized_key', 'postcode'
    ):
        found[item['normalized_key']].add(str(item['postcode']).strip())
    return {
        (case.suburb, case.state): sorted(found.get(f'{case.state}{case.suburb}'.upper().strip(), set()))
        for case in cases
    }


def _run_case(engine, case: DispatchCase, postcodes: list[str], index: int):
    case_id = f'OP-{index:03d}'
    base = {
        'case_id': case_id,
        'source_row': case.source_row,
        'source_job_number': case.job_number,
        'destination': {'suburb': case.suburb, 'state': case.state, 'postcodes': postcodes},
        'historical_reference': {
            'zone': case.historical_zone,
            'carrier': case.historical_carrier,
            'service': case.historical_service,
        },
        'source_cargo': {
            'quantity': str(case.quantity), 'pallets': str(case.pallets),
            'weight_kg': str(case.weight_kg), 'cubic_m3': str(case.cubic_m3),
            'tailgate': case.tailgate,
        },
        'outcome': 'NOT_QUOTED', 'review_required': True,
        'checks': [], 'warnings': [], 'results': [],
    }
    if not postcodes:
        base['checks'].append(_check('POSTCODE_RESOLUTION', False, 'No operational postcode matched.'))
        return base
    if len(postcodes) > 1:
        base['checks'].append(_check(
            'POSTCODE_RESOLUTION', False,
            f'Multiple operational postcodes matched: {", ".join(postcodes)}.'
        ))
        return base

    units = case.pallets if case.pallets > Decimal('0.99') else case.quantity
    freight_type = 'P' if case.pallets > Decimal('0.99') else 'C'
    line = FreightLine(
        sku=None,
        quantity=units,
        freight_type=freight_type,
        length_m=Decimal('0'), width_m=Decimal('0'), height_m=Decimal('0'),
        weight_kg=case.weight_kg / units,
        cubic_m3=case.cubic_m3,
    )
    consolidated = consolidate_lines([line], case.tailgate)
    base['calculator_input'] = {
        'freight_type': freight_type,
        'units': str(units),
        'per_unit_weight_kg': str(line.weight_kg),
        'cubic_m3': str(line.cubic_m3),
    }
    base['consolidated_cargo'] = {
        'weight_kg': str(consolidated.weight_total_kg),
        'cubic_m3': str(consolidated.cubic_total_m3),
        'pallets': str(consolidated.pallet_count),
        'cartons': str(consolidated.carton_count),
        'tailgate': consolidated.tailgate,
    }
    request = FreightRequest(
        client_code=case.client, from_address_id=None,
        suburb=case.suburb, state=case.state, postcode=postcodes[0],
        tailgate=case.tailgate, preselect_sku=False, lines=[line],
        cubic_margin_percent=Decimal('0'),
    )
    try:
        results = engine.calculate(request)
    except (ValidationError, ArithmeticError, ValueError) as exc:
        base['checks'].append(_check('CALCULATOR_EXECUTION', False, str(exc)))
        _finalise_case(base, execution_failed=True)
        return base

    base['warnings'] = list(engine.last_warnings or [])
    base['checks'].append(_check('POSTCODE_RESOLUTION', True, f'Unique match: {postcodes[0]}.'))
    base['checks'].append(_check('RESULT_AVAILABLE', bool(results), f'{len(results)} result(s) returned.'))
    invariant_failures = False
    for rank, result in enumerate(results, start=1):
        details = result.details or {}
        operational_status = details.get('operational_status', '')
        estimate_ok = result.estimate_ex_gst >= 0
        zone_ok = bool(str(details.get('zone', '')).strip())
        chargeable = _decimal(details.get('chargeable_weight'))
        actual = _decimal(details.get('actual_weight'))
        actual_rating_units = (
            actual / Decimal('1000')
            if result.carrier == 'TEAMTAS' and result.service == 'GENERAL'
            else actual
        )
        weight_ok = chargeable >= actual_rating_units
        invariant_failures = invariant_failures or not (estimate_ok and zone_ok and weight_ok)
        base['results'].append({
            'rank': rank, 'carrier': result.carrier, 'service': result.service,
            'estimate_ex_gst': str(result.estimate_ex_gst),
            'operational_status': operational_status,
            'zone': details.get('zone', ''), 'subzone': details.get('subzone', ''),
            'chargeable_weight': details.get('chargeable_weight', ''),
            'actual_weight': details.get('actual_weight', ''),
            'cubic_total': details.get('cubic_total', ''),
            'unresolved_charges': details.get('unresolved_charges', []),
            'rate_path': details.get('rate_path', []),
            'source_versions': details.get('source_versions', {}),
            'checks': {
                'non_negative_estimate': estimate_ok,
                'zone_present': zone_ok,
                'chargeable_weight_covers_actual_rating_units': weight_ok,
            },
        })
    _finalise_case(base, invariant_failures=invariant_failures)
    return base


def _finalise_case(case, *, execution_failed=False, invariant_failures=False):
    results = case['results']
    if execution_failed or invariant_failures:
        case['outcome'] = 'FAILED'
    elif any(result.get('operational_status') == 'COMPLETE' for result in results):
        case['outcome'] = 'QUOTED_COMPLETE'
    elif results:
        case['outcome'] = 'QUOTED_PROVISIONAL'
    else:
        case['outcome'] = 'NOT_QUOTED'

    case['review_required'] = bool(
        case['warnings']
        or any(not check['passed'] for check in case['checks'])
        or any(result.get('operational_status') == 'PROVISIONAL' for result in results)
    )


def _check(name, passed, detail):
    return {'name': name, 'passed': passed, 'detail': detail}


def _summary(cases):
    outcomes = Counter(case['outcome'] for case in cases)
    warnings = Counter(
        warning.get('status', 'UNKNOWN')
        for case in cases for warning in case['warnings']
    )
    return {
        'total_cases': len(cases),
        'quoted_complete_cases': outcomes['QUOTED_COMPLETE'],
        'quoted_provisional_cases': outcomes['QUOTED_PROVISIONAL'],
        'not_quoted_cases': outcomes['NOT_QUOTED'],
        'failed_cases': outcomes['FAILED'],
        'review_required_cases': sum(case['review_required'] for case in cases),
        'quoted_cases': sum(bool(case['results']) for case in cases),
        'complete_results': sum(
            result['operational_status'] == 'COMPLETE'
            for case in cases for result in case['results']
        ),
        'provisional_results': sum(
            result['operational_status'] == 'PROVISIONAL'
            for case in cases for result in case['results']
        ),
        'warning_statuses': dict(sorted(warnings.items())),
    }


def _write_csv(path, cases):
    fields = [
        'case_id', 'outcome', 'review_required', 'source_row', 'source_job_number',
        'suburb', 'state',
        'postcode', 'historical_zone', 'historical_carrier', 'historical_service',
        'source_weight_kg', 'source_cubic_m3', 'consolidated_weight_kg',
        'consolidated_cubic_m3', 'results_count', 'complete_results',
        'provisional_results', 'warnings',
    ]
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            results = case['results']
            writer.writerow({
                'case_id': case['case_id'], 'outcome': case['outcome'],
                'review_required': case['review_required'],
                'source_row': case['source_row'], 'source_job_number': case['source_job_number'],
                'suburb': case['destination']['suburb'], 'state': case['destination']['state'],
                'postcode': '|'.join(case['destination']['postcodes']),
                'historical_zone': case['historical_reference']['zone'],
                'historical_carrier': case['historical_reference']['carrier'],
                'historical_service': case['historical_reference']['service'],
                'source_weight_kg': case['source_cargo']['weight_kg'],
                'source_cubic_m3': case['source_cargo']['cubic_m3'],
                'consolidated_weight_kg': case.get('consolidated_cargo', {}).get('weight_kg', ''),
                'consolidated_cubic_m3': case.get('consolidated_cargo', {}).get('cubic_m3', ''),
                'results_count': len(results),
                'complete_results': sum(item['operational_status'] == 'COMPLETE' for item in results),
                'provisional_results': sum(item['operational_status'] == 'PROVISIONAL' for item in results),
                'warnings': ' | '.join(
                    f"{item.get('carrier', '')} {item.get('service', '')}: {item.get('status', '')}"
                    for item in case['warnings']
                ),
            })


def _render_markdown(report):
    summary = report['summary']
    lines = [
        f"# {report['client']} operational procedure test",
        '', f"Generated: {report['generated_at']}",
        '', '> Prices are recorded for traceability but are not used as pass/fail criteria.',
        '', '## Summary', '',
        f"- Cases: {summary['total_cases']}",
        f"- Quoted complete cases: {summary['quoted_complete_cases']}",
        f"- Quoted provisional cases: {summary['quoted_provisional_cases']}",
        f"- Not quoted cases: {summary['not_quoted_cases']}",
        f"- Failed cases: {summary['failed_cases']}",
        f"- Review required cases: {summary['review_required_cases']}",
        f"- Quoted cases: {summary['quoted_cases']}",
        f"- Complete results: {summary['complete_results']}",
        f"- Provisional results: {summary['provisional_results']}",
        '', '## Cases', '',
        '| Case | Source row | Destination | Outcome | Review required | Results | Warnings |',
        '|---|---:|---|---|---|---:|---|',
    ]
    for case in report['cases']:
        destination = case['destination']
        warnings = ', '.join(sorted({item.get('status', '') for item in case['warnings']})) or '—'
        lines.append(
            f"| {case['case_id']} | {case['source_row']} | "
            f"{destination['suburb']} {destination['state']} {'/'.join(destination['postcodes'])} | "
            f"{case['outcome']} | {'Yes' if case['review_required'] else 'No'} | "
            f"{len(case['results'])} | {warnings} |"
        )
    lines.extend(['', '## Interpretation', '',
                  '- QUOTED_COMPLETE: at least one complete quote result was returned.',
                  '- QUOTED_PROVISIONAL: quote results were returned, but all are provisional.',
                  '- NOT_QUOTED: no quote result was returned.',
                  '- FAILED: execution failed or a calculation invariant failed.',
                  '- Review required is independent of the outcome and preserves postcode issues, provisional charges, failed checks and operational source warnings.', ''])
    return '\n'.join(lines)


def _text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value)).strip()
    return str(value).strip()


def _decimal(value):
    try:
        return Decimal(_text(value).replace(',', '') or '0')
    except InvalidOperation:
        return Decimal('0')


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
