"""Tottus adapter: public search JSON (the HTML is behind Cloudflare, never use it)."""

from __future__ import annotations

from decimal import InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import parse_clp, parse_size
from supermercado.stores.base import HttpClient, RawResponse, ResponseShapeError

SEARCH_PATH = "/s/browse/v1/search/cl"


def _amount(entry: dict[str, Any] | None) -> int | None:
    """First price of a price entry as whole CLP; None when absent or not positive."""
    if not entry:
        return None
    raw = entry.get("price")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw in (None, ""):
        return None
    value = parse_clp(raw)
    return value if value > 0 else None


def _listing(product: dict[str, Any]) -> Listing:
    prices = {entry.get("type"): entry for entry in product.get("prices") or []}
    internet = _amount(prices.get("internetPrice"))
    normal = _amount(prices.get("normalPrice"))
    card = _amount(prices.get("cmrPrice"))
    regular = normal or internet
    promo = internet if normal and internet and internet < normal else None
    public = promo or regular
    measurements = product.get("measurements") or {}
    weighted = str(measurements.get("unit") or "").upper() == "KG"
    name = str(product.get("displayName") or "")
    parsed = parse_size(str(measurements.get("format") or "")) or parse_size(name)
    if weighted:
        size, unit = parsed if parsed and parsed[1] is Unit.KG else (1.0, Unit.KG)
    else:
        size, unit = parsed or (None, None)
    return Listing(
        sku=str(product["skuId"]),
        name=name,
        brand=product.get("brand"),
        url=product.get("url"),
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        price=regular,
        promo_price=promo,
        card_price=card if card and public and card < public else None,
        store_unit_price=_amount((prices.get("internetPrice") or {}).get("pum")),
        available=True,  # the search endpoint only lists purchasable products
    )


def is_redirect(payload: Any) -> bool:
    """A query that is exactly one SKU or product id answers with the product URL, not results."""
    return isinstance(payload, dict) and payload.get("responseType") == "alt"


def redirect_query(payload: dict[str, Any]) -> str:
    """Search words from the redirect URL slug (.../articulo/<productId>/<slug>/<sku>)."""
    data = payload.get("data")
    url = str(data.get("altUrl") or "") if isinstance(data, dict) else ""
    segments = urlsplit(url).path.strip("/").split("/")
    try:
        slug = segments[segments.index("articulo") + 2]
    except (ValueError, IndexError) as exc:
        raise ResponseShapeError(f"Tottus: redirect without a product slug: {url!r}") from exc
    words = slug.replace("-", " ").strip()
    if not words:
        raise ResponseShapeError(f"Tottus: redirect without a product slug: {url!r}")
    return words


def parse_search(payload: Any) -> list[Listing]:
    if is_redirect(payload):
        raise ResponseShapeError("Tottus search redirected to a product page (responseType alt)")
    try:
        results = payload["data"]["results"]
    except (KeyError, TypeError) as exc:
        raise ResponseShapeError("Tottus search response has no data.results") from exc
    if not isinstance(results, list):
        raise ResponseShapeError("Tottus data.results is not a list")
    try:
        return [_listing(product) for product in results if product.get("skuId")]
    except (AttributeError, TypeError, ValueError, KeyError, InvalidOperation) as exc:
        raise ResponseShapeError(f"Tottus search: malformed product data: {exc!r}") from exc


class TottusAdapter:
    store_id = "tottus"
    supports_search = True
    batch_size = 20  # live: "Ntt=<sku> <sku> ..." returns exactly those products (48 per page)

    def __init__(self, client: HttpClient, config: StoreConfig) -> None:
        self._client = client
        self._config = config

    def raw_search(self, query: str) -> RawResponse:
        params: dict[str, Any] = {"page": 1, "Ntt": query}
        if self._config.store_ref:
            params["politicalId"] = self._config.store_ref
        return self._client.request(
            "GET",
            f"{self._config.base_url}{SEARCH_PATH}",
            params=params,
            headers={"Accept": "application/json"},
        )

    def raw_fetch(self, sku: str) -> RawResponse:
        return self.raw_search(sku)

    def search(self, query: str) -> list[Listing]:
        return parse_search(self.raw_search(query).json())

    def fetch(self, skus: list[str]) -> list[Listing]:
        wanted = list(dict.fromkeys(skus))
        found: list[Listing] = []
        for start in range(0, len(wanted), self.batch_size):
            chunk = wanted[start : start + self.batch_size]
            listings = self._results(" ".join(chunk))
            found.extend(listing for listing in listings if listing.sku in chunk)
        return found

    def _results(self, query: str) -> list[Listing]:
        payload = self.raw_search(query).json()
        if is_redirect(payload):
            # A lone SKU is answered with its product URL; the URL slug is the product name,
            # and searching for it lists the product (exact-SKU filtering happens in fetch).
            payload = self.raw_search(redirect_query(payload)).json()
        return parse_search(payload)
