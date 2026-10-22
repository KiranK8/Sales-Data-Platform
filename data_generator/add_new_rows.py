"""Add 20 new shipments and change 5 existing invoices in the legacy database.

Use it to test "load only NEW or CHANGED rows":
    python -m data_generator.add_new_rows            # batch 1
    python -m data_generator.add_new_rows --batch 2  # another batch (different rows)

Safe to run twice: a batch that was already applied changes nothing the second time.
To start from the original database again, run:  python -m data_generator.generate
"""
import argparse
import csv
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from .config import TRUTH, make_rng
from .legacy_db import DB_PATH, ORIGINAL_SHIPMENTS
from .truth import build_truth

NEW_SHIPMENTS, CHANGED_INVOICES = 20, 5


def add_batch(db_path=DB_PATH, batch=1, changes_dir=TRUTH):
    truth = build_truth()
    rng = make_rng(f"add-new-{batch}")
    stamp = lambda k: f"2026-10-18 06:{batch:02d}:{k:02d}"   # when the "legacy system" saved the change
    combos = sorted({(p.customer_id, p.lane_id) for p in truth.periods if p.start <= date(2026, 10, 16)})

    con = sqlite3.connect(db_path)
    changes = []
    first_id = ORIGINAL_SHIPMENTS + (batch - 1) * NEW_SHIPMENTS + 1
    for k in range(NEW_SHIPMENTS):                           # NEW rows: created_at = updated_at = the batch time
        cid, lane_id = rng.choice(combos)
        lane = truth.lane(lane_id)
        day = date(2026, 10, 9) + timedelta(days=rng.randint(0, 7))
        row = (first_id + k, cid, lane["origin_city"], lane["dest_city"], day.isoformat(),
               round(rng.uniform(300, 24000), 1), stamp(k), stamp(k))
        inserted = con.execute("INSERT OR IGNORE INTO shipments VALUES (?,?,?,?,?,?,?,?)", row).rowcount
        if inserted:
            changes.append(("shipments", row[0], "new", f"customer {cid}, {lane['origin_city']}-{lane['dest_city']}, {day}"))

    candidates = [r for r in con.execute(
        "SELECT id, amount, status, updated_at FROM invoices WHERE amount IS NOT NULL AND customer_id IN "
        "(SELECT id FROM customers) ORDER BY id")]
    for k, (invoice_id, amount, status, updated_at) in enumerate(rng.sample(candidates, CHANGED_INVOICES)):
        new_amount = round(amount * rng.uniform(0.96, 1.04), 2)   # always drawn: keeps a re-run in step
        if updated_at == stamp(100 + k):
            continue                                              # this batch was already applied
        con.execute("UPDATE invoices SET amount = ?, status = 'paid', updated_at = ? WHERE id = ?",
                    (new_amount, stamp(100 + k), invoice_id))
        changes.append(("invoices", invoice_id, "changed", f"amount {amount:.2f} -> {new_amount:.2f}, status {status} -> paid"))
    con.commit()
    con.close()

    if changes:   # remember what changed, so you can check that a loader found exactly these rows
        with open(changes_dir / f"db_changes_batch{batch}.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["table", "id", "change", "details"])
            writer.writerows(changes)
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--db", default=str(DB_PATH), help="database file (default: the legacy database)")
    parser.add_argument("--changes-dir", default=str(TRUTH), help="where db_changes_batchN.csv is written")
    args = parser.parse_args()
    changes = add_batch(Path(args.db), args.batch, Path(args.changes_dir))
    new = sum(1 for c in changes if c[2] == "new")
    print(f"batch {args.batch}: {new} new shipments, {len(changes) - new} changed invoices"
          + ("" if changes else " (already applied, nothing to do)"))
    for table, row_id, change, details in changes:
        print(f"  {change:<8}{table}.id={row_id}  {details}")


if __name__ == "__main__":
    main()
