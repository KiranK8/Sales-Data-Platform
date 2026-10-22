"""STEP 1: the clean truth. Customers, lanes, charges and the agreed prices (no mess here)."""
import csv
from dataclasses import dataclass, field
from datetime import date, timedelta

from faker import Faker

from .config import SEED, make_rng
from .text import translit

DEMO_CUSTOMER = 4711          # the demo example: Hamburg -> Rotterdam
DEMO_LANE = "L01"
QUARTER_STARTS = [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1)]
YEAR_END = date(2026, 12, 31)

# (origin, origin country, destination, destination country, distance km)
LANES = [
    ("Hamburg", "DE", "Rotterdam", "NL", 480),
    ("München", "DE", "Wien", "AT", 435),
    ("Berlin", "DE", "Warszawa", "PL", 575),
    ("Hamburg", "DE", "Kopenhagen", "DK", 340),
    ("Köln", "DE", "Antwerpen", "BE", 210),
    ("Frankfurt", "DE", "Paris", "FR", 570),
    ("Stuttgart", "DE", "Zürich", "CH", 235),
    ("Hannover", "DE", "Hamburg", "DE", 150),
    ("Düsseldorf", "DE", "Amsterdam", "NL", 230),
    ("Nürnberg", "DE", "Praha", "CZ", 300),
    ("Leipzig", "DE", "Berlin", "DE", 190),
    ("Bremen", "DE", "Hamburg", "DE", 120),
    ("Dortmund", "DE", "Bruxelles", "BE", 330),
    ("München", "DE", "Milano", "IT", 575),
    ("Dresden", "DE", "Praha", "CZ", 150),
    ("Frankfurt", "DE", "München", "DE", 390),
    ("Hamburg", "DE", "Berlin", "DE", 290),
    ("Köln", "DE", "Frankfurt", "DE", 190),
    ("Duisburg", "DE", "Rotterdam", "NL", 220),
    ("Berlin", "DE", "Praha", "CZ", 350),
    ("Wien", "AT", "Budapest", "HU", 245),
    ("München", "DE", "Zürich", "CH", 310),
    ("Hamburg", "DE", "Szczecin", "PL", 330),
    ("Stuttgart", "DE", "Straßburg", "FR", 150),
    ("Kassel", "DE", "Hannover", "DE", 160),
]

CHARGE_TYPES = [
    ("BASE_RATE", "Base rate per shipment", "EUR"),
    ("FUEL_SURCHARGE", "Fuel surcharge on the base rate", "PERCENT"),
    ("TOLL", "Road toll (flat)", "EUR"),
    ("PEAK_SEASON", "Peak season surcharge on the base rate", "PERCENT"),
    ("CURRENCY_ADJUSTMENT", "Currency adjustment on the base rate", "PERCENT"),
    ("HANDLING", "Handling / transshipment (flat)", "EUR"),
]
CHARGE_ORDER = [c[0] for c in CHARGE_TYPES]
PCT_CHARGES = ["FUEL_SURCHARGE", "PEAK_SEASON", "CURRENCY_ADJUSTMENT"]

CHARGE_ALIASES = {
    "BASE_RATE": ["Grundpreis", "Basispreis", "Base rate", "Frachtpreis"],
    "FUEL_SURCHARGE": ["DSZ", "Dieselzuschlag", "Treibstoffzuschlag", "Fuel surch.", "Fuel surcharge"],
    "TOLL": ["Maut", "Mautzuschlag", "Toll"],
    "PEAK_SEASON": ["Hochsaison", "Hochsaisonzuschlag", "Peak season"],
    "CURRENCY_ADJUSTMENT": ["Währungszuschlag", "Currency adj.", "CAF"],
    "HANDLING": ["Handling", "Umschlag", "Umschlagspauschale"],
}

SECTORS = [("Logistik", "Log."), ("Transport", "Trans."), ("Spedition", "Sped."),
           ("Frachtkontor", "Fracht."), ("Handel", "Hdl."), ("Logistics", "Logist."), ("Werke", "Wk.")]
LEGAL_FORMS = ["GmbH", "AG", "GmbH & Co. KG", "KG"]


@dataclass
class Period:
    """One price period of a customer+lane: all its charges are valid from `start` to `end`."""
    pid: int
    customer_id: int
    lane_id: str
    start: date
    end: date
    charges: dict
    source: str            # "excel" or "legacy": which system delivers this price
    demo: bool = False


