"""Readers turn one source file into rows of TEXT. They never convert, clean or correct a value."""
from dataclasses import dataclass, field


class ReaderError(Exception):
    """The whole file cannot be read (empty, not a workbook, no header ...). The run goes on with the next file."""


@dataclass
class Row:
    row_number: int   # position in the file: sheet row (Excel) or line number (CSV, .dat)
    payload: dict     # original column name -> text; None = the field is missing in the file
    columns: dict     # bronze column name -> text (the same values, under the bronze column names)


@dataclass
class ReadResult:
    columns: list                                   # the original column names, as in the file
    rows: list                                      # list of Row
    warnings: list = field(default_factory=list)    # things that look wrong, e.g. a cut-off line
