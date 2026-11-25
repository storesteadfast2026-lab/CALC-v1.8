"""Build review-only evidence for blocked STH Product Master rows.

This script reads source files only. It does not initialise Django or access the
database. Output is a JSON intermediate used to build the review workbook.
"""

import json
import hashlib
from decimal import Decimal
from pathlib import Path

import openpyxl

from apps.imports.services.product_file_adapters import read_product_file
from apps.imports.services.product_source import (
    PRODUCT_ALIASES,
    PRODUCT_CSV_COLUMN_COUNT,
    PRODUCT_REQUIRED_FIELDS,
)
from apps.imports.services.xlsx_reader import normalize_product_sku


ROOT = Path("/app")
CURRENT_PATH = ROOT / "uploaded_data/product_master/2026/11/db724e42bf2c43aeb2a05103f8c5460b_products.xls"
HISTORICAL_PATH = ROOT / "uploaded_data/reference/STH_LIVE_BASELINE_20260709_152102.xlsx"
OUTPUT_PATH = ROOT / "reports/product_dimension_review/shortlist_data.json"


def dec(value):
    return Decimal(str(value or 0))


source = read_product_file(
    CURRENT_PATH.read_bytes(),
    CURRENT_PATH.name,
    aliases=PRODUCT_ALIASES,
    required_fields=PRODUCT_REQUIRED_FIELDS,
    expected_csv_column_count=PRODUCT_CSV_COLUMN_COUNT,
)
current_rows = [
    row for row in source.records
    if str(row.get("customer") or "").strip().upper() == "STH"
]
blocked_rows = [
    row for row in current_rows
    if any(dec(row.get(field)) <= 0 for field in ("length", "width", "height"))
]

workbook = openpyxl.load_workbook(HISTORICAL_PATH, read_only=True, data_only=True)
sheet = workbook["SKUs"]
headers = [str(value or "").strip() for value in next(sheet.iter_rows(values_only=True))]
index = {name: position for position, name in enumerate(headers) if name}
historical = {}
for row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
    sku = normalize_product_sku(values[index["SKU"]])
    if not sku:
        continue
    historical[sku] = {
        "historical_row": row_number,
        "historical_length_m": values[index["Length (m)"]],
        "historical_width_m": values[index["Width (m)"]],
        "historical_height_m": values[index["Height (m)"]],
        "historical_weight_kg": values[index["Weight"]],
        "historical_cubic_m3": values[index["Cubic"]],
        "historical_type": values[index["Type"]],
        "combo_flag": values[index["Combo? (>1 error)"]],
        "m3error_flag": values[index["M3ERROR"]],
        "kgerror_flag": values[index["KGERROR"]],
        "historical_fix": values[index["FIX"]],
    }

positive_historical = []
for current in blocked_rows:
    sku = normalize_product_sku(current.get("code"))
    old = historical.get(sku)
    if not old:
        continue
    if any(dec(old[field]) <= 0 for field in (
        "historical_length_m", "historical_width_m", "historical_height_m"
    )):
        continue
    positive_historical.append((current, old))


def counts(weight_tolerance, cubic_tolerance):
    selected = []
    for current, old in positive_historical:
        weight_difference = abs(dec(current.get("weight")) - dec(old["historical_weight_kg"]))
        cubic_difference = abs(dec(current.get("cubic")) - dec(old["historical_cubic_m3"]))
        flags_clear = not old["m3error_flag"] and not old["kgerror_flag"]
        if weight_difference <= weight_tolerance and cubic_difference <= cubic_tolerance and flags_clear:
            selected.append((current, old, weight_difference, cubic_difference))
    return selected


# The retained handoff states 52 internally consistent candidates. Test only
# explicit decimal precision boundaries present in the sources, and fail unless
# exactly one boundary reproduces that retained control total.
tolerance_candidates = [
    (Decimal("0"), Decimal("0")),
    (Decimal("0.001"), Decimal("0.001")),
    (Decimal("0.01"), Decimal("0.001")),
    (Decimal("0.01"), Decimal("0.01")),
    (Decimal("0.1"), Decimal("0.001")),
    (Decimal("0.1"), Decimal("0.01")),
    (Decimal("1"), Decimal("0.001")),
    (Decimal("1"), Decimal("0.01")),
]
matches = [(w, c, counts(w, c)) for w, c in tolerance_candidates if len(counts(w, c)) == 52]
match_sku_sets = {
    tuple(normalize_product_sku(current.get("code")) for current, _old, _wd, _cd in rows)
    for _w, _c, rows in matches
}
if not matches or len(match_sku_sets) != 1:
    raise RuntimeError(
        "Could not reproduce one stable 52-row shortlist at source-precision tolerances: "
        + repr([(str(w), str(c), len(counts(w, c))) for w, c in tolerance_candidates])
    )
# Use the strictest source-precision boundary that reproduces the retained
# control total. Wider tested weight tolerances identify the same 52 SKUs.
weight_tolerance, cubic_tolerance, selected = matches[0]

rows = []
for current, old, weight_difference, cubic_difference in selected:
    rows.append({
        "sku": normalize_product_sku(current.get("code")),
        "current_row": current["_row_number"],
        "name": current.get("name") or "",
        "description": current.get("description") or "",
        "category": current.get("category") or "",
        "current_length_m": dec(current.get("length")) / Decimal("1000"),
        "current_width_m": dec(current.get("width")) / Decimal("1000"),
        "current_height_m": dec(current.get("height")) / Decimal("1000"),
        "current_weight_kg": dec(current.get("weight")),
        "current_cubic_m3": dec(current.get("cubic")),
        "current_quantity": dec(current.get("quantity")),
        "current_pallet": dec(current.get("pallet")),
        "current_status": current.get("status") or "",
        "current_comment": current.get("comment") or "",
        **old,
        "weight_difference_kg": weight_difference,
        "cubic_difference_m3": cubic_difference,
        "blocking_reason": "New Products require positive dimensions.",
        "approval_decision": "Pending",
        "approved_length_m": None,
        "approved_width_m": None,
        "approved_height_m": None,
        "approval_notes": "",
    })

rows.sort(key=lambda item: item["sku"])


def serialise(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


payload = {
    "controls": {
        "current_sth_rows": len(current_rows),
        "blocked_current_rows": len(blocked_rows),
        "blocked_with_positive_historical_dimensions": len(positive_historical),
        "shortlist_rows": len(rows),
        "weight_tolerance_kg": float(weight_tolerance),
        "cubic_tolerance_m3": float(cubic_tolerance),
    },
    "sources": {
        "current": str(CURRENT_PATH.relative_to(ROOT)),
        "current_sha256": hashlib.sha256(CURRENT_PATH.read_bytes()).hexdigest(),
        "historical": str(HISTORICAL_PATH.relative_to(ROOT)),
        "historical_sha256": hashlib.sha256(HISTORICAL_PATH.read_bytes()).hexdigest(),
    },
    "rows": rows,
}
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(json.dumps(payload, indent=2, default=serialise), encoding="utf-8")
print(json.dumps(payload["controls"], indent=2))