@dataclass
class Price:
    price_id: str
    customer_id: int
    lane_id: str
    charge_type: str
    amount: float          # EUR for BASE_RATE/TOLL/HANDLING, decimal fraction for percent charges
    valid_from: date
    valid_to: date
    period: Period


@dataclass
class Truth:
    customers: list
    aliases: list          # [(raw_name, customer_id)]
    lanes: list
    periods: list
    prices: list
    _alias_by_customer: dict = field(default_factory=dict)

    def aliases_of(self, customer_id):
        return self._alias_by_customer[customer_id]

    def lane(self, lane_id):
        return next(lane for lane in self.lanes if lane["lane_id"] == lane_id)

    def customer(self, customer_id):
        return next(c for c in self.customers if c["customer_id"] == customer_id)


def quarter_of(day):
    return (day.month - 1) // 3 + 1


def agreed_total(charges):
    """Price of one shipment: base rate + percent charges on the base + flat charges."""
    base = charges["BASE_RATE"]
    percent = sum(charges.get(name, 0) for name in PCT_CHARGES)
    return round(base * (1 + percent) + charges.get("TOLL", 0) + charges.get("HANDLING", 0), 2)


def _variants(base, sector, abbreviation, legal):
    """The spelling variants of one customer name."""
    clean = f"{base} {sector} {legal}"
    shouting = f"{base} {sector}".upper() + " " + ("GMBH & CO. KG" if legal == "GmbH" else legal.upper())
    return [clean, translit(f"{base} {sector}"), shouting, translit(f"{base} {abbreviation}")]


def _build_customers(rng):
    fake = Faker("de_DE")
    fake.seed_instance(SEED)
    ids = sorted(rng.sample([i for i in range(1000, 9000) if i != DEMO_CUSTOMER], 39) + [DEMO_CUSTOMER])
    used = {"Müller"}
    customers, aliases = [], []
    for cid in ids:
        if cid == DEMO_CUSTOMER:
            base, sector, abbreviation, legal = "Müller", "Logistik", "Log.", "GmbH"
        else:
            base = fake.last_name()
            while " " in base or base in used:
                base = fake.last_name()
            used.add(base)
            sector, abbreviation = rng.choice(SECTORS)
            legal = rng.choices(LEGAL_FORMS, weights=[6, 1, 2, 1])[0]
        variants = _variants(base, sector, abbreviation, legal)
        if cid != DEMO_CUSTOMER and rng.random() < 0.5:
            variants = variants[:3]          # 3 or 4 variants per customer
        country = "DE" if cid == DEMO_CUSTOMER else rng.choices(
            ["DE", "AT", "NL", "PL", "CH", "FR", "BE", "CZ"], weights=[70, 6, 6, 5, 4, 3, 3, 3])[0]
        customers.append({"customer_id": cid, "clean_name": variants[0], "country": country})
        aliases.extend((v, cid) for v in variants)
    return customers, aliases


def _combo_periods(rng, customer_id, lane, demo):
    """Price history of one customer+lane: 1 to 4 periods that change at quarter starts."""
    if demo:
        starts = [QUARTER_STARTS[0], QUARTER_STARTS[2], QUARTER_STARTS[3]]
    else:
        first = rng.choices(range(4), weights=[70, 15, 10, 5])[0]
        later = list(range(first + 1, 4))
        extra = rng.choices(range(len(later) + 1), weights=[50, 30, 15, 5][: len(later) + 1])[0]
        starts = [QUARTER_STARTS[first]] + [QUARTER_STARTS[i] for i in sorted(rng.sample(later, extra))]

    distance = lane["distance_km"]
    base = round(rng.uniform(2.0, 2.9) * distance / 5) * 5.0
    fuel = rng.randint(12, 20) / 100
    toll = round(distance * rng.uniform(0.08, 0.14), 2)
    handling = float(rng.choice([15, 20, 25, 35, 45]))
    currency = rng.choice([1, 2, 3]) / 100
    has_fuel = demo or rng.random() < 0.95
    has_toll = not demo and rng.random() < 0.5
    has_handling = not demo and rng.random() < 0.3
    has_currency = not demo and rng.random() < 0.1

    periods = []
    for i, start in enumerate(starts):
        end = starts[i + 1] - timedelta(days=1) if i + 1 < len(starts) else YEAR_END
        if i > 0:  # prices drift from one period to the next
            base = round(base * rng.uniform(1.01, 1.06) * 2) / 2
            fuel = round(min(0.25, max(0.08, fuel + rng.choice([-0.02, -0.01, 0.01, 0.02, 0.03]))), 2)
            toll = round(toll * rng.uniform(1.0, 1.05), 2)
        if demo:  # the demo example: Q4 is 1200.00 EUR + 18 % fuel surcharge
            base, fuel = [1150.0, 1175.0, 1200.0][i], [0.14, 0.16, 0.18][i]
        charges = {"BASE_RATE": round(base, 2)}
        if has_fuel:
            charges["FUEL_SURCHARGE"] = fuel
        if has_toll:
            charges["TOLL"] = toll
        if has_currency:
            charges["CURRENCY_ADJUSTMENT"] = currency
        if has_handling:
            charges["HANDLING"] = handling
        if start.month == 10 and not demo and rng.random() < 0.4:
            charges["PEAK_SEASON"] = rng.choice([5, 8, 10]) / 100
        source = "excel" if demo or rng.random() >= 0.2 else "legacy"
        periods.append(Period(0, customer_id, lane["lane_id"], start, end, charges, source, demo))
    return periods


