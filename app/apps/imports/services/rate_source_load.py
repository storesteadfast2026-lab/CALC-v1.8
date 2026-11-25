"""Versioned storage of rates_all.xls and zones.csv for STH.

These rows are not read by the freight calculator. Loading a version changes no
quote, tariff, zone or fuel value. Expressions in the source are stored as text
and are never executed.
"""
from __future__ import annotations

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.carriers.models import ClientCarrierConfig
from apps.imports.models import ExternalDataFile, RateCardLine, ZoneSourceRow
from apps.imports.services.audit import create_audit_event
from apps.imports.services.product_file_adapters import read_product_file
from apps.imports.services.ratecard_chain import (
    SUPPORTED_ROOTS,
    expression_issue,
    load_catalogue,
)
from apps.imports.services.ratecard_source import FIELDS, review_ratecard
from apps.imports.services.xlsx_reader import SourceImportError, calculate_sha256, value_to_text
from apps.imports.services.zone_source import read_zones, summarise_carrier

SUPPORTED_CLIENT = 'STH'
RATE_SOURCE_TYPES = ('RATES', 'ZONES')
RETAINED_VERSIONS = 10
BATCH_SIZE = 2000
MONEY_PLACES = Decimal('0.000001')
FLOAT_NOISE = Decimal('0.000000001')
MAX_LISTED = 50

_TEXT_FIELDS = {
    'rate_no': 'rate_no', 'code': 'code', 'name': 'name', 'filter_field': 'filter_field',
    'from': 'from_value', 'to': 'to_value', 'band': 'band', 'unit': 'unit',
    'gl_code': 'gl_code', 'analysis': 'analysis', 'gst_code': 'gst_code', 'rcst': 'rcst',
    'rc_name': 'rc_name', 'rtst': 'rtst', 'group1': 'group1', 'rate_code': 'rate_code',
}
_DECIMAL_FIELDS = ('greater', 'upto', 'each', 'rate', 'basic_charge', 'min_charge', 'cubic')
_CARD_KEYS = ('break_no', 'item_no', 'run_rate', 'filter_field', 'from_value', 'to_value',
              'greater', 'upto', 'unit', 'rate', 'basic_charge', 'min_charge', 'cubic')
_ZONE_KEYS = ('carrier', 'suburb', 'state', 'postcode', 'zone', 'subzone', 'area')


class RateSourceError(SourceImportError):
    """Raised when a rate source cannot be prepared, loaded or rolled back."""


def _integer(value, *, label, row, required=False):
    text = value_to_text(value).strip()
    if not text:
        if required:
            raise RateSourceError(f'Row {row}: {label} is required.')
        return None
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise RateSourceError(f'Row {row}: {label} must be a number.') from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise RateSourceError(f'Row {row}: {label} must be a whole number.')
    return int(number)


def _money(value, *, label, row):
    """Return the six-decimal value and whether a real digit was lost."""
    text = value_to_text(value).strip()
    if not text:
        return Decimal('0.000000'), False
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise RateSourceError(f'Row {row}: {label} must be a number.') from exc
    if not number.is_finite():
        raise RateSourceError(f'Row {row}: {label} must be a finite number.')
    rounded = number.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    return rounded, abs(rounded - number) > FLOAT_NOISE


def parse_rate_lines(content, filename):
    """Return (line values, rounded value count) keeping every source row."""
    result = read_product_file(content, filename, aliases={key: (key,) for key in FIELDS},
                               required_fields=FIELDS, expected_csv_column_count=len(FIELDS))
    lines = []
    rounded_values = 0
    for record in result.records:
        row = record['_row_number']
        line = {
            'source_row': row,
            'master_rate': _integer(record['master_rate'], label='master_rate', row=row, required=True),
            'break_no': _integer(record['break'], label='break', row=row) or 0,
            'item_no': _integer(record['item_no'], label='item_no', row=row) or 0,
            'run_rate': _integer(record['run_rate'], label='run_rate', row=row) or None,
        }
        for source, target in _TEXT_FIELDS.items():
            line[target] = value_to_text(record[source]).strip()
        for field in _DECIMAL_FIELDS:
            line[field], lost = _money(record[field], label=field, row=row)
            rounded_values += int(lost)
        lines.append(line)
    return lines, rounded_values


