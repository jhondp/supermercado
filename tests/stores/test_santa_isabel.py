import json

import pytest

from factories import make_store_config
from fakes import FIXTURES, FakeTransport, assert_recorded_listings, fixture_response, make_client
from supermercado.domain.models import Unit
from supermercado.stores.base import AdapterError, ApiKeyRejected, RawResponse
from supermercado.stores.cencosud import parse_plp
from supermercado.stores.santa_isabel import SantaIsabelAdapter


def make_adapter(*responses, **overrides):
    transport = FakeTransport(list(responses))
    settings = {
        "base_url": "https://bff.santaisabel.cl",
        "api_key": "sisa-key",
        "store_ref": "pedrofontova",
    }
    settings.update(overrides)
    config = make_store_config("Santa Isabel", **settings)
    return SantaIsabelAdapter(make_client(transport), config), transport


def test_search_sends_store_and_key() -> None:
    adapter, transport = make_adapter(fixture_response("santa_isabel", "plp_search.json"))
    adapter.search("leche entera")
    call = transport.calls[0]
    assert call["url"] == "https://bff.santaisabel.cl/catalog/plp"
    assert call["headers"]["apiKey"] == "sisa-key"
    assert call["headers"]["Origin"] == "https://www.santaisabel.cl"
    assert call["json"]["store"] == "pedrofontova"


def test_parses_listings_with_promo_and_card_price() -> None:
    adapter, _ = make_adapter(fixture_response("santa_isabel", "plp_search.json"))
    milk, dish = adapter.search("x")
    assert (milk.sku, milk.price, milk.size, milk.unit) == ("21810", 1090, 1.0, Unit.L)
    assert milk.url == "https://www.santaisabel.cl/leche-entera-soprole-1-l/p"
    assert (dish.price, dish.promo_price, dish.card_price) == (1890, 1490, 1290)
    assert (dish.size, dish.unit) == (0.5, Unit.L)


def test_store_ref_is_required() -> None:
    adapter, transport = make_adapter(store_ref=None)
    with pytest.raises(AdapterError, match="store_ref"):
        adapter.fetch(["21810"])
    assert transport.calls == []


def test_rejected_key() -> None:
    adapter, _ = make_adapter(RawResponse(403, "{}"))
    with pytest.raises(ApiKeyRejected, match="santa_isabel"):
        adapter.fetch(["21810"])


RECORDED = FIXTURES / "santa_isabel" / "recorded_search.json"


@pytest.mark.skipif(not RECORDED.exists(), reason="recorded fixture not captured yet")
def test_recorded_search_parses() -> None:
    payload = json.loads(RECORDED.read_text(encoding="utf-8"))
    assert_recorded_listings(parse_plp(payload, SantaIsabelAdapter.site_url))
