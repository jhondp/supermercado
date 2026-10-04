"""Basket ranking over comparable items. Prices are never imputed.

Interfaces:
- ``Ranking(ranked, no_data, comparable_items, insufficient_coverage)``: stores with
  no rows go to ``no_data``; stores with rows but fewer than
  ``ceil(min_coverage * len(basket))`` ok+available basket items go to
  ``insufficient_coverage``. Only covered stores are ranked and used to compute
  ``comparable_items``, so a poorly covered store never shrinks the basket.
- ``rank_stores(current, previous, basket, stores, min_coverage=MIN_COVERAGE)`` with MIN_COVERAGE = 0.8.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from supermercado.domain.models import BasketItem, PriceObservation, Status

# Share of the basket a store must price (ok and available) to be ranked.
MIN_COVERAGE = 0.8


@dataclass(frozen=True)
class StoreTotal:
    store: str
    total: int
    change: int | None


@dataclass(frozen=True)
class Ranking:
    ranked: list[StoreTotal]
    no_data: list[str]
    comparable_items: list[str]
    insufficient_coverage: list[str] = field(default_factory=list)


def _usable(observations: Iterable[PriceObservation]) -> dict[tuple[str, str], PriceObservation]:
    return {(o.store, o.item_id): o for o in observations if o.status == Status.OK and o.available}


def comparable_items(
    observations: Iterable[PriceObservation], stores: Sequence[str], item_ids: Sequence[str]
) -> list[str]:
    """Items for which every given store has an ok, available observation."""
    if not stores:
        return []
    usable = _usable(observations)
    return [i for i in item_ids if all((s, i) in usable for s in stores)]


def basket_total(
    observations: Iterable[PriceObservation], store: str, items: Sequence[BasketItem]
) -> int | None:
    """Sum of unit_price x reference_qty, or None if any item lacks a usable observation."""
    usable = _usable(observations)
    total = Decimal(0)
    for item in items:
        obs = usable.get((store, item.id))
        if obs is None:
            return None
        total += Decimal(obs.unit_price) * Decimal(str(item.reference_qty))
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def rank_stores(
    current: Sequence[PriceObservation],
    previous: Sequence[PriceObservation],
    basket: Sequence[BasketItem],
    stores: Sequence[str],
    min_coverage: float = MIN_COVERAGE,
) -> Ranking:
    present = {o.store for o in current}
    no_data = [s for s in stores if s not in present]
    item_ids = [i.id for i in basket]
    usable = _usable(current)
    needed = math.ceil(min_coverage * len(basket))
    covered: list[str] = []
    insufficient: list[str] = []
    for store in stores:
        if store not in present:
            continue
        count = sum(1 for i in item_ids if (store, i) in usable)
        (covered if count >= needed else insufficient).append(store)
    comparable = comparable_items(current, covered, item_ids)
    if not comparable:
        return Ranking(
            ranked=[],
            no_data=no_data,
            comparable_items=[],
            insufficient_coverage=insufficient,
        )
    chosen = set(comparable)
    items = [i for i in basket if i.id in chosen]
    totals = []
    for store in covered:
        total = basket_total(current, store, items)
        if total is None:  # cannot happen: every covered store has every comparable item
            continue
        before = basket_total(previous, store, items)
        totals.append(StoreTotal(store, total, None if before is None else total - before))
    order = {s: n for n, s in enumerate(stores)}
    totals.sort(key=lambda t: (t.total, order[t.store]))
    return Ranking(
        ranked=totals,
        no_data=no_data,
        comparable_items=comparable,
        insufficient_coverage=insufficient,
    )