def client_carriers(client):
    return set(
        code.upper() for code in ClientCarrierConfig.objects.filter(client=client)
        .values_list('carrier_service__carrier__code', flat=True)
    )


def parse_zone_rows(content, client):
    """Return (digest, rows in file, rows for this client's carriers)."""
    digest, rows = read_zones(content)
    carriers = client_carriers(client)
    selected = [row for row in rows if row['carrier'].upper() in carriers]
    return digest, len(rows), selected


def _active_version(client, file_type):
    return (ExternalDataFile.objects.filter(client=client, file_type=file_type, status='ACTIVE')
            .order_by('-activated_at', '-pk').first())


def _card_fingerprints(lines):
    cards = {}
    for line in sorted(lines, key=lambda item: (item['master_rate'], item['break_no'],
                                                item['item_no'], item['source_row'])):
        cards.setdefault(line['master_rate'], []).append(tuple(str(line[key]) for key in _CARD_KEYS))
    return cards


def _listed(values):
    values = sorted(values)
    return {'count': len(values), 'first': values[:MAX_LISTED]}


def rate_expression_diagnostics(content, filename):
    """Inventory expressions the read-only catalogue parser cannot resolve."""
    catalogue = load_catalogue(content, filename)
    groups = {}
    for master, lines in catalogue.masters.items():
        for line in lines:
            reason = expression_issue(line)
            if not reason:
                continue
            key = (reason, line.name, line.filter_field)
            group = groups.setdefault(key, {
                'reason': reason,
                'name': line.name,
                'expression': line.filter_field,
                'count': 0,
                'examples': [],
            })
            group['count'] += 1
            if len(group['examples']) < 5:
                group['examples'].append({'card': master, 'row': line.source_row})
    ordered = sorted(
        groups.values(),
        key=lambda item: (-item['count'], item['reason'], item['name'], item['expression']),
    )
    reason_counts = Counter()
    for item in ordered:
        reason_counts[item['reason']] += item['count']
    return {
        'scope': 'CATALOGUE_WIDE_STRUCTURE_ONLY',
        'issue_rows': sum(item['count'] for item in ordered),
        'issue_groups': len(ordered),
        'reason_counts': dict(sorted(reason_counts.items())),
        'groups': ordered,
        'groups_truncated': 0,
        'route_impact_proven': False,
        'quotes_changed': False,
    }


def rate_preview(content, filename, client):
    lines, rounded_values = parse_rate_lines(content, filename)
    masters = {line['master_rate'] for line in lines}
    references = {line['run_rate'] for line in lines if line['run_rate']}
    preview = {
        'rows': len(lines),
        'cards': len(masters),
        'missing_references': sorted(references - masters),
        'carrier_roots': {carrier: root in masters for carrier, root in SUPPORTED_ROOTS.items()},
        'rounded_values': rounded_values,
        'expression_diagnostics': rate_expression_diagnostics(content, filename),
        'compared_with_file_id': None,
    }
    active = _active_version(client, 'RATES')
    if active:
        new_cards = _card_fingerprints(lines)
        old_cards = _card_fingerprints(active.rate_card_lines.values(*_CARD_KEYS, 'master_rate', 'source_row'))
        preview.update({
            'compared_with_file_id': active.pk,
            'cards_added': _listed(set(new_cards) - set(old_cards)),
            'cards_removed': _listed(set(old_cards) - set(new_cards)),
            'cards_changed': _listed(card for card in set(new_cards) & set(old_cards)
                                     if new_cards[card] != old_cards[card]),
        })
    return preview


