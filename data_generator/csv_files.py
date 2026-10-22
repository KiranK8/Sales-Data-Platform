"""STEP 2B: messy CSV exports (shipments and invoices): semicolon, Windows-1252, German formats."""
import csv
from datetime import timedelta

from .config import INCOMING, LAST_SHIPMENT_DAY, TRUTH, UNKNOWN_CUSTOMER_ID, UNKNOWN_CUSTOMER_NAME, make_rng
from .model import Row, add_duplicates
from .text import de_date, de_decimal, de_number, iso_date
from .truth import agreed_total

SHIPMENT_HEADER = ["Sendungsnr", "Versanddatum", "Kundennr", "Kundenname", "Von", "Nach", "Gewicht_kg"]
INVOICE_HEADER = ["Rechnungsnr", "Rechnungsdatum", "Sendungsnr", "Kundennr", "Rechnungsbetrag", "Waehrung"]
SHIPMENT_FILES = ["shipments_2026_Q1.csv", "shipments_2026_Q2.csv", "shipments_2026_Q3_Q4.csv"]
INVOICE_FILES = ["invoices_2026_H1.csv", "invoices_2026_H2.csv"]
N_SHIPMENTS = 5000
MISMATCH_SHARE = 0.04   # 4 % of the invoices differ from the agreed price


def _mixed_date(day, rng):
    """Two date formats in one column: 09.10.2026 (70 %) and 2026-10-09 (30 %)."""
    return de_date(day) if rng.random() < 0.7 else iso_date(day)


def _write_csv(path, header, rows):
    """Semicolon, Windows-1252, CRLF, and a blank line at the very end."""
    with open(path, "w", encoding="cp1252", newline="") as f:
        f.write(";".join(header) + "\r\n")
        for row in rows:
            f.write((row.raw if row.raw is not None else ";".join(row.cells)) + "\r\n")
        f.write("\r\n")


