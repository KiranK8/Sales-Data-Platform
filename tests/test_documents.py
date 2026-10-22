"""Tests for the Word, PDF and legacy-database generators (they use tmp_path, never the real data folder)."""
import sqlite3
import zipfile
from datetime import date

from data_generator.add_new_rows import add_batch
from data_generator.check_scans import score
from data_generator.docs_common import FIXED_STAMP, long_date, normalise_zip, same_terms, toll_per_km
from data_generator.legacy_db import ORIGINAL_SHIPMENTS, build_legacy_db
from data_generator.model import ErrorLog
from data_generator.truth import build_truth


def test_toll_is_a_whole_per_km_rate():
    """A contract can say '0,12 EUR pro km' and still match the agreed flat toll exactly."""
    truth = build_truth()
    tolls = [p for p in truth.periods if "TOLL" in p.charges]
    assert tolls
    for period in tolls:
        distance = truth.lane(period.lane_id)["distance_km"]
        assert round(toll_per_km(truth, period) * distance, 2) == period.charges["TOLL"]


def test_lanes_in_one_contract_share_the_same_surcharges():
    truth = build_truth()
    for period in truth.periods:
        group = same_terms(truth, period)
        assert period in group
        assert len({p.charges.get("FUEL_SURCHARGE") for p in group}) == 1
        assert len({(p.start, p.end) for p in group}) == 1


def test_long_date_is_german():
    assert long_date(date(2026, 10, 1)) == "1. Oktober 2026"


def test_normalise_zip_sets_a_fixed_time_on_every_entry(tmp_path):
    path = tmp_path / "x.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a.xml", "<a/>")
        z.writestr("b.xml", "<b/>")
    normalise_zip(path)
    with zipfile.ZipFile(path) as z:
        assert {info.date_time for info in z.infolist()} == {FIXED_STAMP}
        assert z.read("b.xml") == b"<b/>"


def test_ocr_score_notices_a_wrong_digit():
    assert score(["Preis 1.310,00 EUR"], "Preis 1.310,00 EUR") == (1.0, 1.0, 1.0)
    words, numbers, _ = score(["Preis 1.310,00 EUR"], "Preis 4.310,00 EUR")
    assert numbers == 0.0 and words < 1.0


def _build_db(tmp_path):
    errors, path = ErrorLog(), tmp_path / "legacy.db"
    build_legacy_db(build_truth(), errors, path)
    return path, errors


def test_legacy_db_has_timestamps_and_the_planted_problems(tmp_path):
    path, errors = _build_db(tmp_path)
    con = sqlite3.connect(path)
    for table in ("customers", "shipments", "invoices", "tenders"):
        columns = [row[1] for row in con.execute(f"PRAGMA table_info({table})")]
        assert "created_at" in columns and "updated_at" in columns
        assert con.execute(f"SELECT COUNT(*) FROM {table} WHERE updated_at < created_at").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM shipments").fetchone()[0] == ORIGINAL_SHIPMENTS
    assert con.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 80
    assert con.execute("SELECT COUNT(*) FROM tenders WHERE status = 'won'").fetchone()[0] == 34
    assert con.execute("SELECT COUNT(*) FROM invoices WHERE amount IS NULL").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM shipments WHERE customer_id NOT IN (SELECT id FROM customers)").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 41
    types = [e["type"] for e in errors.items]
    assert sorted(types) == ["duplicate_customer", "null_amount", "null_amount", "orphan_customer"]


def test_add_new_rows_adds_20_shipments_changes_5_invoices_and_is_repeatable(tmp_path):
    path, _ = _build_db(tmp_path)
    first = add_batch(path, 1, changes_dir=tmp_path)
    assert sum(c[2] == "new" for c in first) == 20 and sum(c[2] == "changed" for c in first) == 5
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM shipments").fetchone()[0] == ORIGINAL_SHIPMENTS + 20
    assert con.execute("SELECT COUNT(*) FROM shipments WHERE updated_at LIKE '2026-10-18 06:01:%'").fetchone()[0] == 20
    assert con.execute("SELECT COUNT(*) FROM invoices WHERE updated_at LIKE '2026-10-18 06:01:%'").fetchone()[0] == 5
    assert add_batch(path, 1, changes_dir=tmp_path) == []          # same batch again: nothing happens
    assert con.execute("SELECT COUNT(*) FROM shipments").fetchone()[0] == ORIGINAL_SHIPMENTS + 20
    assert sum(c[2] == "new" for c in add_batch(path, 2, changes_dir=tmp_path)) == 20   # next batch: more rows
