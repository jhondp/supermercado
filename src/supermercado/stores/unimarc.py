"""Unimarc adapter: SMU BFF search (needs channel/source/version headers)."""

from __future__ import annotations

from decimal import InvalidOperation
from math import isfinite
from typing import Any

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import parse_clp, parse_size
from supermercado.stores.base import (
    AdapterError,
    HttpClient,
    RawResponse,
    ResponseShapeError,
    fetch_by_search,
)

SEARCH_PATH = "/catalog/product/search"
SITE_URL = "https://www.unimarc.cl"
HEADER_PARAMS = ("channel", "source", "version")
# Live (2026-10-04): a `price` below `listPrice` is tagged in priceDetail.promotionalTag.text.
# "Club Unimarc" (loyalty) and Unipay payment prices are card prices; "Exclusivo .cl" is a web
# price open to everyone. Unknown tags stay card prices (never ranked) until observed.
_OPEN_OFFER_TAGS = frozenset({"exclusivo .cl"})


def _amount(value: Any) -> int | None:
    """Whole CLP from a number or "$1.790"-style string; None when absent or not positive."""
    if value is None or value == "":
        return None
    amount = parse_clp(value)  # ValueError/TypeError on junk becomes ResponseShapeError upstream
    return amount if amount > 0 else None


def _unit_price(value: Any) -> int | None:
    """ppum is informational: junk means 'unknown', not a failed store."""
    try:
        return _amount(value)
    except (ValueError, TypeError):
        return None


def _multiplier(value: Any) -> float:
    if value is None:
        return 1.0
    if isinstance(value, bool):
        raise TypeError("unitMultiplier is not a number")
    multiplier = float(value)
    if not isfinite(multiplier) or multiplier <= 0:
        raise ValueError(f"unitMultiplier {value!r} must be finite and positive")
    return multiplier


def _promo_tag(detail: Any) -> str:
    if detail is None:
        return ""
    if not isinstance(detail, dict):
        raise TypeError("priceDetail is not an object")
    tag = detail.get("promotionalTag")
    if tag is None:
        return ""
    if not isinstance(tag, dict):
        raise TypeError("promotionalTag is not an object")
    return str(tag.get("text") or "").strip().lower()


def _listing(entry: dict[str, Any]) -> Listing:
    item = entry.get("item") or {}
    price = entry.get("price") or {}
    if not isinstance(item["itemId"], (str, int)):
        raise TypeError("itemId is not a string")
    current = _amount(price.get("price"))
    listed = _amount(price.get("listPrice"))
    # A price above listPrice is never trusted as regular; a lower one is club-only unless its
    # promotional tag says the offer is open to every web shopper.
    regular = listed or current
    lower = current if current and listed and current < listed else None
    open_offer = lower is not None and _promo_tag(entry.get("priceDetail")) in _OPEN_OFFER_TAGS
    weighted = str(item.get("measurementUnit") or "").lower() == "kg"
    multiplier = _multiplier(item.get("unitMultiplier"))
    name = str(item.get("nameComplete") or item.get("name") or "")
    if weighted:
        size, unit = multiplier, Unit.KG
    else:
        size, unit = parse_size(name) or (None, None)
    detail = item.get("detailUrl")
    return Listing(
        sku=str(item["itemId"]),
        name=name,
        brand=item.get("brand"),
        url=f"{SITE_URL}{detail}" if isinstance(detail, str) and detail else None,
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        multiplier=multiplier,
        price=regular,
        promo_price=lower if open_offer else None,
        card_price=None if open_offer else lower,
        store_unit_price=_unit_price(price.get("ppum")),
        available=float(price.get("availableQuantity") or 0) > 0,
    )


def parse_search(payload: Any) -> list[Listing]:
    if not isinstance(payload, dict) or not isinstance(payload.get("availableProducts"), list):
        raise ResponseShapeError("Unimarc search response has no 'availableProducts' list")
    try:
        return [
            _listing(entry)
            for entry in payload["availableProducts"]
            if (entry.get("item") or {}).get("itemId")
        ]
    except (AttributeError, TypeError, ValueError, KeyError, InvalidOperation) as exc:
        raise ResponseShapeError(f"Unimarc search: malformed product data: {exc!r}") from exc


class UnimarcAdapter:
    store_id = "unimarc"
    supports_search = True
    page_size = 40

    def __init__(self, client: HttpClient, config: StoreConfig) -> None:
        self._client = client
        self._config = config

    def _api_headers(self) -> dict[str, str]:
        missing = [k for k in HEADER_PARAMS if not self._config.params.get(k)]
        if missing:
            raise AdapterError(
                f"unimarc: params.{', params.'.join(missing)} required in config/stores.yaml"
            )
        return {k: str(self._config.params[k]) for k in HEADER_PARAMS}

    def raw_search(self, query: str) -> RawResponse:
        headers = self._api_headers()
        return self._client.request(
            "POST",
            f"{self._config.base_url}{SEARCH_PATH}",
            headers={
                **headers,
                "Content-Type": "application/json",
                "Origin": SITE_URL,
                "Referer": f"{SITE_URL}/",
            },
            json={"from": "0", "to": str(self.page_size - 1), "searching": query},
        )

    def raw_fetch(self, sku: str) -> RawResponse:
        return self.raw_search(sku)

    def search(self, query: str) -> list[Listing]:
        return parse_search(self.raw_search(query).json())

    def fetch(self, skus: list[str]) -> list[Listing]:
        return fetch_by_search(skus, self.search)
