"""STEP 2A: messy Excel price lists (.xlsx), one per quarter, plus a supplement and a re-sent copy."""
import dataclasses
import shutil
from datetime import date, datetime

import xlsxwriter

from .config import INCOMING, ISSUER, make_rng
from .model import Row, add_duplicates
from .text import de_date, de_number, de_percent, de_percent_decimal, iso_date
from .truth import CHARGE_ALIASES, PCT_CHARGES, quarter_of

Q1, Q2, Q3, Q4 = "prices_Q1_2026.xlsx", "prices_Q2_2026.xlsx", "prices_Q3_2026.xlsx", "prices_Q4_2026.xlsx"
SUPPLEMENT = "prices_Q4_2026_Ergaenzung.xlsx"
Q3_RESENT = "prices_Q3_2026_final.xlsx"
COLUMNS = ["customer", "lane", "charge", "amount", "currency", "valid_from", "valid_to"]


def _headers(customer, lane, charge, amount, currency, valid_from, valid_to, notes=None):
    headers = dict(customer=customer, lane=lane, charge=charge, amount=amount, currency=currency,
                   valid_from=valid_from, valid_to=valid_to)
    if notes:
        headers["notes"] = notes
    return headers


# Each file is messy in its own way: other header names, other number/date/percent styles.
SPECS = {
    Q1: dict(quarter=1, stand="02.01.2026", sep=" - ", blanks=1, pct="charge", amount_text=True,
             dates=["de_text"], headers=_headers("Kunde", "Strecke", "Zuschlag", "Betrag", "Währung", "Gültig von", "Gültig bis")),
    Q2: dict(quarter=2, stand="01.04.2026", sep=" > ", blanks=2, pct="amount", amount_text=False,
             dates=["excel_date"], headers=_headers("Customer", "Lane", "Charge", "Amount", "Currency", "Valid from", "Valid to")),
    Q3: dict(quarter=3, stand="01.07.2026", sep="-", blanks=1, pct="amount", amount_text=True,
             dates=["de_text", "iso_text"], headers=_headers("Cust.", "Strecke", "Kostenart", "Preis", "Whg.", "Gültig von", "Gültig bis")),
    Q4: dict(quarter=4, stand="01.10.2026", sep=" - ", blanks=1, pct="charge", amount_text=True,
             dates=["excel_date", "de_text"], notes=True,   # the later file has an extra column
             headers=_headers("Kunde", "Lane", "Zuschlag", "Betrag", "Währung", "Valid from", "Valid to", "Bemerkung")),
    SUPPLEMENT: dict(quarter=4, stand="14.10.2026", sep=" – ", blanks=1, pct="amount", amount_text=True,
                     dates=["de_text"], title_suffix=" – Ergänzung",
                     headers=_headers("Customer", "Strecke", "Charge", "Amount", "Currency", "Gültig von", "Gültig bis")),
}


def _date_cell(day, style):
    if style == "de_text":
        return ("text", de_date(day))
    if style == "iso_text":
        return ("text", iso_date(day))
    return ("date", day)


def _make_row(price, spec, rng, truth, currency="EUR", amount=None):
    """One price as a messy Excel row. Cells are (kind, value) pairs; the writer turns them into cells."""
    amount = price.amount if amount is None else amount
    lane = truth.lane(price.lane_id)
    alias = rng.choice(CHARGE_ALIASES[price.charge_type])
    if price.charge_type in PCT_CHARGES:
        if spec["pct"] == "charge":              # "DSZ 18 %" in the charge cell, amount cell empty
            charge, amount_cell = ("text", f"{alias} {de_percent(amount)}"), ("blank",)
        else:
            charge = ("text", alias)
            amount_cell = ("text", de_percent_decimal(amount)) if spec["amount_text"] else ("pct", amount)
    else:
        charge = ("text", alias)
        amount_cell = ("text", de_number(amount)) if spec["amount_text"] else ("num", amount)
    cells = [
        ("text", rng.choice(truth.aliases_of(price.customer_id))),
        ("text", f"{lane['origin_city']}{spec['sep']}{lane['dest_city']}"),
        charge, amount_cell, ("text", currency),
        _date_cell(price.valid_from, rng.choice(spec["dates"])),
        _date_cell(price.valid_to, rng.choice(spec["dates"])),
    ]
    if spec.get("notes"):
        note = rng.choice(["", "", "", "neu ab 01.10.", "Index angepasst", "gem. Rahmenvertrag"])
        cells.append(("text", note) if note else ("blank",))
    return Row(cells, key=price.price_id, meta={"price": price})


def _put(ws, r, c, cell, fmt_date, fmt_pct):
    kind, value = cell[0], cell[1] if len(cell) > 1 else None
    if kind == "text":
        ws.write_string(r, c, value)
    elif kind == "num":
        ws.write_number(r, c, value)
    elif kind == "pct":
        ws.write_number(r, c, value, fmt_pct)
    elif kind == "date":
        ws.write_datetime(r, c, value, fmt_date)
    # "blank": leave the cell empty


