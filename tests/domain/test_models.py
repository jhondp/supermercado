from datetime import date

import pytest
from pydantic import ValidationError

from factories import make_item, make_listing
from supermercado.domain.models import Match, MatchRules


def test_listing_is_immutable() -> None:
    listing = make_listing()
    with pytest.raises(ValidationError):
        listing.price = 1  # type: ignore[misc]


def test_listing_allows_missing_price() -> None:
    assert make_listing(price=None).price is None


def test_match_rejects_numeric_sku() -> None:
    with pytest.raises(ValidationError):
        Match(sku=780142021013, size=1.0, approved=date(2026, 10, 4))  # type: ignore[arg-type]


def test_rules_reject_inverted_size_range() -> None:
    with pytest.raises(ValidationError):
        MatchRules(size_range=(1.0, 0.9))


def test_basket_item_requires_positive_reference_qty() -> None:
    with pytest.raises(ValidationError):
        make_item(reference_qty=0)
