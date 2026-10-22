"""Excel price lists: find the header below the title block, keep every cell as text."""
import pandas as pd

from . import ReaderError, ReadResult, Row

# Words that only appear in the real header row, never in the title block
HEADER_WORDS = {"kunde", "customer", "cust.", "strecke", "lane", "gültig von", "valid from"}

# bronze column -> the header spellings that mean it (lower case). Anything else stays in raw_payload only.
COLUMN_NAMES = {
    "customer": ["kunde", "customer", "cust."],
    "lane": ["strecke", "lane"],
    "charge": ["zuschlag", "charge", "kostenart"],
    "amount": ["betrag", "amount", "preis"],
    "currency": ["währung", "currency", "whg."],
    "valid_from": ["gültig von", "valid from"],
    "valid_to": ["gültig bis", "valid to"],
}


def find_header_row(rows):
    """Index of the first row with at least 2 known header words, or None."""
    for index, row in enumerate(rows):
        hits = sum(1 for cell in row if str(cell).strip().casefold() in HEADER_WORDS)
        if hits >= 2:
            return index
    return None


def read_excel_file(path):
    if path.stat().st_size == 0:
        raise ReaderError("file is empty (0 bytes)")
    try:
        # header=None: we find the header ourselves. dtype=str + na_filter=False: nothing is converted, empty cell = ''
        sheet = pd.read_excel(path, header=None, dtype=str, keep_default_na=False, na_filter=False, engine="openpyxl")
    except Exception as error:   # not a valid workbook, damaged zip, ...
        raise ReaderError(f"cannot open the workbook: {type(error).__name__}: {error}") from error

    grid = sheet.values.tolist()   # grid[i] is sheet row i + 1
    header_index = find_header_row(grid)
    if header_index is None:
        raise ReaderError("no header row found (looked for Kunde / Customer / Cust. / Strecke / Lane / Gültig von / Valid from)")

    names = [str(cell) if str(cell).strip() else f"unnamed_{i + 1}" for i, cell in enumerate(grid[header_index])]
    lowered = {name.strip().casefold(): name for name in names}
    rows = []
    for index in range(header_index + 1, len(grid)):
        values = [str(cell) for cell in grid[index]]
        if not any(value.strip() for value in values):
            continue   # a completely empty row carries no information (its row number stays visible as a gap)
        payload = dict(zip(names, values))
        columns = {}
        for column, spellings in COLUMN_NAMES.items():
            header = next((lowered[s] for s in spellings if s in lowered), None)
            columns[column] = payload[header] if header else None
        rows.append(Row(index + 1, payload, columns))

    warnings = [] if rows else ["the file has a header but no data rows"]
    return ReadResult(names, rows, warnings)
