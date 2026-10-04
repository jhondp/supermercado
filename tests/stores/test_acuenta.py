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
from supermercado.stores.acuenta import AcuentaAdapter, parse_products
from supermercado.stores.base import AdapterError, ResponseShapeError

API = "https://nextgentheadless.instaleap.io/api/v3"


def make_adapter(*responses, **overrides):
    transport = FakeTransport(list(responses))
    settings = {"base_url": API, "store_ref": "580", "params": {"client_id": "TEST_CLIENT"}}
    settings.update(overrides)
    return AcuentaAdapter(
        make_client(transport), make_store_config("aCuenta", **settings)
    ), transport


def product(**overrides):
    data = {
        "name": "Arroz 1 Kg", "sku": "1", "brand": None, "price": 1000, "unit": "Un", "subUnit": None,
        "subQty": None, "clickMultiplier": 1, "stock": 5, "isAvailable": True, "promotion": None,
    }  # fmt: skip
    data.update(overrides)
    return {"data": {"searchProducts": {"products": [data]}}}


def test_search_posts_the_graphql_query() -> None:
    adapter, transport = make_adapter(fixture_response("acuenta", "search.json"))
    adapter.search("arroz grado 2")
    call = transport.calls[0]
    assert (call["method"], call["url"]) == ("POST", API)
    assert "searchProducts(" in call["json"]["query"]
    assert call["json"]["variables"]["input"] == {
        "clientId": "TEST_CLIENT",
        "storeReference": "580",
        "currentPage": 1,
        "pageSize": 40,
        "search": [{"query": "arroz grado 2"}],
    }


def test_parses_regular_listing() -> None:
    adapter, _ = make_adapter(fixture_response("acuenta", "search.json"))
    rice = adapter.search("arroz")[0]
    assert (rice.sku, rice.price, rice.promo_price) == ("7801420210130", 1650, None)
    assert (rice.size, rice.unit, rice.available) == (1.0, Unit.KG, True)


def test_single_unit_promotion_is_unconditional() -> None:
    adapter, _ = make_adapter(fixture_response("acuenta", "search.json"))
    assert adapter.search("arroz")[1].promo_price == 1190


def test_multi_buy_is_ignored_and_stock_zero_is_unavailable() -> None:
    adapter, _ = make_adapter(fixture_response("acuenta", "search.json"))
    pasta = adapter.search("spaghetti")[2]
    assert pasta.promo_price is None
    assert pasta.available is False
    assert (pasta.size, pasta.unit) == (0.4, Unit.KG)


def test_kg_unit_is_sold_by_weight() -> None:
    adapter, _ = make_adapter(fixture_response("acuenta", "search.json"))
    chicken = adapter.search("trutro")[3]
    assert (chicken.sold_by, chicken.size, chicken.unit, chicken.multiplier) == (
        SoldBy.WEIGHT,
        1.0,
        Unit.KG,
        0.5,
    )


def test_fetch_uses_get_products_by_sku_and_filters() -> None:
    adapter, transport = make_adapter(fixture_response("acuenta", "by_sku.json"))
    listings = adapter.fetch(["7801420210130"])
    assert [listing.sku for listing in listings] == ["7801420210130"]
    call = transport.calls[0]
    assert "getProductsBySKU(" in call["json"]["query"]
    assert call["json"]["variables"]["input"]["skus"] == ["7801420210130"]
    assert call["json"]["variables"]["input"]["clientId"] == "TEST_CLIENT"


def test_graphql_errors_raise_shape_error() -> None:
    adapter, _ = make_adapter(ok('{"errors": [{"message": "Unknown field"}], "data": null}'))
    with pytest.raises(ResponseShapeError, match="Unknown field"):
        adapter.search("arroz")


def test_store_reference_is_required() -> None:
    adapter, transport = make_adapter(store_ref=None)
    with pytest.raises(AdapterError, match="store_ref"):
        adapter.search("arroz")
    assert transport.calls == []


