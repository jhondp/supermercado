"""Shared adapter for Cencosud BFF catalogs (Jumbo, Santa Isabel)."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, ClassVar

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import parse_size
from supermercado.stores.base import (
    AdapterError,
    ApiKeyRejected,
    HttpClient,
    HttpError,
    RawResponse,
    ResponseShapeError,
)

BATCH_SIZE = 40
_CARD_PROMO_RE = re.compile(r"-\s*\$?\s*(\d[\d.]*)\s*$")
_CARD_PROMO_MARKERS = ("TCENCO", "TARJETA")


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    amount = int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return amount if amount > 0 else None


def _card_price(promotions: list[dict[str, Any]], regular: int | None) -> int | None:
    found = []
    for promo in promotions:
        label = str(promo.get("name") or promo.get("description") or "")
        if not any(marker in label.upper() for marker in _CARD_PROMO_MARKERS):
            continue
        if match := _CARD_PROMO_RE.search(label):
            amount = int(match.group(1).replace(".", ""))
            if regular is not None and 0 < amount < regular:
                found.append(amount)
    return min(found) if found else None


def _listing(product: dict[str, Any], item: dict[str, Any], site_url: str) -> Listing:
    current = _positive_int(item.get("price"))
    regular = _positive_int(item.get("listPrice")) or current
    promo = current if current and regular and current < regular else None
    weighted = str(item.get("measurementUnit") or "").lower() == "kg"
    multiplier = float(item.get("unitMultiplier") or 1)
    name = str(item.get("name") or "")
    if weighted:
        size, unit = multiplier, Unit.KG
    else:
        size, unit = parse_size(name) or (None, None)
    slug = product.get("slug")
    return Listing(
        sku=str(item["skuId"]),
        name=name,
        brand=product.get("brand"),
        url=f"{site_url}/{slug}/p" if slug else None,
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        multiplier=multiplier,
        price=regular,
        promo_price=promo,
        card_price=_card_price(item.get("promotions") or [], regular),
        store_unit_price=_positive_int(item.get("ppumPrice")),
        available=bool(item.get("stock")),
    )


def parse_plp(payload: Any, site_url: str) -> list[Listing]:
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        raise ResponseShapeError("Cencosud PLP response has no 'products' list")
    listings: list[Listing] = []
    try:
        for product in payload["products"]:
            for item in product.get("items") or []:
                if item.get("skuId"):
                    listings.append(_listing(product, item, site_url))
    except (AttributeError, TypeError, ValueError, KeyError, InvalidOperation) as exc:
        raise ResponseShapeError(
            f"Cencosud PLP ({site_url}): malformed product data: {exc!r}"
        ) from exc
    return listings


class CencosudAdapter:
    store_id: ClassVar[str] = ""
    site_url: ClassVar[str] = ""
    supports_search: ClassVar[bool] = True
    page_size: ClassVar[int] = 40

    def __init__(self, client: HttpClient, config: StoreConfig) -> None:
        self._client = client
        self._config = config

    def raw_search(self, query: str) -> RawResponse:
        return self._plp(query)

    def raw_fetch(self, sku: str) -> RawResponse:
        return self._plp(f"sku:{sku}")

    def search(self, query: str) -> list[Listing]:
        return parse_plp(self._plp(query).json(), self.site_url)

    def fetch(self, skus: list[str]) -> list[Listing]:
        wanted = list(dict.fromkeys(skus))
        found: list[Listing] = []
        for start in range(0, len(wanted), BATCH_SIZE):
            chunk = wanted[start : start + BATCH_SIZE]
            listings = parse_plp(self._plp("sku:" + ";".join(chunk)).json(), self.site_url)
            found.extend(listing for listing in listings if listing.sku in chunk)
        return found

    def _plp(self, full_text: str) -> RawResponse:
        if not self._config.api_key:
            raise ApiKeyRejected(f"{self.store_id}: no api_key configured in config/stores.yaml")
        if not self._config.store_ref:
            raise AdapterError(f"{self.store_id}: store_ref is required in config/stores.yaml")
        body = {
            "fullText": full_text,
            "store": self._config.store_ref,
            "from": 0,
            "to": self.page_size - 1,
        }
        headers = {
            "apiKey": self._config.api_key,
            "Content-Type": "application/json",
            "Origin": self.site_url,
            "Referer": f"{self.site_url}/",
        }
        try:
            return self._client.request(
                "POST", f"{self._config.base_url}/catalog/plp", headers=headers, json=body
            )
        except HttpError as exc:
            if exc.status in (401, 403):
                raise ApiKeyRejected(
                    f"{self.store_id}: HTTP {exc.status}, apiKey rejected (or request blocked); "
                    "update api_key in config/stores.yaml"
                ) from exc
            raise
