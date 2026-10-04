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
from supermercado.stores.base import ApiKeyRejected, RawResponse, ResponseShapeError
from supermercado.stores.cencosud import parse_plp
from supermercado.stores.jumbo import JumboAdapter


def make_adapter(*responses, **overrides):
    transport = FakeTransport(list(responses))
    settings = {
        "base_url": "https://bff.jumbo.cl",
        "api_key": "test-key",
        "store_ref": "jumboclj512",
    }
    settings.update(overrides)
    config = make_store_config("Jumbo", **settings)
    return JumboAdapter(make_client(transport), config), transport


def test_search_sends_the_cencosud_plp_request() -> None:
    adapter, transport = make_adapter(fixture_response("jumbo", "plp_search.json"))
    adapter.search("arroz grado 2")
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://bff.jumbo.cl/catalog/plp"
    assert call["headers"]["apiKey"] == "test-key"
    assert call["json"] == {
        "fullText": "arroz grado 2",
        "store": "jumboclj512",
        "from": 0,
        "to": 39,
    }


def test_search_parses_a_regular_listing() -> None:
    adapter, _ = make_adapter(fixture_response("jumbo", "plp_search.json"))
    rice = adapter.search("arroz grado 2")[0]
    assert rice.sku == "1626"
    assert rice.brand == "Tucapel"
    assert (
        rice.url
        == "https://www.jumbo.cl/arroz-grado-2-tucapel-1-kg-blue-bonnet-grano-largo-y-delgado/p"
    )
    assert (rice.size, rice.unit, rice.sold_by) == (1.0, Unit.KG, SoldBy.UNIT)
    assert (rice.price, rice.promo_price, rice.card_price) == (1810, None, None)
    assert rice.store_unit_price == 1810
    assert rice.available is True


def test_discount_becomes_promo_and_card_offer_stays_separate() -> None:
    adapter, _ = make_adapter(fixture_response("jumbo", "plp_search.json"))
    promo = adapter.search("arroz grado 2")[1]
    assert (promo.price, promo.promo_price, promo.card_price) == (1590, 1290, 1150)


def test_weighted_item_is_sold_by_weight() -> None:
    adapter, _ = make_adapter(fixture_response("jumbo", "plp_search.json"))
    chicken = adapter.search("trutro")[2]
    assert (chicken.sold_by, chicken.size, chicken.unit) == (SoldBy.WEIGHT, 1.0, Unit.KG)
    assert chicken.available is False


def test_fetch_batches_skus_and_returns_only_requested_ones() -> None:
    adapter, transport = make_adapter(fixture_response("jumbo", "plp_search.json"))
    listings = adapter.fetch(["1626", "43165"])
    assert transport.calls[0]["json"]["fullText"] == "sku:1626;43165"
    assert sorted(listing.sku for listing in listings) == ["1626", "43165"]


def test_fetch_splits_more_than_forty_skus() -> None:
    adapter, transport = make_adapter(ok('{"products": []}'), ok('{"products": []}'))
    skus = [str(n) for n in range(41)]
    assert adapter.fetch(skus) == []
    assert len(transport.calls) == 2
    assert transport.calls[1]["json"]["fullText"] == "sku:40"


def test_fetch_with_no_skus_makes_no_request() -> None:
    adapter, transport = make_adapter()
    assert adapter.fetch([]) == []
    assert transport.calls == []


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_raises_api_key_rejected(status) -> None:
    adapter, _ = make_adapter(RawResponse(status, "{}"))
    with pytest.raises(ApiKeyRejected, match="jumbo"):
        adapter.search("arroz")


def test_missing_key_fails_before_any_request() -> None:
    adapter, transport = make_adapter(api_key=None)
    with pytest.raises(ApiKeyRejected):
        adapter.fetch(["1626"])
    assert transport.calls == []


@pytest.mark.parametrize("body", ['{"error": "x"}', "<html>blocked</html>"])
def test_unexpected_body_raises_shape_error(body) -> None:
    adapter, _ = make_adapter(ok(body))
    with pytest.raises(ResponseShapeError):
        adapter.search("arroz")


RECORDED = FIXTURES / "jumbo" / "recorded_search.json"


@pytest.mark.skipif(not RECORDED.exists(), reason="recorded fixture not captured yet")
def test_recorded_search_parses() -> None:
    listings = parse_plp(json.loads(RECORDED.read_text(encoding="utf-8")), JumboAdapter.site_url)
    assert_recorded_listings(listings)


def test_fractional_prices_round_half_up() -> None:
    body = json.dumps(
        {
            "products": [
                {
                    "slug": "x",
                    "items": [
                        {"skuId": "1", "name": "X 1 kg", "price": 1000.5, "listPrice": 1000.5}
                    ],
                }
            ]
        }
    )
    adapter, _ = make_adapter(ok(body))
    assert adapter.search("x")[0].price == 1001


def _one_item(**fields) -> str:
    item = {"skuId": "1", "name": "X 1 kg", "price": 1000, "listPrice": 1000}
    item.update(fields)
    return json.dumps({"products": [{"slug": "x", "items": [item]}]})


@pytest.mark.parametrize(
    "body",
    [
        _one_item(price="abc"),
        _one_item(unitMultiplier="x"),
        _one_item(promotions=["oops"]),
        json.dumps({"products": ["oops"]}),
        json.dumps({"products": [{"items": ["oops"]}]}),
    ],
)
def test_malformed_item_raises_shape_error(body) -> None:
    adapter, _ = make_adapter(ok(body))
    with pytest.raises(ResponseShapeError):
        adapter.search("x")


def test_card_price_must_be_below_the_regular_price() -> None:
    body = _one_item(promotions=[{"name": "TCENCO OFERTA - 1500"}, {"name": "TARJETA 0 - 0"}])
    adapter, _ = make_adapter(ok(body))
    assert adapter.search("x")[0].card_price is None


def test_card_label_without_amount_is_ignored() -> None:
    adapter, _ = make_adapter(
        ok(_one_item(promotions=[{"name": "TCENCO - ."}, {"name": "TCENCO - 900"}]))
    )
    assert adapter.search("x")[0].card_price == 900


def test_weighted_size_comes_from_the_multiplier() -> None:
    body = _one_item(measurementUnit="kg", unitMultiplier=0.5, name="Pechuga granel")
    listing = make_adapter(ok(body))[0].search("x")[0]
    assert (listing.sold_by, listing.size, listing.unit) == (SoldBy.WEIGHT, 0.5, Unit.KG)
