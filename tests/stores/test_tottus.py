import json

import pytest

from factories import make_store_config
from fakes import (
    FIXTURES,
    FakeTransport,
    assert_recorded_listings,
    fixture_response,
    make_client,
    ok,
)
from supermercado.domain.models import SoldBy, Unit
from supermercado.stores.base import ResponseShapeError
from supermercado.stores.tottus import TottusAdapter, parse_search


def make_adapter(*responses, **overrides):
    transport = FakeTransport(list(responses))
    settings = {"base_url": "https://www.tottus.cl"}
    settings.update(overrides)
    return TottusAdapter(make_client(transport), make_store_config("Tottus", **settings)), transport


def search_fixture():
    return fixture_response("tottus", "search.json")


def payload_with(*products):
    return {"data": {"results": list(products)}}


def product(prices, **extra):
    base = {"skuId": "1", "displayName": "Arroz 1 Kg", "prices": prices}
    base.update(extra)
    return base


def internet(value="1.000"):
    return {"type": "internetPrice", "crossed": False, "price": [value]}


def test_search_calls_the_json_endpoint() -> None:
    adapter, transport = make_adapter(search_fixture())
    adapter.search("arroz grado 2")
    call = transport.calls[0]
    assert (call["method"], call["url"]) == ("GET", "https://www.tottus.cl/s/browse/v1/search/cl")
    assert call["params"] == {"page": 1, "Ntt": "arroz grado 2"}


def test_store_ref_is_sent_as_political_id() -> None:
    adapter, transport = make_adapter(search_fixture(), store_ref="13")
    adapter.search("arroz")
    assert transport.calls[0]["params"]["politicalId"] == "13"


def test_parses_string_prices_and_sizes() -> None:
    adapter, _ = make_adapter(search_fixture())
    rice = adapter.search("arroz")[0]
    assert rice.sku == "110609848"
    assert (rice.price, rice.promo_price, rice.card_price) == (1890, None, None)
    assert (rice.size, rice.unit, rice.sold_by) == (1.0, Unit.KG, SoldBy.UNIT)
    assert rice.store_unit_price == 1890
    assert rice.url.startswith("https://www.tottus.cl/tottus-cl/articulo/110609847/")


def test_crossed_normal_price_is_regular_and_cmr_is_card() -> None:
    adapter, _ = make_adapter(search_fixture())
    promo = adapter.search("arroz")[1]
    assert (promo.price, promo.promo_price, promo.card_price) == (1590, 1350, 1190)


def test_kg_products_are_sold_by_weight() -> None:
    adapter, _ = make_adapter(search_fixture())
    posta = adapter.search("posta")[2]
    assert (posta.sold_by, posta.size, posta.unit, posta.price) == (
        SoldBy.WEIGHT,
        1.0,
        Unit.KG,
        9990,
    )


def test_fetch_searches_each_sku_and_keeps_exact_matches() -> None:
    adapter, transport = make_adapter(search_fixture(), search_fixture())
    listings = adapter.fetch(["110609848", "20001"])
    assert [listing.sku for listing in listings] == ["110609848", "20001"]
    assert [call["params"]["Ntt"] for call in transport.calls] == ["110609848", "20001"]


def test_missing_results_raise_shape_error() -> None:
    adapter, _ = make_adapter(ok('{"data": {}}'))
    with pytest.raises(ResponseShapeError):
        adapter.search("arroz")


def test_card_price_must_be_below_the_public_price() -> None:
    cmr = {"type": "cmrPrice", "crossed": False, "price": ["1.000"]}
    [listing] = parse_search(payload_with(product([internet("1.000"), cmr])))
    assert listing.card_price is None


def test_card_price_is_dropped_when_not_positive() -> None:
    cmr = {"type": "cmrPrice", "crossed": False, "price": ["0"]}
    [listing] = parse_search(payload_with(product([internet("1.000"), cmr])))
    assert listing.card_price is None


@pytest.mark.parametrize(
    "bad",
    [
        "not a product",
        {"skuId": "1", "prices": "oops"},
        product(["oops"]),
        product([internet("abc")]),
        {"skuId": "1", "prices": [internet()], "measurements": "oops"},
    ],
)
def test_malformed_items_raise_shape_error_naming_the_store(bad) -> None:
    with pytest.raises(ResponseShapeError, match="Tottus"):
        parse_search(payload_with(bad))


def test_results_not_a_list_names_the_store() -> None:
    with pytest.raises(ResponseShapeError, match="Tottus"):
        parse_search({"data": {"results": {}}})


RECORDED = FIXTURES / "tottus" / "recorded_search.json"


@pytest.mark.skipif(not RECORDED.exists(), reason="recorded fixture not captured yet")
def test_recorded_search_parses() -> None:
    assert_recorded_listings(parse_search(json.loads(RECORDED.read_text(encoding="utf-8"))))
