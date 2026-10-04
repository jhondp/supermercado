"""Domain models. Pure data: no HTTP, files, or HTML."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Unit(StrEnum):
    KG = "kg"
    L = "l"
    M = "m"
    UNIT = "unit"


class SoldBy(StrEnum):
    UNIT = "unit"
    WEIGHT = "weight"


class Status(StrEnum):
    OK = "ok"
    SUSPICIOUS = "suspicious"
    SIZE_CHANGED = "size_changed"


class Category(StrEnum):
    PANTRY = "pantry"
    DAIRY_EGGS = "dairy_eggs"
    BAKERY = "bakery"
    MEAT = "meat"
    CLEANING = "cleaning"
    HYGIENE = "hygiene"


class MatchRules(BaseModel):
    """Filters applied to search candidates for a basket item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    size_range: tuple[float, float] | None = None
    exclude: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_range(self) -> MatchRules:
        if self.size_range is not None and self.size_range[0] > self.size_range[1]:
            raise ValueError("size_range lower bound must not exceed the upper bound")
        return self


class BasketItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    category: Category
    unit: Unit
    reference_qty: float = Field(gt=0)
    search: str
    rules: MatchRules = Field(default_factory=MatchRules)


class Match(BaseModel):
    """A human-approved SKU for one (item, store). SKUs must be quoted strings in YAML."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str
    size: float = Field(gt=0)
    approved: date
    url: str | None = None


class Listing(BaseModel):
    """A store product translated by an adapter. `size` is expressed in `unit`."""

    model_config = ConfigDict(frozen=True)

    sku: str
    name: str
    brand: str | None = None
    url: str | None = None
    size: float | None = None
    unit: Unit | None = None
    sold_by: SoldBy = SoldBy.UNIT
    multiplier: float = 1.0
    price: int | None
    promo_price: int | None = None
    card_price: int | None = None
    store_unit_price: int | None = None
    available: bool = True


class PriceObservation(BaseModel):
    """One row of the weekly Parquet snapshot."""

    model_config = ConfigDict(frozen=True)

    week: str = Field(pattern=r"^\d{4}-W\d{2}$")
    scraped_at: datetime
    location: str
    store: str
    item_id: str
    sku: str
    product_name: str
    brand: str | None = None
    url: str | None = None
    size: float = Field(gt=0)
    unit: str
    price: int = Field(gt=0)
    promo_price: int | None = None
    card_price: int | None = None
    effective_price: int = Field(gt=0)
    unit_price: int = Field(ge=0)
    available: bool
    status: Status
