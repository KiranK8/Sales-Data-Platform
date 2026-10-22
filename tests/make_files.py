"""Helpers that build tiny source files for the ingestion tests."""
from datetime import date

import openpyxl

from data_generator.legacy_files import format_record, load_layout

PRICE_HEADER = ["Kunde", "Strecke", "Zuschlag", "Betrag", "Währung", "Gültig von", "Gültig bis"]


def make_xlsx(path, data_rows, header=PRICE_HEADER, blank_rows_before_header=1):
    """A price list with a title block above the table, like the real files. Every cell is written as text."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Rieck Logistik Gruppe – Preisliste Q4 2026"])   # row 1: title
    sheet.append(["Preisliste"])                                  # row 2
    sheet.append(["Stand: 01.10.2026"])                           # row 3
    for _ in range(blank_rows_before_header):
        sheet.append([])
    sheet.append(header)
    for row in data_rows:
        sheet.append(row)
    book.save(path)
    return path


def price_row(customer="Müller Logistik GmbH", charge="DSZ 18 %", amount=None):
    return [customer, "Hamburg - Rotterdam", charge, amount, "EUR", "01.10.2026", "31.12.2026"]


def make_csv(path, text, encoding="cp1252"):
    path.write_bytes(text.encode(encoding))
    return path


SHIPMENTS_CSV = ("Sendungsnr;Versanddatum;Kundennr;Kundenname;Von;Nach;Gewicht_kg\r\n"
                 "SND-1;09.10.2026;4711;Müller Logistik GmbH;Hamburg;Rotterdam;12450,5\r\n"
                 "SND-2;2026-10-09;4711;Mueller Logistik;München;Wien;980,0\r\n"
                 "\r\n")


def make_dat(path, rows=2):
    """Fixed-width legacy lines built with the real layout."""
    layout = load_layout()
    lines = [format_record(layout, dict(
        record_type="PR", customer_no=4711, customer_name="MUELLER LOGISTIK GMBH", lane_code="HAM-ROT",
        charge_text="FUEL SURCH. 0.18", amount=0, valid_from=date(2026, 10, 1), valid_to=date(2026, 12, 31),
        currency="EUR")) for _ in range(rows)]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    return path, lines
