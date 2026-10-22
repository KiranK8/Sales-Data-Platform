"""Tests for the bronze loader. They run against a throw-away PostgreSQL database (see conftest.py)."""
from datetime import date

import pytest
from sqlalchemy import text

from ingestion import db, load_bronze
from tests.make_files import SHIPMENTS_CSV, make_csv, make_dat, make_xlsx, price_row

TODAY = date(2026, 10, 22)


@pytest.fixture
def folders(tmp_path):
    incoming, archive = tmp_path / "incoming", tmp_path / "archive"
    incoming.mkdir()
    return incoming, archive


def fill(incoming):
    """One file of each type, like a small real delivery."""
    make_xlsx(incoming / "prices_Q4.xlsx", [price_row(), price_row(charge="Grundpreis", amount="1.200,50")])
    make_csv(incoming / "shipments_2026.csv", SHIPMENTS_CSV)
    make_csv(incoming / "invoices_2026.csv", "Rechnungsnr;Rechnungsdatum;Sendungsnr;Kundennr;Rechnungsbetrag;Waehrung\r\n"
                                            "RE-1;2026-10-10;SND-1;4711;1.416,00;EUR\r\n")
    make_dat(incoming / "export_20261009.dat")


def counts(engine):
    return {table: db.count_rows(engine, table) for table in db.bronze_tables()}


def statuses(results):
    return {r.file_name: r.status for r in results}


def test_loading_creates_rows_with_metadata_and_everything_as_text(engine, folders):
    incoming, archive = folders
    fill(incoming)
    load_bronze.load_all(engine, incoming, archive, TODAY)
    assert counts(engine) == {"raw_excel_prices": 2, "raw_csv_shipments": 2, "raw_csv_invoices": 1, "raw_legacy_prices": 2}
    with engine.connect() as conn:
        row = conn.execute(text("SELECT amount, charge, source_file, file_hash, row_number, load_id, load_ts "
                                "FROM bronze.raw_excel_prices ORDER BY row_number DESC LIMIT 1")).one()
        types = {r[0] for r in conn.execute(text(
            "SELECT data_type FROM information_schema.columns WHERE table_schema = 'bronze' AND table_name = 'raw_excel_prices' "
            "AND column_name IN ('customer','lane','charge','amount','currency','valid_from','valid_to')"))}
    assert row.amount == "1.200,50" and row.source_file == "prices_Q4.xlsx" and len(row.file_hash) == 64
    assert row.load_id and row.load_ts and types == {"text"}


def test_second_run_adds_zero_rows_and_logs_everything_as_skipped(engine, folders):
    incoming, archive = folders
    fill(incoming)
    first = load_bronze.load_all(engine, incoming, archive, TODAY)
    before = counts(engine)
    second = load_bronze.load_all(engine, incoming, archive, TODAY)
    assert set(statuses(first).values()) == {"SUCCESS"}
    assert set(statuses(second).values()) == {"SKIPPED"} and sum(r.rows_loaded for r in second) == 0
    assert counts(engine) == before
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ops.load_log WHERE status = 'SKIPPED'")).scalar() == 4


def test_same_content_under_a_new_name_is_skipped(engine, folders):
    incoming, archive = folders
    make_xlsx(incoming / "prices_Q3.xlsx", [price_row()])
    (incoming / "prices_Q3_final.xlsx").write_bytes((incoming / "prices_Q3.xlsx").read_bytes())   # delivered twice
    results = load_bronze.load_all(engine, incoming, archive, TODAY)
    assert statuses(results) == {"prices_Q3.xlsx": "SUCCESS", "prices_Q3_final.xlsx": "SKIPPED"}
    assert "same content as prices_Q3.xlsx" in results[1].message and counts(engine)["raw_excel_prices"] == 1