def zone_preview(content, client):
    _, rows_in_file, rows = parse_zone_rows(content, client)
    by_carrier = {}
    for row in rows:
        by_carrier.setdefault(row['carrier'].upper(), []).append(row)
    summaries = {carrier: summarise_carrier(items) for carrier, items in sorted(by_carrier.items())}
    preview = {
        'rows_in_file': rows_in_file,
        'rows_for_client': len(rows),
        'carriers': [
            {
                'carrier': carrier, 'rows': item['rows'], 'zones': len(item['zones']),
                'blank_zone_rows': item['blank_zone_rows'],
                'duplicates': item['duplicates_case_sensitive'],
                'ambiguous': item['ambiguous_suburb_state'],
                'conflicts': item['conflicts_with_postcode'][:MAX_LISTED],
                'conflict_count': len(item['conflicts_with_postcode']),
            }
            for carrier, item in summaries.items()
        ],
        'carriers_missing': sorted(client_carriers(client) - set(summaries)),
        'compared_with_file_id': None,
    }
    active = _active_version(client, 'ZONES')
    if active:
        current = {tuple(row[key] for key in _ZONE_KEYS) for row in rows}
        previous = set(active.zone_source_rows.values_list(*_ZONE_KEYS))
        preview.update({
            'compared_with_file_id': active.pk,
            'rows_added': len(current - previous),
            'rows_removed': len(previous - current),
        })
    return preview


def read_source_bytes(external_file):
    if not external_file.uploaded_file:
        raise RateSourceError('The stored source file is not available.')
    with external_file.uploaded_file.open('rb') as handle:
        content = handle.read()
    if external_file.sha256 and calculate_sha256(content) != external_file.sha256:
        raise RateSourceError('The stored source file does not match its recorded hash.')
    return content


def _require_supported(external_file):
    if external_file.file_type not in RATE_SOURCE_TYPES:
        raise RateSourceError('Only RATES and ZONES sources can use this operation.')
    if external_file.client.code.upper() != SUPPORTED_CLIENT:
        raise RateSourceError(f'Only {SUPPORTED_CLIENT} is supported.')


def prepare_source(external_file, *, actor=None, request=None):
    """Validate a stored source and record its load preview. Saves no source rows."""
    _require_supported(external_file)
    if external_file.status not in {'UPLOADED', 'VALIDATED', 'VALIDATION_FAILED'}:
        raise RateSourceError('This source cannot be prepared in its current status.')
    try:
        content = read_source_bytes(external_file)
        if external_file.file_type == 'RATES':
            summary = review_ratecard(content, external_file.original_filename)
            summary['load_preview'] = rate_preview(content, external_file.original_filename,
                                                   external_file.client)
        else:
            summary = {
                'validation_scope': 'STRUCTURE_ONLY', 'operational_tables_updated': False,
                'activation_allowed': False, 'quotes_use_this_file': False,
                'load_preview': zone_preview(content, external_file.client),
            }
    except SourceImportError as exc:
        external_file.status = 'VALIDATION_FAILED'
        external_file.error_message = str(exc)
        external_file.validation_summary = {
            'validation_scope': 'STRUCTURE_ONLY', 'operational_tables_updated': False,
            'activation_allowed': False, 'quotes_use_this_file': False,
        }
    else:
        external_file.status = 'VALIDATED'
        external_file.error_message = ''
        external_file.validation_summary = summary
    external_file.validated_by = actor if getattr(actor, 'is_authenticated', False) else None
    external_file.validated_at = timezone.now()
    external_file.save(update_fields=['status', 'error_message', 'validation_summary',
                                      'validated_by', 'validated_at'])
    create_audit_event(
        event_type='RATE_SOURCE_PREPARED',
        message=f'{external_file.file_type} source reviewed for {external_file.client.code}; nothing loaded.',
        actor=actor, client=external_file.client, external_file=external_file,
        metadata={'sha256': external_file.sha256, 'status': external_file.status,
                  'operational_tables_updated': False},
        request=request,
    )
    return external_file.validation_summary


def _store_rows(external_file, content):
    if external_file.file_type == 'RATES':
        lines, _ = parse_rate_lines(content, external_file.original_filename)
        RateCardLine.objects.bulk_create(
            [RateCardLine(external_file=external_file, **line) for line in lines],
            batch_size=BATCH_SIZE,
        )
        return len(lines)
    _, _, rows = parse_zone_rows(content, external_file.client)
    ZoneSourceRow.objects.bulk_create(
        [ZoneSourceRow(external_file=external_file, source_row=row['_row_number'],
                       **{key: row[key] for key in _ZONE_KEYS}) for row in rows],
        batch_size=BATCH_SIZE,
    )
    return len(rows)


def _delete_rows(external_file):
    external_file.rate_card_lines.all().delete()
    external_file.zone_source_rows.all().delete()


