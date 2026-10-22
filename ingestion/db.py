"""Database helpers: engine, table creation (bronze + ops), the load log, fast inserts."""
from psycopg2 import sql
from psycopg2.extras import Json, execute_values
from sqlalchemy import create_engine, text

from .config import LAYOUT_FILE, load_settings
from .readers.excel_reader import COLUMN_NAMES
from .readers.legacy_reader import column_names

PAGE_SIZE = 1000   # rows per INSERT statement

# bronze table -> its source columns. Every column is TEXT.
CSV_SHIPMENT_COLUMNS = ["sendungsnr", "versanddatum", "kundennr", "kundenname", "von", "nach", "gewicht_kg"]
CSV_INVOICE_COLUMNS = ["rechnungsnr", "rechnungsdatum", "sendungsnr", "kundennr", "rechnungsbetrag", "waehrung"]


def bronze_tables(layout_file=LAYOUT_FILE):
    return {
        "raw_excel_prices": list(COLUMN_NAMES),               # customer, lane, charge, amount, ...
        "raw_csv_shipments": CSV_SHIPMENT_COLUMNS,
        "raw_csv_invoices": CSV_INVOICE_COLUMNS,
        "raw_legacy_prices": column_names(layout_file),       # named after the YAML layout (the files have no header)
    }


LOAD_LOG_DDL = """
CREATE TABLE IF NOT EXISTS ops.load_log (
    load_id     BIGSERIAL PRIMARY KEY,
    file_name   TEXT NOT NULL,
    file_hash   TEXT NOT NULL,
    source_type TEXT NOT NULL,
    rows_loaded INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL CHECK (status IN ('SUCCESS', 'FAILED', 'SKIPPED', 'WARNING')),
    message     TEXT,
    load_ts     TIMESTAMPTZ NOT NULL DEFAULT now()
)"""

# Raising an error on UPDATE / DELETE / TRUNCATE is how the database itself enforces "append-only".
# (In this text a doubled %% means one % : the database driver treats a single % as a placeholder.)
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION bronze.forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'bronze tables are append-only: %% is not allowed on %%', TG_OP, TG_TABLE_NAME;
END $$"""


def table_ddl(name, columns):
    source = ",\n    ".join(f"{column} TEXT" for column in columns)
    return f"""
CREATE TABLE IF NOT EXISTS bronze.{name} (
    load_id     BIGINT NOT NULL REFERENCES ops.load_log (load_id),
    load_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_file TEXT NOT NULL,
    file_hash   TEXT NOT NULL,
    row_number  INTEGER NOT NULL,
    {source},
    raw_payload JSONB NOT NULL,
    UNIQUE (file_hash, row_number)   -- safety net: the same file can never be loaded twice
)"""


def get_engine(settings=None, database=None):
    settings = settings or load_settings()
    return create_engine(settings.url(database), pool_pre_ping=True)


def create_structures(engine, layout_file=LAYOUT_FILE):
    """Create schemas, the load log and the bronze tables if they are missing (safe to run every time)."""
    with engine.begin() as conn:
        for schema in ("bronze", "silver", "gold", "ops"):
            conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.exec_driver_sql(LOAD_LOG_DDL)
        conn.exec_driver_sql(APPEND_ONLY_FUNCTION)
        for name, columns in bronze_tables(layout_file).items():
            conn.exec_driver_sql(table_ddl(name, columns))
            conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS no_update_delete ON bronze.{name}")
            conn.exec_driver_sql(f"CREATE TRIGGER no_update_delete BEFORE UPDATE OR DELETE ON bronze.{name} "
                                 "FOR EACH ROW EXECUTE FUNCTION bronze.forbid_change()")
            conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS no_truncate ON bronze.{name}")
            conn.exec_driver_sql(f"CREATE TRIGGER no_truncate BEFORE TRUNCATE ON bronze.{name} "
                                 "FOR EACH STATEMENT EXECUTE FUNCTION bronze.forbid_change()")


def find_loaded(conn, file_hash):
    """File name of an earlier SUCCESSFUL load of exactly this content, or None."""
    row = conn.execute(text("SELECT file_name FROM ops.load_log WHERE file_hash = :h AND status = 'SUCCESS' "
                            "ORDER BY load_id LIMIT 1"), {"h": file_hash}).fetchone()
    return row[0] if row else None


def write_log(conn, file_name, file_hash, source_type, status, message, rows_loaded=0):
    """Add one line to ops.load_log and return its load_id."""
    return conn.execute(text(
        "INSERT INTO ops.load_log (file_name, file_hash, source_type, rows_loaded, status, message) "
        "VALUES (:f, :h, :t, :n, :s, :m) RETURNING load_id"),
        {"f": file_name, "h": file_hash, "t": source_type, "n": rows_loaded, "s": status, "m": message}).scalar_one()


def insert_rows(conn, table, columns, load_id, file_name, file_hash, rows):
    """Append rows to a bronze table inside the transaction of `conn`. Values go in exactly as given."""
    statement = sql.SQL("INSERT INTO bronze.{} (load_id, source_file, file_hash, row_number, raw_payload, {}) VALUES %s").format(
        sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(c) for c in columns))
    values = [(load_id, file_name, file_hash, row.row_number, Json(row.payload), *[row.columns.get(c) for c in columns])
              for row in rows]
    with conn.connection.cursor() as cursor:   # same database connection, so same transaction
        execute_values(cursor, statement, values, page_size=PAGE_SIZE)


def count_rows(engine, table, schema="bronze"):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {schema}.{table}")).scalar_one()
