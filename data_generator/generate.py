"""Create the synthetic data. Run from the project root:  python -m data_generator.generate

Same seed = identical files on every run. The script first deletes its own old output
(incoming/ and ground_truth/), so running it again never creates duplicates.
"""
import csv
import sys
from collections import Counter

from .config import INCOMING, SYNTHETIC, TRUTH
from .csv_files import build_csv_files
from .excel_files import build_excel_files
from .legacy_files import build_legacy_files
from .model import ErrorLog
from .truth import build_truth, write_truth

README = """# Synthetic data (invented, deliberately messy)

Everything here is made up by data_generator/generate.py. No real company or customer data.
This folder is NOT in Git. Re-create it any time with:  python -m data_generator.generate
(fixed random seed: every run gives byte-identical files)

## ground_truth/  (the clean answers, to check the platform against)
| File | Content |
|---|---|
| customers.csv | 40 customers: customer_id, clean_name, country (4711 = Müller Logistik GmbH) |
| customer_aliases.csv | 3-4 spelling variants per customer: raw_name, customer_id |
| lanes.csv | 25 lanes: lane_id, cities, countries, distance_km (L01 = Hamburg -> Rotterdam) |
| charge_types.csv | The 6 standard charge types and their unit |
| charge_aliases.csv | German and English names for each charge type: raw_name, charge_type |
| prices.csv | The agreed prices (price history over 2026). BASE_RATE/TOLL/HANDLING in EUR, FUEL_SURCHARGE/PEAK_SEASON/CURRENCY_ADJUSTMENT as decimal fraction (0.18 = 18 %) |
| shipments.csv | The clean shipments: shipment_id, ship_date, customer_id, lane_id, weight_kg |
| invoices.csv | The clean invoices: agreed_amount, billed_amount, is_mismatch (1 = planted error) |
| planted_errors.csv | EVERY deliberate error: error_id, type, file, location, description |

Demo example: customer 4711, lane L01 (Hamburg -> Rotterdam), BASE_RATE 1200.00 EUR and
FUEL_SURCHARGE 0.18, valid 2026-10-01 to 2026-12-31 (total 1,416.00 EUR per shipment).

## incoming/  (the messy files the platform must read)
| Files | Format | How it is messy |
|---|---|---|
| prices_Q1..Q4_2026.xlsx, prices_Q4_2026_Ergaenzung.xlsx | Excel | Merged title cell and title block above the table, empty rows, header names change between files (Kunde / Customer / Cust.), German numbers as text ("1.200,50"), percent as "DSZ 18 %" or "18,0 %", dates as text or real dates, customer name spelling variants. The Q4 file has an extra column "Bemerkung". |
| prices_Q3_2026_final.xlsx | Excel | Byte-identical copy of prices_Q3_2026.xlsx under a second name |
| shipments_*.csv, invoices_*.csv | CSV | Semicolon, Windows-1252 (umlauts), CRLF, dates as 09.10.2026 and 2026-10-09 mixed, decimal comma, blank line at the end |
| export_YYYYMMDD.dat | Legacy dump | Fixed width, no header, DDMMYY dates, amounts without decimal point. Layout: data_generator/legacy_layout.yaml |

Row numbers in planted_errors.csv: Excel = sheet row number, CSV = line number (line 1 is the header),
.dat = line number. "whole file" = the problem is the file itself.

## Planted error types
| type | What is wrong |
|---|---|
| overlapping_validity | Two price periods overlap for the same customer + lane + charge (2 rows, one in the Q4 file, one in the supplement) |
| duplicate_row | An exact copy of another row in the same file (20 in total) |
| duplicate_file | The Q3 Excel file delivered twice under two names |
| unknown_customer | A customer number in shipments that is not in customers.csv |
| wrong_currency | One price written in USD instead of EUR |
| empty_file | A 0-byte legacy file |
| corrupt_row | One invoice line cut off in the middle |
| invoice_mismatch | Invoice amount differs from the agreed price (4 % of the invoices) |

Not messy on purpose: ground_truth/ is always clean. Prices that start in a quarter are delivered in that quarter's
Excel file, about 20 % of the price periods come from the legacy tool instead (and 4711's Q4 price from both).
"""


def clean_outputs():
    """Delete our own old output (never .gitkeep, never archive/) so a re-run starts fresh."""
    for folder in (INCOMING, TRUTH):
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.iterdir():
            if path.is_file() and path.name != ".gitkeep":
                path.unlink()


def write_errors(errors):
    with open(TRUTH / "planted_errors.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["error_id", "type", "file", "location", "description"])
        for number, e in enumerate(errors.items, 1):
            writer.writerow([f"E{number:03d}", e["type"], e["file"], e["location"], e["description"]])


def print_summary(truth, files, errors):
    print("\n=== Ground truth ===")
    print(f"customers {len(truth.customers)}, aliases {len(truth.aliases)}, lanes {len(truth.lanes)}, "
          f"price periods {len(truth.periods)}, price rows {len(truth.prices)}")
    print("\n=== Files in data/synthetic/incoming ===")
    print(f"{'Format':<8}{'File':<34}{'Rows':>6}")
    for fmt, items in files:
        for name, rows in items:
            print(f"{fmt:<8}{name:<34}{rows:>6}")
        print(f"{'':<8}{'-> ' + str(len(items)) + ' files, ' + str(sum(r for _, r in items)) + ' rows':<34}")
    print("\n=== Planted errors by type ===")
    counts = Counter(e["type"] for e in errors.items)
    for error_type, count in sorted(counts.items()):
        print(f"{error_type:<24}{count:>5}")
    print(f"{'TOTAL':<24}{sum(counts.values()):>5}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    clean_outputs()
    truth = build_truth()
    write_truth(truth, TRUTH)

    errors = ErrorLog()
    files = [("xlsx", build_excel_files(truth, errors)),
             ("csv", build_csv_files(truth, errors)),
             ("dat", build_legacy_files(truth, errors))]
    write_errors(errors)
    (SYNTHETIC / "README.md").write_text(README, encoding="utf-8", newline="\n")
    print_summary(truth, files, errors)


if __name__ == "__main__":
    main()
