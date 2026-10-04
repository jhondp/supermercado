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
from supermercado.stores.base import AdapterError, ResponseShapeError, fetch_by_search
from supermercado.stores.unimarc import UnimarcAdapter, parse_search

API = "https://bff-unimarc-ecommerce.unimarc.cl"
PARAMS = {"channel": "UNIMARC", "source": "web", "version": "1.0.0"}


def make_adapter(*responses, params=None):
    transport = FakeTransport(list(responses))
    config = make_store_config("Unimarc", base_url=API, params=PARAMS if params is None else params)
    return UnimarcAdapter(make_client(transport), config), transport


def search_fixture():
    return fixture_response("unimarc", "search.json")


def entry(price, list_price, item_id="9000", **item):
    return {
        "availableProducts": [
            {
                "item": {"itemId": item_id, "nameComplete": "Arroz 1 kg", **item},
                "price": {"price": price, "listPrice": list_price, "availableQuantity": 1},
            }
        ]
    }


def test_search_sends_required_headers_and_body() -> None:
    adapter, transport = make_adapter(search_fixture())
    adapter.search("arroz grado 2")
    call = transport.calls[0]
    assert (call["method"], call["url"]) == ("POST", f"{API}/catalog/product/search")
    assert {k: call["headers"][k] for k in ("channel", "source", "version")} == PARAMS
    assert "Chrome/" in call["headers"]["User-Agent"]
    assert call["json"] == {"from": "0", "to": "39", "searching": "arroz grado 2"}


def test_headers_come_from_config_params() -> None:
    adapter, transport = make_adapter(
        search_fixture(), params={"channel": "C", "source": "S", "version": "9"}
    )
    adapter.search("arroz")
    headers = transport.calls[0]["headers"]
    assert (headers["channel"], headers["source"], headers["version"]) == ("C", "S", "9")


@pytest.mark.parametrize(
    "params",
    [{}, {"channel": "UNIMARC", "source": "web"}, {**PARAMS, "version": ""}],
)
def test_header_params_are_required_before_any_request(params) -> None:
    adapter, transport = make_adapter(params=params)
    with pytest.raises(AdapterError, match="params"):
        adapter.search("arroz")
    with pytest.raises(AdapterError, match="params"):
        adapter.raw_fetch("5000")
    assert transport.calls == []


def test_lower_price_is_club_price_not_promo() -> None:
    adapter, _ = make_adapter(search_fixture())
    rice = adapter.search("arroz")[0]
    assert (rice.sku, rice.price, rice.promo_price, rice.card_price) == ("5000", 1990, None, 1790)
    assert rice.store_unit_price == 1790
    assert (rice.size, rice.unit) == (1.0, Unit.KG)
    assert rice.url == "https://www.unimarc.cl/product/arroz-grado-2-tucapel-1-kg"


def test_zero_quantity_is_unavailable() -> None:
    adapter, _ = make_adapter(search_fixture())
    own = adapter.search("arroz")[1]
    assert (own.price, own.card_price, own.available, own.url) == (1390, None, False, None)


def test_kg_items_are_sold_by_weight_and_accept_numeric_prices() -> None:
    adapter, _ = make_adapter(search_fixture())
    posta = adapter.search("posta")[2]
    assert (posta.sold_by, posta.size, posta.unit, posta.price) == (
        SoldBy.WEIGHT,
        1.0,
        Unit.KG,
        8990,
    )


def test_float_prices_round_half_up() -> None:
    listing = parse_search(entry(1789.5, 1990.5))[0]
    assert (listing.price, listing.card_price) == (1991, 1790)


@pytest.mark.parametrize("current", [0, "$0", 1990, 2500, None, ""])
def test_card_price_only_when_positive_and_below_list(current) -> None:
    listing = parse_search(entry(current, 1990))[0]
    assert listing.card_price is None
    assert listing.promo_price is None


def test_missing_list_price_falls_back_to_price() -> None:
    listing = parse_search(entry(1500, None))[0]
    assert (listing.price, listing.card_price) == (1500, None)


@pytest.mark.parametrize(
    "payload",
    [
        {"availableProducts": [None]},
        {"availableProducts": [{"item": {"itemId": "1"}, "price": "x"}]},
        {"availableProducts": [{"item": {"itemId": "1", "unitMultiplier": 0}, "price": {}}]},
        {"availableProducts": [{"item": {"itemId": "1", "unitMultiplier": "abc"}, "price": {}}]},
        {"availableProducts": [{"item": {"itemId": "1"}, "price": {"price": "gratis"}}]},
        {"availableProducts": [{"item": {"itemId": "1"}, "price": {"availableQuantity": "n/a"}}]},
        {"availableProducts": [{"item": {"itemId": ["1"]}, "price": {}}]},
    ],
)
def test_malformed_items_raise_shape_error_naming_store(payload) -> None:
    with pytest.raises(ResponseShapeError, match="Unimarc"):
        parse_search(payload)


def test_fetch_keeps_exact_item_ids() -> None:
    adapter, transport = make_adapter(search_fixture())
    assert [listing.sku for listing in adapter.fetch(["5002"])] == ["5002"]
    assert transport.calls[0]["json"]["searching"] == "5002"


def test_fetch_by_search_lives_in_base() -> None:
    adapter, _ = make_adapter(search_fixture(), search_fixture())
    assert [listing.sku for listing in fetch_by_search(["5000", "5000"], adapter.search)] == [
        "5000"
    ]


def test_missing_products_raise_shape_error() -> None:
    adapter, _ = make_adapter(ok('{"message": "error"}'))
    with pytest.raises(ResponseShapeError):
        adapter.search("arroz")


RECORDED = FIXTURES / "unimarc" / "recorded_search.json"


@pytest.mark.skipif(not RECORDED.exists(), reason="recorded fixture not captured yet")
def test_recorded_search_parses() -> None:
    assert_recorded_listings(parse_search(json.loads(RECORDED.read_text(encoding="utf-8"))))
