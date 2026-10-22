"""STEP 3C: the legacy shipping database (SQLite). Every table has created_at / updated_at."""
import sqlite3
from datetime import date, datetime, time, timedelta

from .config import LEGACY, make_rng
from .truth import DB_DUPLICATE_ID, DB_DUPLICATE_NAME, DEMO_CUSTOMER, agreed_total

DB_PATH = LEGACY / "legacy_shipping.db"
ORIGINAL_SHIPMENTS = 1200       # the original shipments are 2025; add_new_rows.py appends newer ones
TENDERS, TENDERS_WON = 80, 34   # 34 of 80 = 42.5 % win rate
ORPHAN_CUSTOMER_ID = 9002       # a shipment whose customer is not in the customers table

SCHEMA = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE shipments (id INTEGER PRIMARY KEY, customer_id INTEGER, origin TEXT, destination TEXT,
                        ship_date TEXT, weight_kg REAL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE invoices  (id INTEGER PRIMARY KEY, shipment_id INTEGER, customer_id INTEGER, invoice_date TEXT,
                        amount REAL, status TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE tenders   (id INTEGER PRIMARY KEY, customer_id INTEGER, lanes TEXT, offered_price REAL,
                        status TEXT, offer_date TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX idx_customers_updated ON customers(updated_at);
CREATE INDEX idx_shipments_updated ON shipments(updated_at);
CREATE INDEX idx_invoices_updated  ON invoices(updated_at);
CREATE INDEX idx_tenders_updated   ON tenders(updated_at);
"""


def _stamp(rng, day):
    """A time on the given day, as '2025-03-14 09:21:07'."""
    return datetime.combine(day, time(rng.randint(6, 18), rng.randint(0, 59), rng.randint(0, 59))).strftime("%Y-%m-%d %H:%M:%S")


def _random_day(rng, start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _updated(rng, created, latest):
    """Most rows were never changed (updated_at = created_at); some were changed later."""
    if rng.random() < 0.8:
        return created
    day = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").date()
    return _stamp(rng, _random_day(rng, day, max(day, latest)))


def build_legacy_db(truth, errors, path=DB_PATH):
    rng = make_rng("legacy-db")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    file_name = f"legacy/{path.name}"

    # --- customers: the legacy spelling, plus one duplicate record of customer 4711
    spelling = {cid: raw for raw, cid in truth.db_aliases[:-1]}
    customers = []
    for c in truth.customers:
        created = _stamp(rng, _random_day(rng, date(2019, 1, 1), date(2024, 12, 31)))
        customers.append((c["customer_id"], spelling[c["customer_id"]], c["country"], created,
                          _updated(rng, created, date(2026, 9, 30))))
    created = _stamp(rng, date(2023, 5, 8))
    customers.append((DB_DUPLICATE_ID, DB_DUPLICATE_NAME, "DE", created, created))
    errors.add("duplicate_customer", file_name, f"customers id={DB_DUPLICATE_ID}",
               f"second record of customer {DEMO_CUSTOMER} ('{DB_DUPLICATE_NAME}') under another number")

    # --- 2025 shipments and invoices (prices of the year before: about 5 % lower than the 2026 start prices)
    combos = {}
    for p in truth.periods:
        combos.setdefault((p.customer_id, p.lane_id), p)   # first period of each combination (list is sorted)
    keys = sorted(combos)
    raw = [(_random_day(rng, date(2025, 1, 2), date(2025, 12, 30)), *rng.choice(keys), round(rng.uniform(300, 24000), 1))
           for _ in range(ORIGINAL_SHIPMENTS)]
    raw.sort(key=lambda r: (r[0], r[1], r[2]))

    shipments, invoices, only_4711 = [], [], 0
    orphan_at = rng.choice([i for i, r in enumerate(raw) if r[1] != DEMO_CUSTOMER])
    null_ids = rng.sample([i for i in range(1, ORIGINAL_SHIPMENTS + 1) if i != orphan_at + 1], 2)
    for number, (day, cid, lane_id, kg) in enumerate(raw, 1):
        lane = truth.lane(lane_id)
        if cid == DEMO_CUSTOMER and only_4711 < 12:      # the first 12 shipments of 4711 use the duplicate record
            cid, only_4711 = DB_DUPLICATE_ID, only_4711 + 1
        if number - 1 == orphan_at:
            cid = ORPHAN_CUSTOMER_ID
            errors.add("orphan_customer", file_name, f"shipments id={number}",
                       f"customer_id {ORPHAN_CUSTOMER_ID} does not exist in the customers table")
        created = _stamp(rng, day)
        shipments.append((number, cid, lane["origin_city"], lane["dest_city"], day.isoformat(), kg, created,
                          _updated(rng, created, date(2026, 9, 30))))
        agreed = agreed_total(combos[(raw[number - 1][1], lane_id)].charges)
        amount = None if number in null_ids else round(agreed * rng.uniform(0.93, 0.97), 2)
        invoice_day = day + timedelta(days=rng.randint(1, 10))
        created = _stamp(rng, invoice_day)
        invoices.append((number, number, cid, invoice_day.isoformat(), amount, "paid" if rng.random() < 0.85 else "open",
                         created, _updated(rng, created, date(2026, 9, 30))))
        if amount is None:
            errors.add("null_amount", file_name, f"invoices id={number}", "invoice amount is NULL")

    # --- tenders: offers to customers; exactly TENDERS_WON of them won
    won = set(rng.sample(range(TENDERS), TENDERS_WON))
    tenders = []
    days = sorted(_random_day(rng, date(2025, 1, 6), date(2026, 9, 30)) for _ in range(TENDERS))
    for i, day in enumerate(days):
        lanes = rng.sample(truth.lanes, 1 if rng.random() < 0.8 else 2)
        price = round(sum(lane["distance_km"] * rng.uniform(2.0, 2.9) for lane in lanes) / len(lanes) / 5) * 5.0
        created = _stamp(rng, day)
        decided = _stamp(rng, day + timedelta(days=rng.randint(3, 40)))
        tenders.append((i + 1, rng.choice(truth.customers)["customer_id"],
                        " ; ".join(f"{lane['origin_city']}-{lane['dest_city']}" for lane in lanes), price,
                        "won" if i in won else "lost", day.isoformat(), created, decided))

    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", customers)
    con.executemany("INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?)", shipments)
    con.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)", invoices)
    con.executemany("INSERT INTO tenders VALUES (?,?,?,?,?,?,?,?)", tenders)
    con.commit()
    con.close()
    return [(f"{path.name}: customers", len(customers)), (f"{path.name}: shipments", len(shipments)),
            (f"{path.name}: invoices", len(invoices)), (f"{path.name}: tenders", len(tenders))]
