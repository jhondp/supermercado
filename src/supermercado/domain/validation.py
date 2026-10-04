"""Turn a Listing into a validated PriceObservation."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import datetime

from supermercado.domain.models import BasketItem, Listing, Match, PriceObservation, Status
from supermercado.domain.units import compute_unit_price

SIZE_TOLERANCE = 0.01
SUSPICIOUS_CHANGE = 0.5


def effective_price(listing: Listing) -> int | None:
    """Price anyone pays: an unconditional promo below the regular price, else the regular one."""
    if listing.price is None or listing.price <= 0:
        return None
    if listing.promo_price is not None and 0 < listing.promo_price < listing.price:
        return listing.promo_price
    return listing.price


def size_changed(approved: float, observed: float) -> bool:
    return abs(observed - approved) > approved * SIZE_TOLERANCE


def is_suspicious(current: int, previous: int | None) -> bool:
    if previous is None or previous <= 0:
        return False
    return abs(current - previous) > previous * SUSPICIOUS_CHANGE


def build_observation(
    *,
    week: str,
    scraped_at: datetime,
    store: str,
    item: BasketItem,
    match: Match,
    listing: Listing,
    previous_unit_price: int | None,
    location: str = "santiago",
) -> PriceObservation | None:
    """Validate a listing. Returns None when the row must be dropped (missing or non-positive price)."""
    effective = effective_price(listing)
    if effective is None:
        return None
    observed = listing.size if listing.size and listing.unit == item.unit else None
    size = observed if observed is not None else match.size
    unit_price = compute_unit_price(effective, size)
    if observed is not None and size_changed(match.size, observed):
        status = Status.SIZE_CHANGED
    elif is_suspicious(unit_price, previous_unit_price):
        status = Status.SUSPICIOUS
    else:
        status = Status.OK
    card = listing.card_price if listing.card_price and listing.card_price > 0 else None
    return PriceObservation(
        week=week,
        scraped_at=scraped_at,
        location=location,
        store=store,
        item_id=item.id,
        sku=listing.sku,
        product_name=listing.name,
        brand=listing.brand,
        url=listing.url,
        size=size,
        unit=item.unit.value,
        price=listing.price,
        promo_price=effective if effective != listing.price else None,
        card_price=card,
        effective_price=effective,
        unit_price=unit_price,
        available=listing.available,
        status=status,
    )


def apply_clearances(
    observations: Iterable[PriceObservation], cleared: Collection[tuple[str, str, str]]
) -> list[PriceObservation]:
    """Mark manually cleared (week, store, item_id) rows as OK so they can be ranked."""
    result = []
    for obs in observations:
        if obs.status is not Status.OK and (obs.week, obs.store, obs.item_id) in cleared:
            obs = obs.model_copy(update={"status": Status.OK})
        result.append(obs)
    return result