def _write_workbook(path, name, spec, rows, rng):
    """Write the sheet: merged title, title block, empty rows, header, data. Returns (rows, header row no.)."""
    cols = COLUMNS + (["notes"] if spec.get("notes") else [])
    for pos in sorted(rng.sample(range(1, len(rows)), min(rng.randint(2, 4), len(rows) - 1)), reverse=True):
        rows.insert(pos, Row([("blank",)] * len(cols), kind="blank"))   # random empty rows in the table

    title = f"{ISSUER} – Preisliste Q{spec['quarter']} 2026" + spec.get("title_suffix", "")
    wb = xlsxwriter.Workbook(str(path))
    wb.set_properties({"title": title, "author": ISSUER, "created": datetime(2026, 10, 1, 8, 0, 0)})  # fixed: same bytes each run
    ws = wb.add_worksheet("Preisliste")
    fmt_title = wb.add_format({"bold": True, "font_size": 14})
    fmt_head = wb.add_format({"bold": True})
    fmt_date = wb.add_format({"num_format": "dd.mm.yyyy"})
    fmt_pct = wb.add_format({"num_format": "0%"})

    ws.merge_range(0, 0, 0, len(cols) - 1, title, fmt_title)       # merged title cell
    ws.write_string(1, 0, "Preisliste")
    ws.write_string(2, 0, f"Stand: {spec['stand']}")
    header0 = 3 + spec["blanks"]                                     # 0-based row of the header
    for c, key in enumerate(cols):
        ws.write_string(header0, c, spec["headers"][key], fmt_head)
    for i, row in enumerate(rows):
        for c, cell in enumerate(row.cells):
            _put(ws, header0 + 1 + i, c, cell, fmt_date, fmt_pct)
    ws.set_column(0, len(cols) - 1, 24)
    wb.close()
    return rows, header0 + 1


def build_excel_files(truth, errors):
    rng = make_rng("excel")
    prices = [p for p in truth.prices if p.period.source == "excel"]

    # Late delivery: two price periods that start in Q4 arrive in the supplement file instead of the Q4 file.
    q4_periods = sorted({p.period.pid for p in prices if quarter_of(p.valid_from) == 4 and not p.period.demo})
    moved = set(rng.sample(q4_periods, 2))

    rows = {name: [] for name in SPECS}
    for p in prices:
        q = quarter_of(p.valid_from)
        name = SUPPLEMENT if p.period.pid in moved else [Q1, Q2, Q3, Q4][q - 1]
        rows[name].append(_make_row(p, SPECS[name], rng, truth))

    # PLANTED: two overlapping validity periods for the same customer+lane+charge (Q4 file vs supplement)
    candidates = [r for r in rows[Q4] if r.meta["price"].charge_type == "BASE_RATE" and not r.meta["price"].period.demo]
    original = rng.choice(candidates)
    op = original.meta["price"]
    overlap_price = dataclasses.replace(op, amount=round(op.amount * 1.03 / 5) * 5.0,
                                        valid_from=date(2026, 11, 15), valid_to=date(2027, 3, 31))
    overlap = _make_row(overlap_price, SPECS[SUPPLEMENT], rng, truth)
    what = f"customer {op.customer_id} lane {op.lane_id} BASE_RATE"
    original.tags.append(("overlapping_validity",
                          f"{what} valid {op.valid_from}..{op.valid_to} overlaps the period 2026-11-15..2027-03-31 in {SUPPLEMENT}"))
    overlap.tags.append(("overlapping_validity",
                         f"{what} valid 2026-11-15..2027-03-31 ({overlap_price.amount:.2f} EUR) overlaps the period "
                         f"{op.valid_from}..{op.valid_to} ({op.amount:.2f} EUR) in {Q4}"))
    rows[SUPPLEMENT].insert(rng.randint(0, len(rows[SUPPLEMENT])), overlap)

    # PLANTED: one price given in USD instead of EUR (Q2 file)
    pool = [i for i, r in enumerate(rows[Q2]) if r.meta["price"].charge_type == "BASE_RATE"
            and r.meta["price"].customer_id != 4711]
    index = rng.choice(pool)
    up = rows[Q2][index].meta["price"]
    usd = round(up.amount * 1.09, 2)
    rows[Q2][index] = _make_row(up, SPECS[Q2], rng, truth, currency="USD", amount=usd)
    rows[Q2][index].tags.append(("wrong_currency",
                                 f"customer {up.customer_id} lane {up.lane_id} BASE_RATE written as {usd:.2f} USD, "
                                 f"agreed price is {up.amount:.2f} EUR"))

    # PLANTED: duplicate rows inside the Excel files (6 of the 20 duplicates)
    for name, count in [(Q1, 3), (Q2, 2), (Q4, 1)]:
        add_duplicates(rows[name], count, rng, "duplicate_row",
                       lambda r: f"exact copy of an earlier row (price {r.key})")

    summary = []
    for name in [Q1, Q2, Q3, Q4, SUPPLEMENT]:
        final_rows, header_row = _write_workbook(INCOMING / name, name, SPECS[name], rows[name], rng)
        errors.collect(name, final_rows, lambda i, h=header_row: f"row {h + 1 + i}")
        summary.append((name, sum(1 for r in final_rows if r.kind == "data")))
    summary.append((Q3_RESENT, summary[2][1]))

    # PLANTED: the Q3 file delivered twice (identical content, different file name)
    shutil.copyfile(INCOMING / Q3, INCOMING / Q3_RESENT)
    errors.add("duplicate_file", Q3_RESENT, "whole file", f"identical copy of {Q3}, delivered under a second name")
    return summary
