import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from supermercado.orchestrator.paths import Paths
from supermercado.orchestrator.status import (
    STORE_ORDER,
    Status,
    compute_status,
    recommend_next,
)

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)  # ISO week 2026-W40


@pytest.fixture
def paths(tmp_path: Path, config_dir: Path) -> Paths:
    return Paths.from_root(tmp_path)


def approve_rice_jumbo(paths: Paths) -> None:
    text = paths.matches.read_text(encoding="utf-8")
    entry = 'rice:\n  jumbo: { sku: "100", size: 1.0, approved: 2026-10-04 }\n'
    paths.matches.write_text(entry + text, encoding="utf-8")


def test_paths_default_to_the_root_and_accept_overrides(tmp_path: Path) -> None:
    paths = Paths.from_root(tmp_path)
    assert paths.config == tmp_path / "config"
    assert paths.data == tmp_path / "data"
    assert paths.report == tmp_path / "build" / "report.json"
    assert paths.dist == tmp_path / "dist"
    assert paths.matches == tmp_path / "config" / "matches.yaml"
    custom = Paths.from_root(tmp_path, config=tmp_path / "c", data=tmp_path / "d")
    assert (custom.config, custom.data) == (tmp_path / "c", tmp_path / "d")


def test_fresh_project_status(paths: Paths) -> None:
    status = compute_status(paths, now=NOW)
    assert list(status.approved) == list(STORE_ORDER)
    assert set(status.approved.values()) == {0}
    assert status.basket_size == 23
    assert status.threshold == 19
    assert status.pending == 4
    assert status.proposal_week == "2026-W40"
    assert status.last_week is None
    assert status.current_week == "2026-W40"
    assert status.site_built is False
    assert status.report is None
    assert status.config_error is None
    assert status.store_names["santa_isabel"] == "Santa Isabel"


def test_approved_pairs_count_and_stop_being_pending(paths: Paths) -> None:
    approve_rice_jumbo(paths)
    status = compute_status(paths, now=NOW)
    assert status.approved["jumbo"] == 1
    assert status.pending == 2  # rice/jumbo's two candidates are no longer pending


def test_last_week_site_and_report_are_detected(paths: Paths) -> None:
    prices = paths.data / "prices"
    prices.mkdir(parents=True)
    (prices / "2026-W39.parquet").write_bytes(b"x")
    (prices / "2026-W40.parquet").write_bytes(b"x")
    paths.dist.mkdir()
    (paths.dist / "index.html").write_text("<html>", encoding="utf-8")
    paths.report.parent.mkdir()
    paths.report.write_text(json.dumps({"week": "2026-W40", "failures": []}), encoding="utf-8")
    os.utime(prices / "2026-W39.parquet", (900, 900))
    os.utime(prices / "2026-W40.parquet", (1000, 1000))
    os.utime(paths.dist / "index.html", (2000, 2000))
    status = compute_status(paths, now=NOW)
    assert status.last_week == "2026-W40"
    assert status.site_built is True
    assert status.data_newer_than_site is False
    assert status.report == {"week": "2026-W40", "failures": []}
    os.utime(prices / "2026-W40.parquet", (3000, 3000))
    assert compute_status(paths, now=NOW).data_newer_than_site is True


def test_broken_config_is_reported_not_raised(paths: Paths) -> None:
    paths.matches.write_text("rice:\n  jumbo: { sku: 1 }\n", encoding="utf-8")
    status = compute_status(paths, now=NOW)
    assert status.config_error
    assert set(status.approved.values()) == {0}


BASE = Status(
    approved=dict.fromkeys(STORE_ORDER, 0),
    basket_size=23,
    threshold=19,
    pending=0,
    proposal_week=None,
    last_week=None,
    current_week="2026-W40",
    site_built=False,
    data_newer_than_site=False,
    report=None,
    store_names={s: s for s in STORE_ORDER},
    pending_by_store=dict.fromkeys(STORE_ORDER, 0),
)


def with_approved(count: int) -> dict[str, int]:
    return dict.fromkeys(STORE_ORDER, count)


def test_recommend_propose_when_nothing_exists() -> None:
    assert recommend_next(BASE) == 1


def test_recommend_approve_when_proposals_are_pending_and_stores_are_short() -> None:
    status = replace(BASE, pending=10, pending_by_store={**BASE.pending_by_store, "jumbo": 10})
    assert recommend_next(status) == 2


def test_recommend_collect_when_this_week_has_no_data() -> None:
    status = replace(BASE, approved=with_approved(20), last_week="2026-W39")
    assert recommend_next(status) == 3


def test_recommend_collect_when_pending_proposals_belong_to_complete_stores() -> None:
    status = replace(
        BASE,
        approved=with_approved(20),
        pending=3,
        pending_by_store={**BASE.pending_by_store, "jumbo": 3},
    )
    assert recommend_next(status) == 3


def test_recommend_build_when_data_is_newer_than_the_site() -> None:
    status = replace(BASE, approved=with_approved(20), last_week="2026-W40")
    assert recommend_next(status) == 4
    status = replace(status, site_built=True, data_newer_than_site=True)
    assert recommend_next(status) == 4


def test_recommend_view_when_everything_is_current() -> None:
    status = replace(BASE, approved=with_approved(20), last_week="2026-W40", site_built=True)
    assert recommend_next(status) == 5
