"""Show a few raw rows of an Excel file, a CSV and a legacy .dat file:  python -m data_generator.show_samples"""
import sys

import openpyxl

from .config import INCOMING


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("=== Excel: prices_Q4_2026.xlsx (cell values exactly as stored) ===")
    sheet = openpyxl.load_workbook(INCOMING / "prices_Q4_2026.xlsx").active
    rows = list(sheet.iter_rows(values_only=True))
    for number in range(3):
        print(f"row {number + 1}: {rows[number][:3]}")
    header = next(i for i, r in enumerate(rows) if r[0] in ("Kunde", "Customer", "Cust."))
    for number in range(header, header + 5):
        print(f"row {number + 1}: {rows[number]}")

    print("\n=== CSV: invoices_2026_H2.csv (Windows-1252, as text) ===")
    lines = (INCOMING / "invoices_2026_H2.csv").read_bytes().decode("cp1252").split("\r\n")
    for line in lines[:5]:
        print(repr(line))

    print("\n=== Legacy: export_20261009.dat + export_20260929.dat (fixed width, no header) ===")
    print("          1         2         3         4         5         6         7         8")
    print("12345678901234567890123456789012345678901234567890123456789012345678901234567890123456")
    shown = 0
    for name in ("export_20261009.dat", "export_20260929.dat"):
        for line in (INCOMING / name).read_bytes().decode("ascii").split("\r\n"):
            if line and shown < 5:
                print(line)
                shown += 1


if __name__ == "__main__":
    main()
