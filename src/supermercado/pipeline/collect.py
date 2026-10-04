"""Weekly collection: fetch approved SKUs per store, validate, build observations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from supermercado.config import AppConfig
from supermercado.domain.models import PriceObservation, Status
from supermercado.domain.validation import build_observation
from supermercado.stores.base import StoreAdapter

log = logging.getLogger(__name__)

EMPTY_RESULT_REASONS = 3


class EmptyResult(Exception):
    """A store answered but returned no listing for any approved SKU."""


@dataclass(frozen=True)
class StoreFailure:
    store: str
    error_class: str
    message: str
    at: datetime


@dataclass(frozen=True)
class Alert:
    store: str
    item_id: str
    message: str


@dataclass
class CollectResult:
    week: str
    observations: list[PriceObservation] = field(default_factory=list)
    failures: list[StoreFailure] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    # Only stores that produced at least one observation: a rerun must never wipe
    # the existing rows of a store that failed or had every row dropped.
    collected_stores: set[str] = field(default_factory=set)


def iso_week(moment: datetime) -> str:
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


def collect(
    config: AppConfig,
    adapters: Mapping[str, StoreAdapter],
    *,
    now: datetime,
    previous: Mapping[tuple[str, str], int],
) -> CollectResult:
    result = CollectResult(week=iso_week(now))
    for store_id, adapter in adapters.items():
        matches = config.matches_for_store(store_id)
        if not matches:
            log.info("%s: no approved matches, skipping", store_id)
            continue
        skus = list(dict.fromkeys(match.sku for match in matches.values()))
        try:
            listings = adapter.fetch(skus)
            if not listings:
                raise EmptyResult(f"{store_id} returned no listings for {len(skus)} approved SKUs")
        except Exception as exc:  # one store must never block the others
            log.warning("%s failed: %s: %s", store_id, type(exc).__name__, exc)
            result.failures.append(StoreFailure(store_id, type(exc).__name__, str(exc), now))
            continue
        by_sku = {listing.sku: listing for listing in listings}
        store_dropped: list[str] = []
        store_observations = 0
        for item_id, match in matches.items():
            listing = by_sku.get(match.sku)
            if listing is None:
                store_dropped.append(f"{store_id}/{item_id}: sku {match.sku} not returned")
                continue
            item = config.item(item_id)
            try:
                observation = build_observation(
                    week=result.week,
                    scraped_at=now,
                    store=store_id,
                    item=item,
                    match=match,
                    listing=listing,
                    previous_unit_price=previous.get((store_id, item_id)),
                )
            except Exception as exc:  # one malformed listing must never abort the run
                store_dropped.append(
                    f"{store_id}/{item_id}: invalid listing ({type(exc).__name__}: {exc})"
                )
                continue
            if observation is None:
                store_dropped.append(f"{store_id}/{item_id}: missing or non-positive price")
                continue
            if observation.status is Status.SIZE_CHANGED:
                result.alerts.append(
                    Alert(
                        store_id,
                        item_id,
                        f"sku {match.sku}: approved size {match.size:g} {item.unit.value}, "
                        f"store now reports {observation.size:g} {item.unit.value}",
                    )
                )
            result.observations.append(observation)
            result.collected_stores.add(store_id)
            store_observations += 1
        result.dropped.extend(store_dropped)
        if store_observations == 0:
            # Soft blocks and price-less pages answer 200; without this they would be silent.
            reasons = "; ".join(store_dropped[:EMPTY_RESULT_REASONS])
            message = f"{len(listings)} listings returned but none usable: {reasons}"
            log.warning("%s failed: EmptyResult: %s", store_id, message)
            result.failures.append(StoreFailure(store_id, EmptyResult.__name__, message, now))
    for line in result.dropped:
        log.info("dropped %s", line)
    return result
