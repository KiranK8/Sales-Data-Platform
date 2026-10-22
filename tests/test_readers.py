"""Tests for the three readers (no database needed)."""
import pytest

from ingestion.readers import ReaderError
from ingestion.readers.csv_reader import read_csv_file
from ingestion.readers.excel_reader import find_header_row, read_excel_file
from ingestion.readers.legacy_reader import read_legacy_file
from tests.make_files import SHIPMENTS_CSV, make_csv, make_dat, make_xlsx, price_row


def test_header_row_is_found_below_the_title_block(tmp_path):
    path = make_xlsx(tmp_path / "p.xlsx", [price_row()], header=["Cust.", "Lane", "Charge", "Amount", "Currency",
                                                                  "Valid from", "Valid to"], blank_rows_before_header=2)
    result = read_excel_file(path)
    assert result.columns[:3] == ["Cust.", "Lane", "Charge"]
    assert [row.row_number for row in result.rows] == [7]            # title rows 1-3, 2 blank rows, header row 6, data row 7
    assert result.rows[0].columns["customer"] == "Müller Logistik GmbH"
    assert result.rows[0].columns["valid_from"] == "01.10.2026"


def test_find_header_row_needs_two_known_header_words():
    rows = [["Rieck Logistik Gruppe"], ["Preisliste"], ["Kunde"], ["Kunde", "Strecke", "Betrag"]]
    assert find_header_row(rows) == 3       # a single "Kunde" in the title block is not enough
    assert find_header_row([["nothing"], ["here"]]) is None


def test_german_number_and_percent_text_stay_text(tmp_path):
    path = make_xlsx(tmp_path / "p.xlsx", [price_row(charge="Grundpreis", amount="1.200,50"), price_row()])
    first, second = read_excel_file(path).rows
    assert first.columns["amount"] == "1.200,50"          # not 1200.5, not 1.2005
    assert second.columns["charge"] == "DSZ 18 %"        # the percent sign and the space are still there
    assert second.columns["amount"] == ""                # an empty cell is an empty string, not a number or NaN


def test_unknown_extra_column_is_kept_in_the_payload(tmp_path):
    header = [*["Kunde", "Strecke", "Zuschlag", "Betrag", "Währung", "Gültig von", "Gültig bis"], "Bemerkung"]
    path = make_xlsx(tmp_path / "p.xlsx", [price_row() + ["Index angepasst"]], header=header)
    row = read_excel_file(path).rows[0]
    assert row.payload["Bemerkung"] == "Index angepasst"
    assert "Bemerkung" not in row.columns               # no own column for it, but nothing is lost


def test_completely_empty_rows_in_the_table_are_skipped(tmp_path):
    path = make_xlsx(tmp_path / "p.xlsx", [price_row(), [], price_row()])
    assert [row.row_number for row in read_excel_file(path).rows] == [6, 8]   # the gap shows where the empty row was


def test_csv_reads_windows_1252_umlauts_and_skips_the_blank_last_line(tmp_path):
    result = read_csv_file(make_csv(tmp_path / "shipments_x.csv", SHIPMENTS_CSV))
    assert [row.row_number for row in result.rows] == [2, 3]
    assert result.rows[0].columns["kundenname"] == "Müller Logistik GmbH"
    assert result.rows[0].columns["gewicht_kg"] == "12450,5"          # decimal comma stays text
    assert result.rows[1].columns["versanddatum"] == "2026-10-09"     # mixed date formats stay as they are
    assert result.warnings == []


def test_csv_falls_back_to_utf8_with_bom(tmp_path):
    path = tmp_path / "shipments_u.csv"
    path.write_bytes(b"\xef\xbb\xbf" + "Sendungsnr;Kundenname\r\nSND-1;Müller\r\n".encode("utf-8"))
    assert read_csv_file(path).rows[0].columns["kundenname"] == "Müller"


def test_csv_cut_off_line_gives_a_warning_and_null_fields(tmp_path):
    path = make_csv(tmp_path / "invoices_x.csv", "A;B;C\r\n1;2;3\r\n4;5#\r\n")
    result = read_csv_file(path)
    assert len(result.rows) == 2 and "line 3" in result.warnings[0]
    assert result.rows[1].payload == {"A": "4", "B": "5#", "C": None}    # missing = None, not made-up text


def test_legacy_reader_uses_the_yaml_positions_and_keeps_the_padding(tmp_path):
    path, lines = make_dat(tmp_path / "export_20261009.dat")
    result = read_legacy_file(path)
    row = result.rows[0]
    assert row.row_number == 1 and result.warnings == []
    assert row.payload["customer_no"] == "4711" and row.payload["amount"] == "000000000"
    assert row.payload["charge_text"] == "FUEL SURCH. 0.18"
    assert row.payload["customer_name"] == "MUELLER LOGISTIK GMBH         "   # padded to 30 characters, untouched
    assert row.payload["valid_from"] == "011026"                               # DDMMYY stays text


def test_legacy_short_line_gives_a_warning(tmp_path):
    path = tmp_path / "export_x.dat"
    path.write_bytes(b"PR4711MUELLER\r\n")
    result = read_legacy_file(path)
    assert "line 1" in result.warnings[0] and result.rows[0].payload["valid_from"] is None


@pytest.mark.parametrize("reader, name", [(read_excel_file, "p.xlsx"), (read_csv_file, "shipments_e.csv"),
                                          (read_legacy_file, "export_e.dat")])
def test_an_empty_file_raises_a_clear_error(tmp_path, reader, name):
    path = tmp_path / name
    path.write_bytes(b"")
    with pytest.raises(ReaderError, match="empty"):
        reader(path)


def test_a_file_that_is_not_a_workbook_raises_a_clear_error(tmp_path):
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"this is not an excel file")
    with pytest.raises(ReaderError, match="cannot open"):
        read_excel_file(path)