@pytest.mark.parametrize("params", [{}, {"client_id": ""}])
def test_client_id_is_required_before_any_request(params) -> None:
    adapter, transport = make_adapter(params=params)
    with pytest.raises(AdapterError, match="client_id"):
        adapter.search("arroz")
    with pytest.raises(AdapterError, match="client_id"):
        adapter.fetch(["1"])
    assert transport.calls == []


@pytest.mark.parametrize("kind", ["nx$", "NX$", "MXN"])
def test_conditional_promotions_never_become_promo_price(kind) -> None:
    promotion = {"type": kind, "isActive": True, "conditions": [{"price": 500, "quantity": 1}]}
    assert parse_products(product(promotion=promotion), "searchProducts")[0].promo_price is None


def test_multi_quantity_and_inactive_promotions_are_ignored() -> None:
    multi = {"type": "DISCOUNT", "isActive": True, "conditions": [{"price": 500, "quantity": 3}]}
    inactive = {
        "type": "DISCOUNT",
        "isActive": False,
        "conditions": [{"price": 500, "quantity": 1}],
    }
    assert parse_products(product(promotion=multi), "searchProducts")[0].promo_price is None
    assert parse_products(product(promotion=inactive), "searchProducts")[0].promo_price is None


def test_promo_must_be_below_price_and_is_rounded_half_up() -> None:
    higher = {"type": "DISCOUNT", "isActive": True, "conditions": [{"price": 1200, "quantity": 1}]}
    assert parse_products(product(promotion=higher), "searchProducts")[0].promo_price is None
    half = {"type": "DISCOUNT", "isActive": True, "conditions": [{"price": 899.5, "quantity": 1}]}
    assert parse_products(product(promotion=half), "searchProducts")[0].promo_price == 900


def test_price_rounds_half_up() -> None:
    assert parse_products(product(price=1000.5), "searchProducts")[0].price == 1001
    assert parse_products(product(price=2.5), "searchProducts")[0].price == 3


def test_card_price_is_never_derived_from_promotions() -> None:
    assert parse_products(product(), "searchProducts")[0].card_price is None


@pytest.mark.parametrize(
    "bad",
    [
        {"promotion": "oops"},
        {"promotion": {"isActive": True, "conditions": "x"}},
        {"promotion": {"isActive": True, "conditions": ["x"]}},
        {"promotion": {"isActive": True, "conditions": [{"price": "abc", "quantity": 1}]}},
        {"clickMultiplier": "abc"},
        {"stock": "many"},
        {"price": "abc"},
        {"sku": {"a": 1}},
    ],
)
def test_malformed_item_data_raises_shape_error_naming_the_store(bad) -> None:
    with pytest.raises(ResponseShapeError, match="aCuenta"):
        parse_products(product(**bad), "searchProducts")


def test_non_dict_product_raises_shape_error() -> None:
    with pytest.raises(ResponseShapeError, match="aCuenta"):
        parse_products({"data": {"searchProducts": {"products": ["x"]}}}, "searchProducts")


RECORDED_SEARCH = FIXTURES / "acuenta" / "recorded_search.json"
RECORDED_FETCH = FIXTURES / "acuenta" / "recorded_fetch.json"


@pytest.mark.skipif(not RECORDED_SEARCH.exists(), reason="recorded fixture not captured yet")
def test_recorded_search_parses() -> None:
    payload = json.loads(RECORDED_SEARCH.read_text(encoding="utf-8"))
    assert_recorded_listings(parse_products(payload, "searchProducts"))


@pytest.mark.skipif(not RECORDED_FETCH.exists(), reason="recorded fixture not captured yet")
def test_recorded_fetch_parses() -> None:
    payload = json.loads(RECORDED_FETCH.read_text(encoding="utf-8"))
    assert_recorded_listings(parse_products(payload, "getProductsBySKU"))
