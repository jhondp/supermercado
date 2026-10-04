"""Parse the generated (commented) proposals section of matches.yaml into candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from supermercado.pipeline.propose import MANUAL_NOTE, MARKER

_ITEM = re.compile(r"^# (?P<item>[a-z0-9_]+):\s*$")
_WEEK = re.compile(r"^# week: (?P<week>\S+)\s*$")
_ENTRY = re.compile(
    r"^#\s+(?P<store>[a-z0-9_]+):\s*"
    r'\{\s*sku:\s*"(?P<sku>[^"]+)",\s*size:\s*(?P<size>\d+(?:\.\d+)?),\s*'
    r"approved:\s*\d{4}-\d{2}-\d{2}\s*\}\s+#\s(?P<note>.+)$"
)
_PRICE = re.compile(r"^\$(?P<price>[\d.]+) -> \$(?P<unit_price>[\d.]+)/(?P<unit>\w+)$")


@dataclass(frozen=True)
class Candidate:
    item_id: str
    store: str
    sku: str
    size: float
    name: str
    brand: str | None
    price: int
    unit_price: int
    unit: str
    url: str | None


@dataclass
class ProposalSection:
    week: str | None = None
    candidates: dict[tuple[str, str], list[Candidate]] = field(default_factory=dict)
    malformed: int = 0

    @property
    def total(self) -> int:
        return sum(len(group) for group in self.candidates.values())


def _clp(text: str) -> int:
    return int(text.replace(".", ""))


def _candidate(item_id: str, match: re.Match[str]) -> Candidate | None:
    parts = match["note"].split(" | ")
    price_at = next((i for i, part in enumerate(parts) if _PRICE.match(part)), None)
    if price_at is None or price_at == 0:
        return None
    price = _PRICE.match(parts[price_at])
    assert price is not None
    before = parts[:price_at]
    name = " | ".join(before[:-1]) if len(before) > 1 else before[0]
    brand = before[-1] if len(before) > 1 else None
    url = " | ".join(parts[price_at + 1 :]) or None
    return Candidate(
        item_id=item_id,
        store=match["store"],
        sku=match["sku"],
        size=float(match["size"]),
        name=name,
        brand=brand,
        price=_clp(price["price"]),
        unit_price=_clp(price["unit_price"]),
        unit=price["unit"],
        url=url,
    )


def parse_proposals(matches_text: str) -> ProposalSection:
    """Candidates grouped by (item_id, store) in file order; unparseable lines are counted."""
    section = ProposalSection()
    if MARKER not in matches_text:
        return section
    item_id: str | None = None
    for line in matches_text.split(MARKER, 1)[1].splitlines():
        stripped = line.strip()
        if not stripped or stripped == MANUAL_NOTE:
            continue
        if week := _WEEK.match(stripped):
            section.week = week["week"]
            continue
        if item := _ITEM.match(stripped):
            item_id = item["item"]
            continue
        entry = _ENTRY.match(stripped)
        candidate = _candidate(item_id, entry) if entry and item_id else None
        if candidate is None:
            section.malformed += 1
            continue
        section.candidates.setdefault((item_id, candidate.store), []).append(candidate)
    return section
