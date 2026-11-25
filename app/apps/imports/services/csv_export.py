def safe_csv_cell(value):
    """Return source text that cannot become a spreadsheet formula."""
    text = str(value if value is not None else '')
    return f"'{text}" if text[:1] in '=+-@' else text