def test_an_empty_file_is_logged_as_failed_and_the_run_continues(engine, folders):
    incoming, archive = folders
    fill(incoming)
    (incoming / "export_20261016.dat").write_bytes(b"")        # 0 bytes, sorts between other files
    (incoming / "shipments_empty.csv").write_bytes(b"")
    (incoming / "broken.xlsx").write_bytes(b"not a workbook")
    results = load_bronze.load_all(engine, incoming, archive, TODAY)
    status = statuses(results)
    assert status["export_20261016.dat"] == status["shipments_empty.csv"] == status["broken.xlsx"] == "FAILED"
    assert status["prices_Q4.xlsx"] == status["invoices_2026.csv"] == "SUCCESS"      # the others were still loaded
    assert counts(engine)["raw_excel_prices"] == 2
    with engine.connect() as conn:
        message = conn.execute(text("SELECT message FROM ops.load_log WHERE file_name = 'export_20261016.dat'")).scalar()
    assert "empty" in message


def test_a_failure_halfway_through_a_file_keeps_nothing_of_that_file(engine, folders, monkeypatch):
    incoming, archive = folders
    make_xlsx(incoming / "prices_Q4.xlsx", [price_row() for _ in range(5)])
    real_insert = db.insert_rows

    def insert_some_then_crash(conn, table, columns, load_id, file_name, file_hash, rows):
        real_insert(conn, table, columns, load_id, file_name, file_hash, rows[:2])   # 2 rows really go in ...
        raise RuntimeError("disk full")                                                # ... then it crashes

    monkeypatch.setattr(db, "insert_rows", insert_some_then_crash)
    results = load_bronze.load_all(engine, incoming, archive, TODAY)
    assert results[0].status == "FAILED" and "disk full" in results[0].message
    assert counts(engine)["raw_excel_prices"] == 0                      # the 2 rows were rolled back
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ops.load_log WHERE status = 'SUCCESS'")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM ops.load_log WHERE status = 'FAILED'")).scalar() == 1
    monkeypatch.setattr(db, "insert_rows", real_insert)                  # problem fixed: the next run loads the file
    assert load_bronze.load_all(engine, incoming, archive, TODAY)[0].status == "SUCCESS"
    assert counts(engine)["raw_excel_prices"] == 5


def test_a_corrupt_csv_row_is_loaded_as_received_and_logged_as_warning(engine, folders):
    incoming, archive = folders
    make_csv(incoming / "invoices_x.csv", "Rechnungsnr;Rechnungsdatum;Sendungsnr;Kundennr;Rechnungsbetrag;Waehrung\r\n"
                                          "RE-1;2026-10-10;SND-1;4711;100,00;EUR\r\nRE-2;2026-10-1#\r\n")
    result = load_bronze.load_all(engine, incoming, archive, TODAY)[0]
    assert result.status == "SUCCESS" and result.rows_loaded == 2 and result.warnings == 1
    with engine.connect() as conn:
        warning = conn.execute(text("SELECT message FROM ops.load_log WHERE status = 'WARNING'")).scalar()
        cut = conn.execute(text("SELECT rechnungsdatum, sendungsnr FROM bronze.raw_csv_invoices WHERE row_number = 3")).one()
    assert "line 3" in warning and cut == ("2026-10-1#", None)


def test_bronze_tables_are_append_only(engine, folders):
    incoming, archive = folders
    fill(incoming)
    load_bronze.load_all(engine, incoming, archive, TODAY)
    for statement in ("UPDATE bronze.raw_excel_prices SET amount = '0'", "DELETE FROM bronze.raw_csv_shipments",
                      "TRUNCATE bronze.raw_legacy_prices"):
        with pytest.raises(Exception, match="append-only"):
            with engine.begin() as conn:
                conn.execute(text(statement))
    assert counts(engine)["raw_excel_prices"] == 2


def test_the_original_is_copied_to_a_dated_archive_folder_and_stays_in_place(engine, folders):
    incoming, archive = folders
    fill(incoming)
    load_bronze.load_all(engine, incoming, archive, TODAY)
    copy = archive / "2026-10-22" / "prices_Q4.xlsx"
    assert copy.read_bytes() == (incoming / "prices_Q4.xlsx").read_bytes()      # identical, and the original is still there
    assert len(list((archive / "2026-10-22").iterdir())) == 4


def test_files_this_step_does_not_handle_are_ignored(engine, folders):
    incoming, archive = folders
    (incoming / "contract_4711.docx").write_bytes(b"x")
    (incoming / "preisblatt.pdf").write_bytes(b"x")
    assert load_bronze.load_all(engine, incoming, archive, TODAY) == []
