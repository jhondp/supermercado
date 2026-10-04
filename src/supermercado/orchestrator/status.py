"""Snapshot of the project state and the recommended next menu option."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from supermercado.config import ConfigError, load_config
from supermercado.domain.ranking import MIN_COVERAGE
from supermercado.orchestrator.paths import Paths
from supermercado.orchestrator.proposals import parse_proposals
from supermercado.pipeline.collect import iso_week
from supermercado.pipeline.storage import list_weeks

STORE_ORDER = ("jumbo", "santa_isabel", "tottus", "acuenta", "unimarc", "lider")

PROPOSE, APPROVE, COLLECT, BUILD, VIEW = 1, 2, 3, 4, 5


@dataclass(frozen=True)
class Status:
    approved: dict[str, int]
    basket_size: int
    threshold: int
    pending: int
    proposal_week: str | None
    last_week: str | None
    current_week: str
    site_built: bool
    data_newer_than_site: bool
    report: dict[str, Any] | None
    store_names: dict[str, str]
    pending_by_store: dict[str, int]
    config_error: str | None = None
    malformed_proposals: int = 0

    @property
    def total_approved(self) -> int:
        return sum(self.approved.values())


def threshold_for(basket_size: int) -> int:
    return math.ceil(MIN_COVERAGE * basket_size)


def _read_report(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _newest_mtime(paths: Paths) -> float | None:
    files = list(paths.prices.glob("*.parquet")) if paths.prices.is_dir() else []
    return max((f.stat().st_mtime for f in files), default=None)


def compute_status(paths: Paths, *, now: datetime) -> Status:
    approved = dict.fromkeys(STORE_ORDER, 0)
    store_names = {store: store for store in STORE_ORDER}
    basket_size = 0
    approved_pairs: set[tuple[str, str]] = set()
    config_error: str | None = None
    try:
        config = load_config(paths.config)
    except ConfigError as exc:
        config_error = str(exc)
    else:
        basket_size = len(config.basket)
        store_names.update({store: cfg.name for store, cfg in config.stores.items()})
        for item_id, per_store in config.matches.items():
            for store in per_store:
                approved_pairs.add((item_id, store))
                if store in approved:
                    approved[store] += 1
    try:
        matches_text = paths.matches.read_text(encoding="utf-8")
    except OSError:
        matches_text = ""
    section = parse_proposals(matches_text)
    pending_by_store = dict.fromkeys(STORE_ORDER, 0)
    for (item_id, store), group in section.candidates.items():
        if (item_id, store) not in approved_pairs:
            pending_by_store[store] = pending_by_store.get(store, 0) + len(group)
    weeks = list_weeks(paths.data) if paths.prices.is_dir() else []
    index = paths.dist / "index.html"
    site_built = index.is_file()
    data_mtime = _newest_mtime(paths)
    data_newer = data_mtime is not None and (not site_built or data_mtime > index.stat().st_mtime)
    return Status(
        approved=approved,
        basket_size=basket_size,
        threshold=threshold_for(basket_size),
        pending=sum(pending_by_store.values()),
        proposal_week=section.week,
        last_week=weeks[-1] if weeks else None,
        current_week=iso_week(now),
        site_built=site_built,
        data_newer_than_site=data_newer,
        report=_read_report(paths.report),
        store_names=store_names,
        pending_by_store=pending_by_store,
        config_error=config_error,
        malformed_proposals=section.malformed,
    )


def recommend_next(status: Status) -> int:
    """Menu option that moves the project forward from `status`."""
    if status.pending == 0 and status.total_approved == 0:
        return PROPOSE
    short_with_candidates = any(
        count > 0 and status.approved.get(store, 0) < status.threshold
        for store, count in status.pending_by_store.items()
    )
    if status.pending > 0 and short_with_candidates:
        return APPROVE
    if status.last_week != status.current_week:
        return COLLECT
    if not status.site_built or status.data_newer_than_site:
        return BUILD
    return VIEW
