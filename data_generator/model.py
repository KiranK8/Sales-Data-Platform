"""Shared building blocks: a table row that can carry planted-error tags, and the error log."""
from dataclasses import dataclass, field


@dataclass
class Row:
    cells: list
    kind: str = "data"          # "data" or "blank"
    raw: str | None = None      # set for a corrupt row: written exactly as is
    key: str = ""               # readable id (shipment id, invoice id, price id)
    meta: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)  # [(error_type, description)]

    def copy_of(self):
        """An exact copy, WITHOUT the tags (tags describe the copy, not the original)."""
        return Row(list(self.cells), self.kind, self.raw, self.key, dict(self.meta))


class ErrorLog:
    """Collects every planted error. Row numbers are looked up AFTER the final row order is known."""

    def __init__(self):
        self.items = []

    def add(self, error_type, file, location, description):
        self.items.append(
            {"type": error_type, "file": file, "location": location, "description": description}
        )

    def collect(self, file, rows, location_of):
        for index, row in enumerate(rows):
            for error_type, description in row.tags:
                self.add(error_type, file, location_of(index), description)


def add_duplicates(rows, count, rng, error_type, describe):
    """Insert `count` exact copies of random untagged rows, a few rows after the original."""
    candidates = [i for i, r in enumerate(rows) if r.kind == "data" and not r.tags and r.raw is None]
    for i in sorted(rng.sample(candidates, count), reverse=True):
        copy = rows[i].copy_of()
        copy.tags.append((error_type, describe(rows[i])))
        rows.insert(min(i + 1 + rng.randint(0, 5), len(rows)), copy)
