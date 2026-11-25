"""Verified, explicit persistence of global import exceptions (no Product Apply)."""
import csv
import hashlib
import io
import json
import re


class RegistryInputError(ValueError):
    """Reject unverified or inconsistent import evidence before database writes."""


def _sha256(blob):
    return hashlib.sha256(blob).hexdigest().upper()


def _required_digest(value, field):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise RegistryInputError(f"Invalid {field} SHA-256 in reconciliation report")
    return value.upper()


def inspect_exception_evidence(report_bytes, csv_bytes):
    """Validate entire report/CSV pair; never mutate source identifiers."""
    try:
        report = json.loads(report_bytes.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise RegistryInputError('Invalid reconciliation REPORT.json') from exc
    if not isinstance(report, dict):
        raise RegistryInputError('REPORT.json must contain one object')
    if report.get('scope') != 'READ_ONLY_CUSTOMER_PRODUCT_STOCK_RECONCILIATION':
        raise RegistryInputError('Unsupported reconciliation report scope')
    if report.get('status') not in ('REVIEW_REQUIRED', 'PASS'):
        raise RegistryInputError('The source reconciliation has not completed')
    if report.get('production_access') != 'NONE':
        raise RegistryInputError('Cannot import evidence from a production-writing run')
    if report.get('operational_tables_updated') is not False or report.get('calculator_clients_created') != 0:
        raise RegistryInputError('Report claims operational changes; refusing evidence')
    stock_sha = _required_digest(report.get('stock_sha256'), 'Stock source')
    product_sha = _required_digest(report.get('product_sha256'), 'Product source')
    expected_csv = _required_digest(report.get('stock_exception_csv_sha256'), 'Exception CSV')
    if _sha256(csv_bytes) != expected_csv:
        raise RegistryInputError('Exception CSV checksum differs from REPORT.json')
    try:
        reader = csv.DictReader(io.StringIO(csv_bytes.decode('utf-8-sig'), newline=''))
        if reader.fieldnames != ['issue', 'customer', 'sku', 'stock_rows']:
            raise RegistryInputError('Exception CSV headers do not match the accepted schema')
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise RegistryInputError('Cannot read exception CSV') from exc
    if not rows or len(rows) != report.get('stock_exception_groups'):
        raise RegistryInputError('Number of CSV groups differs from REPORT.json')
    allowed = {'MISSING_PRODUCT', 'UNKNOWN_CUSTOMER', 'AMBIGUOUS_PRODUCT', 'INVALID_IDENTIFIER'}
    seen = set()
    totals = {key: 0 for key in allowed}
    entries = []
    for row in rows:
        if None in row or any(row[key] is None for key in reader.fieldnames):
            raise RegistryInputError('Malformed exception CSV data row')
        kind, section, sku, count = (row[key] for key in reader.fieldnames)
        if kind not in allowed:
            raise RegistryInputError(f'Unsupported exception kind: {kind!r}')
        if not section or section != section.strip() or len(section) > 100:
            raise RegistryInputError('Invalid source Section identifier')
        if not sku or sku != sku.strip() or len(sku) > 255:
            raise RegistryInputError('Invalid source SKU identifier')
        if not re.fullmatch(r'[0-9]+', count) or int(count) < 1:
            raise RegistryInputError('Invalid Stock row count in exception CSV')
        key = (section, sku, kind)
        if key in seen:
            raise RegistryInputError('Duplicate source Section/SKU/kind exception group')
        seen.add(key)
        totals[kind] += int(count)
        entries.append({'section_code': section, 'sku': sku, 'kind': kind, 'stock_row_count': int(count)})
    expected = {
        'MISSING_PRODUCT': 'stock_missing_product_rows',
        'UNKNOWN_CUSTOMER': 'stock_unknown_customer_rows',
        'AMBIGUOUS_PRODUCT': 'stock_ambiguous_product_rows',
        'INVALID_IDENTIFIER': 'stock_invalid_identifier_rows',
    }
    for kind, report_key in expected.items():
        if totals[kind] != report.get(report_key):
            raise RegistryInputError(f'CSV {kind} counts differ from REPORT.json')
    if sum(totals.values()) + report.get('stock_matched_product_rows', -1) != report.get('stock_rows'):
        raise RegistryInputError('Reconciliation row totals are inconsistent')
    return {'stock_sha256': stock_sha, 'product_sha256': product_sha,
            'csv_sha256': expected_csv, 'entries': entries, 'stock_rows': sum(totals.values()),
            'counts': totals}


def persist_exception_evidence(report_bytes, csv_bytes, *, apply=False):
    """Default to preview; explicit apply adds review rows, never operational products."""
    evidence = inspect_exception_evidence(report_bytes, csv_bytes)
    result = {'groups': len(evidence['entries']), 'stock_rows': evidence['stock_rows'],
              'source_stock_sha256': evidence['stock_sha256'],
              'source_product_sha256': evidence['product_sha256'],
              'preview_only': not apply, 'new_rows': 0, 'existing_rows': 0}
    if not apply:
        return result
    from django.db import transaction
    from apps.imports.models import ImportReconciliationException
    with transaction.atomic():
        for row in evidence['entries']:
            lookup = {
                'source_stock_sha256': evidence['stock_sha256'],
                'source_product_sha256': evidence['product_sha256'],
                'section_code': row['section_code'], 'sku': row['sku'], 'kind': row['kind'],
            }
            obj, created = ImportReconciliationException.objects.get_or_create(
                **lookup, defaults={'stock_row_count': row['stock_row_count'],
                                    'evidence': {'csv_sha256': evidence['csv_sha256']}})
            if not created and obj.stock_row_count != row['stock_row_count']:
                raise RegistryInputError('Existing exception disagrees with the immutable source snapshot')
            result['new_rows' if created else 'existing_rows'] += 1
    return result
