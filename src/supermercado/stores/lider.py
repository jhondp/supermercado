"""Lider adapter: product pages only. robots.txt disallows /search*, so matches are manual."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from decimal import InvalidOperation
from math import isfinite
from typing import Any

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import parse_clp, parse_size
from supermercado.stores.base import (
    AdapterError,
    BlockedError,
    HttpClient,
    HttpError,
    RawResponse,
    ResponseShapeError,
)

log = logging.getLogger(__name__)
SITE_URL = "https://super.lider.cl"
BLOCKING_STATUSES = frozenset({403, 412})
_NEXT_DATA_RE = re.compile(r'<script[^>]*id="?__NEXT_DATA__"?[^>]*>(.*?)</script>', re.S)
_BLOCK_MARKERS = ("px-captcha", "/blocked", "_pxAppId", "Access Denied")


def _price(block: Any) -> int | None:
    """Whole CLP (half-up) from a {"price": n} block; None when absent or not positive."""
    if block is None:
        return None
    value = block["price"] if isinstance(block, dict) else None
    if value is None:
        return None
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("price is not finite")
    amount = parse_clp(value)
    return amount if amount > 0 else None


def _multiplier(value: Any) -> float:
    if value is None:
        return 1.0
    if isinstance(value, bool):
        raise TypeError("averageWeight is not a number")
    multiplier = float(value)
    if not isfinite(multiplier) or multiplier <= 0:
        raise ValueError(f"averageWeight {value!r} must be finite and positive")
    return multiplier


def _listing(product: dict[str, Any]) -> Listing:
    sku = product["usItemId"]
    if not isinstance(sku, (str, int)) or isinstance(sku, bool) or sku == "":
        raise TypeError("usItemId is not a string")
    info = product.get("priceInfo") or {}
    current = _price(info.get("currentPrice"))
    was = _price(info.get("wasPrice"))
    # wasPrice above currentPrice: currentPrice is an unconditional promo over the regular price.
    on_sale = bool(was and current and was > current)
    weighted = product.get("salesUnitType") == "WEIGHT"
    name = str(product.get("name") or "")
    if weighted:
        # Assumes currentPrice is per kg; unverified offline (live check in the task report).
        size, unit = 1.0, Unit.KG
    else:
        size, unit = parse_size(name) or (None, None)
    canonical = product.get("canonicalUrl")
    return Listing(
        sku=str(sku),
        name=name,
        brand=product.get("brand"),
        url=f"{SITE_URL}{canonical}" if isinstance(canonical, str) and canonical else None,
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        multiplier=_multiplier(product.get("averageWeight")) if weighted else 1.0,
        price=was if on_sale else current,
        promo_price=current if on_sale else None,
        available=product.get("availabilityStatus") == "IN_STOCK",
    )


def parse_product_page(html: str) -> Listing:
    match = _NEXT_DATA_RE.search(html)
    if match is None:
        if any(marker in html for marker in _BLOCK_MARKERS):
            raise BlockedError("Lider: anti-bot (PerimeterX) page instead of the product")
        raise ResponseShapeError("Lider: page has no __NEXT_DATA__ script")
    try:
        product = json.loads(match.group(1))["props"]["pageProps"]["initialData"]["data"]["product"]
        return _listing(product)
    except (AttributeError, TypeError, ValueError, KeyError, InvalidOperation) as exc:
        raise ResponseShapeError(f"Lider: malformed product page data: {exc!r}") from exc


class LiderAdapter:
    store_id = "lider"
    supports_search = False

    def __init__(
        self, client: HttpClient, config: StoreConfig, url_by_sku: Mapping[str, str]
    ) -> None:
        self._client = client
        self._config = config
        self.url_by_sku = dict(url_by_sku)

    def search(self, query: str) -> list[Listing]:
        raise NotImplementedError("Lider: search is disallowed by robots.txt; add matches manually")

    def raw_fetch(self, sku: str) -> RawResponse:
        url = self.url_by_sku.get(sku)
        if not url:
            raise AdapterError(f"Lider: no product url for sku {sku}")
        try:
            return self._client.request(
                "GET",
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "es-CL,es;q=0.9",
                },
                cookies=dict(self._config.cookies),
            )
        except HttpError as exc:
            if exc.status in BLOCKING_STATUSES:
                raise BlockedError(f"Lider: blocked with HTTP {exc.status} at {url}") from exc
            raise

    def fetch(self, skus: list[str]) -> list[Listing]:
        listings = []
        for sku in dict.fromkeys(skus):
            try:
                page = self.raw_fetch(sku)
            except HttpError as exc:
                if exc.status == 404:
                    log.warning("Lider: product page for sku %s is gone (404)", sku)
                    continue
                raise
            listings.append(parse_product_page(page.text))
        return listings
