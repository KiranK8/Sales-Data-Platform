"""Settings shared by all generator modules."""
import random
from datetime import date
from pathlib import Path

SEED = 20261018  # fixed seed: every run gives identical files

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data" / "synthetic"
INCOMING = SYNTHETIC / "incoming"
TRUTH = SYNTHETIC / "ground_truth"
LEGACY = SYNTHETIC / "legacy"
LAYOUT_FILE = Path(__file__).with_name("legacy_layout.yaml")

ISSUER = "Rieck Logistik Gruppe"  # shown in the title block of the price lists
LAST_SHIPMENT_DAY = date(2026, 10, 8)
UNKNOWN_CUSTOMER_ID = 9001  # appears in shipments, but not in customers.csv
UNKNOWN_CUSTOMER_NAME = "Nordlicht Frachtkontor GmbH"


def make_rng(name):
    """A separate random generator per module, so changing one module never changes the others."""
    return random.Random(f"{SEED}-{name}")
