"""Match rules: filter and rank search candidates for a basket item."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from supermercado.domain.models import BasketItem, Listing
from supermercado.domain.units import compute_unit_price
from supermercado.domain.validation import effective_price

_EPSILON = 1e-9


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _contains_term(name: str, term: str) -> bool:
    pattern = rf"(?<!\w){re.escape(normalize_text(term))}(?!\w)"
    return re.search(pattern, name) is not None


def matches_rules(item: BasketItem, listing: Listing) -> bool:
    if not listing.available or effective_price(listing) is None:
        return False
    if listing.unit != item.unit or not listing.size:
        return False
    if item.rules.size_range is not None:
        low, high = item.rules.size_range
        if not low - _EPSILON <= listing.size <= high + _EPSILON:
            return False
    name = normalize_text(listing.name)
    return not any(_contains_term(name, term) for term in item.rules.exclude)


def filter_candidates(item: BasketItem, listings: Iterable[Listing]) -> list[tuple[Listing, int]]:
    scored = []
    for listing in listings:
        if not matches_rules(item, listing):
            continue
        price = effective_price(listing)
        assert price is not None and listing.size  # guaranteed by matches_rules
        scored.append((listing, compute_unit_price(price, listing.size)))
    return sorted(scored, key=lambda pair: (pair[1], pair[0].sku))
