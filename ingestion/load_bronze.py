"""Load the raw files from data/synthetic/incoming/ into PostgreSQL schema "bronze".

Run from the project root:   python -m ingestion.load_bronze

Rules: bronze keeps every value as TEXT exactly as received, rows are only ever appended, and a file whose
content (SHA-256) was already loaded is skipped. Each file is loaded in ONE transaction: all of it or nothing.
"""
import hashlib
import shutil
import sys
from dataclasses import dataclass
from datetime import date

from . import db
from .config import ARCHIVE, INCOMING
from .readers.csv_reader import read_csv_file
from .readers.excel_reader import read_excel_file
from .readers.legacy_reader import read_legacy_file


@dataclass
class FileResult:
    file_name: str
    source_type: str
    rows_loaded: int
    status: str      # SUCCESS / FAILED / SKIPPED
    message: str
    warnings: int = 0


def route(path):
    """Which source type, bronze table and reader fit this file? None = not handled in this step."""
    suffix, name = path.suffix.lower(), path.name.lower()
    if name.startswith("~$"):
        return None   # Excel's temporary lock file
    if suffix == ".xlsx":
        return "excel_prices", "raw_excel_prices", read_excel_file
    if suffix == ".csv" and name.startswith("shipments"):
        return "csv_shipments", "raw_csv_shipments", read_csv_file
    if suffix == ".csv" and name.startswith("invoices"):
        return "csv_invoices", "raw_csv_invoices", read_csv_file
    if suffix == ".dat":
        return "legacy_prices", "raw_legacy_prices", read_legacy_file
    return None


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_copy(path, file_hash, archive_dir, today):
    """COPY (never move) the original, unchanged, into archive/<load date>/."""
    folder = archive_dir / today.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    if target.exists() and sha256_of(target) != file_hash:   # same name, other content: keep both
        target = folder / f"{path.stem}__{file_hash[:8]}{path.suffix}"
    if not target.exists():
        shutil.copy2(path, target)
    return target


def load_file(engine, path, archive_dir, today):
    source_type, table, reader = route(path)
    file_hash = sha256_of(path)

    with engine.begin() as conn:
        earlier = db.find_loaded(conn, file_hash)
        if earlier:   # same content already loaded (maybe under another name): do nothing
            message = "skipped: already loaded" + ("" if earlier == path.name else f" (same content as {earlier})")
            db.write_log(conn, path.name, file_hash, source_type, "SKIPPED", message)
            return FileResult(path.name, source_type, 0, "SKIPPED", message)

    def failed(message):
        with engine.begin() as conn:   # a new transaction: the log line stays even though the load was rolled back
            db.write_log(conn, path.name, file_hash, source_type, "FAILED", message[:1000])
        return FileResult(path.name, source_type, 0, "FAILED", message[:200])

    try:
        result = reader(path)
    except Exception as error:   # ReaderError or anything unexpected: log it and go on with the next file
        return failed(str(error))

    columns = db.bronze_tables()[table]
    try:
        with engine.begin() as conn:   # ONE transaction: the log line and all rows commit together, or nothing does
            load_id = db.write_log(conn, path.name, file_hash, source_type, "SUCCESS",
                                   f"{len(result.rows)} rows loaded", len(result.rows))
            db.insert_rows(conn, table, columns, load_id, path.name, file_hash, result.rows)
    except Exception as error:
        return failed(f"database error, nothing from this file was kept: {type(error).__name__}: {error}")

    notes = list(result.warnings)
    try:
        archive_copy(path, file_hash, archive_dir, today)
    except OSError as error:
        notes.append(f"loaded, but the archive copy failed: {error}")
    with engine.begin() as conn:       # each warning gets its own WARNING line, so you can query them
        for note in notes:
            db.write_log(conn, path.name, file_hash, source_type, "WARNING", note[:1000])
    message = f"{len(result.rows)} rows loaded" + (f", {len(notes)} warning(s)" if notes else "")
    return FileResult(path.name, source_type, len(result.rows), "SUCCESS", message, len(notes))


def load_all(engine, incoming_dir=INCOMING, archive_dir=ARCHIVE, today=None):
    """Load every supported file in the folder (sorted by name). Returns one FileResult per file."""
    today = today or date.today()
    db.create_structures(engine)
    results = []
    for path in sorted(p for p in incoming_dir.iterdir() if p.is_file() and route(p)):
        results.append(load_file(engine, path, archive_dir, today))
    return results


def print_report(results, ignored):
    width = max((len(r.file_name) for r in results), default=10) + 2
    print(f"{'file':<{width}}{'type':<15}{'rows':>6}  {'status':<8} message")
    for r in results:
        print(f"{r.file_name:<{width}}{r.source_type:<15}{r.rows_loaded:>6}  {r.status:<8} {r.message}")
    totals = {s: sum(1 for r in results if r.status == s) for s in ("SUCCESS", "SKIPPED", "FAILED")}
    print(f"\nfiles: {len(results)} | SUCCESS {totals['SUCCESS']}, SKIPPED {totals['SKIPPED']}, FAILED {totals['FAILED']} "
          f"| rows loaded this run: {sum(r.rows_loaded for r in results)} | warnings: {sum(r.warnings for r in results)}")
    if ignored:
        print(f"not handled in this step (Word, PDF, ... come later): {ignored} files")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    engine = db.get_engine()
    results = load_all(engine)
    ignored = sum(1 for p in INCOMING.iterdir() if p.is_file() and not p.name.startswith(".") and not route(p))
    print_report(results, ignored)


if __name__ == "__main__":
    main()
