"""Read-only validation of the native zones.csv export; no database access."""
import csv
import hashlib
import io
from collections import Counter, defaultdict

from apps.imports.services.xlsx_reader import SourceImportError

MAX_BYTES = 64 * 1024 * 1024
COLUMNS = ('index', 'index2', 'carrier', 'suburb', 'state', 'postcode', 'zone', 'subzone', 'area')


def _decode(content):
    try:
        return content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return content.decode('latin-1')


def read_zones(content):
    """Return (sha256, rows). Postcodes stay text so leading zeros survive."""
    if not content or len(content) > MAX_BYTES:
        raise SourceImportError('Select a non-empty zones.csv no larger than 64 MiB.')
    reader = csv.reader(io.StringIO(_decode(content), newline=''))
    headers = [cell.strip().lower() for cell in next(reader, [])]
    if tuple(headers) != COLUMNS:
        raise SourceImportError(f'zones.csv columns must be exactly {", ".join(COLUMNS)}.')
    rows = []
    for number, cells in enumerate(reader, start=2):
        if len(cells) != len(COLUMNS):
            raise SourceImportError(f'zones.csv line {number}: expected {len(COLUMNS)} columns.')
        row = {name: value.strip() for name, value in zip(COLUMNS, cells)}
        row['_row_number'] = number
        rows.append(row)
    return hashlib.sha256(content).hexdigest(), rows


def summarise_carrier(rows):
    """Quality figures for one carrier; conflicts are reported, never resolved."""
    exact = Counter()
    insensitive = Counter()
    by_suburb = defaultdict(set)
    by_postcode = defaultdict(set)
    conflict_rows = defaultdict(list)
    for row in rows:
        exact[(row['suburb'], row['state'], row['postcode'])] += 1
        suburb, state = row['suburb'].upper(), row['state'].upper()
        insensitive[(suburb, state, row['postcode'])] += 1
        by_suburb[(suburb, state)].add(row['zone'])
        postcode_key = (suburb, state, row['postcode'])
        by_postcode[postcode_key].add(row['zone'])
        conflict_rows[postcode_key].append(row)
    conflicts = sorted(key for key, zones in by_postcode.items() if len(zones) > 1)
    conflict_details = []
    for key in conflicts:
        matching = conflict_rows[key]
        conflict_details.append({
            'suburb': key[0],
            'state': key[1],
            'postcode': key[2],
            'zones': sorted({row['zone'] for row in matching}),
            'rows': sorted(row['_row_number'] for row in matching),
        })
    return {
        'rows': len(rows),
        'zones': sorted({row['zone'] for row in rows if row['zone']}),
        'blank_zone_rows': sum(1 for row in rows if not row['zone']),
        'duplicates_case_sensitive': sum(count - 1 for count in exact.values()),
        'duplicates_case_insensitive': sum(count - 1 for count in insensitive.values()),
        'ambiguous_suburb_state': sum(1 for zones in by_suburb.values() if len(zones) > 1),
        'conflicts_with_postcode': [list(key) for key in conflicts],
        'conflict_details': conflict_details,
    }
