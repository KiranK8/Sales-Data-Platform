"""Helpers shared by the Word and PDF generators: which prices go into one document."""
import zipfile
from datetime import datetime

MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]
FIXED_STAMP = (2026, 10, 1, 8, 0, 0)   # every zip entry gets this time, so files are byte-identical on each run


def long_date(day):
    """date(2026, 10, 1) -> '1. Oktober 2026'"""
    return f"{day.day}. {MONTHS[day.month - 1]} {day.year}"


def prices_by_period(truth):
    """{period id: [Price, ...]} in the standard charge order."""
    result = {}
    for price in truth.prices:
        result.setdefault(price.period.pid, []).append(price)
    return result


def toll_per_km(truth, period):
    """The toll rate in EUR per km (the flat toll divided by the lane distance)."""
    return round(period.charges["TOLL"] / truth.lane(period.lane_id)["distance_km"], 2)


def same_dates(truth, period):
    """All periods of this customer that are valid for exactly the same dates (any lane)."""
    return [p for p in truth.periods
            if p.customer_id == period.customer_id and p.start == period.start and p.end == period.end]


def same_terms(truth, period):
    """Periods with the same dates AND the same surcharge values: one contract text fits all of them."""
    def key(p):
        c = p.charges
        return (p.start, p.end, c.get("FUEL_SURCHARGE"), c.get("PEAK_SEASON"), c.get("CURRENCY_ADJUSTMENT"),
                c.get("HANDLING"), toll_per_km(truth, p) if "TOLL" in c else None)
    return [p for p in truth.periods if p.customer_id == period.customer_id and key(p) == key(period)]


def normalise_zip(path):
    """Rewrite a zip (.docx) with fixed entry times. python-docx stamps 'now', which changes every run."""
    with zipfile.ZipFile(path) as zin:
        items = [(info, zin.read(info.filename)) for info in zin.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in items:
            entry = zipfile.ZipInfo(info.filename, date_time=FIXED_STAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = info.external_attr
            zout.writestr(entry, data)


FIXED_DATETIME = datetime(*FIXED_STAMP)
