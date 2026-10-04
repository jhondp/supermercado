# Supermarket Price Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a weekly scraper plus a static site that ranks Santiago supermarkets by the cost of a 23-item basic basket, with a clean, traceable price history.

**Architecture:** Light hexagonal. `supermercado.domain` is pure Python (models, unit normalization, validation, ranking, match rules). `supermercado.stores` holds one adapter per chain behind a `StoreAdapter` port and a shared polite HTTP client (`curl_cffi`, Chrome impersonation). `supermercado.pipeline` orchestrates collect / propose / smoke and writes one Parquet file per ISO week. `supermercado.site` reads Parquet with DuckDB and renders Jinja templates into `dist/`, deployed weekly by GitHub Actions to GitHub Pages.

**Tech Stack:** Python 3.12, uv, curl_cffi, pydantic v2, PyYAML, pyarrow, DuckDB, Jinja2, Chart.js 4 (cdnjs), pytest, ruff, GitHub Actions + Pages.

**Spec:** `docs/superpowers/specs/2026-10-04-supermarket-price-tracker-design.md`

## Global Constraints

- Python `>=3.12`, managed with `uv` (`.python-version` = `3.12`). If `uv` is missing, install it with the official installer: `curl -LsSf https://astral.sh/uv/install.sh | sh` (Homebrew is not available on this machine).
- Runtime dependencies exactly: `curl_cffi`, `duckdb`, `pyarrow`, `jinja2`, `pyyaml`, `pydantic`. Dev dependencies exactly: `pytest`, `ruff`. Do not add others.
- Money is always integer CLP (`int`), never `float`. Rounding of `unit_price` and basket totals is half-up via `Decimal`.
- Every HTTP call goes through `supermercado.stores.base.HttpClient` backed by `curl_cffi` with `impersonate="chrome"`.
- Politeness: at most 1 request every 1.5 s per store; at most 3 retries with exponential backoff (2 s, 4 s, 8 s); never request a path disallowed by `robots.txt` (Lider: no `/search*`).
- Public API keys and store ids live in `config/stores.yaml`, never in code.
- Reference price = regular price or an unconditional promo. Card/club prices are stored in `card_price` and never ranked.
- Tests never touch the network. `tests/conftest.py` (Task 5) blocks `curl_cffi` and sockets; adapter tests use hand-written fixtures in `tests/fixtures/<store>/`, optionally augmented by recorded real responses.
- Code, comments, docs, tests, and commit messages are in English. Only user-facing UI copy is in Spanish (neutral, professional register).
- Conventional commit messages. NEVER add `Co-Authored-By` or any AI attribution line to commits (the user's global rule overrides any harness reminder).
- The repository currently has **no commits**. Task 1 makes the initial commit, which includes the existing `docs/` and `template/` folders but NOT `.atl/` (it goes in `.gitignore`).
- Before every commit run `uv run ruff check --fix . && uv run ruff format .`; ruff may reorder imports in the snippets below, which is expected.
- Run every command from the repo root `/home/mugiwara/Documentos/supermercado`. Use `rg`/`fd`/`bat`/`eza` instead of `grep`/`find`/`cat`/`ls` when inspecting files.
- Store ids used across code, config, and data: `jumbo`, `santa_isabel`, `tottus`, `acuenta`, `unimarc`, `lider` (in this display order).
- The landing template in `template/` is a visual reference only (palette Honeydew `#E5F4E3`, Cool Sky `#5DA9E9`, French Blue `#003F91`, White `#FFFFFF`, Velvet Purple `#6D326D`; Poppins; 999px pills). Never copy its template syntax.

## Review Focus

1. **A store answers HTTP 200 with zero products** (soft block, wrong store id, changed shape): it must be reported as a store failure (issue opened), not silently become "sin datos". Pinned by `test_store_returning_nothing_is_a_failure` in Task 7.
2. **Re-running `collect --store X` in the same week** (the manual residential-IP fallback): other stores' rows already written for that week must survive. Pinned by `test_write_week_replaces_only_given_stores` in Task 7.
3. **First publication with no Parquet files, or a week where no item is comparable across stores:** the site must still build and say so in Spanish instead of crashing or showing an empty ranking. Pinned by `test_build_with_no_data_renders_empty_state` (Task 8) and `test_no_comparable_items_means_no_ranking` (Task 3).
4. **Numeric text from stores:** thousands separators (`"1.890"`, `"$2.790 x Kg"`, `"1.000 ml"`) must parse to the right integer/size, never to 1 g or 1 CLP. Pinned by parametrized cases in Task 1.
5. **An unquoted numeric SKU in `matches.yaml`** (e.g. Lider `00780142021013`) silently loses leading zeros in YAML and would never match: config loading must reject non-string SKUs. Pinned by `test_unquoted_numeric_sku_is_rejected` in Task 4.

## File Structure

```
pyproject.toml, uv.lock, .python-version, .gitignore
config/
  basket.yaml            # 23 basket items + match rules (Task 4)
  matches.yaml           # approved SKU per (item, store); comment-only at start (Task 4)
  stores.yaml            # per-store base_url, api_key, store_ref, comuna, smoke SKU (Task 4)
  cleared.yaml           # manual clearances of suspicious rows (Task 4)
src/supermercado/
  __init__.py, __main__.py
  cli.py                 # collect | build | issue-body | propose | smoke
  config.py              # StoreConfig, AppConfig, load_config, ConfigError
  domain/
    models.py            # Unit, SoldBy, Status, Category, MatchRules, BasketItem, Match, Listing, PriceObservation
    units.py             # normalize, parse_size, parse_clp, compute_unit_price
    validation.py        # effective_price, build_observation, apply_clearances
    ranking.py           # comparable_items, basket_total, rank_stores
    matching.py          # normalize_text, matches_rules, filter_candidates (Task 15)
  stores/
    __init__.py          # FACTORIES registry + build_adapters
    base.py              # errors, RawResponse, HttpClient, curl_transport, StoreAdapter
    cencosud.py          # shared Cencosud BFF adapter
    jumbo.py, santa_isabel.py, tottus.py, acuenta.py, unimarc.py, lider.py
  pipeline/
    collect.py           # collect(), iso_week()
    storage.py           # Parquet read/write per ISO week
    report.py            # report_to_dict, render_issue_body
    propose.py           # propose(), render_proposals()
    smoke.py             # smoke(), render_smoke_table()
  site/
    build.py             # load_observations (DuckDB), render_site, build_site
    format.py            # format_clp, format_change, format_date_es
    templates/           # base, index, products, product, methodology
    static/              # style.css, app.js
scripts/record_fixtures.py
data/prices/YYYY-Www.parquet
docs/store-locations.md  # Task 17
tests/ (conftest.py, fakes.py, factories.py, domain/, stores/, pipeline/, site/, fixtures/<store>/)
.github/workflows/weekly.yml, contract-smoke.yml
```

Task order: vertical slice first (Tasks 1–9 ship a working Jumbo-only weekly site), then the remaining adapters (10–14), proposals (15), contract smoke (16), and store-location pinning (17).

---

### Task 1: Project scaffold, domain models, unit normalization and price parsing

**Files:**
- Create: `.gitignore`, `.python-version`, `pyproject.toml`, `uv.lock` (generated)
- Create: `src/supermercado/__init__.py`, `src/supermercado/domain/__init__.py`
- Create: `src/supermercado/domain/models.py`, `src/supermercado/domain/units.py`
- Create: `tests/factories.py`
- Test: `tests/domain/test_models.py`, `tests/domain/test_units.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `supermercado.domain.models`: `Unit` (StrEnum: `KG="kg"`, `L="l"`, `M="m"`, `UNIT="unit"`), `SoldBy` (`UNIT`, `WEIGHT`), `Status` (`OK="ok"`, `SUSPICIOUS="suspicious"`, `SIZE_CHANGED="size_changed"`), `Category` (`pantry`, `dairy_eggs`, `bakery`, `meat`, `cleaning`, `hygiene`), `MatchRules(size_range: tuple[float, float] | None, exclude: list[str])`, `BasketItem(id, name, category, unit, reference_qty, search, rules)`, `Match(sku: str, size: float, approved: date, url: str | None)`, `Listing(sku, name, brand, url, size, unit, sold_by, multiplier, price, promo_price, card_price, store_unit_price, available)`, `PriceObservation(week, scraped_at, location, store, item_id, sku, product_name, brand, url, size, unit, price, promo_price, card_price, effective_price, unit_price, available, status)`.
  - `supermercado.domain.units`: `UnknownUnitError(ValueError)`, `normalize(size: float, raw_unit: str) -> tuple[float, Unit]`, `parse_size(text: str) -> tuple[float, Unit] | None`, `parse_clp(value: str | int | float) -> int`, `compute_unit_price(effective_price: int, size: float) -> int`.
  - `tests/factories.py`: `make_item(...) -> BasketItem`, `make_listing(**overrides) -> Listing`, `make_match(sku="1626", *, size=1.0, url=None) -> Match`.

- [ ] **Step 1: Make the initial commit with the existing docs**

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
dist/
build/
*.duckdb
*.duckdb.wal
.atl/
```

Run:

```bash
git add .gitignore docs template
git status --short
git commit -m "chore: add design spec and landing template reference"
```

Expected: `git status --short` lists only `.gitignore`, `docs/...`, `template/...` as staged; `.atl/` does not appear.

- [ ] **Step 2: Create the uv project files**

`.python-version`:

```text
3.12
```

`pyproject.toml`:

```toml
[project]
name = "supermercado"
version = "0.1.0"
description = "Weekly grocery basket price tracker for Santiago supermarkets"
requires-python = ">=3.12"
dependencies = [
    "curl_cffi>=0.7",
    "duckdb>=1.1",
    "jinja2>=3.1",
    "pyarrow>=17",
    "pydantic>=2.8",
    "pyyaml>=6.0",
]

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/supermercado"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
addopts = "--import-mode=importlib"

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]
```

`src/supermercado/__init__.py`:

```python
"""Supermarket basket price tracker for Santiago."""
```

`src/supermercado/domain/__init__.py`:

```python
"""Pure domain logic: no HTTP, files, or HTML."""
```

Run: `uv sync`
Expected: creates `.venv/` and `uv.lock`, installs the six runtime and two dev dependencies.

- [ ] **Step 3: Write the failing model and unit tests**

`tests/factories.py`:

```python
"""Test data builders shared across the suite."""

from __future__ import annotations

from datetime import date

from supermercado.domain.models import (
    BasketItem,
    Category,
    Listing,
    Match,
    MatchRules,
    Unit,
)


def make_item(
    item_id: str = "rice",
    *,
    unit: Unit = Unit.KG,
    reference_qty: float = 1.0,
    category: Category = Category.PANTRY,
    name: str = "Arroz grado 2",
    search: str = "arroz grado 2",
    size_range: tuple[float, float] | None = None,
    exclude: tuple[str, ...] = (),
) -> BasketItem:
    return BasketItem(
        id=item_id,
        name=name,
        category=category,
        unit=unit,
        reference_qty=reference_qty,
        search=search,
        rules=MatchRules(size_range=size_range, exclude=list(exclude)),
    )


def make_listing(**overrides: object) -> Listing:
    data: dict[str, object] = {
        "sku": "1626",
        "name": "Arroz Grado 2 Tucapel 1 kg",
        "brand": "Tucapel",
        "url": "https://www.jumbo.cl/arroz-grado-2-tucapel-1-kg/p",
        "size": 1.0,
        "unit": Unit.KG,
        "price": 1810,
    }
    data.update(overrides)
    return Listing(**data)


def make_match(sku: str = "1626", *, size: float = 1.0, url: str | None = None) -> Match:
    return Match(sku=sku, size=size, approved=date(2026, 10, 4), url=url)
```

`tests/domain/test_models.py`:

```python
from datetime import date

import pytest
from factories import make_item, make_listing
from pydantic import ValidationError

from supermercado.domain.models import Match, MatchRules


def test_listing_is_immutable() -> None:
    listing = make_listing()
    with pytest.raises(ValidationError):
        listing.price = 1  # type: ignore[misc]


def test_listing_allows_missing_price() -> None:
    assert make_listing(price=None).price is None


def test_match_rejects_numeric_sku() -> None:
    with pytest.raises(ValidationError):
        Match(sku=780142021013, size=1.0, approved=date(2026, 10, 4))  # type: ignore[arg-type]


def test_rules_reject_inverted_size_range() -> None:
    with pytest.raises(ValidationError):
        MatchRules(size_range=(1.0, 0.9))


def test_basket_item_requires_positive_reference_qty() -> None:
    with pytest.raises(ValidationError):
        make_item(reference_qty=0)
```

`tests/domain/test_units.py`:

```python
import pytest

from supermercado.domain.models import Unit
from supermercado.domain.units import (
    UnknownUnitError,
    compute_unit_price,
    normalize,
    parse_clp,
    parse_size,
)


@pytest.mark.parametrize(
    ("size", "raw_unit", "expected"),
    [
        (1, "kg", (1.0, Unit.KG)),
        (400, "g", (0.4, Unit.KG)),
        (500, "ml", (0.5, Unit.L)),
        (1, "L", (1.0, Unit.L)),
        (3, "Lt", (3.0, Unit.L)),
        (12, "un", (12.0, Unit.UNIT)),
        (30, "mts", (30.0, Unit.M)),
        (1, "Kg.", (1.0, Unit.KG)),
    ],
)
def test_normalize_converts_to_canonical_units(size, raw_unit, expected) -> None:
    assert normalize(size, raw_unit) == expected


def test_normalize_rejects_unknown_unit() -> None:
    with pytest.raises(UnknownUnitError):
        normalize(1, "pack")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Arroz Grado 2 Tucapel Blue Grano Largo y Delgado 1 kg", (1.0, Unit.KG)),
        ("Arroz Tucapel G2 Grano Largo Ancho 1 Kg", (1.0, Unit.KG)),
        ("Spaghetti N°5 Carozzi 400 g", (0.4, Unit.KG)),
        ("Aceite Vegetal Belmont 1 L", (1.0, Unit.L)),
        ("Lavalozas Quix Limón 500 ml", (0.5, Unit.L)),
        ("Leche Entera Colun 1,5 L", (1.5, Unit.L)),
        ("Detergente Líquido 1.000 ml", (1.0, Unit.L)),
        ("Jabón de tocador 3 x 90 g", (0.27, Unit.KG)),
        ("Papel Higiénico Doble Hoja 4 rollos 30 m", (120.0, Unit.M)),
        ("Té Supremo 100 bolsitas", (100.0, Unit.UNIT)),
        ("Huevos Blancos Extra x12", (12.0, Unit.UNIT)),
        ("Huevo Color Extra 12 un", (12.0, Unit.UNIT)),
        ("1 KG", (1.0, Unit.KG)),
        ("Marraqueta granel", None),
        ("Leche Entera 2 marcas", None),
    ],
)
def test_parse_size_reads_product_names(text, expected) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.890", 1890),
        ("$2.790 x Kg", 2790),
        ("$ 990", 990),
        ("12.345.678", 12345678),
        (1290, 1290),
        (1290.0, 1290),
    ],
)
def test_parse_clp_handles_thousands_separators(value, expected) -> None:
    assert parse_clp(value) == expected


@pytest.mark.parametrize("value", ["", "sin precio"])
def test_parse_clp_rejects_text_without_digits(value) -> None:
    with pytest.raises(ValueError):
        parse_clp(value)


@pytest.mark.parametrize(
    ("price", "size", "expected"),
    [(1810, 1.0, 1810), (990, 0.4, 2475), (1000, 0.3, 3333), (1001, 2.0, 501)],
)
def test_compute_unit_price_rounds_half_up(price, size, expected) -> None:
    assert compute_unit_price(price, size) == expected


def test_compute_unit_price_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError):
        compute_unit_price(1000, 0)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/domain -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.domain.models'`.

- [ ] **Step 5: Implement the domain models**

`src/supermercado/domain/models.py`:

```python
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
```

- [ ] **Step 6: Implement unit normalization and price parsing**

`src/supermercado/domain/units.py`:

```python
"""Unit normalization and price parsing. Pure functions, no I/O."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from supermercado.domain.models import Unit


class UnknownUnitError(ValueError):
    """Raised when a unit string cannot be mapped to a canonical Unit."""


_ALIASES: dict[str, tuple[Unit, float]] = {
    "kg": (Unit.KG, 1.0),
    "kgs": (Unit.KG, 1.0),
    "kilo": (Unit.KG, 1.0),
    "kilos": (Unit.KG, 1.0),
    "g": (Unit.KG, 0.001),
    "gr": (Unit.KG, 0.001),
    "grs": (Unit.KG, 0.001),
    "gramos": (Unit.KG, 0.001),
    "l": (Unit.L, 1.0),
    "lt": (Unit.L, 1.0),
    "lts": (Unit.L, 1.0),
    "litro": (Unit.L, 1.0),
    "litros": (Unit.L, 1.0),
    "ml": (Unit.L, 0.001),
    "cc": (Unit.L, 0.001),
    "m": (Unit.M, 1.0),
    "mt": (Unit.M, 1.0),
    "mts": (Unit.M, 1.0),
    "metros": (Unit.M, 1.0),
    "un": (Unit.UNIT, 1.0),
    "und": (Unit.UNIT, 1.0),
    "unid": (Unit.UNIT, 1.0),
    "unidad": (Unit.UNIT, 1.0),
    "unidades": (Unit.UNIT, 1.0),
    "u": (Unit.UNIT, 1.0),
    "unit": (Unit.UNIT, 1.0),
}

_NUM = r"(\d+(?:[.,]\d+)?)"
_MEASURE = r"(kgs?|kilos?|gramos|grs?|g|ml|cc|litros?|lts?|l|metros|mts?|m)"
_ROLLS_RE = re.compile(
    rf"(\d+)\s*(?:rollos?|un\b\.?|unid\w*)\D*?{_NUM}\s*(?:metros|mts?|m)\b", re.IGNORECASE
)
_PACK_RE = re.compile(rf"(\d+)\s*x\s*{_NUM}\s*{_MEASURE}\b", re.IGNORECASE)
_SIZE_RE = re.compile(rf"{_NUM}\s*{_MEASURE}\b", re.IGNORECASE)
_COUNT_RE = re.compile(
    r"\bx\s*(\d+)\b|\b(\d+)\s*(?:un|unid|unidades|bolsitas|sobres|huevos)\b", re.IGNORECASE
)
_THOUSANDS_RE = re.compile(r"\d{1,3}\.\d{3}")
_CLP_RE = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+")


def normalize(size: float, raw_unit: str) -> tuple[float, Unit]:
    """Convert a size in any supported unit to (size, canonical unit)."""
    key = raw_unit.strip().lower().rstrip(".")
    if key not in _ALIASES:
        raise UnknownUnitError(raw_unit)
    unit, factor = _ALIASES[key]
    return round(size * factor, 6), unit


def _number(raw: str, unit_key: str) -> float:
    # "1.000 ml" means one thousand millilitres, not one.
    if _THOUSANDS_RE.fullmatch(raw) and _ALIASES[unit_key.lower()][1] < 1:
        return float(raw.replace(".", ""))
    return float(raw.replace(",", "."))


def parse_size(text: str) -> tuple[float, Unit] | None:
    """Extract the package size from a product name or format string."""
    if match := _ROLLS_RE.search(text):
        meters = int(match.group(1)) * float(match.group(2).replace(",", "."))
        return normalize(meters, "m")
    if match := _PACK_RE.search(text):
        count = int(match.group(1))
        return normalize(count * _number(match.group(2), match.group(3)), match.group(3))
    if match := _SIZE_RE.search(text):
        return normalize(_number(match.group(1), match.group(2)), match.group(2))
    if match := _COUNT_RE.search(text):
        return normalize(float(match.group(1) or match.group(2)), "un")
    return None


def parse_clp(value: str | int | float) -> int:
    """Parse a CLP amount such as "1.890" or "$2.790 x Kg" into an int."""
    if isinstance(value, bool):
        raise TypeError("bool is not a price")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    match = _CLP_RE.search(value)
    if match is None:
        raise ValueError(f"no CLP amount in {value!r}")
    return int(match.group(0).replace(".", ""))


def compute_unit_price(effective_price: int, size: float) -> int:
    """Price per canonical unit, rounded half-up to whole CLP."""
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    ratio = Decimal(effective_price) / Decimal(str(size))
    return int(ratio.quantize(Decimal(1), rounding=ROUND_HALF_UP))
```

- [ ] **Step 7: Run tests and lint**

Run: `uv run pytest tests/domain -v && uv run ruff check --fix . && uv run ruff format .`
Expected: all tests PASS; ruff reports no remaining issues.

- [ ] **Step 8: Commit**

```bash
git add .python-version pyproject.toml uv.lock src tests
git commit -m "feat(domain): add domain models, unit normalization and price parsing"
```

---

### Task 2: Validation statuses

**Files:**
- Create: `src/supermercado/domain/validation.py`
- Modify: `tests/factories.py` (add `make_obs`)
- Test: `tests/domain/test_validation.py`

**Interfaces:**
- Consumes: `BasketItem`, `Match`, `Listing`, `PriceObservation`, `Status` (Task 1); `compute_unit_price` (Task 1).
- Produces (`supermercado.domain.validation`):
  - `SIZE_TOLERANCE = 0.01`, `SUSPICIOUS_CHANGE = 0.5`
  - `effective_price(listing: Listing) -> int | None`
  - `size_changed(approved: float, observed: float) -> bool`
  - `is_suspicious(current: int, previous: int | None) -> bool`
  - `build_observation(*, week: str, scraped_at: datetime, store: str, item: BasketItem, match: Match, listing: Listing, previous_unit_price: int | None, location: str = "santiago") -> PriceObservation | None` (returns `None` when the row must be dropped)
  - `apply_clearances(observations: Iterable[PriceObservation], cleared: Collection[tuple[str, str, str]]) -> list[PriceObservation]` (key = `(week, store, item_id)`)
  - `tests/factories.py`: `make_obs(**overrides) -> PriceObservation`

- [ ] **Step 1: Add the observation factory**

Append to `tests/factories.py` (add `from datetime import UTC, datetime` and `PriceObservation, Status` to the existing imports at the top):

```python
def make_obs(**overrides: object) -> PriceObservation:
    data: dict[str, object] = {
        "week": "2026-W40",
        "scraped_at": datetime(2026, 9, 28, 9, 0, tzinfo=UTC),
        "location": "santiago",
        "store": "jumbo",
        "item_id": "rice",
        "sku": "1626",
        "product_name": "Arroz Grado 2 Tucapel 1 kg",
        "brand": "Tucapel",
        "url": "https://www.jumbo.cl/arroz-grado-2-tucapel-1-kg/p",
        "size": 1.0,
        "unit": "kg",
        "price": 1810,
        "promo_price": None,
        "card_price": None,
        "effective_price": 1810,
        "unit_price": 1810,
        "available": True,
        "status": Status.OK,
    }
    data.update(overrides)
    return PriceObservation(**data)
```

- [ ] **Step 2: Write the failing tests**

`tests/domain/test_validation.py`:

```python
from datetime import UTC, datetime

from factories import make_item, make_listing, make_match, make_obs

from supermercado.domain.models import Status, Unit
from supermercado.domain.validation import (
    apply_clearances,
    build_observation,
    effective_price,
    is_suspicious,
)

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)


def observe(listing, *, match=None, item=None, previous=None):
    return build_observation(
        week="2026-W40",
        scraped_at=NOW,
        store="jumbo",
        item=item or make_item(),
        match=match or make_match(),
        listing=listing,
        previous_unit_price=previous,
    )


def test_effective_price_uses_regular_price_without_promo() -> None:
    assert effective_price(make_listing(price=1810)) == 1810


def test_effective_price_uses_lower_unconditional_promo() -> None:
    assert effective_price(make_listing(price=1590, promo_price=1290)) == 1290


def test_effective_price_ignores_promo_not_below_price() -> None:
    assert effective_price(make_listing(price=1590, promo_price=1590)) == 1590
    assert effective_price(make_listing(price=1590, promo_price=0)) == 1590


def test_effective_price_is_none_for_missing_or_non_positive_price() -> None:
    assert effective_price(make_listing(price=None)) is None
    assert effective_price(make_listing(price=0)) is None


def test_card_price_never_becomes_effective() -> None:
    assert effective_price(make_listing(price=1590, card_price=1150)) == 1590


def test_build_observation_ok_row() -> None:
    obs = observe(make_listing(price=1590, promo_price=1290, card_price=1150))
    assert obs is not None
    assert obs.status is Status.OK
    assert obs.week == "2026-W40"
    assert obs.price == 1590
    assert obs.promo_price == 1290
    assert obs.card_price == 1150
    assert obs.effective_price == 1290
    assert obs.unit_price == 1290
    assert obs.unit == "kg"
    assert obs.location == "santiago"


def test_build_observation_drops_row_without_price() -> None:
    assert observe(make_listing(price=None)) is None
    assert observe(make_listing(price=-5)) is None


def test_promo_not_stored_when_not_effective() -> None:
    obs = observe(make_listing(price=1590, promo_price=1700))
    assert obs is not None
    assert obs.promo_price is None


def test_size_change_beyond_tolerance_is_flagged() -> None:
    obs = observe(make_listing(size=0.9, price=1800), match=make_match(size=1.0))
    assert obs is not None
    assert obs.status is Status.SIZE_CHANGED
    assert obs.size == 0.9
    assert obs.unit_price == 2000


def test_size_within_tolerance_is_ok() -> None:
    obs = observe(make_listing(size=0.995), match=make_match(size=1.0))
    assert obs is not None
    assert obs.status is Status.OK


def test_unknown_listing_size_falls_back_to_approved_size() -> None:
    obs = observe(make_listing(size=None, unit=None, price=990), match=make_match(size=0.4))
    assert obs is not None
    assert obs.size == 0.4
    assert obs.unit_price == 2475
    assert obs.status is Status.OK


def test_listing_in_other_unit_falls_back_to_approved_size() -> None:
    item = make_item("toilet_paper", unit=Unit.M, reference_qty=120.0)
    obs = observe(
        make_listing(size=4.0, unit=Unit.UNIT, price=3000),
        item=item,
        match=make_match(size=120.0),
    )
    assert obs is not None
    assert obs.size == 120.0
    assert obs.unit == "m"
    assert obs.unit_price == 25


def test_jump_over_fifty_percent_is_suspicious() -> None:
    obs = observe(make_listing(price=1610), previous=1000)
    assert obs is not None
    assert obs.status is Status.SUSPICIOUS


def test_exactly_fifty_percent_is_not_suspicious() -> None:
    assert is_suspicious(1500, 1000) is False
    assert is_suspicious(500, 1000) is False
    assert is_suspicious(499, 1000) is True


def test_no_previous_week_is_not_suspicious() -> None:
    assert is_suspicious(5000, None) is False


def test_size_change_takes_precedence_over_suspicious() -> None:
    obs = observe(make_listing(size=0.5, price=1810), previous=1000)
    assert obs is not None
    assert obs.status is Status.SIZE_CHANGED


def test_apply_clearances_marks_cleared_rows_ok() -> None:
    flagged = make_obs(status=Status.SUSPICIOUS)
    other = make_obs(store="lider", status=Status.SUSPICIOUS)
    result = apply_clearances([flagged, other], {("2026-W40", "jumbo", "rice")})
    assert [o.status for o in result] == [Status.OK, Status.SUSPICIOUS]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/domain/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.domain.validation'`.

- [ ] **Step 4: Implement validation**

`src/supermercado/domain/validation.py`:

```python
"""Turn a Listing into a validated PriceObservation."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import datetime

from supermercado.domain.models import BasketItem, Listing, Match, PriceObservation, Status
from supermercado.domain.units import compute_unit_price

SIZE_TOLERANCE = 0.01
SUSPICIOUS_CHANGE = 0.5


def effective_price(listing: Listing) -> int | None:
    """Price anyone pays: an unconditional promo below the regular price, else the regular one."""
    if listing.price is None or listing.price <= 0:
        return None
    if listing.promo_price is not None and 0 < listing.promo_price < listing.price:
        return listing.promo_price
    return listing.price


def size_changed(approved: float, observed: float) -> bool:
    return abs(observed - approved) > approved * SIZE_TOLERANCE


def is_suspicious(current: int, previous: int | None) -> bool:
    if previous is None or previous <= 0:
        return False
    return abs(current - previous) > previous * SUSPICIOUS_CHANGE


def build_observation(
    *,
    week: str,
    scraped_at: datetime,
    store: str,
    item: BasketItem,
    match: Match,
    listing: Listing,
    previous_unit_price: int | None,
    location: str = "santiago",
) -> PriceObservation | None:
    """Validate a listing. Returns None when the row must be dropped (missing or non-positive price)."""
    effective = effective_price(listing)
    if effective is None:
        return None
    observed = listing.size if listing.size and listing.unit == item.unit else None
    size = observed if observed is not None else match.size
    unit_price = compute_unit_price(effective, size)
    if observed is not None and size_changed(match.size, observed):
        status = Status.SIZE_CHANGED
    elif is_suspicious(unit_price, previous_unit_price):
        status = Status.SUSPICIOUS
    else:
        status = Status.OK
    card = listing.card_price if listing.card_price and listing.card_price > 0 else None
    return PriceObservation(
        week=week,
        scraped_at=scraped_at,
        location=location,
        store=store,
        item_id=item.id,
        sku=listing.sku,
        product_name=listing.name,
        brand=listing.brand,
        url=listing.url,
        size=size,
        unit=item.unit.value,
        price=listing.price,
        promo_price=effective if effective != listing.price else None,
        card_price=card,
        effective_price=effective,
        unit_price=unit_price,
        available=listing.available,
        status=status,
    )


def apply_clearances(
    observations: Iterable[PriceObservation], cleared: Collection[tuple[str, str, str]]
) -> list[PriceObservation]:
    """Mark manually cleared (week, store, item_id) rows as OK so they can be ranked."""
    result = []
    for obs in observations:
        if obs.status is not Status.OK and (obs.week, obs.store, obs.item_id) in cleared:
            obs = obs.model_copy(update={"status": Status.OK})
        result.append(obs)
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/domain -v && uv run ruff check .`
Expected: PASS, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add src/supermercado/domain/validation.py tests/factories.py tests/domain/test_validation.py
git commit -m "feat(domain): validate observations with suspicious and size-changed statuses"
```

---

### Task 3: Ranking and comparable items

> **AMENDMENT (user decision, 2026-10-04) — overrides the code below where they conflict:**
> - A store is ranked only if it has an `ok`, available observation for at least 80% of basket items that week (`ceil(0.8 * len(basket))`, i.e. 19 of 23).
> - Add parameter `min_coverage: float = 0.8` to `rank_stores` (keyword, last). Compute coverage over `basket` item ids using `_usable`.
> - Add field `insufficient_coverage: list[str]` to `Ranking` (last field, `field(default_factory=list)`), in configured store order. Stores below the threshold are NOT used to compute `comparable_items`, so they never shrink the basket of covered stores. `no_data` (no rows at all) stays separate from `insufficient_coverage`.
> - Existing tests in Step 1 use 3-item baskets with partial data: pass `min_coverage=0.0` to their `rank_stores(...)` calls so they keep their meaning.
> - Add these tests to Step 1:
>
> ```python
> def test_store_below_coverage_threshold_is_not_ranked_and_does_not_shrink_basket() -> None:
>     current = [
>         obs("jumbo", "rice", 1810), obs("jumbo", "spaghetti", 2475), obs("jumbo", "milk", 990),
>         obs("tottus", "rice", 1700), obs("tottus", "spaghetti", 2400), obs("tottus", "milk", 950),
>         obs("lider", "rice", 1190),
>     ]
>     ranking = rank_stores(current, [], BASKET, STORES)
>     assert [t.store for t in ranking.ranked] == ["tottus", "jumbo"]
>     assert ranking.insufficient_coverage == ["lider"]
>     assert ranking.comparable_items == ["rice", "spaghetti", "milk"]
>
>
> def test_coverage_counts_only_ok_and_available_rows() -> None:
>     current = [
>         obs("jumbo", "rice", 1810), obs("jumbo", "spaghetti", 2475), obs("jumbo", "milk", 990),
>         obs("lider", "rice", 1190), obs("lider", "spaghetti", 2600, available=False),
>         obs("lider", "milk", 950, status=Status.SUSPICIOUS),
>     ]
>     ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"])
>     assert ranking.insufficient_coverage == ["lider"]
>     assert [t.store for t in ranking.ranked] == ["jumbo"]
> ```

**Files:**
- Create: `src/supermercado/domain/ranking.py`
- Test: `tests/domain/test_ranking.py`

**Interfaces:**
- Consumes: `BasketItem`, `PriceObservation`, `Status` (Task 1); `make_item`, `make_obs` (Tasks 1–2).
- Produces (`supermercado.domain.ranking`):
  - `@dataclass(frozen=True) StoreTotal(store: str, total: int, change: int | None)`
  - `@dataclass(frozen=True) Ranking(ranked: list[StoreTotal], no_data: list[str], comparable_items: list[str])`
  - `comparable_items(observations: Iterable[PriceObservation], stores: Sequence[str], item_ids: Sequence[str]) -> list[str]`
  - `basket_total(observations: Iterable[PriceObservation], store: str, items: Sequence[BasketItem]) -> int | None`
  - `rank_stores(current: Sequence[PriceObservation], previous: Sequence[PriceObservation], basket: Sequence[BasketItem], stores: Sequence[str]) -> Ranking`

- [ ] **Step 1: Write the failing tests**

`tests/domain/test_ranking.py`:

```python
from factories import make_item, make_obs

from supermercado.domain.models import Status
from supermercado.domain.ranking import basket_total, comparable_items, rank_stores

RICE = make_item("rice")
SPAGHETTI = make_item("spaghetti", reference_qty=0.4, name="Spaghetti 400 g")
MILK = make_item("milk", name="Leche entera 1 L")
BASKET = [RICE, SPAGHETTI, MILK]
STORES = ["jumbo", "lider", "tottus"]


def obs(store, item_id, unit_price, **extra):
    return make_obs(store=store, item_id=item_id, unit_price=unit_price, **extra)


def test_ranks_stores_by_total_over_comparable_items() -> None:
    current = [
        obs("jumbo", "rice", 1810),
        obs("jumbo", "spaghetti", 2475),
        obs("lider", "rice", 1190),
        obs("lider", "spaghetti", 2600),
    ]
    ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"])
    assert [(t.store, t.total) for t in ranking.ranked] == [("lider", 2230), ("jumbo", 2800)]
    assert ranking.comparable_items == ["rice", "spaghetti"]
    assert ranking.no_data == []


def test_item_missing_in_one_store_is_not_comparable() -> None:
    current = [obs("jumbo", "rice", 1810), obs("jumbo", "milk", 990), obs("lider", "rice", 1190)]
    assert comparable_items(current, ["jumbo", "lider"], ["rice", "spaghetti", "milk"]) == ["rice"]


def test_suspicious_or_unavailable_rows_are_not_comparable() -> None:
    current = [
        obs("jumbo", "rice", 1810),
        obs("lider", "rice", 1190, status=Status.SUSPICIOUS),
        obs("jumbo", "milk", 990),
        obs("lider", "milk", 950, available=False),
    ]
    assert comparable_items(current, ["jumbo", "lider"], ["rice", "milk"]) == []


def test_store_without_rows_is_listed_as_no_data_and_does_not_shrink_basket() -> None:
    current = [obs("jumbo", "rice", 1810), obs("lider", "rice", 1190)]
    ranking = rank_stores(current, [], BASKET, STORES)
    assert ranking.no_data == ["tottus"]
    assert [t.store for t in ranking.ranked] == ["lider", "jumbo"]
    assert ranking.comparable_items == ["rice"]


def test_no_comparable_items_means_no_ranking() -> None:
    current = [obs("jumbo", "rice", 1810), obs("lider", "milk", 950)]
    ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"])
    assert ranking.ranked == []
    assert ranking.comparable_items == []


def test_change_vs_previous_week_uses_the_same_items() -> None:
    current = [obs("jumbo", "rice", 1810), obs("lider", "rice", 1190)]
    previous = [
        obs("jumbo", "rice", 1790, week="2026-W39"),
        obs("jumbo", "milk", 900, week="2026-W39"),
    ]
    ranking = rank_stores(current, previous, BASKET, ["jumbo", "lider"])
    changes = {t.store: t.change for t in ranking.ranked}
    assert changes == {"jumbo": 20, "lider": None}


def test_ties_keep_configured_store_order() -> None:
    current = [obs("lider", "rice", 1000), obs("jumbo", "rice", 1000)]
    ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"])
    assert [t.store for t in ranking.ranked] == ["jumbo", "lider"]


def test_basket_total_rounds_half_up_and_returns_none_when_item_missing() -> None:
    current = [obs("jumbo", "rice", 1001), obs("jumbo", "spaghetti", 2501)]
    half = make_item("rice", reference_qty=0.5)
    assert basket_total(current, "jumbo", [half]) == 501
    assert basket_total(current, "jumbo", [RICE, MILK]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/domain/test_ranking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.domain.ranking'`.

- [ ] **Step 3: Implement ranking**

`src/supermercado/domain/ranking.py`:

```python
"""Basket ranking over comparable items. Prices are never imputed."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from supermercado.domain.models import BasketItem, PriceObservation, Status


@dataclass(frozen=True)
class StoreTotal:
    store: str
    total: int
    change: int | None


@dataclass(frozen=True)
class Ranking:
    ranked: list[StoreTotal]
    no_data: list[str]
    comparable_items: list[str]


def _usable(observations: Iterable[PriceObservation]) -> dict[tuple[str, str], PriceObservation]:
    return {
        (o.store, o.item_id): o
        for o in observations
        if o.status == Status.OK and o.available
    }


def comparable_items(
    observations: Iterable[PriceObservation], stores: Sequence[str], item_ids: Sequence[str]
) -> list[str]:
    """Items for which every given store has an ok, available observation."""
    if not stores:
        return []
    usable = _usable(observations)
    return [i for i in item_ids if all((s, i) in usable for s in stores)]


def basket_total(
    observations: Iterable[PriceObservation], store: str, items: Sequence[BasketItem]
) -> int | None:
    """Sum of unit_price x reference_qty, or None if any item lacks a usable observation."""
    usable = _usable(observations)
    total = Decimal(0)
    for item in items:
        obs = usable.get((store, item.id))
        if obs is None:
            return None
        total += Decimal(obs.unit_price) * Decimal(str(item.reference_qty))
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def rank_stores(
    current: Sequence[PriceObservation],
    previous: Sequence[PriceObservation],
    basket: Sequence[BasketItem],
    stores: Sequence[str],
) -> Ranking:
    present = {o.store for o in current}
    with_data = [s for s in stores if s in present]
    no_data = [s for s in stores if s not in present]
    comparable = comparable_items(current, with_data, [i.id for i in basket])
    if not comparable:
        return Ranking(ranked=[], no_data=no_data, comparable_items=[])
    chosen = set(comparable)
    items = [i for i in basket if i.id in chosen]
    totals = []
    for store in with_data:
        total = basket_total(current, store, items)
        if total is None:  # cannot happen: every store has every comparable item
            continue
        before = basket_total(previous, store, items)
        totals.append(StoreTotal(store, total, None if before is None else total - before))
    order = {s: n for n, s in enumerate(stores)}
    totals.sort(key=lambda t: (t.total, order[t.store]))
    return Ranking(ranked=totals, no_data=no_data, comparable_items=comparable)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/domain -v && uv run ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/supermercado/domain/ranking.py tests/domain/test_ranking.py
git commit -m "feat(domain): rank stores by basket total over comparable items"
```

---

### Task 4: Configuration loading (basket, matches, stores, clearances)

**Files:**
- Create: `src/supermercado/config.py`
- Create: `config/basket.yaml`, `config/matches.yaml`, `config/stores.yaml`, `config/cleared.yaml`
- Modify: `tests/factories.py` (add `make_store_config`, `make_config`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `BasketItem`, `Match`, `Category` (Task 1).
- Produces (`supermercado.config`):
  - `ConfigError(ValueError)`
  - `StoreConfig(name: str, enabled: bool = True, base_url: str, api_key: str | None, store_ref: str | None, comuna: str, location_verified: date | None, cookies: dict[str, str], smoke_sku: str | None, smoke_url: str | None)`
  - `Clearance(week: str, store: str, item_id: str)`
  - `AppConfig(basket: list[BasketItem], matches: dict[str, dict[str, Match]], stores: dict[str, StoreConfig], cleared: list[Clearance])` with methods `item(item_id) -> BasketItem`, `matches_for_store(store) -> dict[str, Match]` (basket order), `enabled_stores() -> list[str]` (stores.yaml order)
  - `load_config(config_dir: Path) -> AppConfig`
  - `tests/factories.py`: `make_store_config(name: str, **overrides) -> StoreConfig`, `make_config(*, items=None, stores=("jumbo", "lider"), matches=None) -> AppConfig`
- All stores start with `enabled: false`; each adapter task flips its own store to `true`.

- [ ] **Step 1: Write the config files**

`config/basket.yaml` (sizes and `size_range` are in the item's `unit`; `reference_qty` is the quantity counted in the basket total):

```yaml
# Basic basket: 23 items. Sizes are expressed in each item's normalization unit.
# unit: kg | l | m | unit
- id: rice
  name: Arroz grado 2 (1 kg)
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: "arroz grado 2"
  rules:
    size_range: [0.9, 1.0]
    exclude: [integral, preparado, "con leche"]
- id: spaghetti
  name: Fideos spaghetti (400 g)
  category: pantry
  unit: kg
  reference_qty: 0.4
  search: "spaghetti 400 g"
  rules:
    size_range: [0.4, 0.5]
    exclude: [integral, "sin gluten", "de arroz"]
- id: vegetable_oil
  name: Aceite vegetal (1 L)
  category: pantry
  unit: l
  reference_qty: 1.0
  search: "aceite vegetal 1 l"
  rules:
    size_range: [0.9, 1.0]
    exclude: [oliva, spray, coco, sesamo]
- id: sugar
  name: Azúcar (1 kg)
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: "azucar 1 kg"
  rules:
    size_range: [1.0, 1.0]
    exclude: [flor, rubia, morena, endulzante, stevia]
- id: flour
  name: Harina sin polvos de hornear (1 kg)
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: "harina sin polvos de hornear 1 kg"
  rules:
    size_range: [1.0, 1.0]
    exclude: ["con polvos", integral, "sin gluten", pizza]
- id: beans
  name: Porotos secos (1 kg)
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: "porotos 1 kg"
  rules:
    size_range: [0.9, 1.0]
    exclude: [conserva, lata, precocidos, "listos"]
- id: lentils
  name: Lentejas (1 kg)
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: "lentejas 1 kg"
  rules:
    size_range: [0.9, 1.0]
    exclude: [conserva, lata, precocidas, "listas"]
- id: salt
  name: Sal fina (1 kg)
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: "sal fina 1 kg"
  rules:
    size_range: [1.0, 1.0]
    exclude: [parrillera, gruesa, "de mar", "baja en sodio", light]
- id: tea
  name: Té (100 bolsitas)
  category: pantry
  unit: unit
  reference_qty: 100
  search: "te 100 bolsitas"
  rules:
    size_range: [100, 100]
    exclude: [hierbas, verde, rooibos, manzanilla, matcha]
- id: instant_coffee
  name: Café instantáneo (170 g)
  category: pantry
  unit: kg
  reference_qty: 0.17
  search: "cafe instantaneo 170 g"
  rules:
    size_range: [0.17, 0.17]
    exclude: [grano, molido, capsulas, descafeinado, cappuccino]
- id: whole_milk
  name: Leche entera (1 L)
  category: dairy_eggs
  unit: l
  reference_qty: 1.0
  search: "leche entera 1 l"
  rules:
    size_range: [1.0, 1.0]
    exclude: ["sin lactosa", polvo, descremada, semidescremada, chocolate, frutilla, vainilla]
- id: eggs
  name: Huevos (12 unidades)
  category: dairy_eggs
  unit: unit
  reference_qty: 12
  search: "huevos 12 unidades"
  rules:
    size_range: [12, 12]
    exclude: [codorniz]
- id: bread
  name: Pan marraqueta o hallulla a granel (1 kg)
  category: bakery
  unit: kg
  reference_qty: 1.0
  search: "marraqueta"
  rules:
    exclude: [integral, congelada, envasada]
- id: chicken_thigh
  name: Trutro entero de pollo a granel (1 kg)
  category: meat
  unit: kg
  reference_qty: 1.0
  search: "trutro entero pollo"
  rules:
    exclude: [congelado, marinado, apanado, deshuesado, filete]
- id: ground_beef
  name: Carne molida 10% grasa (1 kg)
  category: meat
  unit: kg
  reference_qty: 1.0
  search: "carne molida 10% grasa"
  rules:
    exclude: [cerdo, pollo, pavo, soya, "4%", "5%", "7%", "15%", "20%"]
- id: posta
  name: Posta a granel (1 kg)
  category: meat
  unit: kg
  reference_qty: 1.0
  search: "posta granel"
  rules:
    exclude: [cerdo, pollo, congelada, molida]
- id: laundry_detergent
  name: Detergente líquido (3 L)
  category: cleaning
  unit: l
  reference_qty: 3.0
  search: "detergente liquido 3 l"
  rules:
    size_range: [2.7, 3.0]
    exclude: [polvo, capsulas, suavizante]
- id: dish_soap
  name: Lavalozas (500 ml)
  category: cleaning
  unit: l
  reference_qty: 0.5
  search: "lavalozas 500 ml"
  rules:
    size_range: [0.5, 0.5]
    exclude: [polvo, pastillas, capsulas, lavavajillas]
- id: bleach
  name: Cloro (1 L)
  category: cleaning
  unit: l
  reference_qty: 1.0
  search: "cloro 1 l"
  rules:
    size_range: [0.9, 1.0]
    exclude: [gel, "ropa color", spray]
- id: toilet_paper
  name: Papel higiénico doble hoja (4 rollos)
  category: cleaning
  unit: m
  reference_qty: 120
  search: "papel higienico doble hoja 4 rollos"
  rules:
    exclude: ["hoja simple", "una hoja", toalla, servilleta, humedo]
- id: deodorant
  name: Desodorante en spray (150 ml)
  category: hygiene
  unit: l
  reference_qty: 0.15
  search: "desodorante spray 150 ml"
  rules:
    size_range: [0.15, 0.15]
    exclude: [barra, "roll on", crema]
- id: toothpaste
  name: Pasta dental (90 g)
  category: hygiene
  unit: kg
  reference_qty: 0.09
  search: "pasta dental 90 g"
  rules:
    size_range: [0.09, 0.09]
    exclude: [cepillo, enjuague, infantil, kids]
- id: bar_soap
  name: Jabón en barra (125 g)
  category: hygiene
  unit: kg
  reference_qty: 0.125
  search: "jabon de tocador barra"
  rules:
    size_range: [0.08, 0.5]
    exclude: [liquido, ropa, repuesto]
```

`config/matches.yaml`:

```yaml
# Approved SKU per (basket item, store). Changed only through reviewed pull requests.
# Always quote SKUs: unquoted numbers lose leading zeros and are rejected.
# `size` is the package size in the item's unit (see basket.yaml).
# Lider entries also need `url` (Lider has no automated search).
#
# Example:
# rice:
#   jumbo: { sku: "1626", size: 1.0, approved: 2026-10-04 }
#   lider: { sku: "00780142021013", url: "https://super.lider.cl/ip/arroz-y-legumbres/00780142021013", size: 1.0, approved: 2026-10-04 }
```

`config/stores.yaml`:

```yaml
# Per-store settings. API keys are public web-app keys; if a store rejects one, the weekly
# issue names the store and the ApiKeyRejected error so this file can be updated.
# `comuna` and `location_verified` are pinned by the store-location task (docs/store-locations.md).
jumbo:
  name: Jumbo
  enabled: false
  base_url: https://bff.jumbo.cl
  api_key: be-reg-groceries-jumbo-catalog-w54byfvkmju5
  store_ref: jumboclj512
  comuna: pending-verification
  smoke_sku: "1626"
santa_isabel:
  name: Santa Isabel
  enabled: false
  base_url: https://bff.santaisabel.cl
  api_key: be-reg-groceries-sisa-catalog-wdhhq5a2fken
  store_ref: pedrofontova
  comuna: pending-verification
tottus:
  name: Tottus
  enabled: false
  base_url: https://www.tottus.cl
  comuna: pending-verification
  smoke_sku: "110609848"
acuenta:
  name: aCuenta
  enabled: false
  base_url: https://nextgentheadless.instaleap.io/api/v3
  store_ref: "580"
  comuna: pending-verification
unimarc:
  name: Unimarc
  enabled: false
  base_url: https://bff-unimarc-ecommerce.unimarc.cl
  comuna: pending-verification
lider:
  name: Lider
  enabled: false
  base_url: https://super.lider.cl
  store_ref: "0000000057"
  comuna: pending-verification
  cookies:
    walmart.nearestLatLng: "-33.4521,-70.6536"
  smoke_sku: "00780142021013"
  smoke_url: https://super.lider.cl/ip/arroz-y-legumbres/00780142021013
```

`config/cleared.yaml`:

```yaml
# Suspicious or size-changed rows that a human reviewed and accepted.
# They are ranked as ok from the next site build.
# - { week: "2026-W40", store: jumbo, item_id: rice }
```

- [ ] **Step 2: Add config factories**

Add to the imports of `tests/factories.py`: `from supermercado.config import AppConfig, StoreConfig`. Append:

```python
STORE_NAMES = {
    "jumbo": "Jumbo",
    "santa_isabel": "Santa Isabel",
    "tottus": "Tottus",
    "acuenta": "aCuenta",
    "unimarc": "Unimarc",
    "lider": "Lider",
}


def make_store_config(name: str, **overrides: object) -> StoreConfig:
    data: dict[str, object] = {"name": name, "base_url": "https://example.invalid", "comuna": "Santiago"}
    data.update(overrides)
    return StoreConfig(**data)


def make_config(
    *,
    items: list[BasketItem] | None = None,
    stores: tuple[str, ...] = ("jumbo", "lider"),
    matches: dict[str, dict[str, Match]] | None = None,
) -> AppConfig:
    return AppConfig(
        basket=items or [make_item()],
        stores={s: make_store_config(STORE_NAMES.get(s, s)) for s in stores},
        matches=matches or {},
    )
```

- [ ] **Step 3: Write the failing tests**

`tests/test_config.py`:

```python
from pathlib import Path

import pytest
from factories import make_config, make_item, make_match

from supermercado.config import ConfigError, load_config
from supermercado.domain.models import Category

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

BASKET = """
- id: rice
  name: Arroz
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: arroz
- id: milk
  name: Leche
  category: dairy_eggs
  unit: l
  reference_qty: 1.0
  search: leche
"""

STORES = """
jumbo: {name: Jumbo, base_url: "https://bff.jumbo.cl", comuna: Santiago}
lider: {name: Lider, base_url: "https://super.lider.cl", comuna: Santiago}
"""


def write_config(tmp_path: Path, *, matches: str = "", basket: str = BASKET) -> Path:
    (tmp_path / "basket.yaml").write_text(basket, encoding="utf-8")
    (tmp_path / "stores.yaml").write_text(STORES, encoding="utf-8")
    (tmp_path / "matches.yaml").write_text(matches, encoding="utf-8")
    return tmp_path


def test_repository_config_loads_the_full_basket() -> None:
    config = load_config(CONFIG_DIR)
    assert len(config.basket) == 23
    assert {item.category for item in config.basket} == set(Category)
    assert len({item.id for item in config.basket}) == 23
    assert all(item.search.strip() for item in config.basket)
    assert config.matches == {}
    assert list(config.stores) == ["jumbo", "santa_isabel", "tottus", "acuenta", "unimarc", "lider"]


def test_comment_only_matches_file_means_no_matches(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, matches="# nothing approved yet\n"))
    assert config.matches == {}


def test_matches_are_parsed(tmp_path: Path) -> None:
    matches = 'rice:\n  jumbo: { sku: "1626", size: 1.0, approved: 2026-10-04 }\n'
    config = load_config(write_config(tmp_path, matches=matches))
    assert config.matches["rice"]["jumbo"].sku == "1626"
    assert config.matches_for_store("jumbo") == {"rice": config.matches["rice"]["jumbo"]}
    assert config.matches_for_store("lider") == {}


def test_unquoted_numeric_sku_is_rejected(tmp_path: Path) -> None:
    matches = "rice:\n  jumbo: { sku: 1626, size: 1.0, approved: 2026-10-04 }\n"
    with pytest.raises(ConfigError, match="sku"):
        load_config(write_config(tmp_path, matches=matches))


def test_unknown_item_in_matches_is_rejected(tmp_path: Path) -> None:
    matches = 'bread:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-04 }\n'
    with pytest.raises(ConfigError, match="unknown item 'bread'"):
        load_config(write_config(tmp_path, matches=matches))


def test_unknown_store_in_matches_is_rejected(tmp_path: Path) -> None:
    matches = 'rice:\n  alvi: { sku: "1", size: 1.0, approved: 2026-10-04 }\n'
    with pytest.raises(ConfigError, match="unknown store 'alvi'"):
        load_config(write_config(tmp_path, matches=matches))


def test_lider_match_requires_url(tmp_path: Path) -> None:
    matches = 'rice:\n  lider: { sku: "00780142021013", size: 1.0, approved: 2026-10-04 }\n'
    with pytest.raises(ConfigError, match="url"):
        load_config(write_config(tmp_path, matches=matches))


def test_duplicate_item_ids_are_rejected(tmp_path: Path) -> None:
    basket = BASKET + BASKET
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(write_config(tmp_path, basket=basket))


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="basket.yaml"):
        load_config(tmp_path)


def test_matches_for_store_follows_basket_order() -> None:
    config = make_config(
        items=[make_item("rice"), make_item("milk")],
        matches={"milk": {"jumbo": make_match("2")}, "rice": {"jumbo": make_match("1")}},
    )
    assert list(config.matches_for_store("jumbo")) == ["rice", "milk"]


def test_enabled_stores_keeps_file_order() -> None:
    config = load_config(CONFIG_DIR)
    assert config.enabled_stores() == [s for s, c in config.stores.items() if c.enabled]
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.config'`.

- [ ] **Step 5: Implement config loading**

`src/supermercado/config.py`:

```python
"""Load and cross-validate YAML configuration (basket, matches, stores, clearances)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from supermercado.domain.models import BasketItem, Match


class ConfigError(ValueError):
    """Configuration is missing, malformed, or inconsistent."""


class StoreConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    enabled: bool = True
    base_url: str
    api_key: str | None = None
    store_ref: str | None = None
    comuna: str
    location_verified: date | None = None
    cookies: dict[str, str] = Field(default_factory=dict)
    smoke_sku: str | None = None
    smoke_url: str | None = None


class Clearance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    week: str
    store: str
    item_id: str


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    basket: list[BasketItem]
    matches: dict[str, dict[str, Match]] = Field(default_factory=dict)
    stores: dict[str, StoreConfig]
    cleared: list[Clearance] = Field(default_factory=list)

    def item(self, item_id: str) -> BasketItem:
        for item in self.basket:
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def matches_for_store(self, store: str) -> dict[str, Match]:
        return {
            item.id: self.matches[item.id][store]
            for item in self.basket
            if store in self.matches.get(item.id, {})
        }

    def enabled_stores(self) -> list[str]:
        return [store for store, cfg in self.stores.items() if cfg.enabled]


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    with path.open(encoding="utf-8") as handle:
        try:
            return yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path.name}: invalid YAML: {exc}") from exc


def load_config(config_dir: Path) -> AppConfig:
    basket = _read_yaml(config_dir / "basket.yaml") or []
    stores = _read_yaml(config_dir / "stores.yaml") or {}
    matches = _read_yaml(config_dir / "matches.yaml") or {}
    cleared_path = config_dir / "cleared.yaml"
    cleared = (_read_yaml(cleared_path) or []) if cleared_path.exists() else []
    try:
        config = AppConfig(basket=basket, stores=stores, matches=matches, cleared=cleared)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration in {config_dir}:\n{exc}") from exc
    _check_consistency(config)
    return config


def _check_consistency(config: AppConfig) -> None:
    ids = [item.id for item in config.basket]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ConfigError(f"basket.yaml: duplicate item ids {duplicates}")
    for item_id, per_store in config.matches.items():
        if item_id not in ids:
            raise ConfigError(f"matches.yaml: unknown item {item_id!r}")
        for store, match in per_store.items():
            if store not in config.stores:
                raise ConfigError(f"matches.yaml: unknown store {store!r} for item {item_id!r}")
            if store == "lider" and not match.url:
                raise ConfigError(f"matches.yaml: lider match for {item_id!r} needs a url")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check .`
Expected: PASS (the pydantic error message for an int SKU contains the field name `sku`).

- [ ] **Step 7: Commit**

```bash
git add config src/supermercado/config.py tests/factories.py tests/test_config.py
git commit -m "feat(config): load basket, matches, stores and clearances from YAML"
```

---

### Task 5: StoreAdapter port and polite HTTP client

**Files:**
- Create: `src/supermercado/stores/__init__.py` (empty docstring for now), `src/supermercado/stores/base.py`
- Create: `tests/conftest.py`, `tests/fakes.py`
- Test: `tests/stores/test_http_client.py`

**Interfaces:**
- Consumes: `Listing` (Task 1).
- Produces (`supermercado.stores.base`):
  - Errors: `AdapterError(Exception)`, `ApiKeyRejected(AdapterError)`, `BlockedError(AdapterError)`, `ResponseShapeError(AdapterError)`, `TransportError(AdapterError)`, `HttpError(AdapterError)` with `.status: int`, `.url: str`
  - `@dataclass(frozen=True) RawResponse(status: int, text: str)` with `.json() -> Any` (raises `ResponseShapeError` on non-JSON)
  - `Transport = Callable[..., RawResponse]`, called as `transport(method, url, *, headers=None, params=None, json=None, cookies=None)`
  - `curl_transport(timeout: float = 30.0) -> Transport` (curl_cffi `Session(impersonate="chrome")`)
  - `HttpClient(transport, *, min_interval=1.5, max_retries=3, backoff_base=2.0, clock=time.monotonic, sleep=time.sleep)` with `.request(method, url, *, headers=None, params=None, json=None, cookies=None) -> RawResponse`; retries 429/500/502/503/504 and `TransportError`; raises `HttpError` for other 4xx/5xx
  - `StoreAdapter` Protocol: `store_id: str`, `supports_search: bool`, `search(query: str) -> list[Listing]`, `fetch(skus: list[str]) -> list[Listing]`
- Produces (`tests/fakes.py`): `FIXTURES: Path`, `FakeClock`, `FakeTransport(responses)` with `.calls: list[dict]`, `make_client(transport, clock=None) -> HttpClient`, `ok(text) -> RawResponse`, `fixture_text(store, name) -> str`, `fixture_response(store, name, status=200) -> RawResponse`, `assert_recorded_listings(listings) -> None`

- [ ] **Step 1: Write the test helpers and the network guard**

`tests/conftest.py`:

```python
"""Global test guards: the suite must never reach the network."""

import socket

import pytest


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("network access is forbidden in tests")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("curl_cffi.requests.Session.request", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
```

`tests/fakes.py`:

```python
"""Fakes for HTTP transport, time, and recorded fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from supermercado.domain.models import Listing
from supermercado.stores.base import HttpClient, RawResponse

FIXTURES = Path(__file__).parent / "fixtures"


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTransport:
    """Returns queued responses (or raises queued exceptions) and records every call."""

    def __init__(self, responses: list[RawResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        cookies: dict[str, str] | None = None,
    ) -> RawResponse:
        self.calls.append(
            {"method": method, "url": url, "headers": headers or {}, "params": params or {},
             "json": json, "cookies": cookies or {}}
        )
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(transport: FakeTransport, clock: FakeClock | None = None) -> HttpClient:
    clock = clock or FakeClock()
    return HttpClient(transport, clock=clock, sleep=clock.sleep)


def ok(text: str) -> RawResponse:
    return RawResponse(status=200, text=text)


def fixture_text(store: str, name: str) -> str:
    return (FIXTURES / store / name).read_text(encoding="utf-8")


def fixture_response(store: str, name: str, status: int = 200) -> RawResponse:
    return RawResponse(status=status, text=fixture_text(store, name))


def assert_recorded_listings(listings: list[Listing]) -> None:
    """Sanity checks for parsers run over real recorded responses."""
    assert listings, "recorded fixture produced no listings"
    assert all(listing.sku and listing.name for listing in listings)
    priced = [listing for listing in listings if listing.price and listing.price > 0]
    assert len(priced) >= 0.9 * len(listings), "most recorded listings should carry a price"
```

- [ ] **Step 2: Write the failing client tests**

`tests/stores/test_http_client.py`:

```python
import pytest
from fakes import FakeClock, FakeTransport, make_client, ok

from supermercado.stores.base import HttpError, RawResponse, ResponseShapeError, TransportError


def test_returns_successful_response_and_forwards_arguments() -> None:
    transport = FakeTransport([ok('{"a": 1}')])
    response = make_client(transport).request(
        "POST", "https://x.test/p", headers={"h": "1"}, json={"q": 1}, cookies={"c": "2"}
    )
    assert response.json() == {"a": 1}
    call = transport.calls[0]
    assert (call["method"], call["url"], call["headers"], call["json"], call["cookies"]) == (
        "POST", "https://x.test/p", {"h": "1"}, {"q": 1}, {"c": "2"},
    )


def test_waits_min_interval_between_requests() -> None:
    clock = FakeClock()
    client = make_client(FakeTransport([ok("{}"), ok("{}")]), clock)
    client.request("GET", "https://x.test/1")
    client.request("GET", "https://x.test/2")
    assert clock.sleeps == [1.5]


def test_no_wait_when_interval_already_elapsed() -> None:
    clock = FakeClock()
    client = make_client(FakeTransport([ok("{}"), ok("{}")]), clock)
    client.request("GET", "https://x.test/1")
    clock.advance(2.0)
    client.request("GET", "https://x.test/2")
    assert clock.sleeps == []


def test_retries_retryable_status_with_exponential_backoff() -> None:
    clock = FakeClock()
    transport = FakeTransport([RawResponse(503, ""), RawResponse(429, ""), ok("{}")])
    assert make_client(transport, clock).request("GET", "https://x.test").status == 200
    assert clock.sleeps == [2.0, 4.0]


def test_gives_up_after_three_retries() -> None:
    clock = FakeClock()
    transport = FakeTransport([RawResponse(503, "")] * 4)
    with pytest.raises(HttpError) as excinfo:
        make_client(transport, clock).request("GET", "https://x.test")
    assert excinfo.value.status == 503
    assert len(transport.calls) == 4
    assert clock.sleeps == [2.0, 4.0, 8.0]


def test_client_errors_are_not_retried() -> None:
    transport = FakeTransport([RawResponse(404, "")])
    with pytest.raises(HttpError) as excinfo:
        make_client(transport).request("GET", "https://x.test/missing")
    assert excinfo.value.status == 404
    assert len(transport.calls) == 1


def test_transport_errors_are_retried_then_propagated() -> None:
    transport = FakeTransport([TransportError("reset"), ok("{}")])
    assert make_client(transport).request("GET", "https://x.test").status == 200
    failing = FakeTransport([TransportError("reset")] * 4)
    with pytest.raises(TransportError):
        make_client(failing).request("GET", "https://x.test")
    assert len(failing.calls) == 4


def test_non_json_body_raises_shape_error() -> None:
    with pytest.raises(ResponseShapeError):
        RawResponse(200, "<html>blocked</html>").json()


def test_network_is_blocked_in_tests() -> None:
    from curl_cffi import requests

    with pytest.raises(RuntimeError, match="network"):
        requests.Session(impersonate="chrome").request("GET", "https://example.com")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stores/test_http_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.stores'`.

- [ ] **Step 4: Implement the port and client**

`src/supermercado/stores/__init__.py`:

```python
"""Store adapters behind the StoreAdapter port."""
```

`src/supermercado/stores/base.py`:

```python
"""StoreAdapter port, adapter errors, and the shared polite HTTP client."""

from __future__ import annotations

import json as _json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from supermercado.domain.models import Listing


class AdapterError(Exception):
    """Base class for every store adapter failure."""


class ApiKeyRejected(AdapterError):
    """The store rejected the public API key configured in stores.yaml."""


class BlockedError(AdapterError):
    """The store answered with an anti-bot page."""


class ResponseShapeError(AdapterError):
    """The response does not have the expected structure."""


class TransportError(AdapterError):
    """Network-level failure (DNS, TLS, reset, timeout)."""


class HttpError(AdapterError):
    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} from {url}")
        self.status = status
        self.url = url


@dataclass(frozen=True)
class RawResponse:
    status: int
    text: str

    def json(self) -> Any:
        try:
            return _json.loads(self.text)
        except ValueError as exc:
            raise ResponseShapeError(f"expected JSON, got: {self.text[:120]!r}") from exc


Transport = Callable[..., RawResponse]


def curl_transport(timeout: float = 30.0) -> Transport:
    """Real transport: curl_cffi with Chrome TLS impersonation."""
    from curl_cffi import requests as curl_requests
    from curl_cffi.requests.exceptions import RequestException

    session = curl_requests.Session(impersonate="chrome")

    def send(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        cookies: dict[str, str] | None = None,
    ) -> RawResponse:
        try:
            response = session.request(
                method, url, headers=headers, params=params, json=json, cookies=cookies,
                timeout=timeout,
            )
        except RequestException as exc:
            raise TransportError(str(exc)) from exc
        return RawResponse(status=response.status_code, text=response.text)

    return send


class HttpClient:
    """One client per store: enforces the minimum interval and retries with backoff."""

    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        transport: Transport,
        *,
        min_interval: float = 1.5,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        cookies: dict[str, str] | None = None,
    ) -> RawResponse:
        attempt = 0
        while True:
            self._wait_turn()
            try:
                response = self._transport(
                    method, url, headers=headers, params=params, json=json, cookies=cookies
                )
            except TransportError:
                if attempt >= self._max_retries:
                    raise
            else:
                if response.status < 400:
                    return response
                if response.status not in self.RETRY_STATUSES or attempt >= self._max_retries:
                    raise HttpError(response.status, url)
            self._sleep(self._backoff_base * 2**attempt)
            attempt += 1

    def _wait_turn(self) -> None:
        now = self._clock()
        if self._last is not None:
            elapsed = now - self._last
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last = self._clock()


class StoreAdapter(Protocol):
    store_id: str
    supports_search: bool

    def search(self, query: str) -> list[Listing]: ...

    def fetch(self, skus: list[str]) -> list[Listing]: ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check .`
Expected: PASS. If `curl_cffi.requests.exceptions` does not exist in the installed version, check `uv run python -c "import curl_cffi; print(curl_cffi.__version__)"` and import `RequestException` from where that version exposes it (`curl_cffi.requests.errors.RequestsError` in versions < 0.7).

- [ ] **Step 6: Commit**

```bash
git add src/supermercado/stores tests/conftest.py tests/fakes.py tests/stores/test_http_client.py
git commit -m "feat(stores): add StoreAdapter port and polite retrying HTTP client"
```

---

### Task 6: Jumbo adapter (shared Cencosud BFF), adapter registry, fixture recorder

**Files:**
- Create: `src/supermercado/stores/cencosud.py`, `src/supermercado/stores/jumbo.py`
- Modify: `src/supermercado/stores/__init__.py` (registry)
- Modify: `config/stores.yaml` (`jumbo.enabled: true`)
- Create: `scripts/record_fixtures.py`
- Create: `tests/fixtures/jumbo/plp_search.json`
- Test: `tests/stores/test_jumbo.py`, `tests/stores/test_registry.py`

**Interfaces:**
- Consumes: `HttpClient`, `RawResponse`, errors (Task 5); `StoreConfig`, `AppConfig`, `ConfigError` (Task 4); `parse_size` (Task 1); `make_store_config` (Task 4).
- Produces:
  - `supermercado.stores.cencosud`: `BATCH_SIZE = 40`, `parse_plp(payload: Any, site_url: str) -> list[Listing]`, `class CencosudAdapter` (class attrs `store_id`, `site_url`, `supports_search = True`, `page_size = 40`; `__init__(client: HttpClient, config: StoreConfig)`; `search`, `fetch`, `raw_search(query) -> RawResponse`, `raw_fetch(sku) -> RawResponse`)
  - `supermercado.stores.jumbo.JumboAdapter(CencosudAdapter)` with `store_id = "jumbo"`, `site_url = "https://www.jumbo.cl"`
  - `supermercado.stores`: `AdapterFactory = Callable[[HttpClient, StoreConfig, AppConfig], StoreAdapter]`, `FACTORIES: dict[str, AdapterFactory]`, `build_adapters(config: AppConfig, *, only: str | None = None, transport_factory: Callable[[], Transport] = curl_transport) -> dict[str, StoreAdapter]`
  - Every concrete adapter from now on exposes `raw_search(query: str) -> RawResponse` (if it supports search) and `raw_fetch(sku: str) -> RawResponse`, used only by `scripts/record_fixtures.py`.
  - Price mapping rule for Cencosud: `price < listPrice` ⇒ `price=listPrice`, `promo_price=price`; promotions whose name contains `TCENCO`/`TARJETA` and ends in `- <amount>` ⇒ `card_price`; `measurementUnit == "kg"` ⇒ sold by weight, `size = unitMultiplier` kg.

- [ ] **Step 1: Write the hand-written fixture (mirrors real BFF field names)**

`tests/fixtures/jumbo/plp_search.json`:

```json
{
  "products": [
    {
      "productId": "1621",
      "slug": "arroz-grado-2-tucapel-1-kg-blue-bonnet-grano-largo-y-delgado",
      "brand": "Tucapel",
      "weightToUnit": false,
      "items": [
        {
          "skuId": "1626",
          "name": "Arroz Grado 2 Tucapel Blue Grano Largo y Delgado 1 kg",
          "measurementUnit": "un",
          "unitMultiplier": 1,
          "price": 1810,
          "listPrice": 1810,
          "ppumPrice": 1810,
          "ppumMeasurementUnit": "kg",
          "stock": true,
          "promotions": []
        }
      ]
    },
    {
      "productId": "43160",
      "slug": "arroz-grado-2-miraflores-1-kg",
      "brand": "Miraflores",
      "weightToUnit": false,
      "items": [
        {
          "skuId": "43165",
          "name": "Arroz Grado 2 Miraflores 1 kg",
          "measurementUnit": "un",
          "unitMultiplier": 1,
          "price": 1290,
          "listPrice": 1590,
          "ppumPrice": 1290,
          "ppumMeasurementUnit": "kg",
          "stock": true,
          "promotions": [{"name": "TCENCO OFERTA - 1150"}]
        }
      ]
    },
    {
      "productId": "9001",
      "slug": "trutro-entero-de-pollo-granel",
      "brand": "Jumbo",
      "weightToUnit": true,
      "items": [
        {
          "skuId": "9002",
          "name": "Trutro Entero de Pollo Granel",
          "measurementUnit": "kg",
          "unitMultiplier": 1,
          "price": 3290,
          "listPrice": 3290,
          "ppumPrice": 3290,
          "ppumMeasurementUnit": "kg",
          "stock": false,
          "promotions": []
        }
      ]
    }
  ],
  "results": 3
}
```

- [ ] **Step 2: Write the failing adapter and registry tests**

`tests/stores/test_jumbo.py`:

```python
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
    assert call["json"] == {"fullText": "arroz grado 2", "store": "jumboclj512", "from": 0, "to": 39}


def test_search_parses_a_regular_listing() -> None:
    adapter, _ = make_adapter(fixture_response("jumbo", "plp_search.json"))
    rice = adapter.search("arroz grado 2")[0]
    assert rice.sku == "1626"
    assert rice.brand == "Tucapel"
    assert rice.url == "https://www.jumbo.cl/arroz-grado-2-tucapel-1-kg-blue-bonnet-grano-largo-y-delgado/p"
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
```

`tests/stores/test_registry.py`:

```python
import pytest
from factories import make_config, make_store_config
from fakes import FakeTransport

from supermercado.config import AppConfig, ConfigError
from supermercado.stores import build_adapters
from supermercado.stores.jumbo import JumboAdapter


def config_with(**stores):
    base = make_config()
    return AppConfig(basket=base.basket, stores=stores, matches={})


def jumbo_cfg(**overrides):
    return make_store_config("Jumbo", api_key="k", store_ref="s", **overrides)


def test_builds_enabled_registered_stores() -> None:
    config = config_with(jumbo=jumbo_cfg(), lider=make_store_config("Lider", enabled=False))
    adapters = build_adapters(config, transport_factory=lambda: FakeTransport([]))
    assert list(adapters) == ["jumbo"]
    assert isinstance(adapters["jumbo"], JumboAdapter)


def test_only_selects_a_single_store() -> None:
    config = config_with(jumbo=jumbo_cfg())
    assert list(build_adapters(config, only="jumbo", transport_factory=lambda: FakeTransport([]))) == ["jumbo"]


def test_only_rejects_unknown_or_disabled_store() -> None:
    config = config_with(jumbo=jumbo_cfg(enabled=False))
    with pytest.raises(ConfigError, match="disabled"):
        build_adapters(config, only="jumbo", transport_factory=lambda: FakeTransport([]))
    with pytest.raises(ConfigError, match="unknown store"):
        build_adapters(config, only="alvi", transport_factory=lambda: FakeTransport([]))


def test_enabled_store_without_adapter_is_a_config_error() -> None:
    config = config_with(alvi=make_store_config("Alvi"))
    with pytest.raises(ConfigError, match="no adapter"):
        build_adapters(config, transport_factory=lambda: FakeTransport([]))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stores -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.stores.cencosud'`.

- [ ] **Step 4: Implement the Cencosud adapter and Jumbo**

`src/supermercado/stores/cencosud.py`:

```python
"""Shared adapter for Cencosud BFF catalogs (Jumbo, Santa Isabel)."""

from __future__ import annotations

import re
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
_CARD_PROMO_RE = re.compile(r"-\s*\$?\s*([\d.]+)\s*$")
_CARD_PROMO_MARKERS = ("TCENCO", "TARJETA")


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    amount = int(round(float(value)))
    return amount if amount > 0 else None


def _card_price(promotions: list[dict[str, Any]]) -> int | None:
    found = []
    for promo in promotions:
        label = str(promo.get("name") or promo.get("description") or "")
        if not any(marker in label.upper() for marker in _CARD_PROMO_MARKERS):
            continue
        if match := _CARD_PROMO_RE.search(label):
            found.append(int(match.group(1).replace(".", "")))
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
        card_price=_card_price(item.get("promotions") or []),
        store_unit_price=_positive_int(item.get("ppumPrice")),
        available=bool(item.get("stock")),
    )


def parse_plp(payload: Any, site_url: str) -> list[Listing]:
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        raise ResponseShapeError("Cencosud PLP response has no 'products' list")
    return [
        _listing(product, item, site_url)
        for product in payload["products"]
        for item in (product.get("items") or [])
        if item.get("skuId")
    ]


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
```

`src/supermercado/stores/jumbo.py`:

```python
"""Jumbo adapter (Cencosud BFF)."""

from supermercado.stores.cencosud import CencosudAdapter


class JumboAdapter(CencosudAdapter):
    store_id = "jumbo"
    site_url = "https://www.jumbo.cl"
```

Replace `src/supermercado/stores/__init__.py` with:

```python
"""Store adapters behind the StoreAdapter port, plus the registry that builds them."""

from __future__ import annotations

from collections.abc import Callable

from supermercado.config import AppConfig, ConfigError, StoreConfig
from supermercado.stores.base import HttpClient, StoreAdapter, Transport, curl_transport
from supermercado.stores.jumbo import JumboAdapter

AdapterFactory = Callable[[HttpClient, StoreConfig, AppConfig], StoreAdapter]

FACTORIES: dict[str, AdapterFactory] = {
    "jumbo": lambda client, store, app: JumboAdapter(client, store),
}


def build_adapters(
    config: AppConfig,
    *,
    only: str | None = None,
    transport_factory: Callable[[], Transport] = curl_transport,
) -> dict[str, StoreAdapter]:
    """One adapter (with its own polite HttpClient) per enabled store."""
    if only is not None and only not in config.stores:
        raise ConfigError(f"unknown store {only!r}")
    adapters: dict[str, StoreAdapter] = {}
    for store_id, store_cfg in config.stores.items():
        if only is not None and store_id != only:
            continue
        if not store_cfg.enabled:
            if only is not None:
                raise ConfigError(f"store {only!r} is disabled in config/stores.yaml")
            continue
        factory = FACTORIES.get(store_id)
        if factory is None:
            raise ConfigError(f"no adapter registered for enabled store {store_id!r}")
        adapters[store_id] = factory(HttpClient(transport_factory()), store_cfg, config)
    return adapters
```

In `config/stores.yaml`, change `jumbo.enabled` from `false` to `true`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check .`
Expected: PASS; `test_recorded_search_parses` is SKIPPED.

- [ ] **Step 6: Write the fixture recorder**

`scripts/record_fixtures.py`:

```python
"""Record live store responses into tests/fixtures/<store>/.

Run manually, once per store, from a residential IP (never from CI):

    uv run python scripts/record_fixtures.py jumbo --query "arroz grado 2" --sku 1626
    uv run python scripts/record_fixtures.py lider --sku 00780142021013

Writes recorded_search.(json|html) and/or recorded_fetch.(json|html). Commit the files;
tests that parse them are skipped until they exist.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from supermercado.config import load_config
from supermercado.stores import build_adapters

ROOT = Path(__file__).resolve().parents[1]


def _save(directory: Path, stem: str, text: str) -> Path:
    suffix = ".html" if text.lstrip().startswith("<") else ".json"
    path = directory / f"{stem}{suffix}"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("store")
    parser.add_argument("--query", help="search text to record (stores with search only)")
    parser.add_argument("--sku", help="single SKU to record through the fetch path")
    parser.add_argument("--config", type=Path, default=ROOT / "config")
    args = parser.parse_args()

    adapter = build_adapters(load_config(args.config), only=args.store)[args.store]
    out_dir = ROOT / "tests" / "fixtures" / args.store
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.query:
        print("saved", _save(out_dir, "recorded_search", adapter.raw_search(args.query).text))
    if args.sku:
        print("saved", _save(out_dir, "recorded_fetch", adapter.raw_fetch(args.sku).text))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Record the real Jumbo response (requires network from a residential IP)**

Run: `uv run python scripts/record_fixtures.py jumbo --query "arroz grado 2"`
Expected: `saved .../tests/fixtures/jumbo/recorded_search.json`. Then run `uv run pytest tests/stores/test_jumbo.py -v`; `test_recorded_search_parses` now runs and PASSES. If there is no network access in your environment, skip this step and note it in your report: the hand-written fixture keeps the suite deterministic, and the recorded test stays skipped until a human records it.

- [ ] **Step 8: Commit**

```bash
git add src/supermercado/stores config/stores.yaml scripts/record_fixtures.py tests/fixtures/jumbo tests/stores/test_jumbo.py tests/stores/test_registry.py
git commit -m "feat(stores): add Jumbo adapter over the Cencosud BFF and adapter registry"
```

---

### Task 7: Collect pipeline, weekly Parquet storage, and CLI

**Files:**
- Create: `src/supermercado/pipeline/__init__.py`, `src/supermercado/pipeline/collect.py`, `src/supermercado/pipeline/storage.py`, `src/supermercado/pipeline/report.py`
- Create: `src/supermercado/cli.py`, `src/supermercado/__main__.py`
- Create: `data/prices/.gitkeep`
- Modify: `tests/fakes.py` (add `FakeAdapter`)
- Test: `tests/pipeline/test_collect.py`, `tests/pipeline/test_storage.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `AppConfig`, `load_config`, `ConfigError` (Task 4); `build_observation` (Task 2); `StoreAdapter`, adapter errors (Task 5); `build_adapters` (Task 6).
- Produces:
  - `supermercado.pipeline.collect`: `iso_week(moment: datetime) -> str`; `StoreFailure(store, error_class, message, at: datetime)`; `Alert(store, item_id, message)`; `CollectResult(week, observations, failures, alerts, dropped, collected_stores: set[str])`; `EmptyResult(Exception)`; `collect(config: AppConfig, adapters: Mapping[str, StoreAdapter], *, now: datetime, previous: Mapping[tuple[str, str], int]) -> CollectResult`
  - `supermercado.pipeline.storage`: `SCHEMA: pa.Schema`, `week_path(data_dir, week) -> Path`, `list_weeks(data_dir) -> list[str]`, `read_week(data_dir, week) -> list[PriceObservation]`, `write_week(data_dir, week, observations, *, replace_stores: set[str]) -> Path | None`, `previous_unit_prices(data_dir, week) -> dict[tuple[str, str], int]`
  - `supermercado.pipeline.report`: `report_to_dict(result: CollectResult) -> dict[str, Any]` (keys `week`, `observations`, `collected_stores`, `failures[{store, error_class, message, at}]`, `alerts[{store, item_id, message}]`, `dropped`)
  - `supermercado.cli`: `main(argv: list[str] | None = None) -> int`, module-level `_now()`, `COMMANDS: dict[str, Callable[[argparse.Namespace], int]]`, `_parser() -> argparse.ArgumentParser`. Global options `--config` (default `config`), `--data` (default `data`) go before the subcommand. `collect [--store X] [--report build/report.json]`. Exit code 2 on `ConfigError`.
  - `tests/fakes.py`: `FakeAdapter(store_id, listings=(), *, error=None, supports_search=True, search_results=None)` with `.fetched`, `.searched`

- [ ] **Step 1: Add the fake adapter**

Append to `tests/fakes.py`:

```python
class FakeAdapter:
    """In-memory StoreAdapter for pipeline tests."""

    def __init__(
        self,
        store_id: str,
        listings: list[Listing] | tuple[Listing, ...] = (),
        *,
        error: Exception | None = None,
        supports_search: bool = True,
        search_results: dict[str, list[Listing]] | None = None,
    ) -> None:
        self.store_id = store_id
        self.supports_search = supports_search
        self._listings = list(listings)
        self._error = error
        self._search_results = dict(search_results or {})
        self.fetched: list[list[str]] = []
        self.searched: list[str] = []

    def fetch(self, skus: list[str]) -> list[Listing]:
        self.fetched.append(list(skus))
        if self._error is not None:
            raise self._error
        return [listing for listing in self._listings if listing.sku in skus]

    def search(self, query: str) -> list[Listing]:
        self.searched.append(query)
        if self._error is not None:
            raise self._error
        return list(self._search_results.get(query, []))
```

- [ ] **Step 2: Write the failing pipeline tests**

`tests/pipeline/test_collect.py`:

```python
from datetime import UTC, datetime

from factories import make_config, make_item, make_listing, make_match
from fakes import FakeAdapter

from supermercado.domain.models import Status, Unit
from supermercado.pipeline.collect import collect, iso_week
from supermercado.stores.base import BlockedError

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
LIDER_URL = "https://super.lider.cl/ip/arroz-y-legumbres/00780142021013"
MILK = make_listing(sku="555", name="Leche Entera 1 L", size=1.0, unit=Unit.L, price=990)
LIDER_RICE = make_listing(sku="00780142021013", price=1190)


def config(matches=None):
    return make_config(
        items=[make_item("rice"), make_item("milk", unit=Unit.L)],
        stores=("jumbo", "lider"),
        matches=matches
        or {
            "rice": {
                "jumbo": make_match("1626"),
                "lider": make_match("00780142021013", url=LIDER_URL),
            },
            "milk": {"jumbo": make_match("555")},
        },
    )


def test_iso_week_formats_year_and_week() -> None:
    assert iso_week(NOW) == "2026-W40"
    assert iso_week(datetime(2027, 1, 1, tzinfo=UTC)) == "2026-W53"


def test_collects_every_store_and_item() -> None:
    jumbo = FakeAdapter("jumbo", [make_listing(), MILK])
    lider = FakeAdapter("lider", [LIDER_RICE])
    result = collect(config(), {"jumbo": jumbo, "lider": lider}, now=NOW, previous={})
    assert result.week == "2026-W40"
    assert sorted((o.store, o.item_id, o.unit_price) for o in result.observations) == [
        ("jumbo", "milk", 990),
        ("jumbo", "rice", 1810),
        ("lider", "rice", 1190),
    ]
    assert jumbo.fetched == [["1626", "555"]]
    assert result.collected_stores == {"jumbo", "lider"}
    assert result.failures == []


def test_failing_store_does_not_block_others() -> None:
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing(), MILK]),
        "lider": FakeAdapter("lider", error=BlockedError("captcha page")),
    }
    result = collect(config(), adapters, now=NOW, previous={})
    assert {o.store for o in result.observations} == {"jumbo"}
    assert [(f.store, f.error_class, f.message, f.at) for f in result.failures] == [
        ("lider", "BlockedError", "captcha page", NOW)
    ]
    assert result.collected_stores == {"jumbo"}


def test_store_returning_nothing_is_a_failure() -> None:
    adapters = {"jumbo": FakeAdapter("jumbo", [make_listing(), MILK]), "lider": FakeAdapter("lider")}
    result = collect(config(), adapters, now=NOW, previous={})
    assert [(f.store, f.error_class) for f in result.failures] == [("lider", "EmptyResult")]
    assert "lider" not in result.collected_stores


def test_missing_sku_is_dropped_without_failing_the_store() -> None:
    adapters = {"jumbo": FakeAdapter("jumbo", [make_listing()]), "lider": FakeAdapter("lider", [LIDER_RICE])}
    result = collect(config(), adapters, now=NOW, previous={})
    assert any(d.startswith("jumbo/milk") for d in result.dropped)
    assert result.failures == []


def test_row_without_price_is_dropped() -> None:
    no_price = make_listing(sku="555", name="Leche Entera 1 L", size=1.0, unit=Unit.L, price=None)
    adapters = {"jumbo": FakeAdapter("jumbo", [make_listing(), no_price]), "lider": FakeAdapter("lider", [LIDER_RICE])}
    result = collect(config(), adapters, now=NOW, previous={})
    assert "jumbo/milk: missing or non-positive price" in result.dropped


def test_previous_week_price_marks_suspicious_rows() -> None:
    adapters = {"jumbo": FakeAdapter("jumbo", [make_listing(), MILK]), "lider": FakeAdapter("lider", [LIDER_RICE])}
    result = collect(config(), adapters, now=NOW, previous={("jumbo", "rice"): 1000})
    status = {(o.store, o.item_id): o.status for o in result.observations}
    assert status[("jumbo", "rice")] is Status.SUSPICIOUS
    assert status[("lider", "rice")] is Status.OK


def test_size_change_raises_an_alert() -> None:
    shrunk = make_listing(size=0.9, name="Arroz Grado 2 Tucapel 900 g")
    adapters = {"jumbo": FakeAdapter("jumbo", [shrunk, MILK]), "lider": FakeAdapter("lider", [LIDER_RICE])}
    result = collect(config(), adapters, now=NOW, previous={})
    assert [(a.store, a.item_id) for a in result.alerts] == [("jumbo", "rice")]


def test_store_without_matches_is_not_fetched() -> None:
    lider = FakeAdapter("lider", [LIDER_RICE])
    matches = {"rice": {"jumbo": make_match("1626")}}
    result = collect(config(matches), {"jumbo": FakeAdapter("jumbo", [make_listing()]), "lider": lider}, now=NOW, previous={})
    assert lider.fetched == []
    assert result.collected_stores == {"jumbo"}
```

`tests/pipeline/test_storage.py`:

```python
from pathlib import Path

from factories import make_obs

from supermercado.domain.models import Status
from supermercado.pipeline.storage import (
    list_weeks,
    previous_unit_prices,
    read_week,
    week_path,
    write_week,
)

W40 = "2026-W40"


def test_round_trip_preserves_values_and_types(tmp_path: Path) -> None:
    rows = [
        make_obs(store="lider", sku="00780142021013", price=1790, promo_price=1190,
                 effective_price=1190, unit_price=1190, card_price=None),
        make_obs(card_price=1150),
    ]
    path = write_week(tmp_path, W40, rows, replace_stores={"jumbo", "lider"})
    assert path == week_path(tmp_path, W40) == tmp_path / "prices" / "2026-W40.parquet"
    loaded = read_week(tmp_path, W40)
    assert loaded == sorted(rows, key=lambda o: (o.store, o.item_id))
    assert loaded[0].scraped_at.tzinfo is not None
    assert isinstance(loaded[0].unit_price, int)


def test_write_week_replaces_only_given_stores(tmp_path: Path) -> None:
    write_week(
        tmp_path, W40,
        [make_obs(store="jumbo"), make_obs(store="lider", unit_price=1190)],
        replace_stores={"jumbo", "lider"},
    )
    write_week(tmp_path, W40, [make_obs(store="lider", unit_price=1200)], replace_stores={"lider"})
    assert {(o.store, o.unit_price) for o in read_week(tmp_path, W40)} == {
        ("jumbo", 1810),
        ("lider", 1200),
    }


def test_writing_nothing_creates_no_file(tmp_path: Path) -> None:
    assert write_week(tmp_path, W40, [], replace_stores=set()) is None
    assert list_weeks(tmp_path) == []


def test_previous_unit_prices_use_latest_earlier_week_and_ok_rows(tmp_path: Path) -> None:
    write_week(tmp_path, "2026-W38", [make_obs(week="2026-W38", unit_price=1700)], replace_stores={"jumbo"})
    write_week(
        tmp_path, "2026-W39",
        [
            make_obs(week="2026-W39", unit_price=1790),
            make_obs(week="2026-W39", item_id="milk", unit_price=5000, status=Status.SUSPICIOUS),
        ],
        replace_stores={"jumbo"},
    )
    write_week(tmp_path, W40, [make_obs(unit_price=1810)], replace_stores={"jumbo"})
    assert list_weeks(tmp_path) == ["2026-W38", "2026-W39", "2026-W40"]
    assert previous_unit_prices(tmp_path, W40) == {("jumbo", "rice"): 1790}
    assert previous_unit_prices(tmp_path, "2026-W38") == {}
```

`tests/test_cli.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factories import make_config, make_item, make_listing, make_match
from fakes import FakeAdapter

from supermercado import cli
from supermercado.config import ConfigError
from supermercado.pipeline.storage import read_week
from supermercado.stores.base import BlockedError

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):
    config = make_config(
        items=[make_item("rice")],
        stores=("jumbo", "lider"),
        matches={"rice": {"jumbo": make_match("1626"), "lider": make_match("007", url="https://super.lider.cl/ip/x/007")}},
    )
    adapters = {
        "jumbo": FakeAdapter("jumbo", [make_listing()]),
        "lider": FakeAdapter("lider", error=BlockedError("captcha")),
    }
    calls: dict[str, object] = {}

    def fake_build_adapters(_config, only=None):
        calls["only"] = only
        return {k: v for k, v in adapters.items() if only in (None, k)}

    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "build_adapters", fake_build_adapters)
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    return calls


def run(tmp_path: Path, *extra: str) -> int:
    return cli.main(["--config", str(tmp_path / "config"), "--data", str(tmp_path / "data"), *extra])


def test_collect_writes_snapshot_and_report(tmp_path: Path, wired) -> None:
    report = tmp_path / "build" / "report.json"
    assert run(tmp_path, "collect", "--report", str(report)) == 0
    assert [o.store for o in read_week(tmp_path / "data", "2026-W40")] == ["jumbo"]
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["week"] == "2026-W40"
    assert [(f["store"], f["error_class"]) for f in data["failures"]] == [("lider", "BlockedError")]


def test_collect_forwards_the_store_filter(tmp_path: Path, wired) -> None:
    assert run(tmp_path, "collect", "--store", "jumbo", "--report", str(tmp_path / "r.json")) == 0
    assert wired["only"] == "jumbo"


def test_config_error_exits_with_code_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_path):
        raise ConfigError("bad basket")

    monkeypatch.setattr(cli, "load_config", broken)
    assert run(tmp_path, "collect") == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/pipeline tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.pipeline'`.

- [ ] **Step 4: Implement collect**

`src/supermercado/pipeline/__init__.py`:

```python
"""Orchestration: collect, propose, smoke. Adapters in, observations out."""
```

`src/supermercado/pipeline/collect.py`:

```python
"""Weekly collection: fetch approved SKUs per store, validate, build observations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from supermercado.config import AppConfig
from supermercado.domain.models import PriceObservation, Status
from supermercado.domain.validation import build_observation
from supermercado.stores.base import StoreAdapter

log = logging.getLogger(__name__)


class EmptyResult(Exception):
    """A store answered but returned no listing for any approved SKU."""


@dataclass(frozen=True)
class StoreFailure:
    store: str
    error_class: str
    message: str
    at: datetime


@dataclass(frozen=True)
class Alert:
    store: str
    item_id: str
    message: str


@dataclass
class CollectResult:
    week: str
    observations: list[PriceObservation] = field(default_factory=list)
    failures: list[StoreFailure] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    collected_stores: set[str] = field(default_factory=set)


def iso_week(moment: datetime) -> str:
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


def collect(
    config: AppConfig,
    adapters: Mapping[str, StoreAdapter],
    *,
    now: datetime,
    previous: Mapping[tuple[str, str], int],
) -> CollectResult:
    result = CollectResult(week=iso_week(now))
    for store_id, adapter in adapters.items():
        matches = config.matches_for_store(store_id)
        if not matches:
            log.info("%s: no approved matches, skipping", store_id)
            continue
        skus = list(dict.fromkeys(match.sku for match in matches.values()))
        try:
            listings = adapter.fetch(skus)
            if not listings:
                raise EmptyResult(f"{store_id} returned no listings for {len(skus)} approved SKUs")
        except Exception as exc:  # one store must never block the others
            log.warning("%s failed: %s: %s", store_id, type(exc).__name__, exc)
            result.failures.append(StoreFailure(store_id, type(exc).__name__, str(exc), now))
            continue
        result.collected_stores.add(store_id)
        by_sku = {listing.sku: listing for listing in listings}
        for item_id, match in matches.items():
            listing = by_sku.get(match.sku)
            if listing is None:
                result.dropped.append(f"{store_id}/{item_id}: sku {match.sku} not returned")
                continue
            item = config.item(item_id)
            observation = build_observation(
                week=result.week,
                scraped_at=now,
                store=store_id,
                item=item,
                match=match,
                listing=listing,
                previous_unit_price=previous.get((store_id, item_id)),
            )
            if observation is None:
                result.dropped.append(f"{store_id}/{item_id}: missing or non-positive price")
                continue
            if observation.status is Status.SIZE_CHANGED:
                result.alerts.append(
                    Alert(
                        store_id,
                        item_id,
                        f"sku {match.sku}: approved size {match.size:g} {item.unit.value}, "
                        f"store now reports {observation.size:g} {item.unit.value}",
                    )
                )
            result.observations.append(observation)
    for line in result.dropped:
        log.info("dropped %s", line)
    return result
```

- [ ] **Step 5: Implement storage and the report**

`src/supermercado/pipeline/storage.py`:

```python
"""One immutable Parquet file per ISO week: data/prices/YYYY-Www.parquet."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from supermercado.domain.models import PriceObservation, Status

SCHEMA = pa.schema(
    [
        ("week", pa.string()),
        ("scraped_at", pa.timestamp("us", tz="UTC")),
        ("location", pa.string()),
        ("store", pa.string()),
        ("item_id", pa.string()),
        ("sku", pa.string()),
        ("product_name", pa.string()),
        ("brand", pa.string()),
        ("url", pa.string()),
        ("size", pa.float64()),
        ("unit", pa.string()),
        ("price", pa.int64()),
        ("promo_price", pa.int64()),
        ("card_price", pa.int64()),
        ("effective_price", pa.int64()),
        ("unit_price", pa.int64()),
        ("available", pa.bool_()),
        ("status", pa.string()),
    ]
)


def week_path(data_dir: Path, week: str) -> Path:
    return data_dir / "prices" / f"{week}.parquet"


def list_weeks(data_dir: Path) -> list[str]:
    return sorted(path.stem for path in (data_dir / "prices").glob("*.parquet"))


def _record(obs: PriceObservation) -> dict[str, object]:
    data = obs.model_dump()
    data["status"] = obs.status.value
    return {name: data[name] for name in SCHEMA.names}


def read_week(data_dir: Path, week: str) -> list[PriceObservation]:
    path = week_path(data_dir, week)
    if not path.exists():
        return []
    return [PriceObservation.model_validate(row) for row in pq.read_table(path).to_pylist()]


def write_week(
    data_dir: Path,
    week: str,
    observations: Iterable[PriceObservation],
    *,
    replace_stores: set[str],
) -> Path | None:
    """Replace the rows of `replace_stores` in this week's file, keeping every other store."""
    kept = [obs for obs in read_week(data_dir, week) if obs.store not in replace_stores]
    fresh = [obs for obs in observations if obs.store in replace_stores]
    rows = sorted(kept + fresh, key=lambda obs: (obs.store, obs.item_id))
    if not rows:
        return None
    path = week_path(data_dir, week)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([_record(obs) for obs in rows], schema=SCHEMA)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)
    return path


def previous_unit_prices(data_dir: Path, week: str) -> dict[tuple[str, str], int]:
    earlier = [w for w in list_weeks(data_dir) if w < week]
    if not earlier:
        return {}
    return {
        (obs.store, obs.item_id): obs.unit_price
        for obs in read_week(data_dir, earlier[-1])
        if obs.status == Status.OK
    }
```

`src/supermercado/pipeline/report.py`:

```python
"""Machine-readable collection report consumed by the weekly workflow."""

from __future__ import annotations

from typing import Any

from supermercado.pipeline.collect import CollectResult


def report_to_dict(result: CollectResult) -> dict[str, Any]:
    return {
        "week": result.week,
        "observations": len(result.observations),
        "collected_stores": sorted(result.collected_stores),
        "failures": [
            {"store": f.store, "error_class": f.error_class, "message": f.message, "at": f.at.isoformat()}
            for f in result.failures
        ],
        "alerts": [{"store": a.store, "item_id": a.item_id, "message": a.message} for a in result.alerts],
        "dropped": list(result.dropped),
    }
```

- [ ] **Step 6: Implement the CLI**

`src/supermercado/cli.py`:

```python
"""Command line entry point: python -m supermercado <command>."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from supermercado.config import ConfigError, load_config
from supermercado.pipeline.collect import collect, iso_week
from supermercado.pipeline.report import report_to_dict
from supermercado.pipeline.storage import previous_unit_prices, write_week
from supermercado.stores import build_adapters


def _now() -> datetime:
    return datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="supermercado")
    parser.add_argument("--config", type=Path, default=Path("config"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    sub = parser.add_subparsers(dest="command", required=True)

    collect_cmd = sub.add_parser("collect", help="fetch approved SKUs and write this week's snapshot")
    collect_cmd.add_argument("--store", help="collect a single store (manual fallback)")
    collect_cmd.add_argument("--report", type=Path, default=Path("build/report.json"))
    return parser


def _cmd_collect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    adapters = build_adapters(config, only=args.store)
    now = _now()
    week = iso_week(now)
    result = collect(config, adapters, now=now, previous=previous_unit_prices(args.data, week))
    path = write_week(args.data, week, result.observations, replace_stores=result.collected_stores)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report_to_dict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{week}: {len(result.observations)} observations, {len(result.failures)} store failures")
    if path is not None:
        print(f"written {path}")
    for failure in result.failures:
        print(f"FAILED {failure.store}: {failure.error_class}: {failure.message}", file=sys.stderr)
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "collect": _cmd_collect,
}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
```

`src/supermercado/__main__.py`:

```python
from supermercado.cli import main

raise SystemExit(main())
```

Create the empty file `data/prices/.gitkeep`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 8: Smoke-run the real CLI against Jumbo (optional, needs network)**

Run: `uv run python -m supermercado collect`
Expected with the comment-only `matches.yaml`: `2026-Wnn: 0 observations, 0 store failures` and no Parquet file (no store has matches yet). This proves wiring without touching data.

- [ ] **Step 9: Commit**

```bash
git add src/supermercado/pipeline src/supermercado/cli.py src/supermercado/__main__.py data/prices/.gitkeep tests/fakes.py tests/pipeline tests/test_cli.py
git commit -m "feat(pipeline): collect approved SKUs into weekly Parquet snapshots via CLI"
```

---

### Task 8: Static site build

> **AMENDMENT (2026-10-04):** `Ranking` has a new `insufficient_coverage: list[str]` field (Task 3). The home template lists those stores under "Cobertura insuficiente" (already added to `home.html` below). Add a build test asserting a store with fewer than 80% of items appears under "cobertura insuficiente esta semana" and not in the ranking. Methodology page must mention the 80% coverage rule.

**Files:**
- Create: `src/supermercado/site/__init__.py`, `src/supermercado/site/format.py`, `src/supermercado/site/build.py`
- Create: `src/supermercado/site/templates/base.html`, `index.html`, `products.html`, `product.html`, `methodology.html`
- Create: `src/supermercado/site/static/style.css`, `src/supermercado/site/static/app.js`
- Modify: `src/supermercado/cli.py` (add `build` command)
- Test: `tests/site/test_format.py`, `tests/site/test_build.py`

**Interfaces:**
- Consumes: `AppConfig` (Task 4); `rank_stores`, `Ranking`, `StoreTotal` (Task 3); `apply_clearances` (Task 2); `write_week` (Task 7, tests only); `make_obs`, `make_config`, `make_item`, `make_match` (factories).
- Produces:
  - `supermercado.site.format`: `format_clp(amount: int | None) -> str` (`1890 → "$1.890"`, `None → "—"`, negatives use `−`), `format_change(delta: int | None) -> str`, `format_date_es(moment: datetime) -> str` (America/Santiago)
  - `supermercado.site.build`: `UNIT_LABELS`, `CATEGORY_LABELS`, `Cell(text, css)`, `load_observations(data_dir: Path) -> list[PriceObservation]` (DuckDB), `chart_data(item_id, observations, stores, names) -> dict`, `render_site(config, observations, out_dir) -> None`, `build_site(config, data_dir, out_dir) -> None`
  - Output tree: `dist/index.html`, `dist/productos/index.html`, `dist/producto/<item_id>/index.html`, `dist/metodologia/index.html`, `dist/static/{style.css,app.js}`. All links are relative so the site works under a GitHub Pages project path.
  - Chart JSON (embedded as `<script type="application/json" id="chart-data">`): `{"weeks": [str], "series": [{"store", "label", "points": [{"week", "unit_price", "sku", "sku_changed", "status"}]}]}`
  - CLI: `build [--out dist]`

- [ ] **Step 1: Write the failing tests**

`tests/site/test_format.py`:

```python
from datetime import UTC, datetime

import pytest

from supermercado.site.format import format_change, format_clp, format_date_es


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(1890, "$1.890"), (0, "$0"), (1234567, "$1.234.567"), (-100, "−$100"), (None, "—")],
)
def test_format_clp(amount, expected) -> None:
    assert format_clp(amount) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (None, "sin semana anterior"),
        (0, "sin cambio vs semana anterior"),
        (20, "+$20 vs semana anterior"),
        (-1500, "−$1.500 vs semana anterior"),
    ],
)
def test_format_change(delta, expected) -> None:
    assert format_change(delta) == expected


def test_format_date_uses_santiago_time() -> None:
    assert format_date_es(datetime(2026, 9, 28, 9, 0, tzinfo=UTC)) == "28 de septiembre de 2026"
    assert format_date_es(datetime(2026, 10, 5, 2, 0, tzinfo=UTC)) == "4 de octubre de 2026"
```

`tests/site/test_build.py`:

```python
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factories import make_config, make_item, make_match, make_obs

from supermercado.config import load_config
from supermercado.domain.models import Category, Unit
from supermercado.pipeline.storage import write_week
from supermercado.site.build import build_site, load_observations

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
ITEMS = [
    make_item("rice", name="Arroz grado 2 (1 kg)"),
    make_item("spaghetti", reference_qty=0.4, name="Fideos spaghetti (400 g)"),
    make_item("whole_milk", unit=Unit.L, category=Category.DAIRY_EGGS, name="Leche entera (1 L)"),
]
W39 = {"week": "2026-W39", "scraped_at": datetime(2026, 9, 21, 9, 0, tzinfo=UTC)}


def site_config():
    lider = "https://super.lider.cl/ip/x/"
    return make_config(
        items=ITEMS,
        stores=("jumbo", "tottus", "lider"),
        matches={
            "rice": {"jumbo": make_match("1626"), "lider": make_match("00780142021013", url=lider + "1")},
            "spaghetti": {
                "jumbo": make_match("2001", size=0.4),
                "lider": make_match("3001", size=0.4, url=lider + "2"),
            },
            "whole_milk": {"jumbo": make_match("4001")},
        },
    )


def observations():
    return [
        make_obs(**W39, store="jumbo", item_id="rice", unit_price=1790),
        make_obs(**W39, store="jumbo", item_id="spaghetti", sku="2001", unit_price=2475),
        make_obs(**W39, store="lider", item_id="rice", sku="00780142021000", unit_price=1290),
        make_obs(**W39, store="lider", item_id="spaghetti", sku="3001", unit_price=2600),
        make_obs(store="jumbo", item_id="rice", unit_price=1810),
        make_obs(store="jumbo", item_id="spaghetti", sku="2001", unit_price=2475),
        make_obs(store="jumbo", item_id="whole_milk", sku="4001", unit="l", unit_price=990),
        make_obs(store="lider", item_id="rice", sku="00780142021013", unit_price=1190),
        make_obs(store="lider", item_id="spaghetti", sku="3001", unit_price=2600),
    ]


def write_fixture_parquet(data: Path) -> None:
    rows = observations()
    for week in ("2026-W39", "2026-W40"):
        write_week(data, week, [o for o in rows if o.week == week], replace_stores={"jumbo", "lider"})


@pytest.fixture
def built(tmp_path: Path) -> Path:
    write_fixture_parquet(tmp_path / "data")
    build_site(site_config(), tmp_path / "data", tmp_path / "dist")
    return tmp_path / "dist"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_load_observations_reads_every_week_through_duckdb(tmp_path: Path) -> None:
    write_fixture_parquet(tmp_path / "data")
    loaded = load_observations(tmp_path / "data")
    assert loaded == sorted(observations(), key=lambda o: (o.week, o.store, o.item_id))


def test_home_ranks_stores_and_highlights_the_winner(built: Path) -> None:
    html = read(built / "index.html")
    assert "¿Dónde sale más barata la canasta esta semana?" in html
    assert "Actualizado: 28 de septiembre de 2026 · Precios de referencia Santiago" in html
    assert "Comparando 2 de 3 productos" in html
    assert html.index("Lider") < html.index("Jumbo")
    assert 'class="rank-card is-winner"' in html
    assert "$2.230" in html and "$2.800" in html
    assert "−$100 vs semana anterior" in html
    assert "+$20 vs semana anterior" in html
    assert "Tottus: sin datos esta semana" in html


def test_products_table_highlights_cheapest_and_explains_gaps(built: Path) -> None:
    html = read(built / "productos" / "index.html")
    assert '<td class="best">$1.190/kg</td>' in html
    assert '<td class="">$1.810/kg</td>' in html
    assert "sin match" in html
    assert 'data-category="dairy_eggs"' in html
    assert 'data-filter="meat"' in html


def test_product_page_embeds_valid_chart_json_and_marks_sku_changes(built: Path) -> None:
    html = read(built / "producto" / "rice" / "index.html")
    match = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', html, re.S)
    assert match is not None
    chart = json.loads(match.group(1))
    assert chart["weeks"] == ["2026-W39", "2026-W40"]
    lider = next(s for s in chart["series"] if s["store"] == "lider")
    assert [p["sku_changed"] for p in lider["points"]] == [False, True]
    assert "SKU 00780142021000 → 00780142021013" in html


def test_every_page_exists(built: Path) -> None:
    for item in ITEMS:
        assert (built / "producto" / item.id / "index.html").exists()
    assert "Metodología" in read(built / "metodologia" / "index.html")
    assert (built / "static" / "style.css").exists()
    assert (built / "static" / "app.js").exists()


def test_build_with_no_data_renders_empty_state(tmp_path: Path) -> None:
    config = load_config(CONFIG_DIR)
    build_site(config, tmp_path / "data", tmp_path / "dist")
    assert "Aún no hay datos" in read(tmp_path / "dist" / "index.html")
    assert len(list((tmp_path / "dist" / "producto").iterdir())) == 23
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/site -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.site'`.

- [ ] **Step 3: Implement formatting helpers**

`src/supermercado/site/__init__.py`:

```python
"""Static site generation."""
```

`src/supermercado/site/format.py`:

```python
"""Spanish (Chile) display formatting for the site."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SANTIAGO = ZoneInfo("America/Santiago")
MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def format_clp(amount: int | None) -> str:
    if amount is None:
        return "—"
    sign = "−" if amount < 0 else ""
    return f"{sign}${abs(amount):,}".replace(",", ".")


def format_change(delta: int | None) -> str:
    if delta is None:
        return "sin semana anterior"
    if delta == 0:
        return "sin cambio vs semana anterior"
    sign = "+" if delta > 0 else "−"
    return f"{sign}{format_clp(abs(delta))} vs semana anterior"


def format_date_es(moment: datetime) -> str:
    local = moment.astimezone(SANTIAGO)
    return f"{local.day} de {MONTHS_ES[local.month - 1]} de {local.year}"
```

- [ ] **Step 4: Implement the build**

`src/supermercado/site/build.py`:

```python
"""Static site build: Parquet (read with DuckDB) -> Jinja templates -> dist/."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
from jinja2 import Environment, FileSystemLoader, select_autoescape

from supermercado.config import AppConfig
from supermercado.domain.models import BasketItem, Category, PriceObservation, Status, Unit
from supermercado.domain.ranking import rank_stores
from supermercado.domain.validation import apply_clearances
from supermercado.site.format import format_change, format_clp, format_date_es

PACKAGE_DIR = Path(__file__).parent
UNIT_LABELS = {Unit.KG: "kg", Unit.L: "L", Unit.M: "m", Unit.UNIT: "un"}
CATEGORY_LABELS = {
    Category.PANTRY: "Despensa",
    Category.DAIRY_EGGS: "Lácteos y huevos",
    Category.BAKERY: "Panadería",
    Category.MEAT: "Carnes",
    Category.CLEANING: "Limpieza",
    Category.HYGIENE: "Higiene",
}


@dataclass(frozen=True)
class Cell:
    text: str
    css: str = ""


def load_observations(data_dir: Path) -> list[PriceObservation]:
    prices = data_dir / "prices"
    if not any(prices.glob("*.parquet")):
        return []
    pattern = str(prices / "*.parquet").replace("'", "''")
    con = duckdb.connect()
    try:
        table = con.execute(
            f"SELECT * FROM read_parquet('{pattern}') ORDER BY week, store, item_id"
        ).to_arrow_table()
    finally:
        con.close()
    return [PriceObservation.model_validate(row) for row in table.to_pylist()]


def chart_data(
    item_id: str,
    observations: Sequence[PriceObservation],
    stores: Sequence[str],
    names: dict[str, str],
) -> dict[str, Any]:
    rows = [o for o in observations if o.item_id == item_id]
    series = []
    for store in stores:
        points: list[dict[str, Any]] = []
        previous_sku: str | None = None
        for obs in sorted((o for o in rows if o.store == store), key=lambda o: o.week):
            points.append(
                {
                    "week": obs.week,
                    "unit_price": obs.unit_price,
                    "sku": obs.sku,
                    "sku_changed": previous_sku is not None and obs.sku != previous_sku,
                    "status": obs.status.value,
                }
            )
            previous_sku = obs.sku
        if points:
            series.append({"store": store, "label": names[store], "points": points})
    return {"weeks": sorted({o.week for o in rows}), "series": series}


def _sku_changes(chart: dict[str, Any]) -> list[dict[str, str]]:
    changes = []
    for series in chart["series"]:
        points = series["points"]
        for before, after in zip(points, points[1:], strict=False):
            if after["sku_changed"]:
                changes.append(
                    {"store": series["store"], "week": after["week"],
                     "previous": before["sku"], "sku": after["sku"]}
                )
    return changes


def _latest_rows(
    item_id: str, observations: Sequence[PriceObservation], stores: Sequence[str]
) -> list[PriceObservation]:
    latest: dict[str, PriceObservation] = {}
    for obs in sorted(observations, key=lambda o: o.week):
        if obs.item_id == item_id:
            latest[obs.store] = obs
    return [latest[s] for s in stores if s in latest]


def _cell(
    item: BasketItem, store: str, obs: PriceObservation | None, config: AppConfig, best: int | None
) -> Cell:
    if store not in config.matches.get(item.id, {}):
        return Cell("sin match", "muted")
    if obs is None:
        return Cell("sin datos", "muted")
    if not obs.available:
        return Cell("agotado", "muted")
    if obs.status != Status.OK:
        return Cell("en revisión", "warn")
    text = f"{format_clp(obs.unit_price)}/{UNIT_LABELS[item.unit]}"
    return Cell(text, "best" if obs.unit_price == best else "")


def _product_rows(
    config: AppConfig, current: Sequence[PriceObservation], stores: Sequence[str]
) -> list[dict[str, Any]]:
    by_key = {(o.store, o.item_id): o for o in current}
    rows = []
    for item in config.basket:
        usable = [
            o.unit_price
            for s in stores
            if (o := by_key.get((s, item.id))) is not None and o.status == Status.OK and o.available
        ]
        best = min(usable, default=None)
        cells = [_cell(item, s, by_key.get((s, item.id)), config, best) for s in stores]
        rows.append({"item": item, "category": item.category.value, "cells": cells})
    return rows


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(PACKAGE_DIR / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["clp"] = format_clp
    env.filters["change"] = format_change
    return env


def _script_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def render_site(config: AppConfig, observations: Sequence[PriceObservation], out_dir: Path) -> None:
    stores = config.enabled_stores()
    names = {store: cfg.name for store, cfg in config.stores.items()}
    weeks = sorted({o.week for o in observations})
    latest_week = weeks[-1] if weeks else None
    previous_week = weeks[-2] if len(weeks) > 1 else None
    current = [o for o in observations if o.week == latest_week]
    previous = [o for o in observations if o.week == previous_week]
    common: dict[str, Any] = {
        "week": latest_week,
        "updated": format_date_es(max(o.scraped_at for o in current)) if current else None,
        "store_names": names,
        "stores": stores,
        "comunas": {store: config.stores[store].comuna for store in stores},
        "basket_size": len(config.basket),
    }
    env = _environment()
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PACKAGE_DIR / "static", out_dir / "static", dirs_exist_ok=True)

    ranking = rank_stores(current, previous, config.basket, stores)
    _write(
        out_dir / "index.html",
        env.get_template("index.html").render(root="./", page="home", ranking=ranking, **common),
    )
    _write(
        out_dir / "productos" / "index.html",
        env.get_template("products.html").render(
            root="../",
            page="products",
            rows=_product_rows(config, current, stores),
            categories=[(c.value, CATEGORY_LABELS[c]) for c in Category],
            **common,
        ),
    )
    product_template = env.get_template("product.html")
    for item in config.basket:
        chart = chart_data(item.id, observations, stores, names)
        _write(
            out_dir / "producto" / item.id / "index.html",
            product_template.render(
                root="../../",
                page="product",
                item=item,
                unit_label=UNIT_LABELS[item.unit],
                category_label=CATEGORY_LABELS[item.category],
                chart=chart,
                chart_json=_script_json(chart),
                latest=_latest_rows(item.id, observations, stores),
                sku_changes=_sku_changes(chart),
                **common,
            ),
        )
    _write(
        out_dir / "metodologia" / "index.html",
        env.get_template("methodology.html").render(root="../", page="methodology", **common),
    )


def build_site(config: AppConfig, data_dir: Path, out_dir: Path) -> None:
    cleared = {(c.week, c.store, c.item_id) for c in config.cleared}
    render_site(config, apply_clearances(load_observations(data_dir), cleared), out_dir)
```

- [ ] **Step 5: Write the templates (UI copy in Spanish)**

`src/supermercado/site/templates/base.html`:

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Canasta Santiago · ¿Dónde sale más barata?{% endblock %}</title>
  <meta name="description" content="Comparación semanal del precio de la canasta básica en supermercados de Santiago.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{{ root }}static/style.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="{{ root }}"><span class="brand-dot"></span>canasta</a>
    <nav class="pill-nav" aria-label="Secciones">
      <a class="pill {{ 'is-active' if page == 'home' }}" href="{{ root }}">Ranking</a>
      <a class="pill {{ 'is-active' if page in ('products', 'product') }}" href="{{ root }}productos/">Productos</a>
      <a class="pill {{ 'is-active' if page == 'methodology' }}" href="{{ root }}metodologia/">Metodología</a>
    </nav>
  </header>
  <main class="container">
{% block content %}{% endblock %}
  </main>
  <footer class="site-footer">
    Precios de referencia Santiago · Datos públicos de cada supermercado · Sin cookies de seguimiento
  </footer>
{% block scripts %}{% endblock %}
  <script src="{{ root }}static/app.js" defer></script>
</body>
</html>
```

`src/supermercado/site/templates/index.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="hero">
  <p class="eyebrow">Canasta básica · Semana {{ week or "—" }}</p>
  <h1>¿Dónde sale más barata la canasta esta semana?</h1>
  {% if updated %}
  <p class="meta">Actualizado: {{ updated }} · Precios de referencia Santiago</p>
  {% endif %}
</section>
{% if not week %}
<p class="empty">Aún no hay datos. La primera actualización se publicará el próximo lunes.</p>
{% elif not ranking.ranked %}
<p class="empty">Esta semana no hay productos comparables entre los supermercados con datos.</p>
{% else %}
<p class="meta">Comparando {{ ranking.comparable_items | length }} de {{ basket_size }} productos</p>
<ol class="ranking">
  {% for row in ranking.ranked %}
  <li class="rank-card {{ 'is-winner' if loop.first }}">
    <span class="rank-pos">{{ loop.index }}</span>
    <span class="rank-store">{{ store_names[row.store] }}</span>
    <span class="rank-total">{{ row.total | clp }}</span>
    <span class="rank-change">{{ row.change | change }}</span>
    {% if loop.first %}<span class="badge">Más barata</span>{% endif %}
  </li>
  {% endfor %}
</ol>
{% endif %}
{% if week and ranking.insufficient_coverage %}
<section class="no-data">
  <h2>Cobertura insuficiente</h2>
  <ul class="plain-list">
    {% for store in ranking.insufficient_coverage %}
    <li>{{ store_names[store] }}: cobertura insuficiente esta semana</li>
    {% endfor %}
  </ul>
</section>
{% endif %}
{% if week and ranking.no_data %}
<section class="no-data">
  <h2>Supermercados sin datos</h2>
  <ul class="plain-list">
    {% for store in ranking.no_data %}
    <li>{{ store_names[store] }}: sin datos esta semana</li>
    {% endfor %}
  </ul>
</section>
{% endif %}
{% endblock %}
```

Note: `{{ 'is-winner' if loop.first }}` renders an empty string otherwise, so the first card's class is exactly `rank-card is-winner`.

`src/supermercado/site/templates/products.html`:

```html
{% extends "base.html" %}
{% block title %}Productos · Canasta Santiago{% endblock %}
{% block content %}
<section class="hero hero--compact">
  <p class="eyebrow">Semana {{ week or "—" }}</p>
  <h1>Precio por unidad en cada supermercado</h1>
  <p class="meta">Precio normalizado por kg, litro, metro o unidad. El más barato aparece destacado.</p>
</section>
<div class="pill-row" role="group" aria-label="Filtrar por categoría">
  <button type="button" class="pill is-active" data-filter="all">Todos</button>
  {% for value, label in categories %}
  <button type="button" class="pill" data-filter="{{ value }}">{{ label }}</button>
  {% endfor %}
</div>
<div class="table-scroll">
  <table class="price-table">
    <thead>
      <tr>
        <th scope="col">Producto</th>
        {% for store in stores %}<th scope="col">{{ store_names[store] }}</th>{% endfor %}
      </tr>
    </thead>
    <tbody>
      {% for row in rows %}
      <tr data-category="{{ row.category }}">
        <th scope="row"><a href="{{ root }}producto/{{ row.item.id }}/">{{ row.item.name }}</a></th>
        {% for cell in row.cells %}<td class="{{ cell.css }}">{{ cell.text }}</td>{% endfor %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

`src/supermercado/site/templates/product.html`:

```html
{% extends "base.html" %}
{% block title %}{{ item.name }} · Canasta Santiago{% endblock %}
{% block content %}
<section class="hero hero--compact">
  <p class="eyebrow">{{ category_label }}</p>
  <h1>{{ item.name }}</h1>
  <p class="meta">Precio por {{ unit_label }} en el tiempo. Los triángulos marcan semanas en que cambió el producto (SKU).</p>
</section>
{% if chart.series %}
<div class="card chart-card">
  <canvas id="price-chart" role="img" aria-label="Evolución del precio por {{ unit_label }}"></canvas>
</div>
{% else %}
<p class="empty">Todavía no hay precios registrados para este producto.</p>
{% endif %}
<h2>Producto usado en cada supermercado</h2>
<div class="table-scroll">
  <table class="price-table">
    <thead>
      <tr><th scope="col">Supermercado</th><th scope="col">SKU</th><th scope="col">Producto</th><th scope="col">Precio por {{ unit_label }}</th><th scope="col">Semana</th></tr>
    </thead>
    <tbody>
      {% for row in latest %}
      <tr>
        <th scope="row">{{ store_names[row.store] }}</th>
        <td>{{ row.sku }}</td>
        <td>{% if row.url %}<a href="{{ row.url }}" rel="nofollow noopener">{{ row.product_name }}</a>{% else %}{{ row.product_name }}{% endif %}</td>
        <td>{{ row.unit_price | clp }}</td>
        <td>{{ row.week }}</td>
      </tr>
      {% else %}
      <tr><td colspan="5">Sin datos.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% if sku_changes %}
<h2>Cambios de producto</h2>
<ul class="plain-list">
  {% for change in sku_changes %}
  <li>{{ store_names[change.store] }} · semana {{ change.week }}: SKU {{ change.previous }} → {{ change.sku }}</li>
  {% endfor %}
</ul>
{% endif %}
<script type="application/json" id="chart-data">{{ chart_json | safe }}</script>
{% endblock %}
{% block scripts %}
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" defer></script>
{% endblock %}
```

`src/supermercado/site/templates/methodology.html`:

```html
{% extends "base.html" %}
{% block title %}Metodología · Canasta Santiago{% endblock %}
{% block content %}
<section class="hero hero--compact">
  <p class="eyebrow">Cómo trabajamos</p>
  <h1>Metodología</h1>
</section>
<article class="prose">
  <h2>Productos equivalentes</h2>
  <p>Cada producto de la canasta tiene una regla de equivalencia: tipo de producto, tamaño aceptado y términos excluidos. El sistema propone candidatos y una persona aprueba cada coincidencia antes de que entre al historial. No comparamos marcas exactas: comparamos el producto equivalente aprobado en cada supermercado.</p>

  <h2>Ubicación de referencia</h2>
  <p>Los precios corresponden a una sucursal o zona de despacho fija de Santiago por cadena:</p>
  <ul class="plain-list">
    {% for store in stores %}
    <li>{{ store_names[store] }}: {{ comunas[store] }}</li>
    {% endfor %}
  </ul>

  <h2>Frecuencia</h2>
  <p>Los precios se recolectan una vez por semana, los lunes en la mañana (hora de Santiago).</p>

  <h2>Precios con tarjeta o club</h2>
  <p>Usamos el precio que cualquier persona paga: el precio normal o una oferta sin condiciones. Los precios exclusivos para tarjetas o clubes se registran aparte y nunca se usan en el ranking.</p>

  <h2>Cómo se calcula el total</h2>
  <p>Cada producto se normaliza a precio por kg, litro, metro o unidad y se multiplica por la cantidad de referencia de la canasta. Solo se suman los productos que todos los supermercados con datos tienen disponibles esa semana, para comparar siempre la misma canasta. Nunca estimamos precios faltantes.</p>

  <h2>Qué significa cada estado</h2>
  <ul class="plain-list">
    <li><strong>Sin datos:</strong> no pudimos obtener precios de ese supermercado esta semana.</li>
    <li><strong>Sin match:</strong> todavía no hay un producto equivalente aprobado en ese supermercado.</li>
    <li><strong>Agotado:</strong> el producto aprobado no tenía stock al momento de la consulta.</li>
    <li><strong>En revisión:</strong> el precio por unidad cambió más de 50 % o el tamaño del envase cambió; queda fuera del ranking hasta que una persona lo revise.</li>
  </ul>
</article>
{% endblock %}
```

- [ ] **Step 6: Write the static assets**

`src/supermercado/site/static/style.css`:

```css
:root {
  --honeydew: #E5F4E3;
  --sky: #5DA9E9;
  --blue: #003F91;
  --white: #FFFFFF;
  --purple: #6D326D;
  --ink: #0B1F3A;
  --muted: #5B6B80;
  --line: rgba(0, 63, 145, 0.14);
  --radius-lg: 32px;
  --radius-md: 16px;
  --radius-pill: 999px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--honeydew);
  color: var(--ink);
  font-family: "Poppins", system-ui, sans-serif;
  line-height: 1.5;
}

a { color: var(--blue); }

.site-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
  padding: 20px 16px;
  background: var(--blue);
  color: var(--white);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--white);
  text-decoration: none;
  font-weight: 600;
  font-size: 20px;
  letter-spacing: -0.03em;
}

.brand-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--sky);
}

.pill-nav {
  display: flex;
  gap: 6px;
  padding: 6px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.12);
}

.pill {
  border: 0;
  padding: 8px 16px;
  border-radius: var(--radius-pill);
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
}

.pill.is-active { background: var(--white); color: var(--blue); }
.pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.pill-row .pill { background: var(--white); color: var(--blue); border: 1px solid var(--line); }
.pill-row .pill.is-active { background: var(--blue); color: var(--white); }

.container { max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }

.hero { padding: 16px 0 8px; }
.hero h1 { font-size: clamp(28px, 6vw, 48px); line-height: 1.1; letter-spacing: -0.03em; margin: 8px 0; }
.hero--compact h1 { font-size: clamp(24px, 5vw, 36px); }
.eyebrow { margin: 0; color: var(--purple); font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.14em; }
.meta { color: var(--muted); margin: 4px 0 16px; }
.empty { background: var(--white); border-radius: var(--radius-md); padding: 20px; }

.ranking { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }

.rank-card {
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-areas: "pos store total" "pos change change";
  gap: 4px 12px;
  align-items: center;
  padding: 16px 20px;
  border-radius: var(--radius-md);
  background: var(--white);
}

.rank-card.is-winner { background: var(--blue); color: var(--white); border-radius: var(--radius-lg); }
.rank-pos { grid-area: pos; font-size: 28px; font-weight: 700; color: var(--sky); }
.rank-store { grid-area: store; font-weight: 600; font-size: 18px; }
.rank-total { grid-area: total; font-weight: 700; font-size: 20px; }
.rank-change { grid-area: change; font-size: 14px; opacity: 0.8; }
.badge { justify-self: start; padding: 2px 10px; border-radius: var(--radius-pill); background: var(--sky); color: var(--white); font-size: 12px; font-weight: 600; }

.no-data { margin-top: 32px; }
.plain-list { padding-left: 18px; }

.card { background: var(--white); border-radius: var(--radius-md); padding: 16px; }
.chart-card { margin-bottom: 24px; }

.table-scroll { overflow-x: auto; background: var(--white); border-radius: var(--radius-md); }
.price-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.price-table th, .price-table td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
.price-table thead th { color: var(--muted); font-weight: 500; }
.price-table td.best { background: var(--sky); color: var(--white); font-weight: 600; }
.price-table td.muted { color: var(--muted); }
.price-table td.warn { color: var(--purple); font-style: italic; }

.prose h2 { margin-top: 28px; }
.site-footer { padding: 24px 16px; text-align: center; color: var(--muted); font-size: 13px; }

@media (min-width: 720px) {
  .site-header { padding: 24px 5vw; }
  .rank-card { grid-template-columns: 48px 1fr auto auto; grid-template-areas: "pos store change total"; }
}
```

`src/supermercado/site/static/app.js`:

```js
document.addEventListener("DOMContentLoaded", () => {
  const pills = document.querySelectorAll("[data-filter]");
  pills.forEach((pill) => {
    pill.addEventListener("click", () => {
      const value = pill.dataset.filter;
      pills.forEach((other) => other.classList.toggle("is-active", other === pill));
      document.querySelectorAll("tr[data-category]").forEach((row) => {
        row.hidden = value !== "all" && row.dataset.category !== value;
      });
    });
  });

  const dataEl = document.getElementById("chart-data");
  const canvas = document.getElementById("price-chart");
  if (!dataEl || !canvas || typeof Chart === "undefined") return;
  const data = JSON.parse(dataEl.textContent);
  const palette = ["#003F91", "#5DA9E9", "#6D326D", "#2E8B57", "#E07A5F", "#3D405B"];
  const clp = (value) => "$" + Number(value).toLocaleString("es-CL");
  const datasets = data.series.map((series, index) => {
    const byWeek = Object.fromEntries(series.points.map((point) => [point.week, point]));
    const changed = (week) => Boolean(byWeek[week] && byWeek[week].sku_changed);
    const color = palette[index % palette.length];
    return {
      label: series.label,
      data: data.weeks.map((week) => (byWeek[week] ? byWeek[week].unit_price : null)),
      pointStyle: data.weeks.map((week) => (changed(week) ? "triangle" : "circle")),
      pointRadius: data.weeks.map((week) => (changed(week) ? 7 : 3)),
      borderColor: color,
      backgroundColor: color,
      spanGaps: false,
      tension: 0.2,
    };
  });
  new Chart(canvas, {
    type: "line",
    data: { labels: data.weeks, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${clp(ctx.parsed.y)}` } },
      },
      scales: { y: { ticks: { callback: (value) => clp(value) } } },
    },
  });
});
```

- [ ] **Step 7: Add the `build` CLI command**

In `src/supermercado/cli.py`, add the import `from supermercado.site.build import build_site`, add to `_parser()` before `return parser`:

```python
    build_cmd = sub.add_parser("build", help="render the static site into --out")
    build_cmd.add_argument("--out", type=Path, default=Path("dist"))
```

add the handler:

```python
def _cmd_build(args: argparse.Namespace) -> int:
    build_site(load_config(args.config), args.data, args.out)
    print(f"site written to {args.out}")
    return 0
```

and register it: `COMMANDS = {"collect": _cmd_collect, "build": _cmd_build}`.

Append to `tests/test_cli.py`:

```python
def test_build_command_renders_site(tmp_path: Path) -> None:
    config_dir = Path(__file__).resolve().parents[1] / "config"
    out = tmp_path / "dist"
    code = cli.main(["--config", str(config_dir), "--data", str(tmp_path / "data"), "build", "--out", str(out)])
    assert code == 0
    assert (out / "index.html").exists()
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS. `to_arrow_table()` is the current DuckDB name; if the installed DuckDB is older and lacks it, use `fetch_arrow_table()` instead (same `pyarrow.Table`).

- [ ] **Step 9: Eyeball the site**

Run: `uv run python -m supermercado build --out dist && uv run python -m http.server -d dist 8000`
Open `http://localhost:8000/` at phone width (375 px) and desktop width; check there is no horizontal page scroll (tables scroll inside their card) and the nav pills wrap cleanly. Stop the server with Ctrl+C.

- [ ] **Step 10: Commit**

```bash
git add src/supermercado/site src/supermercado/cli.py tests/site tests/test_cli.py
git commit -m "feat(site): render ranking, products, product detail and methodology pages"
```

---

### Task 9: Weekly GitHub Actions workflow, failure issue, and Pages deploy

**Files:**
- Create: `.github/workflows/weekly.yml`
- Modify: `src/supermercado/pipeline/report.py` (add `render_issue_body`)
- Modify: `src/supermercado/cli.py` (add `issue-body` command)
- Test: `tests/pipeline/test_report.py`, `tests/test_workflows.py`

**Interfaces:**
- Consumes: `report_to_dict` output shape (Task 7); CLI `collect`, `build` (Tasks 7–8).
- Produces:
  - `supermercado.pipeline.report.render_issue_body(report: Mapping[str, Any]) -> str` (empty string when there are no failures and no alerts)
  - CLI: `issue-body --report PATH` prints the Markdown body (prints nothing when empty)
  - Workflow `weekly.yml` with jobs `collect` (collect → commit snapshot → report issue → build → upload Pages artifact) and `deploy` (`needs: collect`); label `weekly-collect` on the issue.

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_report.py`:

```python
from supermercado.pipeline.report import render_issue_body

FAILURE = {
    "store": "lider",
    "error_class": "BlockedError",
    "message": "captcha | page",
    "at": "2026-09-28T09:00:00+00:00",
}
ALERT = {"store": "jumbo", "item_id": "rice", "message": "sku 1626: approved size 1 kg, store now reports 0.9 kg"}


def test_no_problems_means_empty_body() -> None:
    assert render_issue_body({"week": "2026-W40", "failures": [], "alerts": []}) == ""


def test_failures_name_store_error_class_and_time() -> None:
    body = render_issue_body({"week": "2026-W40", "failures": [FAILURE], "alerts": []})
    assert "2026-W40" in body
    assert "| lider | `BlockedError` | 2026-09-28T09:00:00+00:00 | captcha \\| page |" in body
    assert "collect --store" in body


def test_alerts_are_listed_as_size_changes() -> None:
    body = render_issue_body({"week": "2026-W40", "failures": [], "alerts": [ALERT]})
    assert "Size changes" in body
    assert "| jumbo | rice |" in body
```

`tests/test_workflows.py`:

```python
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))  # PyYAML parses the `on` key as True
    return data


def runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_weekly_runs_monday_morning_and_on_demand() -> None:
    workflow = load("weekly.yml")
    assert workflow["on"]["schedule"][0]["cron"] == "0 9 * * 1"
    assert "workflow_dispatch" in workflow["on"]


def test_weekly_collects_commits_reports_and_builds() -> None:
    script = runs(load("weekly.yml")["jobs"]["collect"])
    for fragment in (
        "python -m supermercado collect",
        "git add data/prices",
        "python -m supermercado issue-body",
        "gh issue create",
        "python -m supermercado build --out dist",
    ):
        assert fragment in script


def test_deploy_waits_for_collect() -> None:
    assert load("weekly.yml")["jobs"]["deploy"]["needs"] == "collect"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pipeline/test_report.py tests/test_workflows.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_issue_body'` and `FileNotFoundError` for `weekly.yml`.

- [ ] **Step 3: Implement `render_issue_body` and the CLI command**

Append to `src/supermercado/pipeline/report.py` (add `from collections.abc import Mapping` to the imports):

```python
def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")[:300]


def render_issue_body(report: Mapping[str, Any]) -> str:
    failures = report.get("failures") or []
    alerts = report.get("alerts") or []
    if not failures and not alerts:
        return ""
    lines = [f"## Weekly collection {report.get('week', '?')}", ""]
    if failures:
        lines += [
            "### Store failures",
            "",
            "| Store | Error class | Time (UTC) | Message |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {f['store']} | `{f['error_class']}` | {f['at']} | {_cell(f['message'])} |"
            for f in failures
        ]
        lines += [
            "",
            "Manual fallback from a residential IP: "
            "`uv run python -m supermercado collect --store <id>`, then commit `data/prices/`.",
            "",
        ]
    if alerts:
        lines += ["### Size changes (possible shrinkflation)", "", "| Store | Item | Detail |", "|---|---|---|"]
        lines += [f"| {a['store']} | {a['item_id']} | {_cell(a['message'])} |" for a in alerts]
        lines += ["", "Confirm the product and update `size` in `config/matches.yaml`."]
    return "\n".join(lines).rstrip() + "\n"
```

In `src/supermercado/cli.py`: add `from supermercado.pipeline.report import render_issue_body` (next to `report_to_dict`), add to `_parser()`:

```python
    issue_cmd = sub.add_parser("issue-body", help="print the failure issue body for a report")
    issue_cmd.add_argument("--report", type=Path, default=Path("build/report.json"))
```

add the handler:

```python
def _cmd_issue_body(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    sys.stdout.write(render_issue_body(report))
    return 0
```

and register `"issue-body": _cmd_issue_body` in `COMMANDS`.

- [ ] **Step 4: Write the workflow**

`.github/workflows/weekly.yml`:

```yaml
name: weekly

on:
  schedule:
    # 06:00 America/Santiago during summer time (UTC-3); 05:00 local in winter (UTC-4).
    - cron: "0 9 * * 1"
  workflow_dispatch:

permissions:
  contents: write
  issues: write
  pages: write
  id-token: write

concurrency:
  group: weekly
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - run: uv sync --locked

      - name: Collect prices
        run: uv run python -m supermercado collect --report build/report.json

      - name: Commit snapshot
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/prices
          if ! git diff --cached --quiet; then
            git commit -m "chore(data): weekly price snapshot"
            git push
          fi

      - name: Open or update the failure issue
        if: always()
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          [ -f build/report.json ] || exit 0
          body="$(uv run python -m supermercado issue-body --report build/report.json)"
          [ -n "$body" ] || exit 0
          gh label create weekly-collect --color B60205 --force
          number="$(gh issue list --label weekly-collect --state open --json number --jq '.[0].number')"
          if [ -n "$number" ]; then
            gh issue comment "$number" --body "$body"
          else
            gh issue create --title "Weekly collection problems" --label weekly-collect --body "$body"
          fi

      - name: Build site
        run: uv run python -m supermercado build --out dist

      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist

  deploy:
    needs: collect
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 6: Report the one-time repository settings**

No file changes. Include these manual steps in your task report for the human: (1) Settings → Pages → Source: **GitHub Actions**; (2) Settings → Actions → General → Workflow permissions: **Read and write**, and tick **Allow GitHub Actions to create and approve pull requests** (needed by Task 15); (3) after the first push, run the `weekly` workflow once from the Actions tab (`workflow_dispatch`) to verify the deploy.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/weekly.yml src/supermercado/pipeline/report.py src/supermercado/cli.py tests/pipeline/test_report.py tests/test_workflows.py
git commit -m "ci: add weekly collect, failure issue and GitHub Pages deploy workflow"
```

---

### Task 10: Santa Isabel adapter

**Files:**
- Create: `src/supermercado/stores/santa_isabel.py`
- Create: `tests/fixtures/santa_isabel/plp_search.json`
- Modify: `src/supermercado/stores/__init__.py` (register), `config/stores.yaml` (`santa_isabel.enabled: true`)
- Test: `tests/stores/test_santa_isabel.py`

**Interfaces:**
- Consumes: `CencosudAdapter`, `parse_plp` (Task 6); test helpers (Tasks 4–5).
- Produces: `supermercado.stores.santa_isabel.SantaIsabelAdapter(CencosudAdapter)` with `store_id = "santa_isabel"`, `site_url = "https://www.santaisabel.cl"`; registry entry `"santa_isabel"`. `store_ref` is required (default `pedrofontova`).

- [ ] **Step 1: Write the fixture**

`tests/fixtures/santa_isabel/plp_search.json`:

```json
{
  "products": [
    {
      "productId": "21800",
      "slug": "leche-entera-soprole-1-l",
      "brand": "Soprole",
      "items": [
        {
          "skuId": "21810",
          "name": "Leche Entera Soprole 1 L",
          "measurementUnit": "un",
          "unitMultiplier": 1,
          "price": 1090,
          "listPrice": 1090,
          "ppumPrice": 1090,
          "ppumMeasurementUnit": "l",
          "stock": true,
          "promotions": []
        }
      ]
    },
    {
      "productId": "33000",
      "slug": "lavalozas-quix-limon-500-ml",
      "brand": "Quix",
      "items": [
        {
          "skuId": "33001",
          "name": "Lavalozas Quix Limón 500 ml",
          "measurementUnit": "un",
          "unitMultiplier": 1,
          "price": 1490,
          "listPrice": 1890,
          "ppumPrice": 2980,
          "ppumMeasurementUnit": "l",
          "stock": true,
          "promotions": [{"name": "TCENCO OFERTA - 1290"}]
        }
      ]
    }
  ],
  "results": 2
}
```

- [ ] **Step 2: Write the failing tests**

`tests/stores/test_santa_isabel.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stores/test_santa_isabel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.stores.santa_isabel'`.

- [ ] **Step 4: Implement and register**

`src/supermercado/stores/santa_isabel.py`:

```python
"""Santa Isabel adapter (Cencosud BFF; `store` is mandatory in the request body)."""

from supermercado.stores.cencosud import CencosudAdapter


class SantaIsabelAdapter(CencosudAdapter):
    store_id = "santa_isabel"
    site_url = "https://www.santaisabel.cl"
```

In `src/supermercado/stores/__init__.py` add `from supermercado.stores.santa_isabel import SantaIsabelAdapter` and this `FACTORIES` entry:

```python
    "santa_isabel": lambda client, store, app: SantaIsabelAdapter(client, store),
```

In `config/stores.yaml`, set `santa_isabel.enabled: true`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS (recorded test skipped).

- [ ] **Step 6: Record the real response (requires a residential IP; skip and report if no network)**

Run: `uv run python scripts/record_fixtures.py santa_isabel --query "leche entera 1 l"`
Then: `uv run pytest tests/stores/test_santa_isabel.py -v`
Expected: `test_recorded_search_parses` PASSES.

- [ ] **Step 7: Commit**

```bash
git add src/supermercado/stores config/stores.yaml tests/fixtures/santa_isabel tests/stores/test_santa_isabel.py
git commit -m "feat(stores): add Santa Isabel adapter"
```

---

### Task 11: Tottus adapter

**Files:**
- Create: `src/supermercado/stores/tottus.py`
- Create: `tests/fixtures/tottus/search.json`
- Modify: `src/supermercado/stores/__init__.py`, `config/stores.yaml` (`tottus.enabled: true`)
- Test: `tests/stores/test_tottus.py`

**Interfaces:**
- Consumes: `HttpClient`, `RawResponse`, `ResponseShapeError` (Task 5); `parse_size`, `parse_clp` (Task 1); `StoreConfig` (Task 4).
- Produces: `supermercado.stores.tottus`: `SEARCH_PATH = "/s/browse/v1/search/cl"`, `parse_search(payload: Any) -> list[Listing]`, `TottusAdapter(client, config)` with `store_id = "tottus"`, `supports_search = True`, `search`, `fetch` (one search per SKU, `Ntt=<sku>`, filtered by `skuId`), `raw_search`, `raw_fetch`. When `store_ref` is set it is sent as the `politicalId` query parameter.
- Price mapping: `internetPrice` is the current online price; a crossed `normalPrice` is the regular price (then `internetPrice` is the unconditional promo); `cmrPrice` is the card price. Prices arrive as lists of strings such as `["1.890"]`.

- [ ] **Step 1: Write the fixture (mirrors the real `data.results[]` shape)**

`tests/fixtures/tottus/search.json`:

```json
{
  "data": {
    "results": [
      {
        "productId": "110609847",
        "skuId": "110609848",
        "displayName": "Arroz Tucapel G2 Grano Largo Ancho 1 Kg",
        "url": "https://www.tottus.cl/tottus-cl/articulo/110609847/arroz-g-2-gran-selec-poli-1-kl-tucapel",
        "brand": "TUCAPEL",
        "measurements": {"format": "1 KG", "unit": "UN"},
        "prices": [
          {"type": "internetPrice", "crossed": false, "price": ["1.890"],
           "pum": {"label": "KG", "type": "pum", "price": ["1.890"]}}
        ]
      },
      {
        "productId": "110607000",
        "skuId": "110607001",
        "displayName": "Arroz American Thai Grano Largo G2 Bonanza 1 Kg",
        "url": "https://www.tottus.cl/tottus-cl/articulo/110607000/arroz-bonanza-1-kg",
        "brand": "BONANZA",
        "measurements": {"format": "1 KG", "unit": "UN"},
        "prices": [
          {"type": "internetPrice", "crossed": false, "price": ["1.350"],
           "pum": {"label": "KG", "type": "pum", "price": ["1.350"]}},
          {"type": "normalPrice", "crossed": true, "price": ["1.590"]},
          {"type": "cmrPrice", "crossed": false, "price": ["1.190"]}
        ]
      },
      {
        "productId": "20000",
        "skuId": "20001",
        "displayName": "Posta Negra Granel",
        "url": "https://www.tottus.cl/tottus-cl/articulo/20000/posta-negra-granel",
        "brand": "TOTTUS",
        "measurements": {"format": "", "unit": "KG"},
        "prices": [{"type": "internetPrice", "crossed": false, "price": ["9.990"]}]
      }
    ]
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/stores/test_tottus.py`:

```python
import json

import pytest
from factories import make_store_config
from fakes import FIXTURES, FakeTransport, assert_recorded_listings, fixture_response, make_client, ok

from supermercado.domain.models import SoldBy, Unit
from supermercado.stores.base import ResponseShapeError
from supermercado.stores.tottus import TottusAdapter, parse_search


def make_adapter(*responses, **overrides):
    transport = FakeTransport(list(responses))
    settings = {"base_url": "https://www.tottus.cl"}
    settings.update(overrides)
    return TottusAdapter(make_client(transport), make_store_config("Tottus", **settings)), transport


def search_fixture():
    return fixture_response("tottus", "search.json")


def test_search_calls_the_json_endpoint() -> None:
    adapter, transport = make_adapter(search_fixture())
    adapter.search("arroz grado 2")
    call = transport.calls[0]
    assert (call["method"], call["url"]) == ("GET", "https://www.tottus.cl/s/browse/v1/search/cl")
    assert call["params"] == {"page": 1, "Ntt": "arroz grado 2"}


def test_store_ref_is_sent_as_political_id() -> None:
    adapter, transport = make_adapter(search_fixture(), store_ref="13")
    adapter.search("arroz")
    assert transport.calls[0]["params"]["politicalId"] == "13"


def test_parses_string_prices_and_sizes() -> None:
    adapter, _ = make_adapter(search_fixture())
    rice = adapter.search("arroz")[0]
    assert rice.sku == "110609848"
    assert (rice.price, rice.promo_price, rice.card_price) == (1890, None, None)
    assert (rice.size, rice.unit, rice.sold_by) == (1.0, Unit.KG, SoldBy.UNIT)
    assert rice.store_unit_price == 1890
    assert rice.url.startswith("https://www.tottus.cl/tottus-cl/articulo/110609847/")


def test_crossed_normal_price_is_regular_and_cmr_is_card() -> None:
    adapter, _ = make_adapter(search_fixture())
    promo = adapter.search("arroz")[1]
    assert (promo.price, promo.promo_price, promo.card_price) == (1590, 1350, 1190)


def test_kg_products_are_sold_by_weight() -> None:
    adapter, _ = make_adapter(search_fixture())
    posta = adapter.search("posta")[2]
    assert (posta.sold_by, posta.size, posta.unit, posta.price) == (SoldBy.WEIGHT, 1.0, Unit.KG, 9990)


def test_fetch_searches_each_sku_and_keeps_exact_matches() -> None:
    adapter, transport = make_adapter(search_fixture(), search_fixture())
    listings = adapter.fetch(["110609848", "20001"])
    assert [listing.sku for listing in listings] == ["110609848", "20001"]
    assert [call["params"]["Ntt"] for call in transport.calls] == ["110609848", "20001"]


def test_missing_results_raise_shape_error() -> None:
    adapter, _ = make_adapter(ok('{"data": {}}'))
    with pytest.raises(ResponseShapeError):
        adapter.search("arroz")


RECORDED = FIXTURES / "tottus" / "recorded_search.json"


@pytest.mark.skipif(not RECORDED.exists(), reason="recorded fixture not captured yet")
def test_recorded_search_parses() -> None:
    assert_recorded_listings(parse_search(json.loads(RECORDED.read_text(encoding="utf-8"))))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stores/test_tottus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.stores.tottus'`.

- [ ] **Step 4: Implement and register**

`src/supermercado/stores/tottus.py`:

```python
"""Tottus adapter: public search JSON (the HTML is behind Cloudflare, never use it)."""

from __future__ import annotations

from typing import Any

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import parse_clp, parse_size
from supermercado.stores.base import HttpClient, RawResponse, ResponseShapeError

SEARCH_PATH = "/s/browse/v1/search/cl"


def _amount(entry: dict[str, Any] | None) -> int | None:
    if not entry:
        return None
    raw = entry.get("price")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw in (None, ""):
        return None
    try:
        value = parse_clp(raw)
    except ValueError:
        return None
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
        card_price=card if card and (public is None or card < public) else None,
        store_unit_price=_amount((prices.get("internetPrice") or {}).get("pum")),
        available=True,  # the search endpoint only lists purchasable products
    )


def parse_search(payload: Any) -> list[Listing]:
    try:
        results = payload["data"]["results"]
    except (KeyError, TypeError) as exc:
        raise ResponseShapeError("Tottus search response has no data.results") from exc
    if not isinstance(results, list):
        raise ResponseShapeError("Tottus data.results is not a list")
    return [_listing(product) for product in results if product.get("skuId")]


class TottusAdapter:
    store_id = "tottus"
    supports_search = True

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
        found = []
        for sku in dict.fromkeys(skus):
            found.extend(listing for listing in self.search(sku) if listing.sku == sku)
        return found
```

In `src/supermercado/stores/__init__.py` add `from supermercado.stores.tottus import TottusAdapter` and:

```python
    "tottus": lambda client, store, app: TottusAdapter(client, store),
```

In `config/stores.yaml`, set `tottus.enabled: true`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 6: Record real responses and verify fetch-by-SKU (residential IP; skip and report if no network)**

Run: `uv run python scripts/record_fixtures.py tottus --query "arroz grado 2" --sku 110609848`
Then open `tests/fixtures/tottus/recorded_fetch.json` with `bat` and confirm a result with `"skuId": "110609848"` exists. If it does not, searching by SKU is not supported: report it as a blocker for Tottus fetch (do not invent another endpoint). Also check the recorded search for a `cmrPrice` entry name; if card prices use a different `type`, update `_listing` and the fixture to the real name. Run `uv run pytest tests/stores/test_tottus.py -v`; the recorded test PASSES.

- [ ] **Step 7: Commit**

```bash
git add src/supermercado/stores config/stores.yaml tests/fixtures/tottus tests/stores/test_tottus.py
git commit -m "feat(stores): add Tottus adapter over the search JSON endpoint"
```

---

### Task 12: aCuenta adapter (Instaleap GraphQL)

**Files:**
- Create: `src/supermercado/stores/acuenta.py`
- Create: `tests/fixtures/acuenta/search.json`, `tests/fixtures/acuenta/by_sku.json`
- Modify: `src/supermercado/stores/__init__.py`, `config/stores.yaml` (`acuenta.enabled: true`)
- Test: `tests/stores/test_acuenta.py`

**Interfaces:**
- Consumes: `HttpClient`, errors (Task 5); `normalize`, `parse_size`, `UnknownUnitError` (Task 1); `StoreConfig` (Task 4).
- Produces: `supermercado.stores.acuenta`: `CLIENT_ID = "SUPER_BODEGA"`, `SEARCH_QUERY`, `SKU_QUERY`, `parse_products(payload: Any, field: str) -> list[Listing]`, `AcuentaAdapter(client, config)` with `store_id = "acuenta"`, `supports_search = True`, `page_size = 40`, `batch_size = 50`. `store_ref` (`storeReference`, default `"580"`) is required. Promotions count as `promo_price` only when active and the condition quantity is 1 (multi-buy offers are conditional and ignored). Products whose `unit` is `Kg` are sold by weight with size 1 kg.

- [ ] **Step 1: Write the fixtures**

`tests/fixtures/acuenta/search.json`:

```json
{
  "data": {
    "searchProducts": {
      "products": [
        {"name": "Arroz Grado 2 Tucapel 1 Kg", "sku": "7801420210130", "brand": "Tucapel", "price": 1650,
         "unit": "Un", "subUnit": "kg", "subQty": 1, "clickMultiplier": 1, "stock": 120, "isAvailable": true,
         "promotion": null},
        {"name": "Arroz Grado 2 Acuenta 1 Kg", "sku": "7800000000011", "brand": "Acuenta", "price": 1290,
         "unit": "Un", "subUnit": null, "subQty": null, "clickMultiplier": 1, "stock": 40, "isAvailable": true,
         "promotion": {"type": "DISCOUNT", "isActive": true, "conditions": [{"price": 1190, "quantity": 1}]}},
        {"name": "Fideos Spaghetti 5 400 g", "sku": "7800000000028", "brand": "Carozzi", "price": 990,
         "unit": "Un", "subUnit": "g", "subQty": 400, "clickMultiplier": 1, "stock": 0, "isAvailable": false,
         "promotion": {"type": "MXN", "isActive": true, "conditions": [{"price": 1600, "quantity": 2}]}},
        {"name": "Trutro Entero de Pollo", "sku": "2000000000017", "brand": null, "price": 2990,
         "unit": "Kg", "subUnit": null, "subQty": null, "clickMultiplier": 0.5, "stock": 15, "isAvailable": true,
         "promotion": null}
      ]
    }
  }
}
```

`tests/fixtures/acuenta/by_sku.json`:

```json
{
  "data": {
    "getProductsBySKU": [
      {"name": "Arroz Grado 2 Tucapel 1 Kg", "sku": "7801420210130", "brand": "Tucapel", "price": 1650,
       "unit": "Un", "subUnit": "kg", "subQty": 1, "clickMultiplier": 1, "stock": 120, "isAvailable": true,
       "promotion": null},
      {"name": "Azúcar Iansa 1 Kg", "sku": "7801111111111", "brand": "Iansa", "price": 1250,
       "unit": "Un", "subUnit": "kg", "subQty": 1, "clickMultiplier": 1, "stock": 10, "isAvailable": true,
       "promotion": null}
    ]
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/stores/test_acuenta.py`:

```python
import json

import pytest
from factories import make_store_config
from fakes import FIXTURES, FakeTransport, assert_recorded_listings, fixture_response, make_client, ok

from supermercado.domain.models import SoldBy, Unit
from supermercado.stores.acuenta import AcuentaAdapter, parse_products
from supermercado.stores.base import AdapterError, ResponseShapeError

API = "https://nextgentheadless.instaleap.io/api/v3"


def make_adapter(*responses, **overrides):
    transport = FakeTransport(list(responses))
    settings = {"base_url": API, "store_ref": "580"}
    settings.update(overrides)
    return AcuentaAdapter(make_client(transport), make_store_config("aCuenta", **settings)), transport


def test_search_posts_the_graphql_query() -> None:
    adapter, transport = make_adapter(fixture_response("acuenta", "search.json"))
    adapter.search("arroz grado 2")
    call = transport.calls[0]
    assert (call["method"], call["url"]) == ("POST", API)
    assert "searchProducts(" in call["json"]["query"]
    assert call["json"]["variables"]["input"] == {
        "clientId": "SUPER_BODEGA",
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
    assert (chicken.sold_by, chicken.size, chicken.unit, chicken.multiplier) == (SoldBy.WEIGHT, 1.0, Unit.KG, 0.5)


def test_fetch_uses_get_products_by_sku_and_filters() -> None:
    adapter, transport = make_adapter(fixture_response("acuenta", "by_sku.json"))
    listings = adapter.fetch(["7801420210130"])
    assert [listing.sku for listing in listings] == ["7801420210130"]
    call = transport.calls[0]
    assert "getProductsBySKU(" in call["json"]["query"]
    assert call["json"]["variables"]["input"]["skus"] == ["7801420210130"]


def test_graphql_errors_raise_shape_error() -> None:
    adapter, _ = make_adapter(ok('{"errors": [{"message": "Unknown field"}], "data": null}'))
    with pytest.raises(ResponseShapeError, match="Unknown field"):
        adapter.search("arroz")


def test_store_reference_is_required() -> None:
    adapter, transport = make_adapter(store_ref=None)
    with pytest.raises(AdapterError, match="store_ref"):
        adapter.search("arroz")
    assert transport.calls == []


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stores/test_acuenta.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.stores.acuenta'`.

- [ ] **Step 4: Implement and register**

`src/supermercado/stores/acuenta.py`:

```python
"""aCuenta adapter: Instaleap headless GraphQL API (clientId SUPER_BODEGA)."""

from __future__ import annotations

from typing import Any

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import UnknownUnitError, normalize, parse_size
from supermercado.stores.base import AdapterError, HttpClient, RawResponse, ResponseShapeError

CLIENT_ID = "SUPER_BODEGA"
SITE_URL = "https://www.acuenta.cl"
_FIELDS = (
    "name sku brand price unit subUnit subQty clickMultiplier stock isAvailable "
    "promotion { type isActive conditions { price quantity } }"
)
SEARCH_QUERY = (
    "query Search($input: SearchProductsInput!) "
    "{ searchProducts(searchProductsInput: $input) { products { " + _FIELDS + " } } }"
)
SKU_QUERY = (
    "query BySku($input: GetProductsBySKUInput!) "
    "{ getProductsBySKU(getProductsBySKUInput: $input) { " + _FIELDS + " } }"
)


def _positive(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(round(value)) if value > 0 else None


def _promo(product: dict[str, Any], price: int | None) -> int | None:
    promotion = product.get("promotion") or {}
    if price is None or not promotion.get("isActive"):
        return None
    conditions = promotion.get("conditions") or []
    if isinstance(conditions, dict):
        conditions = [conditions]
    for condition in conditions:
        amount = _positive(condition.get("price"))
        if condition.get("quantity") in (None, 1) and amount is not None and amount < price:
            return amount
    return None


def _size(product: dict[str, Any]) -> tuple[float, Unit] | None:
    parsed = parse_size(str(product.get("name") or ""))
    if parsed is None and product.get("subUnit") and product.get("subQty"):
        try:
            parsed = normalize(float(product["subQty"]), str(product["subUnit"]))
        except (UnknownUnitError, ValueError):
            parsed = None
    return parsed


def _listing(product: dict[str, Any]) -> Listing:
    price = _positive(product.get("price"))
    weighted = str(product.get("unit") or "").strip().lower() == "kg"
    if weighted:
        size, unit = 1.0, Unit.KG
    else:
        size, unit = _size(product) or (None, None)
    stock = product.get("stock") or 0
    return Listing(
        sku=str(product["sku"]),
        name=str(product.get("name") or ""),
        brand=product.get("brand"),
        url=None,
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        multiplier=float(product.get("clickMultiplier") or 1),
        price=price,
        promo_price=_promo(product, price),
        available=bool(product.get("isAvailable")) and stock > 0,
    )


def parse_products(payload: Any, field: str) -> list[Listing]:
    if not isinstance(payload, dict):
        raise ResponseShapeError("aCuenta response is not a JSON object")
    if payload.get("errors"):
        raise ResponseShapeError(f"aCuenta GraphQL errors: {str(payload['errors'])[:300]}")
    data = (payload.get("data") or {}).get(field)
    if isinstance(data, dict):
        data = data.get("products")
    if not isinstance(data, list):
        raise ResponseShapeError(f"aCuenta response has no {field} products")
    return [_listing(product) for product in data if product.get("sku")]


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
            {
                "clientId": CLIENT_ID,
                "storeReference": self._store_ref(),
                "currentPage": 1,
                "pageSize": self.page_size,
                "search": [{"query": query}],
            },
        )

    def raw_fetch(self, sku: str) -> RawResponse:
        return self._sku_request([sku])

    def search(self, query: str) -> list[Listing]:
        return parse_products(self.raw_search(query).json(), "searchProducts")

    def fetch(self, skus: list[str]) -> list[Listing]:
        wanted = list(dict.fromkeys(skus))
        found: list[Listing] = []
        for start in range(0, len(wanted), self.batch_size):
            chunk = wanted[start : start + self.batch_size]
            listings = parse_products(self._sku_request(chunk).json(), "getProductsBySKU")
            found.extend(listing for listing in listings if listing.sku in chunk)
        return found

    def _sku_request(self, skus: list[str]) -> RawResponse:
        return self._post(
            SKU_QUERY, {"clientId": CLIENT_ID, "storeReference": self._store_ref(), "skus": skus}
        )

    def _store_ref(self) -> str:
        if not self._config.store_ref:
            raise AdapterError("acuenta: store_ref (storeReference) is required in config/stores.yaml")
        return self._config.store_ref

    def _post(self, query: str, variables: dict[str, Any]) -> RawResponse:
        return self._client.request(
            "POST",
            self._config.base_url,
            headers={"Content-Type": "application/json", "Origin": SITE_URL, "Referer": f"{SITE_URL}/"},
            json={"query": query, "variables": {"input": variables}},
        )
```

In `src/supermercado/stores/__init__.py` add `from supermercado.stores.acuenta import AcuentaAdapter` and:

```python
    "acuenta": lambda client, store, app: AcuentaAdapter(client, store),
```

In `config/stores.yaml`, set `acuenta.enabled: true`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 6: Record and verify the SKU query (residential IP; skip and report if no network)**

Run: `uv run python scripts/record_fixtures.py acuenta --query "arroz grado 2"`, pick one `sku` from `tests/fixtures/acuenta/recorded_search.json`, then `uv run python scripts/record_fixtures.py acuenta --sku <that sku>`.
Check `recorded_fetch.json`: if it contains `"errors"` (for example the input type is not named `GetProductsBySKUInput`, or the field returns `{products: [...]}`), fix `SKU_QUERY` to the name the error message suggests and re-record; `parse_products` already accepts either a list or an object with `products`. Run `uv run pytest tests/stores/test_acuenta.py -v`; both recorded tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/supermercado/stores config/stores.yaml tests/fixtures/acuenta tests/stores/test_acuenta.py
git commit -m "feat(stores): add aCuenta adapter over the Instaleap GraphQL API"
```

---

### Task 13: Unimarc adapter

**Files:**
- Create: `src/supermercado/stores/unimarc.py`
- Create: `tests/fixtures/unimarc/search.json`
- Modify: `src/supermercado/stores/__init__.py`, `config/stores.yaml` (`unimarc.enabled: true`)
- Test: `tests/stores/test_unimarc.py`

**Interfaces:**
- Consumes: `HttpClient`, errors (Task 5); `parse_size`, `parse_clp` (Task 1); `StoreConfig` (Task 4).
- Produces: `supermercado.stores.unimarc`: `SEARCH_PATH = "/catalog/product/search"`, `CHROME_USER_AGENT`, `parse_search(payload: Any) -> list[Listing]`, `UnimarcAdapter(client, config)` with `store_id = "unimarc"`, `supports_search = True`, `page_size = 40`; `fetch` searches each SKU and keeps exact `itemId` matches.
- Price mapping (conservative, per spec "distinguishes the club price from listPrice"): `listPrice` is the regular price; when `price < listPrice` the lower `price` is stored as `card_price` (club), never as `promo_price`. `ppum` strings such as `"$1.790 x Kg"` become `store_unit_price`.

- [ ] **Step 1: Write the fixture**

`tests/fixtures/unimarc/search.json`:

```json
{
  "availableProducts": [
    {
      "item": {"itemId": "5000", "nameComplete": "Arroz Grado 2 Tucapel 1 kg", "name": "Arroz Grado 2",
               "brand": "Tucapel", "measurementUnit": "un", "unitMultiplier": 1,
               "netContent": "1", "netContentLevelSmall": "kg",
               "detailUrl": "/product/arroz-grado-2-tucapel-1-kg"},
      "price": {"price": "$1.790", "listPrice": "$1.990", "ppum": "$1.790 x Kg", "availableQuantity": 50}
    },
    {
      "item": {"itemId": "5001", "nameComplete": "Arroz Grado 2 Unimarc 1 kg", "name": "Arroz Grado 2",
               "brand": "Unimarc", "measurementUnit": "un", "unitMultiplier": 1},
      "price": {"price": "$1.390", "listPrice": "$1.390", "ppum": "$1.390 x Kg", "availableQuantity": 0}
    },
    {
      "item": {"itemId": "5002", "nameComplete": "Posta Rosada Granel", "brand": "Unimarc",
               "measurementUnit": "kg", "unitMultiplier": 1},
      "price": {"price": 8990, "listPrice": 8990, "ppum": "$8.990 x Kg", "availableQuantity": 10}
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

`tests/stores/test_unimarc.py`:

```python
import json

import pytest
from factories import make_store_config
from fakes import FIXTURES, FakeTransport, assert_recorded_listings, fixture_response, make_client, ok

from supermercado.domain.models import SoldBy, Unit
from supermercado.stores.base import ResponseShapeError
from supermercado.stores.unimarc import UnimarcAdapter, parse_search

API = "https://bff-unimarc-ecommerce.unimarc.cl"


def make_adapter(*responses):
    transport = FakeTransport(list(responses))
    config = make_store_config("Unimarc", base_url=API)
    return UnimarcAdapter(make_client(transport), config), transport


def search_fixture():
    return fixture_response("unimarc", "search.json")


def test_search_sends_required_headers_and_body() -> None:
    adapter, transport = make_adapter(search_fixture())
    adapter.search("arroz grado 2")
    call = transport.calls[0]
    assert (call["method"], call["url"]) == ("POST", f"{API}/catalog/product/search")
    assert {k: call["headers"][k] for k in ("channel", "source", "version")} == {
        "channel": "UNIMARC",
        "source": "web",
        "version": "1.0.0",
    }
    assert "Chrome/" in call["headers"]["User-Agent"]
    assert call["json"] == {"from": "0", "to": "39", "searching": "arroz grado 2"}


def test_lower_price_is_club_price_not_promo() -> None:
    adapter, _ = make_adapter(search_fixture())
    rice = adapter.search("arroz")[0]
    assert (rice.sku, rice.price, rice.promo_price, rice.card_price) == ("5000", 1990, None, 1790)
    assert rice.store_unit_price == 1790
    assert (rice.size, rice.unit) == (1.0, Unit.KG)
    assert rice.url == "https://www.unimarc.cl/product/arroz-grado-2-tucapel-1-kg"


def test_zero_quantity_is_unavailable() -> None:
    adapter, _ = make_adapter(search_fixture())
    own = adapter.search("arroz")[1]
    assert (own.price, own.card_price, own.available, own.url) == (1390, None, False, None)


def test_kg_items_are_sold_by_weight_and_accept_numeric_prices() -> None:
    adapter, _ = make_adapter(search_fixture())
    posta = adapter.search("posta")[2]
    assert (posta.sold_by, posta.size, posta.unit, posta.price) == (SoldBy.WEIGHT, 1.0, Unit.KG, 8990)


def test_fetch_keeps_exact_item_ids() -> None:
    adapter, transport = make_adapter(search_fixture())
    assert [listing.sku for listing in adapter.fetch(["5002"])] == ["5002"]
    assert transport.calls[0]["json"]["searching"] == "5002"


def test_missing_products_raise_shape_error() -> None:
    adapter, _ = make_adapter(ok('{"message": "error"}'))
    with pytest.raises(ResponseShapeError):
        adapter.search("arroz")


RECORDED = FIXTURES / "unimarc" / "recorded_search.json"


@pytest.mark.skipif(not RECORDED.exists(), reason="recorded fixture not captured yet")
def test_recorded_search_parses() -> None:
    assert_recorded_listings(parse_search(json.loads(RECORDED.read_text(encoding="utf-8"))))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stores/test_unimarc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.stores.unimarc'`.

- [ ] **Step 4: Implement and register**

`src/supermercado/stores/unimarc.py`:

```python
"""Unimarc adapter: SMU BFF search (needs channel/source/version headers and a full Chrome UA)."""

from __future__ import annotations

from typing import Any

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import parse_clp, parse_size
from supermercado.stores.base import HttpClient, RawResponse, ResponseShapeError

SEARCH_PATH = "/catalog/product/search"
SITE_URL = "https://www.unimarc.cl"
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _amount(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        amount = parse_clp(value)
    except ValueError:
        return None
    return amount if amount > 0 else None


def _listing(entry: dict[str, Any]) -> Listing:
    item = entry.get("item") or {}
    price = entry.get("price") or {}
    current = _amount(price.get("price"))
    listed = _amount(price.get("listPrice"))
    regular = listed or current
    weighted = str(item.get("measurementUnit") or "").lower() == "kg"
    multiplier = float(item.get("unitMultiplier") or 1)
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
        url=f"{SITE_URL}{detail}" if detail else None,
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        multiplier=multiplier,
        price=regular,
        card_price=current if current and listed and current < listed else None,
        store_unit_price=_amount(price.get("ppum")),
        available=float(price.get("availableQuantity") or 0) > 0,
    )


def parse_search(payload: Any) -> list[Listing]:
    if not isinstance(payload, dict) or not isinstance(payload.get("availableProducts"), list):
        raise ResponseShapeError("Unimarc search response has no 'availableProducts' list")
    return [
        _listing(entry)
        for entry in payload["availableProducts"]
        if (entry.get("item") or {}).get("itemId")
    ]


class UnimarcAdapter:
    store_id = "unimarc"
    supports_search = True
    page_size = 40

    def __init__(self, client: HttpClient, config: StoreConfig) -> None:
        self._client = client
        self._config = config

    def raw_search(self, query: str) -> RawResponse:
        return self._client.request(
            "POST",
            f"{self._config.base_url}{SEARCH_PATH}",
            headers={
                "channel": "UNIMARC",
                "source": "web",
                "version": "1.0.0",
                "User-Agent": CHROME_USER_AGENT,
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
        found = []
        for sku in dict.fromkeys(skus):
            found.extend(listing for listing in self.search(sku) if listing.sku == sku)
        return found
```

In `src/supermercado/stores/__init__.py` add `from supermercado.stores.unimarc import UnimarcAdapter` and:

```python
    "unimarc": lambda client, store, app: UnimarcAdapter(client, store),
```

In `config/stores.yaml`, set `unimarc.enabled: true`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 6: Record and verify (residential IP; skip and report if no network)**

Run: `uv run python scripts/record_fixtures.py unimarc --query "arroz grado 2"`, take one `itemId` from the file, then `uv run python scripts/record_fixtures.py unimarc --sku <itemId>`.
Verify in `recorded_fetch.json` that searching by `itemId` returns that item; if not, report it as a blocker for Unimarc fetch. Also confirm the real price field types and whether a product URL field exists (`detailUrl` or similar); adjust `_listing` and the hand-written fixture to the real names if they differ. Run `uv run pytest tests/stores/test_unimarc.py -v`; the recorded test PASSES.

- [ ] **Step 7: Commit**

```bash
git add src/supermercado/stores config/stores.yaml tests/fixtures/unimarc tests/stores/test_unimarc.py
git commit -m "feat(stores): add Unimarc adapter over the SMU BFF"
```

---

### Task 14: Lider adapter (product pages only)

**Files:**
- Create: `src/supermercado/stores/lider.py`
- Create: `tests/fixtures/lider/product_page.html`, `tests/fixtures/lider/product_page_weight.html`
- Modify: `src/supermercado/stores/__init__.py`, `config/stores.yaml` (`lider.enabled: true`)
- Test: `tests/stores/test_lider.py`

**Interfaces:**
- Consumes: `HttpClient`, `HttpError`, `BlockedError`, `ResponseShapeError`, `AdapterError` (Task 5); `parse_size` (Task 1); `StoreConfig`, `AppConfig` (Task 4); `build_adapters` (Task 6).
- Produces: `supermercado.stores.lider`: `SITE_URL = "https://super.lider.cl"`, `parse_product_page(html: str) -> Listing`, `LiderAdapter(client, config, url_by_sku: Mapping[str, str])` with public `url_by_sku`, `store_id = "lider"`, `supports_search = False`; `search` raises `NotImplementedError` (robots.txt disallows `/search*`); `fetch` GETs each product page with `config.cookies`, skips HTTP 404, raises `BlockedError` on PerimeterX pages. Registry builds `url_by_sku` from Lider matches plus `smoke_sku → smoke_url`.
- Price mapping: `wasPrice > currentPrice` ⇒ `price=wasPrice`, `promo_price=currentPrice`; otherwise `price=currentPrice`. `salesUnitType == "WEIGHT"` ⇒ sold by weight, size 1 kg (assumes `currentPrice` is per kg; verified in Step 6), `multiplier = averageWeight`.

- [ ] **Step 1: Write the fixtures (structure of the real `__NEXT_DATA__`)**

`tests/fixtures/lider/product_page.html`:

```html
<!doctype html>
<html><head><title>Lider</title></head><body>
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"initialData":{"data":{"product":{"usItemId":"00780142021013","name":"Arroz Grado 2 Grano Largo Bolsa, 1 kg","brand":"Tucapel","canonicalUrl":"/ip/arroz-y-legumbres/00780142021013","availabilityStatus":"IN_STOCK","salesUnitType":null,"averageWeight":null,"priceInfo":{"currentPrice":{"price":1190,"priceString":"$1.190"},"wasPrice":{"price":1790,"priceString":"$1.790"}}}}}}}}</script>
</body></html>
```

`tests/fixtures/lider/product_page_weight.html`:

```html
<!doctype html>
<html><head><title>Lider</title></head><body>
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"initialData":{"data":{"product":{"usItemId":"00000000123456","name":"Trutro Entero de Pollo Granel","brand":"Lider","canonicalUrl":"/ip/pollo/00000000123456","availabilityStatus":"OUT_OF_STOCK","salesUnitType":"WEIGHT","averageWeight":1.2,"priceInfo":{"currentPrice":{"price":3990,"priceString":"$3.990"},"wasPrice":null}}}}}}}</script>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/stores/test_lider.py`:

```python
import pytest
from factories import make_item, make_match, make_store_config
from fakes import FIXTURES, FakeTransport, fixture_response, fixture_text, make_client, ok

from supermercado.config import AppConfig
from supermercado.domain.models import SoldBy, Unit
from supermercado.stores import build_adapters
from supermercado.stores.base import AdapterError, BlockedError, RawResponse
from supermercado.stores.lider import LiderAdapter, parse_product_page

URL = "https://super.lider.cl/ip/arroz-y-legumbres/00780142021013"
COOKIES = {"walmart.nearestLatLng": "-33.4521,-70.6536"}


def make_adapter(*responses, urls=None):
    transport = FakeTransport(list(responses))
    config = make_store_config("Lider", base_url="https://super.lider.cl", cookies=COOKIES)
    adapter = LiderAdapter(make_client(transport), config, urls or {"00780142021013": URL})
    return adapter, transport


def test_fetch_gets_the_product_page_with_location_cookie() -> None:
    adapter, transport = make_adapter(fixture_response("lider", "product_page.html"))
    adapter.fetch(["00780142021013"])
    call = transport.calls[0]
    assert (call["method"], call["url"], call["cookies"]) == ("GET", URL, COOKIES)


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


def test_perimeterx_page_raises_blocked() -> None:
    adapter, _ = make_adapter(ok('<html><body><div id="px-captcha"></div></body></html>'))
    with pytest.raises(BlockedError):
        adapter.fetch(["00780142021013"])


def test_missing_page_is_skipped() -> None:
    urls = {"gone": "https://super.lider.cl/ip/x/gone", "00780142021013": URL}
    adapter, _ = make_adapter(RawResponse(404, ""), fixture_response("lider", "product_page.html"), urls=urls)
    assert [listing.sku for listing in adapter.fetch(["gone", "00780142021013"])] == ["00780142021013"]


def test_sku_without_url_is_an_error() -> None:
    adapter, transport = make_adapter()
    with pytest.raises(AdapterError, match="no product url"):
        adapter.fetch(["unknown"])
    assert transport.calls == []


def test_search_is_never_attempted() -> None:
    adapter, _ = make_adapter()
    assert adapter.supports_search is False
    with pytest.raises(NotImplementedError):
        adapter.search("arroz")


def test_registry_builds_urls_from_matches_and_smoke_settings() -> None:
    config = AppConfig(
        basket=[make_item()],
        stores={"lider": make_store_config("Lider", smoke_sku="S1", smoke_url="https://super.lider.cl/ip/x/S1")},
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/stores/test_lider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.stores.lider'`.

- [ ] **Step 4: Implement and register**

`src/supermercado/stores/lider.py`:

```python
"""Lider adapter: product pages only. robots.txt disallows /search*, so matches are manual."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from supermercado.config import StoreConfig
from supermercado.domain.models import Listing, SoldBy, Unit
from supermercado.domain.units import parse_size
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
_NEXT_DATA_RE = re.compile(r'<script[^>]*id="?__NEXT_DATA__"?[^>]*>(.*?)</script>', re.S)
_BLOCK_MARKERS = ("px-captcha", "/blocked?", "_pxAppId", "Access Denied")


def _price(block: Any) -> int | None:
    if not isinstance(block, dict):
        return None
    value = block.get("price")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(round(value))


def parse_product_page(html: str) -> Listing:
    match = _NEXT_DATA_RE.search(html)
    if match is None:
        if any(marker in html for marker in _BLOCK_MARKERS):
            raise BlockedError("lider: anti-bot (PerimeterX) page instead of the product")
        raise ResponseShapeError("lider: page has no __NEXT_DATA__ script")
    try:
        product = json.loads(match.group(1))["props"]["pageProps"]["initialData"]["data"]["product"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ResponseShapeError("lider: __NEXT_DATA__ has no product") from exc
    info = product.get("priceInfo") or {}
    current = _price(info.get("currentPrice"))
    was = _price(info.get("wasPrice"))
    on_sale = bool(was and current and was > current)
    weighted = product.get("salesUnitType") == "WEIGHT"
    name = str(product.get("name") or "")
    if weighted:
        size, unit = 1.0, Unit.KG
    else:
        size, unit = parse_size(name) or (None, None)
    canonical = product.get("canonicalUrl")
    return Listing(
        sku=str(product["usItemId"]),
        name=name,
        brand=product.get("brand"),
        url=f"{SITE_URL}{canonical}" if canonical else None,
        size=size,
        unit=unit,
        sold_by=SoldBy.WEIGHT if weighted else SoldBy.UNIT,
        multiplier=float(product.get("averageWeight") or 1.0),
        price=was if on_sale else current,
        promo_price=current if on_sale else None,
        available=product.get("availabilityStatus") == "IN_STOCK",
    )


class LiderAdapter:
    store_id = "lider"
    supports_search = False

    def __init__(self, client: HttpClient, config: StoreConfig, url_by_sku: Mapping[str, str]) -> None:
        self._client = client
        self._config = config
        self.url_by_sku = dict(url_by_sku)

    def search(self, query: str) -> list[Listing]:
        raise NotImplementedError("lider: search is disallowed by robots.txt; add matches manually")

    def raw_fetch(self, sku: str) -> RawResponse:
        url = self.url_by_sku.get(sku)
        if not url:
            raise AdapterError(f"lider: no product url for sku {sku}")
        return self._client.request(
            "GET",
            url,
            headers={"Accept": "text/html,application/xhtml+xml", "Accept-Language": "es-CL,es;q=0.9"},
            cookies=dict(self._config.cookies),
        )

    def fetch(self, skus: list[str]) -> list[Listing]:
        listings = []
        for sku in dict.fromkeys(skus):
            try:
                page = self.raw_fetch(sku)
            except HttpError as exc:
                if exc.status == 404:
                    log.warning("lider: product page for sku %s is gone (404)", sku)
                    continue
                raise
            listings.append(parse_product_page(page.text))
        return listings
```

In `src/supermercado/stores/__init__.py` add `from supermercado.stores.lider import LiderAdapter`, this helper above `FACTORIES`:

```python
def _lider_urls(store: StoreConfig, app: AppConfig) -> dict[str, str]:
    urls = {m.sku: m.url for m in app.matches_for_store("lider").values() if m.url}
    if store.smoke_sku and store.smoke_url:
        urls.setdefault(store.smoke_sku, store.smoke_url)
    return urls
```

and the entry:

```python
    "lider": lambda client, store, app: LiderAdapter(client, store, _lider_urls(store, app)),
```

In `config/stores.yaml`, set `lider.enabled: true`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 6: Record and verify weighted pricing (residential IP; skip and report if no network)**

Run: `uv run python scripts/record_fixtures.py lider --sku 00780142021013`
Expected: `tests/fixtures/lider/recorded_fetch.html` is written and `test_recorded_page_parses` PASSES. If the file is a PerimeterX page, the adapter will raise `BlockedError`; report it, delete the file, and do not commit it.
Then open one weighted product page in a browser (for example a "trutro entero" product) and compare the shown "$ x kg" price with `currentPrice.price` in its `__NEXT_DATA__`. If `currentPrice` is the price of one `averageWeight` piece instead of 1 kg, change the weighted branch to `size, unit = float(product.get("averageWeight") or 1.0), Unit.KG`, update `test_parses_weight_page` to expect `size == 1.2`, and rerun the tests.

- [ ] **Step 7: Commit**

```bash
git add src/supermercado/stores config/stores.yaml tests/fixtures/lider tests/stores/test_lider.py
git commit -m "feat(stores): add Lider product-page adapter"
```

---

### Task 15: Match proposals and the weekly proposal PR

**Files:**
- Create: `src/supermercado/domain/matching.py`, `src/supermercado/pipeline/propose.py`
- Modify: `src/supermercado/cli.py` (add `propose`), `.github/workflows/weekly.yml` (add `propose` job)
- Test: `tests/domain/test_matching.py`, `tests/pipeline/test_propose.py`, `tests/test_cli.py`, `tests/test_workflows.py`

**Interfaces:**
- Consumes: `BasketItem`, `Listing`, `Match` (Task 1); `effective_price` (Task 2); `compute_unit_price` (Task 1); `StoreFailure`, `iso_week` (Task 7); `FakeAdapter` (Task 7).
- Produces:
  - `supermercado.domain.matching`: `normalize_text(text: str) -> str`, `matches_rules(item: BasketItem, listing: Listing) -> bool`, `filter_candidates(item: BasketItem, listings: Iterable[Listing]) -> list[tuple[Listing, int]]` (sorted by unit price, then SKU)
  - `supermercado.pipeline.propose`: `MARKER: str`, `Proposal(item_id, store, listing, unit_price, unit)`, `propose(config, adapters, *, now, max_per_pair=3) -> tuple[list[Proposal], list[StoreFailure]]`, `render_proposals(matches_text: str, proposals, *, week: str, today: date) -> str`
  - CLI `propose [--store X]` rewrites `config/matches.yaml` in place (only the section after `MARKER`).
  - Rules: only stores with `supports_search`; only (item, store) pairs without an approved match; candidates must be available, priced, in the item's unit, inside `size_range`, and contain no excluded term as a whole word (accent- and case-insensitive).

- [ ] **Step 1: Write the failing tests**

`tests/domain/test_matching.py`:

```python
from factories import make_item, make_listing

from supermercado.domain.matching import filter_candidates, matches_rules, normalize_text
from supermercado.domain.models import Unit

RICE = make_item("rice", size_range=(0.9, 1.0), exclude=("integral", "con leche"))


def test_normalize_text_strips_accents_and_case() -> None:
    assert normalize_text("Arroz ÍNTEGRAL Pequeño") == "arroz integral pequeno"


def test_excluded_terms_are_whole_words_without_accents() -> None:
    assert not matches_rules(RICE, make_listing(name="Arroz Íntegral 1 kg"))
    assert not matches_rules(RICE, make_listing(name="Arroz con Leche 1 kg"))
    beans = make_item("beans", exclude=("lata", "4%"))
    assert matches_rules(beans, make_listing(name="Porotos Plata 1 kg"))
    assert not matches_rules(beans, make_listing(name="Porotos en lata 1 kg"))
    assert matches_rules(beans, make_listing(name="Porotos 14% proteína 1 kg"))


def test_size_unit_price_and_availability_rules() -> None:
    assert matches_rules(RICE, make_listing(size=1.0))
    assert not matches_rules(RICE, make_listing(size=0.8))
    assert not matches_rules(RICE, make_listing(size=None, unit=None))
    assert not matches_rules(RICE, make_listing(unit=Unit.L))
    assert not matches_rules(RICE, make_listing(available=False))
    assert not matches_rules(RICE, make_listing(price=None))


def test_filter_candidates_sorts_by_unit_price() -> None:
    listings = [
        make_listing(sku="a", price=1810),
        make_listing(sku="b", price=1590, promo_price=1290),
        make_listing(sku="c", name="Arroz Integral 1 kg", price=900),
        make_listing(sku="d", size=0.9, price=1260),
    ]
    assert [(listing.sku, price) for listing, price in filter_candidates(RICE, listings)] == [
        ("b", 1290),
        ("d", 1400),
        ("a", 1810),
    ]
```

`tests/pipeline/test_propose.py`:

```python
from datetime import UTC, date, datetime

import yaml
from factories import make_config, make_item, make_listing, make_match
from fakes import FakeAdapter

from supermercado.domain.models import Match, Unit
from supermercado.pipeline.propose import MARKER, Proposal, propose, render_proposals
from supermercado.stores.base import HttpError

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
RICE = make_item("rice", size_range=(0.9, 1.0), exclude=("integral",))
MILK = make_item("whole_milk", unit=Unit.L, search="leche entera 1 l", size_range=(1.0, 1.0))
HEAD = '# Approved matches\nrice:\n  jumbo: { sku: "1626", size: 1.0, approved: 2026-10-04 }\n'


def test_proposes_cheapest_valid_candidates_for_unmatched_pairs() -> None:
    config = make_config(
        items=[RICE, MILK], stores=("jumbo", "lider"), matches={"whole_milk": {"jumbo": make_match("4001")}}
    )
    jumbo = FakeAdapter(
        "jumbo",
        search_results={
            "arroz grado 2": [
                make_listing(sku="a", price=1810),
                make_listing(sku="b", price=1290),
                make_listing(sku="c", name="Arroz Integral 1 kg", price=900),
                make_listing(sku="d", price=1500),
                make_listing(sku="e", price=1700),
            ]
        },
    )
    lider = FakeAdapter("lider", supports_search=False)
    proposals, failures = propose(config, {"jumbo": jumbo, "lider": lider}, now=NOW)
    assert [(p.item_id, p.store, p.listing.sku, p.unit_price) for p in proposals] == [
        ("rice", "jumbo", "b", 1290),
        ("rice", "jumbo", "d", 1500),
        ("rice", "jumbo", "e", 1700),
    ]
    assert jumbo.searched == ["arroz grado 2"]
    assert lider.searched == []
    assert failures == []


def test_search_failure_is_reported_and_other_stores_continue() -> None:
    config = make_config(items=[RICE], stores=("jumbo", "tottus"))
    broken = FakeAdapter("jumbo", error=HttpError(503, "https://bff.jumbo.cl/catalog/plp"))
    tottus = FakeAdapter("tottus", search_results={"arroz grado 2": [make_listing(sku="t1", price=1890)]})
    proposals, failures = propose(config, {"jumbo": broken, "tottus": tottus}, now=NOW)
    assert [(f.store, f.error_class) for f in failures] == [("jumbo", "HttpError")]
    assert [p.listing.sku for p in proposals] == ["t1"]


def proposal(sku: str, price: int) -> Proposal:
    return Proposal("rice", "tottus", make_listing(sku=sku, price=price), price, "kg")


def test_render_appends_a_commented_section_that_keeps_data_unchanged() -> None:
    text = render_proposals(HEAD, [proposal("t1", 1890)], week="2026-W41", today=date(2026, 10, 5))
    assert text.startswith(HEAD)
    assert MARKER in text
    assert '#   tottus: { sku: "t1", size: 1, approved: 2026-10-05 }' in text
    assert yaml.safe_load(text) == yaml.safe_load(HEAD)


def test_render_replaces_the_previous_section_and_can_remove_it() -> None:
    first = render_proposals(HEAD, [proposal("t1", 1890)], week="2026-W41", today=date(2026, 10, 5))
    second = render_proposals(first, [proposal("t2", 1990)], week="2026-W42", today=date(2026, 10, 12))
    assert "t1" not in second
    assert second.count(MARKER) == 1
    assert render_proposals(second, [], week="2026-W42", today=date(2026, 10, 12)) == HEAD


def test_uncommented_proposal_is_a_valid_match() -> None:
    text = render_proposals("", [proposal("t1", 1890)], week="2026-W41", today=date(2026, 10, 5))
    lines = [line[2:] for line in text.splitlines() if line.startswith(("# rice:", "#   tottus:"))]
    data = yaml.safe_load("\n".join(lines))
    assert Match.model_validate(data["rice"]["tottus"]).sku == "t1"
```

Append to `tests/test_cli.py`:

```python
def test_propose_rewrites_only_the_proposal_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "matches.yaml").write_text("# approved\n", encoding="utf-8")
    config = make_config(items=[make_item("rice")], stores=("jumbo",))
    adapter = FakeAdapter("jumbo", search_results={"arroz grado 2": [make_listing()]})
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "build_adapters", lambda _config, only=None: {"jumbo": adapter})
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    assert cli.main(["--config", str(config_dir), "propose"]) == 0
    text = (config_dir / "matches.yaml").read_text(encoding="utf-8")
    assert text.startswith("# approved\n")
    assert '#   jumbo: { sku: "1626", size: 1, approved: 2026-09-28 }' in text
```

Append to `tests/test_workflows.py`:

```python
def test_propose_job_never_blocks_publication() -> None:
    job = load("weekly.yml")["jobs"]["propose"]
    assert "needs" not in job
    assert job["continue-on-error"] is True
    assert "python -m supermercado propose" in runs(job)
    assert any(step.get("uses", "").startswith("peter-evans/create-pull-request") for step in job["steps"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/domain/test_matching.py tests/pipeline/test_propose.py tests/test_cli.py tests/test_workflows.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.domain.matching'` (and the CLI/workflow tests fail on the missing command/job).

- [ ] **Step 3: Implement the match rules**

`src/supermercado/domain/matching.py`:

```python
"""Match rules: filter and rank search candidates for a basket item."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from supermercado.domain.models import BasketItem, Listing
from supermercado.domain.units import compute_unit_price
from supermercado.domain.validation import effective_price

_EPSILON = 1e-9


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _contains_term(name: str, term: str) -> bool:
    pattern = rf"(?<!\w){re.escape(normalize_text(term))}(?!\w)"
    return re.search(pattern, name) is not None


def matches_rules(item: BasketItem, listing: Listing) -> bool:
    if not listing.available or effective_price(listing) is None:
        return False
    if listing.unit != item.unit or not listing.size:
        return False
    if item.rules.size_range is not None:
        low, high = item.rules.size_range
        if not low - _EPSILON <= listing.size <= high + _EPSILON:
            return False
    name = normalize_text(listing.name)
    return not any(_contains_term(name, term) for term in item.rules.exclude)


def filter_candidates(item: BasketItem, listings: Iterable[Listing]) -> list[tuple[Listing, int]]:
    scored = []
    for listing in listings:
        if not matches_rules(item, listing):
            continue
        price = effective_price(listing)
        assert price is not None and listing.size  # guaranteed by matches_rules
        scored.append((listing, compute_unit_price(price, listing.size)))
    return sorted(scored, key=lambda pair: (pair[1], pair[0].sku))
```

- [ ] **Step 4: Implement proposals**

`src/supermercado/pipeline/propose.py`:

```python
"""Search candidates for unmatched (item, store) pairs and render them as YAML comments."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from supermercado.config import AppConfig
from supermercado.domain.matching import filter_candidates
from supermercado.domain.models import Listing
from supermercado.pipeline.collect import StoreFailure
from supermercado.stores.base import StoreAdapter

log = logging.getLogger(__name__)
MARKER = (
    "# --- match proposals (generated by `python -m supermercado propose`; "
    "move approved entries above this line) ---"
)


@dataclass(frozen=True)
class Proposal:
    item_id: str
    store: str
    listing: Listing
    unit_price: int
    unit: str


def propose(
    config: AppConfig,
    adapters: Mapping[str, StoreAdapter],
    *,
    now: datetime,
    max_per_pair: int = 3,
) -> tuple[list[Proposal], list[StoreFailure]]:
    proposals: list[Proposal] = []
    failures: list[StoreFailure] = []
    for store_id, adapter in adapters.items():
        if not adapter.supports_search:
            continue
        for item in config.basket:
            if store_id in config.matches.get(item.id, {}):
                continue
            try:
                listings = adapter.search(item.search)
            except Exception as exc:  # a failing store must not stop the others
                log.warning("%s search failed: %s", store_id, exc)
                failures.append(StoreFailure(store_id, type(exc).__name__, str(exc), now))
                break
            for listing, unit_price in filter_candidates(item, listings)[:max_per_pair]:
                proposals.append(Proposal(item.id, store_id, listing, unit_price, item.unit.value))
    return proposals, failures


def _clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def _line(proposal: Proposal, today: date) -> str:
    listing = proposal.listing
    entry = f'{{ sku: "{listing.sku}", size: {listing.size:g}, approved: {today.isoformat()} }}'
    note = " | ".join(
        part
        for part in (
            listing.name,
            listing.brand or "",
            f"{_clp(listing.promo_price or listing.price or 0)} -> {_clp(proposal.unit_price)}/{proposal.unit}",
            listing.url or "",
        )
        if part
    )
    return f"#   {proposal.store}: {entry}  # {note}"


def render_proposals(
    matches_text: str, proposals: Sequence[Proposal], *, week: str, today: date
) -> str:
    head = matches_text.split(MARKER, 1)[0].rstrip("\n")
    if not proposals:
        return f"{head}\n" if head else ""
    lines = [head, ""] if head else []
    lines += [MARKER, f"# week: {week}"]
    order: list[str] = []
    grouped: dict[str, list[Proposal]] = {}
    for proposal in proposals:
        if proposal.item_id not in grouped:
            order.append(proposal.item_id)
            grouped[proposal.item_id] = []
        grouped[proposal.item_id].append(proposal)
    for item_id in order:
        lines.append(f"# {item_id}:")
        lines += [_line(proposal, today) for proposal in grouped[item_id]]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Add the CLI command and the workflow job**

In `src/supermercado/cli.py`: add `from supermercado.pipeline.propose import propose, render_proposals`; add to `_parser()`:

```python
    propose_cmd = sub.add_parser("propose", help="write candidate matches into matches.yaml")
    propose_cmd.add_argument("--store", help="propose for a single store")
```

add the handler:

```python
def _cmd_propose(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    adapters = build_adapters(config, only=args.store)
    now = _now()
    proposals, failures = propose(config, adapters, now=now)
    path = args.config / "matches.yaml"
    path.write_text(
        render_proposals(
            path.read_text(encoding="utf-8"), proposals, week=iso_week(now), today=now.date()
        ),
        encoding="utf-8",
    )
    print(f"{len(proposals)} candidates written to {path}")
    for failure in failures:
        print(f"FAILED {failure.store}: {failure.error_class}: {failure.message}", file=sys.stderr)
    return 0
```

and register `"propose": _cmd_propose` in `COMMANDS`.

In `.github/workflows/weekly.yml`, add `pull-requests: write` under the top-level `permissions`, and append this job under `jobs:` (it has no `needs`, so collect/build/deploy never wait for it):

```yaml
  propose:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - run: uv sync --locked
      - name: Search candidates for unmatched items
        run: uv run python -m supermercado propose
      - uses: peter-evans/create-pull-request@v7
        with:
          branch: bot/match-proposals
          add-paths: config/matches.yaml
          commit-message: "chore(matches): weekly match proposals"
          title: "chore(matches): weekly match proposals"
          body: |
            Candidates generated by `python -m supermercado propose`, cheapest unit price first.
            To approve one, move its two lines above the marker, remove the leading `# `, and keep
            at most one SKU per item and store. Delete the rest of the generated section before merging.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/supermercado/domain/matching.py src/supermercado/pipeline/propose.py src/supermercado/cli.py .github/workflows/weekly.yml tests
git commit -m "feat(pipeline): propose match candidates and open a weekly review PR"
```

---

### Task 16: Contract smoke test workflow

**Files:**
- Create: `src/supermercado/pipeline/smoke.py`, `.github/workflows/contract-smoke.yml`
- Modify: `src/supermercado/cli.py` (add `smoke`)
- Test: `tests/pipeline/test_smoke.py`, `tests/test_workflows.py`

**Interfaces:**
- Consumes: `AppConfig`, `StoreConfig.smoke_sku` (Task 4); `build_adapters` incl. Lider smoke URL (Tasks 6, 14); `FakeAdapter` (Task 7).
- Produces:
  - `supermercado.pipeline.smoke`: `SmokeResult(store: str, ok: bool, detail: str)`, `smoke(config: AppConfig, adapters: Mapping[str, StoreAdapter]) -> list[SmokeResult]`, `render_smoke_table(results) -> str`
  - CLI `smoke` prints the Markdown table, exit code 1 if any store failed, else 0.
  - Workflow `contract-smoke.yml`: Thursdays 13:00 UTC + manual; opens/updates an issue labelled `contract-smoke` on failure.

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_smoke.py`:

```python
from factories import make_item, make_listing, make_store_config
from fakes import FakeAdapter

from supermercado.config import AppConfig
from supermercado.pipeline.smoke import render_smoke_table, smoke
from supermercado.stores.base import ResponseShapeError


def config(**stores):
    return AppConfig(basket=[make_item()], stores=stores)


def test_known_sku_with_price_passes() -> None:
    cfg = config(jumbo=make_store_config("Jumbo", smoke_sku="1626"))
    [result] = smoke(cfg, {"jumbo": FakeAdapter("jumbo", [make_listing()])})
    assert result.ok is True
    assert "Arroz Grado 2 Tucapel 1 kg" in result.detail


def test_failures_are_reported_per_store() -> None:
    cfg = config(
        jumbo=make_store_config("Jumbo", smoke_sku="1626"),
        tottus=make_store_config("Tottus", smoke_sku="404"),
        unimarc=make_store_config("Unimarc"),
        acuenta=make_store_config("aCuenta", smoke_sku="1626"),
    )
    adapters = {
        "jumbo": FakeAdapter("jumbo", error=ResponseShapeError("no products list")),
        "tottus": FakeAdapter("tottus", [make_listing()]),
        "unimarc": FakeAdapter("unimarc"),
        "acuenta": FakeAdapter("acuenta", [make_listing(price=None)]),
    }
    results = {r.store: r for r in smoke(cfg, adapters)}
    assert not any(r.ok for r in results.values())
    assert results["jumbo"].detail == "ResponseShapeError: no products list"
    assert "missing" in results["tottus"].detail
    assert "smoke_sku" in results["unimarc"].detail
    assert "price" in results["acuenta"].detail


def test_table_lists_every_store() -> None:
    cfg = config(jumbo=make_store_config("Jumbo", smoke_sku="1626"))
    table = render_smoke_table(smoke(cfg, {"jumbo": FakeAdapter("jumbo", [make_listing()])}))
    assert table.splitlines()[0] == "| Store | Result | Detail |"
    assert "| jumbo | ok |" in table
```

Append to `tests/test_workflows.py`:

```python
def test_contract_smoke_is_scheduled_and_opens_an_issue() -> None:
    workflow = load("contract-smoke.yml")
    assert workflow["on"]["schedule"][0]["cron"] == "0 13 * * 4"
    script = runs(workflow["jobs"]["smoke"])
    assert "python -m supermercado smoke" in script
    assert "contract-smoke" in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/pipeline/test_smoke.py tests/test_workflows.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'supermercado.pipeline.smoke'`.

- [ ] **Step 3: Implement smoke and the CLI command**

`src/supermercado/pipeline/smoke.py`:

```python
"""Contract smoke test: one known SKU per store must still parse with a price."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from supermercado.config import AppConfig
from supermercado.stores.base import StoreAdapter


@dataclass(frozen=True)
class SmokeResult:
    store: str
    ok: bool
    detail: str


def _check(store_id: str, sku: str | None, adapter: StoreAdapter) -> SmokeResult:
    if not sku:
        return SmokeResult(store_id, False, "smoke_sku not configured in config/stores.yaml")
    try:
        listings = adapter.fetch([sku])
    except Exception as exc:  # report every failure class, never crash the run
        return SmokeResult(store_id, False, f"{type(exc).__name__}: {exc}")
    listing = next((item for item in listings if item.sku == sku), None)
    if listing is None:
        return SmokeResult(store_id, False, f"sku {sku} missing from the response")
    if not listing.name or not listing.price or listing.price <= 0:
        return SmokeResult(store_id, False, f"sku {sku} parsed without a name or price")
    return SmokeResult(store_id, True, f"{listing.name} · ${listing.price}")


def smoke(config: AppConfig, adapters: Mapping[str, StoreAdapter]) -> list[SmokeResult]:
    return [
        _check(store_id, config.stores[store_id].smoke_sku, adapter)
        for store_id, adapter in adapters.items()
    ]


def render_smoke_table(results: Sequence[SmokeResult]) -> str:
    lines = ["| Store | Result | Detail |", "|---|---|---|"]
    for result in results:
        detail = result.detail.replace("|", "\\|")
        lines.append(f"| {result.store} | {'ok' if result.ok else 'FAILED'} | {detail} |")
    return "\n".join(lines) + "\n"
```

In `src/supermercado/cli.py`: add `from supermercado.pipeline.smoke import render_smoke_table, smoke`; add to `_parser()`:

```python
    sub.add_parser("smoke", help="fetch one known SKU per store and check the response shape")
```

add the handler:

```python
def _cmd_smoke(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    results = smoke(config, build_adapters(config))
    sys.stdout.write(render_smoke_table(results))
    return 0 if all(result.ok for result in results) else 1
```

and register `"smoke": _cmd_smoke` in `COMMANDS`.

Append to `tests/test_cli.py`:

```python
def test_smoke_exit_code_reflects_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from factories import make_store_config

    from supermercado.config import AppConfig

    config = AppConfig(basket=[make_item()], stores={"jumbo": make_store_config("Jumbo", smoke_sku="1626")})
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "build_adapters", lambda _config, only=None: {"jumbo": FakeAdapter("jumbo")})
    assert cli.main(["smoke"]) == 1
    assert "FAILED" in capsys.readouterr().out
```

- [ ] **Step 4: Write the workflow**

`.github/workflows/contract-smoke.yml`:

```yaml
name: contract-smoke

on:
  schedule:
    - cron: "0 13 * * 4"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - run: uv sync --locked

      - name: Fetch one known SKU per store
        id: smoke
        run: |
          set +e
          uv run python -m supermercado smoke > smoke.md
          echo "exit=$?" >> "$GITHUB_OUTPUT"
          cat smoke.md

      - name: Open or update the contract issue
        if: steps.smoke.outputs.exit != '0'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh label create contract-smoke --color D93F0B --force
          body="$(printf '## Store contract check failed\n\n%s\n' "$(cat smoke.md)")"
          number="$(gh issue list --label contract-smoke --state open --json number --jq '.[0].number')"
          if [ -n "$number" ]; then
            gh issue comment "$number" --body "$body"
          else
            gh issue create --title "Store response contract changed" --label contract-smoke --body "$body"
          fi

      - name: Fail the run
        if: steps.smoke.outputs.exit != '0'
        run: exit 1
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

- [ ] **Step 6: Live check (residential IP; skip and report if no network)**

Run: `uv run python -m supermercado smoke`
Expected: a table; stores without `smoke_sku` show `FAILED` with "smoke_sku not configured" until Task 17 fills them in. Report which stores pass.

- [ ] **Step 7: Commit**

```bash
git add src/supermercado/pipeline/smoke.py src/supermercado/cli.py .github/workflows/contract-smoke.yml tests
git commit -m "ci: add weekly store contract smoke test"
```

---

### Task 17: Verify and pin a Santiago store per chain

This task needs a human (or an agent with a real browser) on a residential connection. If you cannot run a browser, finish Steps 1–2, then stop and report BLOCKED with the checklist from Step 3.

**Files:**
- Create: `docs/store-locations.md`
- Modify: `config/stores.yaml` (`store_ref`, `comuna`, `location_verified`, `smoke_sku`, `smoke_url`)
- Test: `tests/test_store_locations.py`

**Interfaces:**
- Consumes: `load_config`, `StoreConfig` fields (Task 4); CLI `smoke` (Task 16).
- Produces: every enabled store in `config/stores.yaml` has a verified Santiago `comuna`, a `location_verified` date, and a `smoke_sku` (Lider also `smoke_url`). The methodology page lists these comunas automatically (Task 8).

- [ ] **Step 1: Write the failing test**

`tests/test_store_locations.py`:

```python
from pathlib import Path

from supermercado.config import load_config

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def test_every_enabled_store_pins_a_verified_santiago_location() -> None:
    config = load_config(CONFIG_DIR)
    assert config.enabled_stores(), "at least one store must be enabled"
    for store_id in config.enabled_stores():
        store = config.stores[store_id]
        assert store.comuna != "pending-verification", f"{store_id}: comuna not verified"
        assert store.location_verified is not None, f"{store_id}: location_verified missing"
        assert store.smoke_sku, f"{store_id}: smoke_sku missing"
    assert config.stores["lider"].smoke_url
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_store_locations.py -v`
Expected: FAIL with `jumbo: comuna not verified`.

- [ ] **Step 3: Verify each chain manually and write `docs/store-locations.md`**

Create `docs/store-locations.md` with this content, then fill the table while doing the checks:

```markdown
# Store locations (Santiago reference)

Prices differ by branch and delivery zone, so each chain is pinned to one explicit store or zone
in `config/stores.yaml`. Re-verify when a chain changes its website or when prices look off.

| Chain | `store_ref` | Comuna | How it was verified | Verified on |
|---|---|---|---|---|
| Jumbo | | | | |
| Santa Isabel | | | | |
| Tottus | | | | |
| aCuenta | | | | |
| Unimarc | | | | |
| Lider | | | | |

## How to verify

Use a private browser window on a residential connection, with DevTools open on the Network tab.

1. **Jumbo** (`www.jumbo.cl`): choose a delivery address or pickup store in the target Santiago
   comuna, search "arroz grado 2", and open the `POST bff.jumbo.cl/catalog/plp` request. Copy the
   `store` value from the request body. The spike saw `jumboclj512` in requests and `jumboclj410`
   as a default id; record which one belongs to which comuna.
2. **Santa Isabel** (`www.santaisabel.cl`): same as Jumbo with `bff.santaisabel.cl`. The spike
   default is `pedrofontova`; confirm the comuna of that branch.
3. **Tottus** (`www.tottus.cl`): choose the delivery comuna in the header, search a product, and
   inspect the `GET /s/browse/v1/search/cl` request for a `politicalId` (or zone) parameter or
   cookie. Put its value in `store_ref`; if prices do not depend on it, leave `store_ref` empty
   and write "chain-wide price" in the table.
4. **aCuenta** (`www.acuenta.cl`): choose a store, search a product, and copy `storeReference`
   from the GraphQL request to `nextgentheadless.instaleap.io`. The spike used `580`.
5. **Unimarc** (`www.unimarc.cl`): choose a store or address and inspect
   `POST /catalog/product/search` for a store or sales-channel field. The adapter sends none; if
   prices change with the selected store, write it in the table and open a follow-up issue
   instead of changing the adapter here.
6. **Lider** (`super.lider.cl`): open a product page with the cookie
   `walmart.nearestLatLng=-33.4521,-70.6536` (Santiago Centro) and confirm which store the page
   shows (the spike saw `0000000057`). Adjust the coordinates to the chosen comuna if needed.

For each chain, also pick one basket product that is stable and in stock and record its SKU as
`smoke_sku` (Lider: also `smoke_url`).
```

- [ ] **Step 4: Update `config/stores.yaml`**

For every enabled store set the verified values, for example:

```yaml
jumbo:
  name: Jumbo
  enabled: true
  base_url: https://bff.jumbo.cl
  api_key: be-reg-groceries-jumbo-catalog-w54byfvkmju5
  store_ref: jumboclj512        # replace with the verified id
  comuna: Santiago              # replace with the verified comuna
  location_verified: 2026-10-05 # the date you verified it
  smoke_sku: "1626"
```

Quote every SKU and store id.

- [ ] **Step 5: Run the tests and the live smoke check**

Run: `uv run pytest -v && uv run python -m supermercado smoke`
Expected: all tests PASS; the smoke table shows `ok` for every store (a store blocked from your IP may show `BlockedError`; note it in the doc).

- [ ] **Step 6: Commit**

```bash
git add docs/store-locations.md config/stores.yaml tests/test_store_locations.py
git commit -m "docs: pin and document a verified Santiago store per chain"
```

---

## Self-Review Notes

- **Spec coverage:** stores and access methods (Tasks 6, 10–14); politeness, retries, `curl_cffi` impersonation (Task 5); `ApiKeyRejected` (Task 6); reference vs card price (Tasks 2, 6, 11–14); data model and Parquet schema (Tasks 1, 7); validation rules (Task 2); comparable-item ranking and "never impute" (Task 3); per-store isolation, failure issue, manual `--store` fallback (Tasks 7, 9); propose PR (Task 15); site pages, palette, Spanish copy, chart JSON (Task 8); contract smoke test (Task 16); Santiago store pinning (Task 17). "Until manually cleared" for suspicious rows is implemented with `config/cleared.yaml` (Tasks 2, 4, 8).
- **Known assumptions to confirm while recording fixtures:** Tottus `cmrPrice` type name and search-by-SKU (Task 11); aCuenta `GetProductsBySKUInput` name and return shape (Task 12); Unimarc search-by-`itemId` and product URL field (Task 13); Lider per-kg meaning of `currentPrice` for weighted items (Task 14). Each task has an explicit verification step instead of guessing silently.
