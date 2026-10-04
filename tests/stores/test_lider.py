import json

import pytest

from factories import make_item, make_match, make_store_config
from fakes import FIXTURES, FakeTransport, fixture_response, fixture_text, make_client, ok
from supermercado.config import AppConfig
from supermercado.domain.models import SoldBy, Unit
from supermercado.stores import build_adapters
from supermercado.stores.base import AdapterError, BlockedError, RawResponse, ResponseShapeError
from supermercado.stores.lider import LiderAdapter, parse_product_page

URL = "https://super.lider.cl/ip/arroz-y-legumbres/00780142021013"
COOKIES = {"walmart.nearestLatLng": "-33.4521,-70.6536"}


def make_adapter(*responses, urls=None):
    transport = FakeTransport(list(responses))
    config = make_store_config("Lider", base_url="https://super.lider.cl", cookies=COOKIES)
    adapter = LiderAdapter(make_client(transport), config, urls or {"00780142021013": URL})
    return adapter, transport


def page(product: dict) -> str:
    data = {"props": {"pageProps": {"initialData": {"data": {"product": product}}}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


def product(**overrides) -> dict:
    base = {
        "usItemId": "1",
        "name": "Arroz 1 kg",
        "canonicalUrl": "/ip/x/1",
        "availabilityStatus": "IN_STOCK",
        "priceInfo": {"currentPrice": {"price": 1000}, "wasPrice": None},
    }
    base.update(overrides)
    return base


def test_fetch_gets_the_product_page_with_location_cookie() -> None:
    adapter, transport = make_adapter(fixture_response("lider", "product_page.html"))
    adapter.fetch(["00780142021013"])
    call = transport.calls[0]
    assert (call["method"], call["url"], call["cookies"]) == ("GET", URL, COOKIES)


def test_adapter_sends_no_hand_rolled_user_agent() -> None:
    adapter, transport = make_adapter(fixture_response("lider", "product_page.html"))
    adapter.fetch(["00780142021013"])
    assert "user-agent" not in {k.lower() for k in transport.calls[0]["headers"]}


def test_parses_promo_page() -> None:
    listing = parse_product_page(fixture_text("lider", "product_page.html"))
    assert listing.sku == "00780142021013"
    assert (listing.price, listing.promo_price) == (1790, 1190)
    assert (listing.size, listing.unit, listing.available) == (1.0, Unit.KG, True)
    assert listing.url == URL


def test_parses_weight_page() -> None:
    listing = parse_product_page(fixture_text("lider", "product_page_weight.html"))
    assert (listing.sold_by, listing.size, listing.unit) == (SoldBy.WEIGHT, 1.0, Unit.KG)
    assert (listing.price, listing.promo_price, listing.multiplier) == (3990, None, 1.2)
    assert listing.available is False


def test_was_price_not_above_current_is_ignored() -> None:
    info = {"currentPrice": {"price": 1000}, "wasPrice": {"price": 1000}}
    listing = parse_product_page(page(product(priceInfo=info)))
    assert (listing.price, listing.promo_price) == (1000, None)


def test_fractional_price_rounds_half_up() -> None:
    info = {"currentPrice": {"price": 1000.5}, "wasPrice": None}
    assert parse_product_page(page(product(priceInfo=info))).price == 1001


@pytest.mark.parametrize(
    "bad",
    [
        {"usItemId": None},
        {"priceInfo": {"currentPrice": {"price": "abc"}}},
        {"averageWeight": "heavy", "salesUnitType": "WEIGHT"},
        {"averageWeight": -1, "salesUnitType": "WEIGHT"},
        {"priceInfo": "oops"},
    ],
)
def test_malformed_product_raises_shape_error_naming_store(bad) -> None:
    with pytest.raises(ResponseShapeError, match="Lider"):
        parse_product_page(page(product(**bad)))


def test_next_data_without_product_raises_shape_error() -> None:
    with pytest.raises(ResponseShapeError, match="Lider"):
        parse_product_page(
            '<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script>'
        )


def test_html_without_next_data_raises_clear_error() -> None:
    with pytest.raises(AdapterError, match="Lider"):
        parse_product_page("<html><body>hello</body></html>")


def test_perimeterx_page_raises_blocked() -> None:
    adapter, _ = make_adapter(ok('<html><body><div id="px-captcha"></div></body></html>'))
    with pytest.raises(BlockedError, match="Lider"):
        adapter.fetch(["00780142021013"])


def test_blocked_redirect_page_raises_blocked() -> None:
    adapter, _ = make_adapter(
        ok('<html><script>window.location="/blocked?url=abc"</script></html>')
    )
    with pytest.raises(BlockedError, match="Lider"):
        adapter.fetch(["00780142021013"])


@pytest.mark.parametrize("status", [403, 412])
def test_blocking_status_raises_blocked(status) -> None:
    adapter, _ = make_adapter(RawResponse(status, "denied"))
    with pytest.raises(BlockedError, match="Lider"):
        adapter.fetch(["00780142021013"])


def test_missing_page_is_skipped() -> None:
    urls = {"gone": "https://super.lider.cl/ip/x/gone", "00780142021013": URL}
    adapter, _ = make_adapter(
        RawResponse(404, ""), fixture_response("lider", "product_page.html"), urls=urls
    )
    assert [listing.sku for listing in adapter.fetch(["gone", "00780142021013"])] == [
        "00780142021013"
    ]


def test_sku_without_url_is_an_error() -> None:
    adapter, transport = make_adapter()
    with pytest.raises(AdapterError, match="no product url"):
        adapter.fetch(["unknown"])
    assert transport.calls == []


def test_search_is_never_attempted() -> None:
    adapter, transport = make_adapter()
    assert adapter.supports_search is False
    with pytest.raises(NotImplementedError):
        adapter.search("arroz")
    assert transport.calls == []


def test_registry_builds_urls_from_matches_and_smoke_settings() -> None:
    config = AppConfig(
        basket=[make_item()],
        stores={
            "lider": make_store_config(
                "Lider", smoke_sku="S1", smoke_url="https://super.lider.cl/ip/x/S1"
            )
        },
        matches={"rice": {"lider": make_match("00780142021013", url=URL)}},
    )
    adapter = build_adapters(config, transport_factory=lambda: FakeTransport([]))["lider"]
    assert adapter.url_by_sku == {"00780142021013": URL, "S1": "https://super.lider.cl/ip/x/S1"}


RECORDED = FIXTURES / "lider" / "recorded_fetch.html"


@pytest.mark.skipif(not RECORDED.exists(), reason="recorded fixture not captured yet")
def test_recorded_page_parses() -> None:
    listing = parse_product_page(RECORDED.read_text(encoding="utf-8"))
    assert listing.sku and listing.name
    assert listing.price and listing.price > 0