def build_truth():
    rng = make_rng("truth")
    customers, aliases = _build_customers(rng)
    lanes = [
        {"lane_id": f"L{i:02d}", "origin_city": o, "origin_country": oc,
         "dest_city": d, "dest_country": dc, "distance_km": km}
        for i, (o, oc, d, dc, km) in enumerate(LANES, 1)
    ]
    lane_ids = [lane["lane_id"] for lane in lanes]
    lane_by_id = {lane["lane_id"]: lane for lane in lanes}

    periods = []
    for customer in customers:
        cid = customer["customer_id"]
        count = rng.choices([2, 3, 4, 5], weights=[15, 40, 30, 15])[0]
        if cid == DEMO_CUSTOMER:
            chosen = [DEMO_LANE] + rng.sample([x for x in lane_ids if x != DEMO_LANE], count - 1)
        else:
            chosen = rng.sample(lane_ids, count)
        for lane_id in sorted(chosen):
            periods.extend(_combo_periods(rng, cid, lane_by_id[lane_id], cid == DEMO_CUSTOMER and lane_id == DEMO_LANE))

    periods.sort(key=lambda p: (p.customer_id, p.lane_id, p.start))
    prices = []
    for pid, period in enumerate(periods, 1):
        period.pid = pid
        for charge in CHARGE_ORDER:
            if charge in period.charges:
                prices.append(Price(f"P{len(prices) + 1:04d}", period.customer_id, period.lane_id, charge,
                                    period.charges[charge], period.start, period.end, period))

    by_customer = {}
    for raw, cid in aliases:
        by_customer.setdefault(cid, []).append(raw)
    return Truth(customers, aliases, lanes, periods, prices, by_customer)


def _write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def write_truth(truth, folder):
    """Write the clean truth as CSV files into ground_truth/."""
    _write_csv(folder / "customers.csv", ["customer_id", "clean_name", "country"],
               [[c["customer_id"], c["clean_name"], c["country"]] for c in truth.customers])
    _write_csv(folder / "customer_aliases.csv", ["raw_name", "customer_id"], truth.aliases)
    _write_csv(folder / "lanes.csv",
               ["lane_id", "origin_city", "origin_country", "dest_city", "dest_country", "distance_km"],
               [[l["lane_id"], l["origin_city"], l["origin_country"], l["dest_city"], l["dest_country"],
                 l["distance_km"]] for l in truth.lanes])
    _write_csv(folder / "charge_types.csv", ["charge_type", "description", "unit"], CHARGE_TYPES)
    _write_csv(folder / "charge_aliases.csv", ["raw_name", "charge_type"],
               [[alias, ct] for ct in CHARGE_ORDER for alias in CHARGE_ALIASES[ct]])
    _write_csv(folder / "prices.csv",
               ["price_id", "customer_id", "lane_id", "charge_type", "amount", "valid_from", "valid_to"],
               [[p.price_id, p.customer_id, p.lane_id, p.charge_type, f"{p.amount:.2f}",
                 p.valid_from.isoformat(), p.valid_to.isoformat()] for p in truth.prices])
