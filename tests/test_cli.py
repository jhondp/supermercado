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


def test_collect_survives_a_malformed_listing_and_writes_the_report(tmp_path: Path, wired) -> None:
    wired["adapters"]["jumbo"] = FakeAdapter("jumbo", [make_listing(size=-1.0)])
    wired["adapters"]["lider"] = FakeAdapter("lider", [make_listing(sku="007", price=1190)])
    report = tmp_path / "r.json"
    assert run(tmp_path, "collect", "--report", str(report)) == 0
    assert [o.store for o in read_week(tmp_path / "data", "2026-W40")] == ["lider"]
    data = json.loads(report.read_text(encoding="utf-8"))
    assert any(d.startswith("jumbo/rice") for d in data["dropped"])
    assert [(f["store"], f["error_class"]) for f in data["failures"]] == [("jumbo", "EmptyResult")]


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


def test_build_command_renders_site(tmp_path: Path) -> None:
    config_dir = Path(__file__).resolve().parents[1] / "config"
    out = tmp_path / "dist"
    code = cli.main(
        ["--config", str(config_dir), "--data", str(tmp_path / "data"), "build", "--out", str(out)]
    )
    assert code == 0
    assert (out / "index.html").exists()


def test_issue_body_prints_markdown_only_when_there_are_problems(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps({"week": "2026-W40", "failures": [], "alerts": []}))
    assert cli.main(["issue-body", "--report", str(clean)]) == 0
    assert capsys.readouterr().out == ""

    bad = tmp_path / "bad.json"
    failure = {"store": "lider", "error_class": "BlockedError", "message": "x", "at": "t"}
    bad.write_text(json.dumps({"week": "2026-W40", "failures": [failure], "alerts": []}))
    assert cli.main(["issue-body", "--report", str(bad)]) == 0
    assert "lider" in capsys.readouterr().out


def test_propose_rewrites_only_the_proposal_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "matches.yaml").write_text("# approved\n", encoding="utf-8")
    config = make_config(items=[make_item("rice")], stores=("jumbo",))
    adapter = FakeAdapter("jumbo", search_results={"arroz grado 2": [make_listing()]})
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "build_adapters", lambda _config, only=None: {"jumbo": adapter})
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    assert cli.main(["--config", str(config_dir), "propose"]) == 0
    text = (config_dir / "matches.yaml").read_text(encoding="utf-8")
    assert text.startswith("# approved\n")
    assert '#   jumbo: { sku: "1626", size: 1, approved: 2026-09-28 }' in text


def test_propose_writes_a_pr_body_with_store_failures_and_lider_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "matches.yaml").write_text("# approved\n", encoding="utf-8")
    config = make_config(items=[make_item("rice")], stores=("jumbo", "lider"))
    adapters = {
        "jumbo": FakeAdapter("jumbo", error=BlockedError("captcha")),
        "lider": FakeAdapter("lider", supports_search=False),
    }
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "build_adapters", lambda _config, only=None: adapters)
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    body = tmp_path / "body.md"
    assert cli.main(["--config", str(config_dir), "propose", "--body", str(body)]) == 0
    text = body.read_text(encoding="utf-8")
    assert "jumbo" in text and "BlockedError" in text
    assert "Lider" in text and "manual" in text


def test_smoke_exit_code_reflects_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from factories import make_store_config
    from supermercado.config import AppConfig

    config = AppConfig(
        basket=[make_item()], stores={"jumbo": make_store_config("Jumbo", smoke_sku="1626")}
    )
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(
        cli, "build_adapters", lambda _config, only=None: {"jumbo": FakeAdapter("jumbo")}
    )
    assert cli.main(["smoke"]) == 1
    assert "FAILED" in capsys.readouterr().out
