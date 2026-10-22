"""CSV exports: semicolon, Windows-1252, every field kept as text exactly as received."""
import codecs
import io

import pandas as pd

from . import ReaderError, ReadResult, Row

SEPARATOR = ";"


def decode(raw):
    """Windows-1252 first, UTF-8 with BOM as the fallback. A file that starts with a UTF-8 BOM is UTF-8 for sure
    (Windows-1252 would turn the BOM into garbage characters instead of failing)."""
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("utf-8-sig")


def read_csv_file(path):
    raw = path.read_bytes()
    if not raw:
        raise ReaderError("file is empty (0 bytes)")
    if not raw.strip():
        raise ReaderError("file contains only blank characters")
    try:
        text = decode(raw)
    except UnicodeDecodeError as error:
        raise ReaderError(f"cannot decode the file as Windows-1252 or UTF-8: {error}") from error
    try:
        # dtype=str, keep_default_na=False, na_filter=False: nothing becomes a number, a date or NaN; '' stays ''
        # skip_blank_lines=False: row i of the table is line i + 2 of the file, so row numbers are exact
        table = pd.read_csv(io.StringIO(text), sep=SEPARATOR, dtype=str, keep_default_na=False, na_filter=False,
                            skip_blank_lines=False, header=0)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        raise ReaderError(f"cannot parse the file as a ';' separated table: {error}") from error

    names = [str(name) for name in table.columns]
    lines = text.splitlines()          # lines[0] is the header, lines[i] is data row i - 1
    rows, warnings = [], []
    for index, values in enumerate(table.itertuples(index=False, name=None)):
        line_number = index + 2
        if not any(str(value).strip() for value in values):
            continue                   # blank line (e.g. the trailing blank line at the end of the export)
        # pandas fills a cut-off line with '' - so we count the separators in the raw line to see the truth
        found = lines[index + 1].count(SEPARATOR) + 1 if index + 1 < len(lines) else len(names)
        values = [str(value) if position < found else None for position, value in enumerate(values)]
        if found != len(names):
            warnings.append(f"line {line_number}: {found} fields found, {len(names)} expected (cut-off or corrupt line); "
                            f"loaded as received, missing fields are NULL. Line starts: {lines[index + 1][:60]!r}")
        payload = dict(zip(names, values))
        rows.append(Row(line_number, payload, {name.lower(): value for name, value in payload.items()}))

    if not rows:
        warnings.append("the file has a header but no data rows")
    return ReadResult(names, rows, warnings)
