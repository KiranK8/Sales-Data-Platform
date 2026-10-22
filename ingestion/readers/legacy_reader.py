"""Legacy tool dumps: fixed-width lines without header. The column positions come from legacy_layout.yaml."""
import io

import pandas as pd
import yaml

from ..config import LAYOUT_FILE
from . import ReaderError, ReadResult, Row


def load_layout(layout_file=LAYOUT_FILE):
    with open(layout_file, encoding="utf-8") as f:
        return yaml.safe_load(f)


def column_names(layout_file=LAYOUT_FILE):
    return [column["name"] for column in load_layout(layout_file)["columns"]]


def read_legacy_file(path, layout_file=LAYOUT_FILE):
    layout = load_layout(layout_file)
    names = [c["name"] for c in layout["columns"]]
    colspecs = [(c["start"] - 1, c["start"] - 1 + c["width"]) for c in layout["columns"]]   # YAML counts from 1

    raw = path.read_bytes()
    if not raw:
        raise ReaderError("file is empty (0 bytes)")
    try:
        text = raw.decode(layout.get("encoding", "ascii"))
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    lines = text.splitlines()          # lines[i] is line i + 1 of the file
    if not any(line.strip() for line in lines):
        raise ReaderError("file contains no data lines")

    # delimiter="\0": pandas must not strip the padding spaces, the value stays exactly as in the file
    table = pd.read_fwf(io.StringIO("\n".join(lines)), colspecs=colspecs, names=names, header=None, dtype=str,
                        keep_default_na=False, na_filter=False, delimiter="\0", skip_blank_lines=False)

    expected_length = layout["record_length"]
    rows, warnings = [], []
    for index, values in enumerate(table.itertuples(index=False, name=None)):
        line = lines[index]
        if not line.strip():
            continue
        if len(line) != expected_length:
            warnings.append(f"line {index + 1}: {len(line)} characters, the layout says {expected_length}; "
                            "loaded as received, fields past the end of the line are NULL")
        # a field that starts after the end of a short line is missing (None), not an empty string
        payload = {name: (str(value) if start < len(line) else None)
                   for name, value, (start, _) in zip(names, values, colspecs)}
        rows.append(Row(index + 1, payload, dict(payload)))
    return ReadResult(names, rows, warnings)
