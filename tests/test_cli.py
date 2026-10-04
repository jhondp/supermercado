import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factories import make_config, make_item, make_listing, make_match
from fakes import FakeAdapter
from supermercado import cli
from supermercado.config import ConfigError
from supermercado.pipeline.storage import read_week
from supermercado.stores.base import BlockedError

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):
    config = make_config(
        items=[make_item("rice")],
        stores=("jumbo", "lider"),
        matches={
            "rice": {
                "jumbo": make_match("1626"),
                "lider": make_match("007", url="https://super.lider.cl/ip/x/007"),
            }
        },
    )
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing()]),
        "lider": FakeAdapter("lider", error=BlockedError("captcha")),
    }
    calls: dict[str, object] = {"adapters": adapters}

    def fake_build_adapters(_config, only=None):
        calls["only"] = only
        return {k: v for k, v in adapters.items() if only in (None, k)}

    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "build_adapters", fake_build_adapters)
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    return calls


def run(tmp_path: Path, *extra: str) -> int:
    return cli.main(
        ["--config", str(tmp_path / "config"), "--data", str(tmp_path / "data"), *extra]
    )


def test_collect_writes_snapshot_and_report(tmp_path: Path, wired) -> None:
    report = tmp_path / "build" / "report.json"
    assert run(tmp_path, "collect", "--report", str(report)) == 0
    assert [o.store for o in read_week(tmp_path / "data", "2026-W40")] == ["jumbo"]
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["week"] == "2026-W40"
    assert [(f["store"], f["error_class"]) for f in data["failures"]] == [("lider", "BlockedError")]


def test_collect_forwards_the_store_filter(tmp_path: Path, wired) -> None:
    assert run(tmp_path, "collect", "--store", "jumbo", "--report", str(tmp_path / "r.json")) == 0
    assert wired["only"] == "jumbo"


def test_rerun_with_dropped_store_keeps_its_existing_rows(tmp_path: Path, wired) -> None:
    report = str(tmp_path / "r.json")
    wired["adapters"]["lider"] = FakeAdapter("lider", [make_listing(sku="007", price=1190)])
    assert run(tmp_path, "collect", "--report", report) == 0
    assert {o.store for o in read_week(tmp_path / "data", "2026-W40")} == {"jumbo", "lider"}
    # rerun: lider answers but its row has no price, so it is dropped
    wired["adapters"]["lider"] = FakeAdapter("lider", [make_listing(sku="007", price=None)])
    assert run(tmp_path, "collect", "--report", report) == 0
    rows = {(o.store, o.unit_price) for o in read_week(tmp_path / "data", "2026-W40")}
    assert rows == {("jumbo", 1810), ("lider", 1190)}


def test_config_error_exits_with_code_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_path):
        raise ConfigError("bad basket")

    monkeypatch.setattr(cli, "load_config", broken)
    assert run(tmp_path, "collect") == 2