def _write_truth(name, header, rows):
    with open(TRUTH / name, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def _make_shipments(truth, rng):
    periods_by_combo = {}
    for p in truth.periods:
        periods_by_combo.setdefault((p.customer_id, p.lane_id), []).append(p)
    combos = sorted(periods_by_combo)

    shipments = []
    for _ in range(N_SHIPMENTS):
        combo = rng.choice(combos)
        periods = periods_by_combo[combo]
        first = periods[0].start
        day = first + timedelta(days=rng.randint(0, (LAST_SHIPMENT_DAY - first).days))
        period = next(p for p in periods if p.start <= day <= p.end)
        shipments.append(dict(date=day, customer=combo[0], lane=combo[1], period=period,
                              kg=round(rng.uniform(300, 24000), 1)))
    for _ in range(3):  # a customer that is NOT in customers.csv
        first = truth.periods[0].start
        day = first + timedelta(days=rng.randint(0, (LAST_SHIPMENT_DAY - first).days))
        shipments.append(dict(date=day, customer=UNKNOWN_CUSTOMER_ID, lane=rng.choice(truth.lanes)["lane_id"],
                              period=None, kg=round(rng.uniform(300, 24000), 1)))
    shipments.sort(key=lambda s: (s["date"], s["customer"], s["lane"]))
    for number, s in enumerate(shipments, 1):
        s["id"] = f"SND-2026-{number:05d}"
    return shipments


def _make_invoices(shipments, rng):
    invoices = []
    for s in shipments:
        if s["period"] is None:
            continue
        agreed = agreed_total(s["period"].charges)
        invoices.append(dict(shipment=s, date=s["date"] + timedelta(days=rng.randint(1, 10)),
                             agreed=agreed, billed=agreed, why=""))
    invoices.sort(key=lambda i: (i["date"], i["shipment"]["id"]))
    for number, inv in enumerate(invoices, 1):
        inv["id"] = f"RE-2026-{number:05d}"

    # PLANTED: 3 to 5 percent of the invoices differ from the agreed price
    for index in rng.sample(range(len(invoices)), round(MISMATCH_SHARE * len(invoices))):
        inv = invoices[index]
        charges = inv["shipment"]["period"].charges
        if "FUEL_SURCHARGE" in charges and rng.random() < 0.4:
            inv["billed"] = round(inv["agreed"] - charges["BASE_RATE"] * charges["FUEL_SURCHARGE"], 2)
            inv["why"] = "fuel surcharge missing"
        else:
            factor = rng.choice([rng.uniform(1.03, 1.12), rng.uniform(0.88, 0.97)])
            inv["billed"] = round(inv["agreed"] * factor, 2)
            inv["why"] = f"billed {factor * 100 - 100:+.1f} % against the agreed total"
    return invoices


def build_csv_files(truth, errors):
    rng = make_rng("csv")
    shipments = _make_shipments(truth, rng)
    invoices = _make_invoices(shipments, rng)

    # --- shipment rows, split into 3 files by date
    ship_rows = {name: [] for name in SHIPMENT_FILES}
    for s in shipments:
        known = s["customer"] != UNKNOWN_CUSTOMER_ID
        name = rng.choice(truth.aliases_of(s["customer"])) if known else UNKNOWN_CUSTOMER_NAME
        lane = truth.lane(s["lane"])
        row = Row([s["id"], _mixed_date(s["date"], rng), str(s["customer"]), name,
                   lane["origin_city"], lane["dest_city"], de_decimal(s["kg"], 1)], key=s["id"])
        if not known:
            row.tags.append(("unknown_customer", f"customer {s['customer']} ({UNKNOWN_CUSTOMER_NAME}) "
                                                 "is in shipments but not in customers.csv"))
        file = SHIPMENT_FILES[0] if s["date"].month <= 3 else SHIPMENT_FILES[1] if s["date"].month <= 6 else SHIPMENT_FILES[2]
        ship_rows[file].append(row)

    # --- invoice rows, split into 2 files by invoice date
    inv_rows = {name: [] for name in INVOICE_FILES}
    for inv in invoices:
        amount = de_number(inv["billed"]) if rng.random() < 0.5 else de_decimal(inv["billed"])
        row = Row([inv["id"], _mixed_date(inv["date"], rng), inv["shipment"]["id"],
                   str(inv["shipment"]["customer"]), amount, "EUR"], key=inv["id"])
        if inv["billed"] != inv["agreed"]:
            row.tags.append(("invoice_mismatch", f"invoice {inv['id']}: billed {inv['billed']:.2f} EUR, "
                                                 f"agreed {inv['agreed']:.2f} EUR ({inv['why']})"))
        inv_rows[INVOICE_FILES[0] if inv["date"].month <= 6 else INVOICE_FILES[1]].append(row)

    # PLANTED: duplicate rows (14 of the 20 duplicates)
    for name, count in zip(SHIPMENT_FILES, [2, 2, 3]):
        add_duplicates(ship_rows[name], count, rng, "duplicate_row", lambda r: f"exact copy of shipment {r.key}")
    for name, count in zip(INVOICE_FILES, [3, 4]):
        add_duplicates(inv_rows[name], count, rng, "duplicate_row", lambda r: f"exact copy of invoice {r.key}")

    # PLANTED: one corrupt row (the line is cut off in the middle)
    h2 = inv_rows[INVOICE_FILES[1]]
    victim = h2[rng.choice([i for i, r in enumerate(h2) if r.kind == "data" and not r.tags])]
    line = ";".join(victim.cells)
    victim.raw = line[: len(line) // 2] + "#"
    victim.tags.append(("corrupt_row", f"invoice {victim.key} is cut off after {len(line) // 2} characters, fields missing"))

    summary = []
    for files, rows, header in [(SHIPMENT_FILES, ship_rows, SHIPMENT_HEADER), (INVOICE_FILES, inv_rows, INVOICE_HEADER)]:
        for name in files:
            _write_csv(INCOMING / name, header, rows[name])
            errors.collect(name, rows[name], lambda i: f"line {i + 2}")   # line 1 is the header
            summary.append((name, len(rows[name])))

    _write_truth("shipments.csv", ["shipment_id", "ship_date", "customer_id", "lane_id", "weight_kg"],
                 [[s["id"], s["date"].isoformat(), s["customer"], s["lane"], f"{s['kg']:.1f}"] for s in shipments])
    _write_truth("invoices.csv",
                 ["invoice_id", "shipment_id", "customer_id", "invoice_date", "agreed_amount", "billed_amount", "is_mismatch"],
                 [[i["id"], i["shipment"]["id"], i["shipment"]["customer"], i["date"].isoformat(),
                   f"{i['agreed']:.2f}", f"{i['billed']:.2f}", int(i["billed"] != i["agreed"])] for i in invoices])
    return summary
