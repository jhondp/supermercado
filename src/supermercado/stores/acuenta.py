"""aCuenta adapter: Instaleap headless GraphQL API (clientId comes from config)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from math import isfinite
from typing import Any

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import UnknownUnitError, normalize, parse_size
from supermercado.stores.base import AdapterError, HttpClient, RawResponse, ResponseShapeError

SITE_URL = "https://www.acuenta.cl"
_FIELDS = (
    "name sku brand price unit subUnit subQty clickMultiplier stock isAvailable "
    "promotion { type isActive conditions { price quantity } }"
)
SEARCH_QUERY = (
    "query Search($input: SearchProductsInput!) "
    "{ searchProducts(searchProductsInput: $input) { products { " + _FIELDS + " } } }"
)
# Input type and `skus` key verified against the live API on 2026-10-04 (store 580).
SKU_QUERY = (
    "query BySku($input: GetProductsBySKUInput!) "
    "{ getProductsBySKU(getProductsBySKUInput: $input) { " + _FIELDS + " } }"
)


def _clp(value: Any) -> int | None:
    """Whole CLP, half-up; None when absent or not positive. Non-numbers are malformed."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"price {value!r} is not a number")
    amount = int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return amount if amount > 0 else None


def _promo(product: dict[str, Any], price: int | None, promo_types: frozenset[str]) -> int | None:
    promotion = product.get("promotion")
    if promotion is None:
        return None
    if not isinstance(promotion, dict):
        raise TypeError("promotion is not an object")
    if price is None or not promotion.get("isActive"):
        return None
    conditions = promotion.get("conditions") or []
    if isinstance(conditions, dict):
        conditions = [conditions]
    if not isinstance(conditions, list):
        raise TypeError("promotion conditions is not a list")
    if str(promotion.get("type") or "").strip().lower() not in promo_types:
        return None
    for condition in conditions:
        amount = _clp(condition.get("price"))
        # Live (2026-10-04): "specialPrice" conditions carry quantity 0 (no minimum); "nx$"
        # multi-buys carry the required quantity (2, 3, ...). A missing quantity is not evidence
        # of "no minimum", so it stays conditional.
        quantity = _quantity(condition.get("quantity"))
        if quantity is not None and quantity <= 1 and amount is not None and amount < price:
            return amount
    return None


def _quantity(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"promotion quantity {value!r} is not a number")
    return value


def _size(product: dict[str, Any]) -> tuple[float, Unit] | None:
    parsed = parse_size(str(product.get("name") or ""))
    if parsed is None and product.get("subUnit") and product.get("subQty"):
        try:
            parsed = normalize(float(product["subQty"]), str(product["subUnit"]))
        except UnknownUnitError:
            parsed = None
    return parsed


def _multiplier(value: Any) -> float:
    if value is None:
        return 1.0
    if isinstance(value, bool):
        raise TypeError("clickMultiplier is not a number")
    multiplier = float(value)
    if not isfinite(multiplier) or multiplier <= 0:
        raise ValueError(f"clickMultiplier {value!r} must be finite and positive")
    return multiplier


def _listing(product: dict[str, Any], promo_types: frozenset[str]) -> Listing:
    if not isinstance(product["sku"], (str, int)):
        raise TypeError("sku is not a string")
    price = _clp(product.get("price"))
    weighted = str(product.get("unit") or "").strip().lower() == "kg"
    size, unit = (1.0, Unit.KG) if weighted else (_size(product) or (None, None))
    stock = product.get("stock") or 0
    return Listing(
        sku=str(product["sku"]),
        name=str(product.get("name") or ""),
        brand=product.get("brand"),
        url=None,
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        multiplier=_multiplier(product.get("clickMultiplier")),
        price=price,
        promo_price=_promo(product, price, promo_types),
        available=bool(product.get("isAvailable")) and stock > 0,
    )


def parse_products(
    payload: Any, field: str, promo_types: frozenset[str] = frozenset()
) -> list[Listing]:
    """Parse products; only promotions whose type is in `promo_types` can become promo_price."""
    if not isinstance(payload, dict):
        raise ResponseShapeError("aCuenta response is not a JSON object")
    if payload.get("errors"):
        raise ResponseShapeError(f"aCuenta GraphQL errors: {str(payload['errors'])[:300]}")
    data = payload.get("data")
    data = data.get(field) if isinstance(data, dict) else None
    if isinstance(data, dict):
        data = data.get("products")
    if not isinstance(data, list):
        raise ResponseShapeError(f"aCuenta response has no {field} products")
    try:
        return [
            _listing(product, promo_types)
            for product in data
            if not isinstance(product, dict) or product.get("sku")
        ]
    except (AttributeError, TypeError, ValueError, KeyError, InvalidOperation) as exc:
        raise ResponseShapeError(f"aCuenta {field}: malformed product data: {exc!r}") from exc


class AcuentaAdapter:
    store_id = "acuenta"
    supports_search = True
    page_size = 40
    batch_size = 50

    def __init__(self, client: HttpClient, config: StoreConfig) -> None:
        self._client = client
        self._config = config

    def raw_search(self, query: str) -> RawResponse:
        return self._post(
            SEARCH_QUERY,
            {"currentPage": 1, "pageSize": self.page_size, "search": [{"query": query}]},
        )

    def raw_fetch(self, sku: str) -> RawResponse:
        return self._sku_request([sku])

    def search(self, query: str) -> list[Listing]:
        return parse_products(self.raw_search(query).json(), "searchProducts", self._promo_types())

    def fetch(self, skus: list[str]) -> list[Listing]:
        wanted = list(dict.fromkeys(skus))
        found: list[Listing] = []
        for start in range(0, len(wanted), self.batch_size):
            chunk = wanted[start : start + self.batch_size]
            listings = parse_products(
                self._sku_request(chunk).json(), "getProductsBySKU", self._promo_types()
            )
            found.extend(listing for listing in listings if listing.sku in chunk)
        return found

    def _sku_request(self, skus: list[str]) -> RawResponse:
        return self._post(SKU_QUERY, {"skus": skus})

    def _promo_types(self) -> frozenset[str]:
        """Allowlist of promotion types known to be unconditional; empty means no promos."""
        raw = self._config.params.get("unconditional_promo_types", "")
        return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())

    def _setting(self, value: str | None, label: str) -> str:
        if not value:
            raise AdapterError(f"acuenta: {label} is required in config/stores.yaml")
        return value

    def _post(self, query: str, variables: dict[str, Any]) -> RawResponse:
        client_id = self._setting(
            self._config.params.get("client_id"), "params.client_id (Instaleap clientId)"
        )
        store_ref = self._setting(self._config.store_ref, "store_ref (storeReference)")
        return self._client.request(
            "POST",
            self._config.base_url,
            headers={
                "Content-Type": "application/json",
                "Origin": SITE_URL,
                "Referer": f"{SITE_URL}/",
            },
            json={
                "query": query,
                "variables": {
                    "input": {"clientId": client_id, "storeReference": store_ref, **variables}
                },
            },
        )
