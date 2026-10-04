from datetime import UTC, datetime
from pathlib import Path

from factories import make_config, make_item, make_listing, make_match, make_obs
from fakes import FakeAdapter
from supermercado.domain.models import Status
from supermercado.pipeline.collect import collect
from supermercado.pipeline.storage import (
    list_weeks,
    previous_unit_prices,
    read_week,
    week_path,
    write_week,
)

W40 = "2026-W40"


def test_round_trip_preserves_values_and_types(tmp_path: Path) -> None:
    rows = [
        make_obs(
            store="lider",
            sku="00780142021013",
            price=1790,
            promo_price=1190,
            effective_price=1190,
            unit_price=1190,
            card_price=None,
        ),
        make_obs(card_price=1150),
    ]
    path = write_week(tmp_path, W40, rows, replace_stores={"jumbo", "lider"})
    assert path == week_path(tmp_path, W40) == tmp_path / "prices" / "2026-W40.parquet"
    loaded = read_week(tmp_path, W40)
    assert loaded == sorted(rows, key=lambda o: (o.store, o.item_id))
    assert loaded[0].scraped_at.tzinfo is not None
    assert isinstance(loaded[0].unit_price, int)


def test_write_week_replaces_only_given_stores(tmp_path: Path) -> None:
    write_week(
        tmp_path,
        W40,
        [make_obs(store="jumbo"), make_obs(store="lider", unit_price=1190)],
        replace_stores={"jumbo", "lider"},
    )
    write_week(tmp_path, W40, [make_obs(store="lider", unit_price=1200)], replace_stores={"lider"})
    assert {(o.store, o.unit_price) for o in read_week(tmp_path, W40)} == {
        ("jumbo", 1810),
        ("lider", 1200),
    }


def test_writing_nothing_creates_no_file(tmp_path: Path) -> None:
    assert write_week(tmp_path, W40, [], replace_stores=set()) is None
    assert list_weeks(tmp_path) == []


def test_previous_unit_prices_use_latest_ok_row_across_earlier_weeks(tmp_path: Path) -> None:
    write_week(
        tmp_path, "2026-W38", [make_obs(week="2026-W38", unit_price=1700)], replace_stores={"jumbo"}
    )
    write_week(
        tmp_path,
        "2026-W39",
        [
            make_obs(week="2026-W39", unit_price=1790),
            make_obs(week="2026-W39", item_id="milk", unit_price=5000, status=Status.SUSPICIOUS),
        ],
        replace_stores={"jumbo"},
    )
    write_week(tmp_path, W40, [make_obs(unit_price=1810)], replace_stores={"jumbo"})
    assert list_weeks(tmp_path) == ["2026-W38", "2026-W39", "2026-W40"]
    assert previous_unit_prices(tmp_path, W40) == {("jumbo", "rice"): 1790}
    assert previous_unit_prices(tmp_path, "2026-W38") == {}


def test_baseline_skips_weeks_where_the_item_was_not_ok(tmp_path: Path) -> None:
    write_week(
        tmp_path, "2026-W38", [make_obs(week="2026-W38", unit_price=1700)], replace_stores={"jumbo"}
    )
    write_week(
        tmp_path,
        "2026-W39",
        [make_obs(week="2026-W39", unit_price=9000, status=Status.SUSPICIOUS)],
        replace_stores={"jumbo"},
    )
    assert previous_unit_prices(tmp_path, W40) == {("jumbo", "rice"): 1700}


def test_persistent_jump_stays_suspicious_until_cleared(tmp_path: Path) -> None:
    config = make_config(
        items=[make_item("rice")],
        stores=("jumbo",),
        matches={"rice": {"jumbo": make_match("1626")}},
    )

    def run_week(week: str, price: int, cleared=()):
        now = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
        adapters = {"jumbo": FakeAdapter("jumbo", [make_listing(price=price)])}
        previous = previous_unit_prices(tmp_path, week, cleared=cleared)
        result = collect(config, adapters, now=now, previous=previous)
        rows = [o.model_copy(update={"week": week}) for o in result.observations]
        write_week(tmp_path, week, rows, replace_stores=result.collected_stores)
        return rows[0].status

    assert run_week("2026-W39", 1000) is Status.OK
    assert run_week("2026-W40", 3000) is Status.SUSPICIOUS
    # same jump again: baseline must still be W39, not the suspicious W40 row
    assert run_week("2026-W41", 3000) is Status.SUSPICIOUS
    # after W40 is cleared, W41 compares against W40 and is fine
    assert previous_unit_prices(tmp_path, "2026-W41", cleared={("2026-W40", "jumbo", "rice")}) == {
        ("jumbo", "rice"): 3000
    }
    assert run_week("2026-W41", 3000, cleared={("2026-W40", "jumbo", "rice")}) is Status.OK