def _purge_old_rows(client, file_type):
    """Keep source rows for the newest versions; the original files always stay."""
    versions = (ExternalDataFile.objects.filter(client=client, file_type=file_type, activated_at__isnull=False)
                .exclude(status='ROLLED_BACK').order_by('-activated_at', '-pk'))
    purged = 0
    for version in versions[RETAINED_VERSIONS:]:
        if version.rate_card_lines.exists() or version.zone_source_rows.exists():
            _delete_rows(version)
            purged += 1
    return purged


def load_source(external_file, *, actor=None, request=None):
    """Store a validated version and mark it as the version in use for comparison."""
    _require_supported(external_file)
    with transaction.atomic():
        locked = ExternalDataFile.objects.select_for_update().get(pk=external_file.pk)
        if locked.status != 'VALIDATED':
            raise RateSourceError('Review the source before loading it.')
        previous = (ExternalDataFile.objects.select_for_update()
                    .filter(client=locked.client, file_type=locked.file_type, status='ACTIVE')
                    .exclude(pk=locked.pk).order_by('-activated_at', '-pk').first())
        if previous and previous.sha256 == locked.sha256:
            raise RateSourceError(f'This content is already loaded as source #{previous.pk}.')
        rows = _store_rows(locked, read_source_bytes(locked))
        if not rows:
            raise RateSourceError('The source has no rows to load.')
        if previous:
            previous.status = 'ARCHIVED'
            previous.save(update_fields=['status'])
        now = timezone.now()
        user = actor if getattr(actor, 'is_authenticated', False) else None
        summary = {'rows_loaded': rows, 'previous_active_file_id': previous.pk if previous else None,
                   'quotes_changed': False}
        locked.status = 'ACTIVE'
        locked.previous_active_file = previous
        locked.activated_by = user
        locked.activated_at = now
        locked.imported_by = user
        locked.last_imported_at = now
        locked.import_summary = summary
        locked.error_message = ''
        locked.save(update_fields=['status', 'previous_active_file', 'activated_by', 'activated_at',
                                   'imported_by', 'last_imported_at', 'import_summary', 'error_message'])
        summary['versions_purged'] = _purge_old_rows(locked.client, locked.file_type)
        create_audit_event(
            event_type='RATE_SOURCE_LOADED',
            message=f'{locked.file_type} source loaded for {locked.client.code}; quotes unchanged.',
            actor=actor, client=locked.client, external_file=locked,
            metadata={**summary, 'sha256': locked.sha256}, request=request,
        )
    return summary


def rollback_source(external_file, *, reason, actor=None, request=None):
    """Return to the previous version. Its rows must still be stored."""
    _require_supported(external_file)
    if not reason.strip():
        raise RateSourceError('A rollback reason is required.')
    with transaction.atomic():
        locked = ExternalDataFile.objects.select_for_update().get(pk=external_file.pk)
        if locked.status != 'ACTIVE':
            raise RateSourceError('Only the version in use can be rolled back.')
        previous = locked.previous_active_file
        if previous and not (previous.rate_card_lines.exists() or previous.zone_source_rows.exists()):
            raise RateSourceError(f'Source #{previous.pk} no longer has stored rows.')
        _delete_rows(locked)
        now = timezone.now()
        locked.status = 'ROLLED_BACK'
        locked.rolled_back_by = actor if getattr(actor, 'is_authenticated', False) else None
        locked.rolled_back_at = now
        locked.import_summary = {**(locked.import_summary or {}), 'rollback_reason': reason.strip(),
                                 'rolled_back_at': now.isoformat()}
        locked.save(update_fields=['status', 'rolled_back_by', 'rolled_back_at', 'import_summary'])
        if previous:
            ExternalDataFile.objects.filter(pk=previous.pk).update(status='ACTIVE')
        summary = {'restored_file_id': previous.pk if previous else None, 'reason': reason.strip(),
                   'quotes_changed': False}
        create_audit_event(
            event_type='RATE_SOURCE_ROLLED_BACK',
            message=f'{locked.file_type} source rolled back for {locked.client.code}; quotes unchanged.',
            actor=actor, client=locked.client, external_file=locked, severity='WARNING',
            metadata=summary, request=request,
        )
    return summary
