import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from factories import make_config, make_item, make_listing, make_match
from fakes import FakeAdapter
from supermercado.config import load_config
from supermercado.domain.models import Match, Unit
from supermercado.pipeline.propose import MARKER, Proposal, propose, render_proposals
from supermercado.stores.base import HttpError

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
RICE = make_item("rice", size_range=(0.9, 1.0), exclude=("integral",))
MILK = make_item("whole_milk", unit=Unit.L, search="leche entera 1 l", size_range=(1.0, 1.0))
HEAD = '# Approved matches\nrice:\n  jumbo: { sku: "1626", size: 1.0, approved: 2026-10-04 }\n'


def test_proposes_cheapest_valid_candidates_for_unmatched_pairs() -> None:
    config = make_config(
        items=[RICE, MILK],
        stores=("jumbo", "lider"),
        matches={"whole_milk": {"jumbo": make_match("4001")}},
    )
    jumbo = FakeAdapter(
        "jumbo",
        search_results={
            "arroz grado 2": [
                make_listing(sku="a", price=1810),
                make_listing(sku="b", price=1290),
                make_listing(sku="c", name="Arroz Integral 1 kg", price=900),
                make_listing(sku="d", price=1500),
                make_listing(sku="e", price=1700),
            ]
        },
    )
    lider = FakeAdapter("lider", supports_search=False)
    proposals, failures = propose(config, {"jumbo": jumbo, "lider": lider}, now=NOW)
    assert [(p.item_id, p.store, p.listing.sku, p.unit_price) for p in proposals] == [
        ("rice", "jumbo", "b", 1290),
        ("rice", "jumbo", "d", 1500),
        ("rice", "jumbo", "e", 1700),
    ]
    assert jumbo.searched == ["arroz grado 2"]
    assert lider.searched == []
    assert failures == []


def test_search_failure_is_reported_and_other_stores_continue() -> None:
    config = make_config(items=[RICE], stores=("jumbo", "tottus"))
    broken = FakeAdapter("jumbo", error=HttpError(503, "https://bff.jumbo.cl/catalog/plp"))
    tottus = FakeAdapter(
        "tottus", search_results={"arroz grado 2": [make_listing(sku="t1", price=1890)]}
    )
    proposals, failures = propose(config, {"jumbo": broken, "tottus": tottus}, now=NOW)
    assert [(f.store, f.error_class) for f in failures] == [("jumbo", "HttpError")]
    assert [p.listing.sku for p in proposals] == ["t1"]


def proposal(sku: str, price: int) -> Proposal:
    return Proposal("rice", "tottus", make_listing(sku=sku, price=price), price, "kg")


def test_render_appends_a_commented_section_that_keeps_data_unchanged() -> None:
    text = render_proposals(HEAD, [proposal("t1", 1890)], week="2026-W41", today=date(2026, 10, 5))
    assert text.startswith(HEAD)
    assert MARKER in text
    assert '#   tottus: { sku: "t1", size: 1, approved: 2026-10-05 }' in text
    assert "lider" in text.lower()
    assert "manual" in text.lower()
    assert yaml.safe_load(text) == yaml.safe_load(HEAD)


def test_render_replaces_the_previous_section_and_can_remove_it() -> None:
    first = render_proposals(HEAD, [proposal("t1", 1890)], week="2026-W41", today=date(2026, 10, 5))
    second = render_proposals(
        first, [proposal("t2", 1990)], week="2026-W42", today=date(2026, 10, 12)
    )
    assert "t1" not in second
    assert second.count(MARKER) == 1
    assert render_proposals(second, [], week="2026-W42", today=date(2026, 10, 12)) == HEAD


def test_uncommented_proposal_is_a_valid_match() -> None:
    text = render_proposals("", [proposal("t1", 1890)], week="2026-W41", today=date(2026, 10, 5))
    lines = [line[2:] for line in text.splitlines() if line.startswith(("# rice:", "#   tottus:"))]
    data = yaml.safe_load("\n".join(lines))
    assert Match.model_validate(data["rice"]["tottus"]).sku == "t1"


def test_rendered_matches_file_still_loads_with_the_config_loader(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree(Path(__file__).resolve().parents[2] / "config", config_dir)
    real = load_config(config_dir)
    item = real.basket[0]
    store = next(s for s in real.stores if s not in real.matches.get(item.id, {}))
    # Proposal for a pair that is already approved must not create a duplicate key either.
    pairs = [(item.id, store)]
    if real.matches.get(item.id):
        pairs.append((item.id, next(iter(real.matches[item.id]))))
    proposals = [
        Proposal(item_id, store_id, make_listing(sku="p1"), 1000, item.unit.value)
        for item_id, store_id in pairs
    ]
    path = config_dir / "matches.yaml"
    path.write_text(
        render_proposals(
            path.read_text(encoding="utf-8"), proposals, week="2026-W41", today=date(2026, 10, 5)
        ),
        encoding="utf-8",
    )
    assert "p1" in path.read_text(encoding="utf-8")
    assert load_config(config_dir).matches == real.matches
