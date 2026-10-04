from datetime import UTC, datetime

import pytest

from factories import make_config, make_item, make_listing, make_match
from fakes import FakeAdapter
from supermercado.domain.models import Status, Unit
from supermercado.pipeline.collect import collect, iso_week
from supermercado.stores.base import BlockedError, ResponseShapeError

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
LIDER_URL = "https://super.lider.cl/ip/arroz-y-legumbres/00780142021013"
MILK = make_listing(sku="555", name="Leche Entera 1 L", size=1.0, unit=Unit.L, price=990)
LIDER_RICE = make_listing(sku="00780142021013", price=1190)


def config(matches=None):
    return make_config(
        items=[make_item("rice"), make_item("milk", unit=Unit.L)],
        stores=("jumbo", "lider"),
        matches=matches
        or {
            "rice": {
                "jumbo": make_match("1626"),
                "lider": make_match("00780142021013", url=LIDER_URL),
            },
            "milk": {"jumbo": make_match("555")},
        },
    )


def test_iso_week_formats_year_and_week() -> None:
    assert iso_week(NOW) == "2026-W40"
    assert iso_week(datetime(2027, 1, 1, tzinfo=UTC)) == "2026-W53"


def test_collects_every_store_and_item() -> None:
    jumbo = FakeAdapter("jumbo", [make_listing(), MILK])
    lider = FakeAdapter("lider", [LIDER_RICE])
    result = collect(config(), {"jumbo": jumbo, "lider": lider}, now=NOW, previous={})
    assert result.week == "2026-W40"
    assert sorted((o.store, o.item_id, o.unit_price) for o in result.observations) == [
        ("jumbo", "milk", 990),
        ("jumbo", "rice", 1810),
        ("lider", "rice", 1190),
    ]
    assert jumbo.fetched == [["1626", "555"]]
    assert result.collected_stores == {"jumbo", "lider"}
    assert result.failures == []


def test_failing_store_does_not_block_others() -> None:
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), MILK]),
        "lider": FakeAdapter("lider", error=BlockedError("captcha page")),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert {o.store for o in result.observations} == {"jumbo"}
    assert [(f.store, f.error_class, f.message, f.at) for f in result.failures] == [
        ("lider", "BlockedError", "captcha page", NOW)
    ]
    assert result.collected_stores == {"jumbo"}


def test_response_shape_error_is_isolated_per_store() -> None:
    adapters = {
        "jumbo": FakeAdapter("jumbo", error=ResponseShapeError("jumbo: bad item")),
        "lider": FakeAdapter("lider", [LIDER_RICE]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert [(f.store, f.error_class) for f in result.failures] == [("jumbo", "ResponseShapeError")]
    assert result.collected_stores == {"lider"}


def test_store_returning_nothing_is_a_failure() -> None:
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), MILK]),
        "lider": FakeAdapter("lider"),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert [(f.store, f.error_class) for f in result.failures] == [("lider", "EmptyResult")]
    assert "lider" not in result.collected_stores


def test_store_whose_rows_were_all_dropped_is_not_collected() -> None:
    no_price = make_listing(sku="00780142021013", price=None)
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), MILK]),
        "lider": FakeAdapter("lider", [no_price]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert result.collected_stores == {"jumbo"}
    assert "lider/rice: missing or non-positive price" in result.dropped


def test_store_with_listings_but_no_usable_row_is_an_empty_result_failure() -> None:
    no_price = make_listing(sku="00780142021013", price=None)
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), MILK]),
        "lider": FakeAdapter("lider", [no_price]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert [(f.store, f.error_class, f.at) for f in result.failures] == [
        ("lider", "EmptyResult", NOW)
    ]
    message = result.failures[0].message
    assert message.startswith("1 listings returned but none usable: ")
    assert "lider/rice: missing or non-positive price" in message


def test_partially_dropped_store_is_not_a_failure() -> None:
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing()]),
        "lider": FakeAdapter("lider", [LIDER_RICE]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert result.failures == []


@pytest.mark.parametrize("bad_size", [-1.0, float("nan")])
def test_malformed_listing_is_dropped_without_aborting_the_run(bad_size: float) -> None:
    broken_milk = make_listing(sku="555", name="Leche", size=bad_size, unit=Unit.L, price=990)
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), broken_milk]),
        "lider": FakeAdapter("lider", [LIDER_RICE]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert sorted((o.store, o.item_id) for o in result.observations) == [
        ("jumbo", "rice"),
        ("lider", "rice"),
    ]
    assert result.collected_stores == {"jumbo", "lider"}
    assert result.failures == []
    [line] = [d for d in result.dropped if d.startswith("jumbo/milk")]
    assert "invalid listing" in line


def test_missing_sku_is_dropped_without_failing_the_store() -> None:
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing()]),
        "lider": FakeAdapter("lider", [LIDER_RICE]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert any(d.startswith("jumbo/milk") for d in result.dropped)
    assert result.failures == []


def test_row_without_price_is_dropped() -> None:
    no_price = make_listing(sku="555", name="Leche Entera 1 L", size=1.0, unit=Unit.L, price=None)
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), no_price]),
        "lider": FakeAdapter("lider", [LIDER_RICE]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert "jumbo/milk: missing or non-positive price" in result.dropped


def test_previous_week_price_marks_suspicious_rows() -> None:
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), MILK]),
        "lider": FakeAdapter("lider", [LIDER_RICE]),
    }
    result = collect(config(), adapters, now=NOW, previous={("jumbo", "rice"): 1000})
    status = {(o.store, o.item_id): o.status for o in result.observations}
    assert status[("jumbo", "rice")] is Status.SUSPICIOUS
    assert status[("lider", "rice")] is Status.OK


def test_size_change_raises_an_alert() -> None:
    shrunk = make_listing(size=0.9, name="Arroz Grado 2 Tucapel 900 g")
    adapters = {
        "jumbo": FakeAdapter("jumbo", [shrunk, MILK]),
        "lider": FakeAdapter("lider", [LIDER_RICE]),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert [(a.store, a.item_id) for a in result.alerts] == [("jumbo", "rice")]


def test_store_without_matches_is_not_fetched() -> None:
    lider = FakeAdapter("lider", [LIDER_RICE])
    matches = {"rice": {"jumbo": make_match("1626")}}
    result = collect(
        config(matches),
        {"jumbo": FakeAdapter("jumbo", [make_listing()]), "lider": lider},
        now=NOW,
        previous={},
    )
    assert lider.fetched == []
    assert result.collected_stores == {"jumbo"}
