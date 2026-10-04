"""Test data builders shared across the suite."""

from __future__ import annotations

from datetime import date

from supermercado.domain.models import (
    BasketItem,
    Category,
    Listing,
    Match,
    MatchRules,
    Unit,
)


def make_item(
    item_id: str = "rice",
    *,
    unit: Unit = Unit.KG,
    reference_qty: float = 1.0,
    category: Category = Category.PANTRY,
    name: str = "Arroz grado 2",
    search: str = "arroz grado 2",
    size_range: tuple[float, float] | None = None,
    exclude: tuple[str, ...] = (),
) -> BasketItem:
    return BasketItem(
        id=item_id,
        name=name,
        category=category,
        unit=unit,
        reference_qty=reference_qty,
        search=search,
        rules=MatchRules(size_range=size_range, exclude=list(exclude)),
    )


def make_listing(**overrides: object) -> Listing:
    data: dict[str, object] = {
        "sku": "1626",
        "name": "Arroz Grado 2 Tucapel 1 kg",
        "brand": "Tucapel",
        "url": "https://www.jumbo.cl/arroz-grado-2-tucapel-1-kg/p",
        "size": 1.0,
        "unit": Unit.KG,
        "price": 1810,
    }
    data.update(overrides)
    return Listing(**data)


def make_match(sku: str = "1626", *, size: float = 1.0, url: str | None = None) -> Match:
    return Match(sku=sku, size=size, approved=date(2026, 10, 4), url=url)
