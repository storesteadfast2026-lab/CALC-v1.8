"""Export and safely re-import physical Product issues as correction drafts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from apps.clients.models import Customer
from apps.imports.models import ProductCorrectionRound, ProductMaster, ProductSourceRow
from apps.imports.services.audit import create_audit_event
from apps.imports.services.product_dimensions import (
    cubic_dimension_confirmation_factor,
    has_large_cubic_dimension_difference,
)
from apps.imports.services.product_reconciliation_apply import new_product_values
from apps.imports.services.product_reconciliation_workspace import build_workspace
from apps.imports.services.xlsx_reader import SourceImportError
from apps.products.models import Product


REPORT_VERSION = '1'
SHEET_NAME = 'Product issues'
HEADER_ROW = 8
REPORT_HEADERS = (
    'Report version', 'Source ID', 'Source SHA256', 'Client', 'Scope',
    'Issue code', 'Issue', 'SKU', 'Name', 'Description', 'Source row',
    'Product ID',
    'Product Master length (m)', 'Product Master width (m)',
    'Product Master height (m)', 'Product Master weight (kg)',
    'Product Master cubic (m3)',
    'App length (m)', 'App width (m)', 'App height (m)',
    'App weight (kg)', 'App cubic (m3)',
    'Ready to import', 'Corrected length (m)', 'Corrected width (m)',
    'Corrected height (m)', 'Corrected weight (kg)', 'Corrected cubic (m3)',
    'Correction notes',
)

ISSUE_MESSAGES = {
    'UNKNOWN_DIMENSIONS': (
        'Dimensions are unavailable. Confirm all three dimensions before quoting.'
    ),
    'INCOMPLETE_PHYSICAL_DATA': (
        'Weight or cubic volume is unavailable. Confirm the missing physical data.'
    ),
    'LARGE_DIMENSION_DIFFERENCE': (
        'Dimensions and cubic volume differ substantially and require confirmation.'
    ),
}


class ProductIssueReportError(Exception):
    pass


def _product_master_workspace(source):
    """Use the complete current Product Master when it matches this source exactly."""
    master = ProductMaster.objects.filter(
        status='VALIDATED', sha256=source.sha256,
    ).order_by('-uploaded_at', '-pk').first()
    customer = Customer.objects.filter(
        linked_client=source.client, is_special=False,
    ).first()
    if not master or not customer:
        return build_workspace(source)[0]
    try:
        # Import locally: product_master also uses the reconciliation services.
        from apps.imports.services.product_master import reconciliation_rows_for_customer

        source_rows, invalid = reconciliation_rows_for_customer(
            master, customer, include_invalid=True,
        )
    except SourceImportError as exc:
        raise ProductIssueReportError(
            f'The current Product Master could not be verified ({exc}).'
        ) from exc
    if invalid:
        raise ProductIssueReportError(
            'The current Product Master contains invalid customer rows that require review.'
        )
    return build_workspace(
        source, source_rows=source_rows, pending_rejected=0,
        include_decisions=False,
    )[0]


def _stage_product_master_row(source, row):
    """Copy one verified Product Master row into staging for the correction draft."""
    existing = ProductSourceRow.objects.filter(
        external_file=source,
        source_row_number=row['source_row_number'],
    ).first()
    if existing:
        return existing
    master_row = row.get('source')
    if not master_row:
        raise ProductIssueReportError(f'{row["sku"]}: Product Master row is unavailable.')
    values = {
        field.attname: getattr(master_row, field.attname)
        for field in ProductSourceRow._meta.concrete_fields
        if field.attname not in {'id', 'external_file_id', 'created_at'}
    }
    return ProductSourceRow.objects.create(external_file=source, **values)


def _issue_code(values, confirmation_factor):
    if any(values.get(field) is None or values[field] <= 0
           for field in ('length_m', 'width_m', 'height_m')):
        return 'UNKNOWN_DIMENSIONS'
    if any(values.get(field) is None or values[field] <= 0
           for field in ('weight_kg', 'cubic_m3')):
        return 'INCOMPLETE_PHYSICAL_DATA'
    if has_large_cubic_dimension_difference(
        values.get('length_m'), values.get('width_m'), values.get('height_m'),
        values.get('cubic_m3'), confirmation_factor,
    ):
        return 'LARGE_DIMENSION_DIFFERENCE'
    return None


def build_product_issue_rows(source):
    """Return current problem rows from this Product Master reconciliation only."""
    rows = _product_master_workspace(source)
    confirmation_factor = cubic_dimension_confirmation_factor(source.client)
    report_rows = []
    for row in rows:
        product = row.get('product')
        if row['status'] == 'SOURCE_ONLY':
            scope = 'SOURCE_ONLY'
            values = row['source_values']
        elif product and product.active:
            scope = 'ACTIVE'
            values = row['operational_values']
        else:
            continue
        issue_code = _issue_code(values, confirmation_factor)
        if not issue_code:
            continue
        source_values = row['source_values']
        operational_values = row['operational_values'] if product else {}
        correction_defaults = source_values
        report_rows.append({
            'report_version': REPORT_VERSION,
            'source_id': source.pk,
            'source_sha256': source.sha256 or '',
            'client': source.client.code,
            'scope': scope,
            'issue_code': issue_code,
            'issue': ISSUE_MESSAGES[issue_code],
            'sku': row['sku'],
            'name': source_values.get('name') or operational_values.get('name') or '',
            'description': (
                source_values.get('description') or operational_values.get('description') or ''
            ),
            'source_row': row.get('source_row_number'),
            'product_id': product.pk if product else None,
            'source_length_m': source_values.get('length_m'),
            'source_width_m': source_values.get('width_m'),
            'source_height_m': source_values.get('height_m'),
            'source_weight_kg': source_values.get('weight_kg'),
            'source_cubic_m3': source_values.get('cubic_m3'),
            'app_length_m': operational_values.get('length_m'),
            'app_width_m': operational_values.get('width_m'),
            'app_height_m': operational_values.get('height_m'),
            'app_weight_kg': operational_values.get('weight_kg'),
            'app_cubic_m3': operational_values.get('cubic_m3'),
            'ready': '',
            'corrected_length_m': correction_defaults.get('length_m'),
            'corrected_width_m': correction_defaults.get('width_m'),
            'corrected_height_m': correction_defaults.get('height_m'),
            'corrected_weight_kg': correction_defaults.get('weight_kg'),
            'corrected_cubic_m3': correction_defaults.get('cubic_m3'),
            'notes': '',
        })
    return sorted(report_rows, key=lambda item: item['sku'])


def _report_values(item):
    return (
        item['report_version'], item['source_id'], item['source_sha256'], item['client'],
        item['scope'], item['issue_code'], item['issue'], item['sku'], item['name'],
        item['description'], item['source_row'], item['product_id'],
        item['source_length_m'], item['source_width_m'], item['source_height_m'],
        item['source_weight_kg'], item['source_cubic_m3'],
        item['app_length_m'], item['app_width_m'], item['app_height_m'],
        item['app_weight_kg'], item['app_cubic_m3'], item['ready'],
        item['corrected_length_m'], item['corrected_width_m'],
        item['corrected_height_m'], item['corrected_weight_kg'],
        item['corrected_cubic_m3'], item['notes'],
    )


def export_product_issue_workbook(source):
    """Build the operational report downloaded from Django."""
    report_rows = build_product_issue_rows(source)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = f'A{HEADER_ROW + 1}'

    last_column = sheet.cell(row=1, column=len(REPORT_HEADERS)).column_letter
    instructions = (
        'Product physical-data issue report',
        f'Source: {source.original_filename} (ID {source.pk}) · Client: {source.client.code}',
        'The Product Master values below are the only source reference. Do not use another file.',
        'Enter reviewed positive values in the amber columns, write a correction note, and set Ready to import to YES.',
        'Uploading this workbook saves correction drafts only. Products change only after Django Preview and explicit Apply.',
        'If any value remains doubtful, leave the row unready and contact Steadfast Contact Center or Customer Service.',
    )
    for row_number, value in enumerate(instructions, start=1):
        sheet.merge_cells(start_row=row_number, start_column=1,
                          end_row=row_number, end_column=len(REPORT_HEADERS))
        cell = sheet.cell(row=row_number, column=1, value=value)
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        if row_number == 1:
            cell.font = Font(size=16, bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='17365D')
        elif row_number == 2:
            cell.font = Font(bold=True, color='17365D')

    for column, header in enumerate(REPORT_HEADERS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=column, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1F4E78')
        cell.alignment = Alignment(wrap_text=True, vertical='center')

    for row_number, item in enumerate(report_rows, start=HEADER_ROW + 1):
        for column, value in enumerate(_report_values(item), start=1):
            sheet.cell(row=row_number, column=column, value=value)
        for column in range(23, 30):
            sheet.cell(row=row_number, column=column).fill = PatternFill(
                'solid', fgColor='FFF2CC'
            )
        for column in range(13, 29):
            sheet.cell(row=row_number, column=column).number_format = '0.000000'
        sheet.cell(row=row_number, column=29).alignment = Alignment(wrap_text=True)

    last_row = HEADER_ROW + max(len(report_rows), 1)
    if report_rows:
        table = Table(displayName='ProductIssueReport', ref=f'A{HEADER_ROW}:{last_column}{last_row}')
        table.tableStyleInfo = TableStyleInfo(
            name='TableStyleMedium2', showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        sheet.add_table(table)
        ready_validation = DataValidation(type='list', formula1='"YES"', allow_blank=True)
        ready_validation.error = 'Choose YES or leave the cell blank.'
        ready_validation.errorTitle = 'Invalid import status'
        sheet.add_data_validation(ready_validation)
        ready_validation.add(f'W{HEADER_ROW + 1}:W{last_row}')
        sheet.conditional_formatting.add(
            f'W{HEADER_ROW + 1}:W{last_row}',
            FormulaRule(formula=[f'=$W{HEADER_ROW + 1}="YES"'],
                        fill=PatternFill('solid', fgColor='C6EFCE')),
        )

    widths = {
        'E': 14, 'F': 28, 'G': 54, 'H': 18, 'I': 28, 'J': 42,
        'K': 12, 'M': 20, 'N': 20, 'O': 20, 'P': 22, 'Q': 21,
        'R': 16, 'S': 16, 'T': 16, 'U': 18, 'V': 17, 'W': 18,
        'X': 20, 'Y': 20, 'Z': 20, 'AA': 22, 'AB': 21, 'AC': 48,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    for column in ('A', 'B', 'C', 'D', 'L'):
        sheet.column_dimensions[column].hidden = True
    sheet.auto_filter.ref = f'A{HEADER_ROW}:{last_column}{last_row}'
    sheet.row_dimensions[1].height = 26
    sheet.row_dimensions[HEADER_ROW].height = 36

    output = BytesIO()
    workbook.save(output)
    return output.getvalue(), report_rows


def _cell_text(value):
    return '' if value is None else str(value).strip()


def _decimal(value, *, sku, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProductIssueReportError(f'{sku}: enter a valid {label}.') from exc
    if not result.is_finite() or result <= 0:
        raise ProductIssueReportError(f'{sku}: {label} must be greater than zero.')
    return result


def preview_product_issue_workbook(source, uploaded_file):
    """Validate an edited report and return rows eligible to become drafts."""
    try:
        workbook = load_workbook(uploaded_file, read_only=True, data_only=False)
    except Exception as exc:
        raise ProductIssueReportError('Upload a valid .xlsx Product issue report.') from exc
    if SHEET_NAME not in workbook.sheetnames:
        raise ProductIssueReportError(f'The workbook must contain the {SHEET_NAME} sheet.')
    sheet = workbook[SHEET_NAME]
    headers = tuple(sheet.cell(HEADER_ROW, column).value for column in range(1, len(REPORT_HEADERS) + 1))
    if headers != REPORT_HEADERS:
        raise ProductIssueReportError('The report columns changed. Export a fresh report and edit only amber fields.')

    current_rows = {item['sku']: item for item in build_product_issue_rows(source)}
    imported = {}
    for values in sheet.iter_rows(min_row=HEADER_ROW + 1, max_col=len(REPORT_HEADERS), values_only=True):
        if not any(value not in (None, '') for value in values):
            continue
        sku = _cell_text(values[7])
        if not sku:
            raise ProductIssueReportError('Every populated report row must retain its SKU.')
        if sku in imported:
            raise ProductIssueReportError(f'{sku}: duplicate report row.')
        imported[sku] = values
    if set(imported) != set(current_rows):
        raise ProductIssueReportError(
            'The problem Product list changed. Export a fresh report before importing corrections.'
        )

    items, errors = [], []
    factor = cubic_dimension_confirmation_factor(source.client)
    workspace = {row['sku']: row for row in _product_master_workspace(source)}
    for sku, values in imported.items():
        current = current_rows[sku]
        immutable = (
            (_cell_text(values[0]), current['report_version'], 'report version'),
            (_cell_text(values[1]), str(current['source_id']), 'Source ID'),
            (_cell_text(values[2]), current['source_sha256'], 'Source SHA256'),
            (_cell_text(values[3]), current['client'], 'client'),
            (_cell_text(values[4]), current['scope'], 'scope'),
            (_cell_text(values[5]), current['issue_code'], 'issue code'),
            (_cell_text(values[10]), _cell_text(current['source_row']), 'Source row'),
            (_cell_text(values[11]), _cell_text(current['product_id']), 'Product ID'),
        )
        mismatch = next((label for actual, expected, label in immutable if actual != expected), None)
        if mismatch:
            errors.append(f'{sku}: immutable {mismatch} changed.')
            continue
        ready = _cell_text(values[22]).upper()
        if ready not in {'', 'YES'}:
            errors.append(f'{sku}: Ready to import must be YES or blank.')
            continue
        if not ready:
            continue
        notes = _cell_text(values[28])
        if not notes:
            errors.append(f'{sku}: enter correction notes before marking the row ready.')
            continue
        try:
            corrected = {
                'length_m': _decimal(values[23], sku=sku, label='corrected length'),
                'width_m': _decimal(values[24], sku=sku, label='corrected width'),
                'height_m': _decimal(values[25], sku=sku, label='corrected height'),
                'weight_kg': _decimal(values[26], sku=sku, label='corrected weight'),
                'cubic_m3': _decimal(values[27], sku=sku, label='corrected cubic volume'),
            }
            if _issue_code(corrected, factor):
                raise ProductIssueReportError(
                    f'{sku}: corrected values still require Contact Center confirmation.'
                )
            # Enforce the same decimal precision used by operational Product fields.
            row = workspace[sku]
            source_values = row['source_values']
            operational = row['operational_values']
            proposed = {
                'name': source_values.get('name') if current['scope'] == 'SOURCE_ONLY' else operational.get('name'),
                'description': source_values.get('description') if current['scope'] == 'SOURCE_ONLY' else operational.get('description'),
                **corrected,
                'freight_type': source_values.get('freight_type') if current['scope'] == 'SOURCE_ONLY' else operational.get('freight_type'),
            }
            new_product_values(proposed)
            Product(client=source.client, sku=sku, active=True,
                    source_row=current['source_row'], **new_product_values(proposed)).full_clean(
                        validate_unique=False
                    )
        except ProductIssueReportError as exc:
            errors.append(str(exc))
            continue
        except Exception as exc:
            errors.append(f'{sku}: corrected values are not valid for a Product ({exc}).')
            continue
        items.append({
            'sku': sku, 'scope': current['scope'],
            'custom_values': {key: str(value) for key, value in corrected.items()},
            'notes': notes,
        })
    if not items and not errors:
        errors.append('No row is marked YES for import.')
    return {'items': items, 'errors': errors, 'can_save': bool(items) and not errors}


@transaction.atomic
def save_product_issue_report_drafts(round_id, *, items, actor=None, request=None):
    """Revalidate imported rows and save them into an existing draft round."""
    from apps.imports.services.product_correction_rounds import (
        CorrectionRoundError,
        _save_decision_for_row,
    )
    from apps.imports.services.product_reconciliation_workspace import has_active_product_apply

    round_obj = ProductCorrectionRound.objects.select_for_update().select_related(
        'external_file', 'external_file__client'
    ).get(pk=round_id)
    if round_obj.status != 'DRAFT' or not has_active_product_apply(round_obj.external_file):
        raise ProductIssueReportError('This correction round is no longer editable.')
    current_report = {row['sku']: row for row in build_product_issue_rows(round_obj.external_file)}
    workspace = {
        row['sku']: row for row in _product_master_workspace(round_obj.external_file)
    }
    saved = []
    for item in items:
        sku = item.get('sku')
        current = current_report.get(sku)
        row = workspace.get(sku)
        if not current or not row or current['scope'] != item.get('scope'):
            raise ProductIssueReportError(f'{sku}: Product issue changed after Preview.')
        if current['scope'] == 'SOURCE_ONLY':
            if not ProductSourceRow.objects.filter(
                external_file=round_obj.external_file,
                product_code_normalized=sku,
            ).exists():
                _stage_product_master_row(round_obj.external_file, row)
                row = {
                    candidate['sku']: candidate
                    for candidate in build_workspace(round_obj.external_file)[0]
                }.get(sku)
                if not row:
                    raise ProductIssueReportError(
                        f'{sku}: Product Master row could not be prepared for the draft.'
                    )
            decisions = {
                'name': 'SOURCE', 'description': 'SOURCE', 'dimensions': 'CUSTOM',
                'weight': 'CUSTOM', 'cubic': 'CUSTOM', 'freight_type': 'SOURCE',
            }
        else:
            decisions = {
                'name': 'NO_CHANGE', 'description': 'NO_CHANGE', 'dimensions': 'CUSTOM',
                'weight': 'CUSTOM', 'cubic': 'CUSTOM', 'freight_type': 'NO_CHANGE',
            }
        try:
            saved.append(_save_decision_for_row(
                round_obj, row=row, field_decisions=decisions,
                custom_values=item.get('custom_values'), notes=item.get('notes'),
                confirm_source_dimensions=True, actor=actor, request=request,
            ))
        except CorrectionRoundError as exc:
            raise ProductIssueReportError(str(exc)) from exc
    create_audit_event(
        event_type='PRODUCT_ISSUE_REPORT_DRAFTS_SAVED',
        message=f'{len(saved)} Product issue report correction draft(s) saved.',
        actor=actor, client=round_obj.external_file.client,
        external_file=round_obj.external_file,
        metadata={
            'round_id': round_obj.pk, 'skus': [decision.sku for decision in saved],
            'operational_tables_updated': False,
        },
        request=request,
    )
    return saved
