from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from orchestrator_samples import HEAD, PROPOSALS
from supermercado.config import load_config
from supermercado.orchestrator import approve
from supermercado.orchestrator.approve import (
    ApproveError,
    NewMatch,
    apply_matches,
    format_entry,
    write_matches,
)
from supermercado.pipeline.propose import MARKER

TODAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, 15, 30, 12, tzinfo=UTC)


def new(item: str = "rice", store: str = "jumbo", sku: str = "100", **kw: object) -> NewMatch:
    return NewMatch(
        item_id=item, store=store, sku=sku, size=kw.pop("size", 1.0), approved=TODAY, **kw
    )  # type: ignore[arg-type]


def never(_item: str, _store: str) -> bool:
    return False


def always(_item: str, _store: str) -> bool:
    return True


def proposals_part(text: str) -> str:
    return text[text.index(MARKER) :]


def test_format_entry_quotes_the_sku_and_adds_url_for_lider() -> None:
    assert format_entry(new(sku="0042")) == "{sku: '0042', size: 1.0, approved: 2026-10-04}"
    lider = new(store="lider", sku="007", url="https://super.lider.cl/ip/x/007")
    assert format_entry(lider) == (
        "{sku: '007', url: 'https://super.lider.cl/ip/x/007', size: 1.0, approved: 2026-10-04}"
    )


def test_new_item_key_is_added_above_the_marker() -> None:
    text = f"{HEAD}\n{PROPOSALS}"
    result, outcome = apply_matches(text, [new()], never)
    assert outcome.added == [("rice", "jumbo")]
    head = result.split(MARKER)[0]
    assert "rice:\n  jumbo: {sku: '100', size: 1.0, approved: 2026-10-04}\n" in head
    assert head.startswith(HEAD)
    assert proposals_part(result) == PROPOSALS


def test_store_is_merged_under_an_existing_item_key() -> None:
    existing = 'rice:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-01 }\nsugar:\n  tottus: { sku: "9", size: 1.0, approved: 2026-10-01 }\n'
    text = f"{HEAD}{existing}\n{PROPOSALS}"
    result, outcome = apply_matches(text, [new(store="acuenta", sku="200")], never)
    assert outcome.added == [("rice", "acuenta")]
    head = result.split(MARKER)[0]
    assert head.count("\nrice:\n") == 1
    assert (
        'rice:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-01 }\n'
        "  acuenta: {sku: '200', size: 1.0, approved: 2026-10-04}\nsugar:\n"
    ) in head


def test_several_new_entries_for_one_new_item_share_one_key() -> None:
    text = f"{HEAD}\n{PROPOSALS}"
    result, _ = apply_matches(text, [new(), new(store="acuenta", sku="200")], never)
    assert result.count("\nrice:\n") == 1


def test_existing_store_entry_is_kept_unless_replacement_is_confirmed() -> None:
    existing = 'rice:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-01 }\n'
    text = f"{HEAD}{existing}\n{PROPOSALS}"
    asked: list[tuple[str, str]] = []

    def refuse(item: str, store: str) -> bool:
        asked.append((item, store))
        return False

    kept, outcome = apply_matches(text, [new(sku="100")], refuse)
    assert asked == [("rice", "jumbo")]
    assert kept == text
    assert outcome.kept == [("rice", "jumbo")]

    replaced, outcome = apply_matches(text, [new(sku="100")], always)
    assert outcome.replaced == [("rice", "jumbo")]
    assert 'sku: "1"' not in replaced.split(MARKER)[0]
    assert replaced.split(MARKER)[0].count("\n  jumbo:") == 1


def test_block_style_store_entry_is_replaced_whole() -> None:
    existing = 'rice:\n  jumbo:\n    sku: "1"\n    size: 1.0\n    approved: 2026-10-01\n  tottus: { sku: "9", size: 1.0, approved: 2026-10-01 }\n'
    text = f"{existing}\n{PROPOSALS}"
    result, _ = apply_matches(text, [new(sku="100")], always)
    assert result.split(MARKER)[0] == (
        "rice:\n  jumbo: {sku: '100', size: 1.0, approved: 2026-10-04}\n"
        '  tottus: { sku: "9", size: 1.0, approved: 2026-10-01 }\n\n'
    )


def test_file_without_marker_is_extended_in_place() -> None:
    result, _ = apply_matches(HEAD, [new()], never)
    assert result == HEAD + "\nrice:\n  jumbo: {sku: '100', size: 1.0, approved: 2026-10-04}\n"


def test_write_produces_a_loadable_file_and_a_backup(config_dir: Path) -> None:
    path = config_dir / "matches.yaml"
    original = path.read_text(encoding="utf-8")
    lider = new(store="lider", sku="007", url="https://super.lider.cl/ip/x/007")
    outcome = write_matches(config_dir, [new(), lider], confirm_replace=never, now=NOW)
    config = load_config(config_dir)
    assert config.matches["rice"]["jumbo"].sku == "100"
    assert config.matches["rice"]["lider"].url == "https://super.lider.cl/ip/x/007"
    written = path.read_text(encoding="utf-8")
    assert proposals_part(written) == proposals_part(original)
    assert written.startswith(HEAD)
    assert outcome.backup == config_dir / "matches.yaml.20261004-153012.bak"
    assert outcome.backup.read_text(encoding="utf-8") == original
    assert not list(config_dir.glob("*.tmp"))


def test_write_without_changes_leaves_the_file_untouched(config_dir: Path) -> None:
    path = config_dir / "matches.yaml"
    original = path.read_text(encoding="utf-8")
    outcome = write_matches(config_dir, [], confirm_replace=never, now=NOW)
    assert outcome.backup is None
    assert path.read_text(encoding="utf-8") == original


def test_write_restores_the_backup_when_validation_fails(config_dir: Path) -> None:
    path = config_dir / "matches.yaml"
    original = path.read_text(encoding="utf-8")
    bad = new(item="not_in_basket")
    with pytest.raises(ApproveError, match="not_in_basket"):
        write_matches(config_dir, [bad], confirm_replace=never, now=NOW)
    assert path.read_text(encoding="utf-8") == original


def test_write_restores_when_the_validator_rejects(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = config_dir / "matches.yaml"
    original = path.read_text(encoding="utf-8")

    def reject(_dir: Path) -> None:
        raise approve.ConfigError("boom")

    monkeypatch.setattr(approve, "load_config", reject)
    with pytest.raises(ApproveError, match="boom"):
        write_matches(config_dir, [new()], confirm_replace=never, now=NOW)
    assert path.read_text(encoding="utf-8") == original


def test_inline_item_mapping_is_refused() -> None:
    with pytest.raises(ApproveError):
        apply_matches(
            'rice: { jumbo: { sku: "1", size: 1.0, approved: 2026-10-01 } }\n', [new()], always
        )
