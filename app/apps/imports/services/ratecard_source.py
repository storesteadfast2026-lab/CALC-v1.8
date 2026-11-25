"""Structural review of native rate-card uploads; never activates tariffs."""
from decimal import Decimal, InvalidOperation
from apps.imports.services.product_file_adapters import read_product_file
from apps.imports.services.xlsx_reader import SourceImportError, value_to_text, normalize_header

MAX_BYTES = 10 * 1024 * 1024
FIELDS = ('master_rate', 'rate_no', 'break', 'item_no', 'code', 'run_rate',
          'name', 'filter_field', 'from', 'greater', 'upto', 'to', 'band',
          'each', 'unit', 'rate', 'basic_charge', 'min_charge', 'cubic',
          'gl_code', 'analysis', 'gst_code', 'rcst', 'rc_name', 'rtst',
          'group1', 'rate_code')


def review_ratecard(content, filename):
    if not content or len(content) > MAX_BYTES:
        raise SourceImportError('Select a non-empty rate-card file no larger than 10 MiB.')
    if not filename.lower().endswith('.xls'):
        raise SourceImportError('This rate-card upload accepts the native .xls export.')
    try:
        result = read_product_file(content, filename, aliases={k: (k,) for k in FIELDS},
                                   required_fields=FIELDS, expected_csv_column_count=len(FIELDS))
    except SourceImportError:
        raise
    except Exception as exc:
        raise SourceImportError('The XLS rate-card file could not be read. Check the export format.') from exc
    headers = [normalize_header(h) for h in result.headers]
    if len(headers) != len(set(headers)):
        raise SourceImportError('The rate-card header contains duplicate column names.')
    masters = set()
    for row in result.records:
        number = row['_row_number']
        for key in ('master_rate', 'rate_no'):
            if not value_to_text(row[key]):
                raise SourceImportError(f'Row {number}: {key} is required.')
        masters.add(value_to_text(row['master_rate']))
        for key in ('rate', 'basic_charge', 'min_charge', 'cubic'):
            text = value_to_text(row[key])
            if not text:
                continue
            try:
                finite = Decimal(text).is_finite()
            except InvalidOperation:
                finite = False
            if not finite:
                raise SourceImportError(f'Row {number}: {key} must contain a finite number.')
    return {
        'review_status': 'REVIEW_REQUIRED', 'validation_scope': 'STRUCTURE_ONLY',
        'worksheet': result.worksheet, 'header_row': result.header_row,
        'headers': result.headers, 'rows_read': len(result.records),
        'master_count': len(masters), 'operational_tables_updated': False,
        'activation_allowed': False, 'quotes_use_this_file': False,
        'warnings': ['The complete catalogue is retained. No STH applicability, rule expressions, '
                     'missing references or full quote semantics are certified by structural validation.'],
    }
