"""STEP 2C: legacy tool dumps: fixed-width .dat files without header (layout: legacy_layout.yaml)."""
from datetime import datetime

import yaml

from .config import INCOMING, LAYOUT_FILE, make_rng
from .text import translit
from .truth import CHARGE_ORDER, DEMO_CUSTOMER, DEMO_LANE, PCT_CHARGES, quarter_of

# One export file per quarter start, a late small export with the demo example, and an empty one.
EXPORT_BY_QUARTER = {1: "export_20251230.dat", 2: "export_20260330.dat", 3: "export_20260629.dat", 4: "export_20260929.dat"}
DEMO_EXPORT = "export_20261009.dat"
EMPTY_EXPORT = "export_20261016.dat"

CHARGE_LABELS = {"BASE_RATE": "BASE RATE", "TOLL": "TOLL", "HANDLING": "HANDLING",
                 "FUEL_SURCHARGE": "FUEL SURCH.", "PEAK_SEASON": "PEAK SEASON", "CURRENCY_ADJUSTMENT": "CURR ADJ."}


def load_layout():
    with open(LAYOUT_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def lane_code(lane):
    return f"{translit(lane['origin_city'])[:3].upper()}-{translit(lane['dest_city'])[:3].upper()}"


def charge_text(charge_type, amount):
    label = CHARGE_LABELS[charge_type]
    return f"{label} {amount:.2f}" if charge_type in PCT_CHARGES else label


def format_record(layout, values):
    """Build one fixed-width line from python values, exactly as the layout says."""
    parts = []
    for col in layout["columns"]:
        value, kind, width = values[col["name"]], col["type"], col["width"]
        if kind == "text":
            text = str(value)[:width].ljust(width)
        elif kind == "int":
            text = str(int(value)).zfill(width)
        elif kind == "cents":
            text = str(round(value * 100)).zfill(width)
        else:  # date_ddmmyy
            text = value.strftime("%d%m%y")
        assert len(text) == width, f"{col['name']} does not fit: {text!r}"
        parts.append(text)
    return "".join(parts)


def parse_record(layout, line):
    """Read one line back with the same layout (this is what a loader will do)."""
    values = {}
    for col in layout["columns"]:
        text = line[col["start"] - 1: col["start"] - 1 + col["width"]]
        if col["type"] == "text":
            values[col["name"]] = text.strip()
        elif col["type"] == "int":
            values[col["name"]] = int(text)
        elif col["type"] == "cents":
            values[col["name"]] = int(text) / 100
        else:
            values[col["name"]] = datetime.strptime(text, "%d%m%y").date()
    return values


def _record(layout, price, truth, rng):
    name = translit(rng.choice(truth.aliases_of(price.customer_id))).upper()
    is_pct = price.charge_type in PCT_CHARGES
    return format_record(layout, dict(
        record_type="PR", customer_no=price.customer_id, customer_name=name,
        lane_code=lane_code(truth.lane(price.lane_id)), charge_text=charge_text(price.charge_type, price.amount),
        amount=0 if is_pct else price.amount, valid_from=price.valid_from, valid_to=price.valid_to, currency="EUR"))


def _write_lines(path, lines):
    with open(path, "w", encoding="ascii", newline="") as f:
        for line in lines:
            f.write(line + "\r\n")


def build_legacy_files(truth, errors):
    rng = make_rng("legacy")
    layout = load_layout()
    order = {name: i for i, name in enumerate(CHARGE_ORDER)}
    legacy = sorted((p for p in truth.prices if p.period.source == "legacy"),
                    key=lambda p: (p.customer_id, p.lane_id, p.valid_from, order[p.charge_type]))

    summary = []
    for quarter, name in EXPORT_BY_QUARTER.items():
        lines = [_record(layout, p, truth, rng) for p in legacy if quarter_of(p.valid_from) == quarter]
        _write_lines(INCOMING / name, lines)
        summary.append((name, len(lines)))

    # The demo example (customer 4711, Hamburg -> Rotterdam, Q4) also arrives from the old tool.
    demo = [p for p in truth.prices if p.customer_id == DEMO_CUSTOMER and p.lane_id == DEMO_LANE
            and p.valid_from.month == 10 and p.charge_type in ("BASE_RATE", "FUEL_SURCHARGE")]
    _write_lines(INCOMING / DEMO_EXPORT, [_record(layout, p, truth, rng) for p in demo])
    summary.append((DEMO_EXPORT, len(demo)))

    # PLANTED: an empty file (0 bytes)
    (INCOMING / EMPTY_EXPORT).write_bytes(b"")
    errors.add("empty_file", EMPTY_EXPORT, "whole file", "file has 0 bytes")
    summary.append((EMPTY_EXPORT, 0))
    return summary
