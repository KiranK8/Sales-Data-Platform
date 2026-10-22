"""Tests for the synthetic data generator (they use the in-memory truth, no files needed)."""
from datetime import date

from data_generator.legacy_files import charge_text, format_record, lane_code, load_layout, parse_record
from data_generator.text import de_number, translit
from data_generator.truth import CHARGE_ALIASES, CHARGE_ORDER, agreed_total, build_truth


def test_truth_is_identical_on_every_run():
    assert build_truth().prices == build_truth().prices


def test_demo_example_is_in_the_truth():
    prices = {(p.charge_type): p for p in build_truth().prices
              if p.customer_id == 4711 and p.lane_id == "L01" and p.valid_from == date(2026, 10, 1)}
    assert prices["BASE_RATE"].amount == 1200.00
    assert prices["FUEL_SURCHARGE"].amount == 0.18
    assert prices["BASE_RATE"].valid_to == date(2026, 12, 31)
    assert agreed_total({"BASE_RATE": 1200.0, "FUEL_SURCHARGE": 0.18}) == 1416.00


def test_sizes():
    truth = build_truth()
    assert len(truth.customers) == 40 and len(truth.lanes) == 25
    assert 500 <= len(truth.prices) <= 750
    assert all(3 <= sum(1 for _, c in truth.aliases if c == cu["customer_id"]) <= 4 for cu in truth.customers)


def test_price_periods_of_one_combo_do_not_overlap():
    periods = {}
    for p in build_truth().periods:
        periods.setdefault((p.customer_id, p.lane_id), []).append(p)
    for combo in periods.values():
        for earlier, later in zip(combo, combo[1:]):
            assert earlier.end < later.start


def test_all_charge_aliases_belong_to_a_known_charge_type():
    assert set(CHARGE_ALIASES) == set(CHARGE_ORDER)


def test_german_number_and_umlaut_helpers():
    assert de_number(1200.5) == "1.200,50"
    assert translit("Müller Straße") == "Mueller Strasse"


def test_legacy_layout_has_no_gaps_and_matches_record_length():
    layout = load_layout()
    position = 1
    for col in layout["columns"]:
        assert col["start"] == position
        position += col["width"]
    assert position - 1 == layout["record_length"]


def test_lane_codes_are_unique():
    lanes = build_truth().lanes
    assert len({lane_code(lane) for lane in lanes}) == len(lanes)


def test_legacy_record_round_trip():
    layout = load_layout()
    values = dict(record_type="PR", customer_no=4711, customer_name="MUELLER LOGISTIK GMBH", lane_code="HAM-ROT",
                  charge_text=charge_text("FUEL_SURCHARGE", 0.18), amount=0, valid_from=date(2026, 10, 1),
                  valid_to=date(2026, 12, 31), currency="EUR")
    line = format_record(layout, values)
    assert len(line) == layout["record_length"]
    back = parse_record(layout, line)
    assert back["charge_text"] == "FUEL SURCH. 0.18" and back["valid_from"] == date(2026, 10, 1)
    assert back["customer_no"] == 4711 and back["amount"] == 0
    base = parse_record(layout, format_record(layout, {**values, "charge_text": "BASE RATE", "amount": 1200.0}))
    assert base["amount"] == 1200.0
