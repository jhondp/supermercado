# Supermarket Price Tracker — Design Spec

- **Date:** 2026-10-04
- **Status:** Draft, pending user review
- **Scope:** v1

## 1. Purpose

A public, static website that answers one question in under 3 seconds: **"Where is the basic grocery basket cheapest this week in Santiago?"**

Prices are collected once a week. The site keeps a growing, clean price history so people can see how basket items evolve over time. The history is secondary context, not the headline.

### Success criteria

- The home page shows a ranking of supermarkets by total basket cost for the latest week.
- Every number on the site can be traced to a specific SKU, store, and scrape timestamp.
- One store failing never blocks the weekly publication of the others.
- A wrong product match can never silently enter the history. Every match is human-approved.
- Running cost: $0 (GitHub Actions + GitHub Pages).

### Out of scope (v1)

- The budget, goals, and app-download features from the landing template.
- User accounts, alerts, and personal shopping lists.
- Locations outside Santiago. The data model keeps a `location` field so more can be added later.
- Exact-brand basket comparison.
- Mayorista 10 / Super10: no online catalog (verified in the spike).
- Alvi: wholesale format with poor coverage of bulk/fresh items.

## 2. Stores (v1)

| Store | Access method | Notes |
|---|---|---|
| Jumbo | Cencosud BFF `POST https://bff.jumbo.cl/catalog/plp`, `apiKey` header, `store` in body | Exposes `ppumPrice` (price per unit of measure). Batch lookup via `fullText: "sku:A;B"` |
| Santa Isabel | Cencosud BFF `POST https://bff.santaisabel.cl/catalog/plp`, `apiKey` header, `store` required | Same shape as Jumbo |
| Tottus | `GET https://www.tottus.cl/s/browse/v1/search/cl?Ntt=<query>` (JSON) | Prices come as strings (`"1.890"`), so they need parsing. The HTML is behind Cloudflare; use the JSON only |
| aCuenta | Instaleap GraphQL `POST https://nextgentheadless.instaleap.io/api/v3` (`searchProducts`, `getProductsBySKU`), `clientId: SUPER_BODEGA` | Integer prices, stock included |
| Unimarc | SMU BFF `POST https://bff-unimarc-ecommerce.unimarc.cl/catalog/product/search`, headers `channel`, `source`, `version`, full Chrome User-Agent | Distinguishes the club price from `listPrice` |
| Lider | Product pages `GET https://super.lider.cl/ip/{slug}/{id}`, parsing `__NEXT_DATA__` | Behind PerimeterX, so it requires TLS impersonation. **No automated search:** `robots.txt` disallows `/search*`. Lider matches are entered manually |

### Cross-cutting scraping rules

- **HTTP client:** `curl_cffi` with `impersonate="chrome"` for every store. The spike showed blocking is TLS-fingerprint based.
- **Politeness:** at most 1 request every 1.5 s per store, at most 3 retries with exponential backoff, and no paths disallowed by `robots.txt`.
- **Public API keys** (Jumbo, Santa Isabel) live in config, not code. If a key is rejected, the adapter fails with an explicit `ApiKeyRejected` error so the weekly issue says exactly what to update.
- **Store location:** each adapter's config pins one explicit store/branch id with a documented Santiago comuna. Mapping the default ids found in the spike (`jumboclj410`, `pedrofontova`, `580`, Tottus `politicalId`, Lider `0000000057`) to comunas is the first implementation task.
- **Reference price:** comparisons use the price **anyone** pays, meaning the regular price or a promo with no conditions. Card-only or club-only prices are stored separately and never ranked.

## 3. Architecture

Light hexagonal: the domain is pure Python and knows nothing about HTTP, files, or HTML.

```
config/
  basket.yaml          # basket items, equivalence rules, unit, reference quantity
  matches.yaml         # approved SKU per (item, store); changed only via PR
  stores.yaml          # per-store settings: base URLs, API keys, store id, comuna
src/supermercado/
  domain/              # BasketItem, Listing, PriceObservation, unit normalization,
                       # match rules, validation, basket ranking
  stores/              # one adapter per store implementing the StoreAdapter port
    base.py            # StoreAdapter protocol + shared HTTP client (curl_cffi)
    jumbo.py, santa_isabel.py, tottus.py, acuenta.py, unimarc.py, lider.py
  pipeline/
    collect.py         # fetch approved SKUs → validate → weekly Parquet snapshot
    propose.py         # search candidates → write proposal for a PR on matches.yaml
  site/
    build.py           # DuckDB over data/ → Jinja → dist/
    templates/
    static/
  cli.py               # python -m supermercado {collect,propose,build} [--store X]
data/prices/YYYY-Www.parquet
tests/
.github/workflows/
```

### StoreAdapter port

```python
class StoreAdapter(Protocol):
    store_id: str
    supports_search: bool                         # False for Lider

    def search(self, query: str) -> list[Listing]: ...
    def fetch(self, skus: list[str]) -> list[Listing]: ...
```

`Listing` is the normalized result:
- **Identity and description:** `sku`, `name`, `brand`, `url`.
- **Size:** `size` and `unit` (kg, L, unit, m, ml, g), plus `sold_by` (`unit` or `weight`) and `multiplier`.
- **Prices:** `price` (regular, CLP int), `promo_price` (CLP int or None, unconditional promos only), `card_price` (CLP int or None), `store_unit_price` (the price per unit the store itself reports, if any).
- **Stock:** `available`.

Adapters only translate store responses into `Listing`. All business rules live in `domain/`.

## 4. Data model

### `config/basket.yaml`

```yaml
- id: rice
  name: Arroz grado 2
  category: pantry          # pantry | dairy_eggs | bakery | meat | cleaning | hygiene
  unit: kg                  # unit used to normalize prices
  reference_qty: 1.0        # quantity counted in the basket total
  search: "arroz grado 2"
  rules:
    size_range: [0.9, 1.0]
    exclude: [integral, preparado, "con leche"]
```

Initial basket (23 items):
- **Pantry:** rice G2 1 kg, spaghetti 400 g, vegetable oil 1 L, sugar 1 kg, flour (no leavening) 1 kg, dry beans 1 kg, lentils 1 kg, fine salt 1 kg, tea 100 bags, instant coffee 170 g.
- **Dairy and eggs:** whole milk 1 L, eggs ×12.
- **Bakery:** bulk marraqueta/hallulla bread.
- **Meat:** bulk whole chicken thigh, ground beef 10% fat, bulk posta.
- **Cleaning:** liquid laundry detergent 3 L, dish soap 500 ml, bleach 1 L, toilet paper 4 double-ply rolls (normalized per meter).
- **Hygiene:** spray deodorant 150 ml, toothpaste 90 g, bar soap.

### `config/matches.yaml`

```yaml
rice:
  jumbo: { sku: "1626", size: 1.0, approved: 2026-10-04 }
  lider: { sku: "00780...", url: "https://super.lider.cl/ip/...", size: 1.0, approved: 2026-10-04 }
```

A missing entry means the item is not yet matched for that store. It is shown as "sin match", not as a missing price.

### `data/prices/YYYY-Www.parquet`

One row per (week, store, item). Each ISO week has its own file. A file is immutable once committed; a rerun for the same week replaces the file before publication only.

| Column | Type | Description |
|---|---|---|
| `week` | str | ISO week, e.g. `2026-W40` |
| `scraped_at` | timestamp (UTC) | |
| `location` | str | `santiago` |
| `store` | str | |
| `item_id` | str | |
| `sku`, `product_name`, `brand`, `url` | str | traceability of the match |
| `size`, `unit` | float, str | |
| `price` | int | regular price, CLP |
| `promo_price` | int, nullable | unconditional promo |
| `card_price` | int, nullable | card/club-only price, never ranked |
| `effective_price` | int | `promo_price` if present, else `price` |
| `unit_price` | int | `effective_price / size`, rounded to CLP |
| `available` | bool | out of stock ≠ no data |
| `status` | str | `ok` \| `suspicious` \| `size_changed` |

Money is always stored as integer CLP, never as a float.

## 5. Weekly pipeline

Runs from GitHub Actions on a weekly cron, Monday 06:00 America/Santiago.

1. **collect:** for each store, fetch all approved SKUs, map them to `PriceObservation`, and validate.
2. **validate**, before writing:
   - A price ≤ 0 or missing drops the row and logs it.
   - A change of more than ±50% in `unit_price` versus the previous week saves the row with `status=suspicious`. Suspicious rows are excluded from the ranking until manually cleared.
   - A SKU whose size differs from the approved size in `matches.yaml` gets `status=size_changed` and triggers an alert. This is how "shrinkflation" gets detected.
3. **commit** the Parquet snapshot to `main`.
4. **build** the site and **deploy** to GitHub Pages.
5. **propose** (separate job; its failure never blocks the steps above): for stores with `supports_search`, search each basket item, filter candidates with `rules`, sort by `unit_price`, and open or update a PR that adds proposals to `matches.yaml` as commented candidates for review.

### Failure handling

- Each store runs in isolation. If a store fails, the remaining stores are still saved and published, and the failed store shows "sin datos esta semana".
- Any store failure opens or updates a GitHub issue that names the store, the error class, and the time.
- **Manual fallback:** `python -m supermercado collect --store <id>` from a residential IP, then commit. This covers stores that block GitHub Actions IPs. Whether datacenter IPs get blocked is unverified; Lider, Unimarc, and Tottus carry the highest risk.

## 6. Website

Static HTML generated with Jinja. Mobile-first. Uses the template palette: Honeydew `#E5F4E3`, Cool Sky `#5DA9E9`, French Blue `#003F91`, White `#FFFFFF`, Velvet Purple `#6D326D`.

The site uses minimal JavaScript (one lightweight chart library from a CDN, reading build-time JSON). It has no backend, accounts, or tracking cookies. UI copy is in Spanish.

### Pages

1. **Home:** the headline "¿Dónde sale más barata la canasta esta semana?", followed by:
   - A ranking of stores by basket total, with the winner highlighted.
   - The change versus the previous week.
   - "Actualizado: <fecha> · Precios de referencia Santiago".
   - "Comparando N de 23 productos".
2. **Products table:** one row per item and one column per store, showing `unit_price` with the cheapest highlighted. Category filter pills.
3. **Product detail** (`/producto/<item_id>/`): a line chart of `unit_price` per store over time. It lists the exact SKU and name used per store, and visibly marks weeks where the SKU changed.
4. **Methodology:** how equivalents are chosen, the reference location, the schedule, the card-price policy, and what "sin datos" and "sin match" mean.

### Ranking rule

- A store is **ranked** only when it has an `ok`, available observation for at least **80%** of basket items that week (19 of 23). Stores below the threshold are listed below the ranking as "cobertura insuficiente esta semana".
- Basket total per store = Σ `unit_price × reference_qty` over the **comparable items**.
- An item is comparable when every ranked store has an `ok`, available observation for it that week.
- A store with no data this week is listed below the ranking as "sin datos" and is not ranked.
- Prices are never imputed.

## 7. Testing

- **Domain (TDD):** unit normalization, match-rule filtering, validation statuses, ranking and comparable-item selection, and price parsing (e.g. `"1.890"` → 1890).
- **Adapters:** fixture-based tests using real JSON/HTML responses recorded once. CI never calls live sites.
- **Contract smoke test:** a separate scheduled workflow fetches one known SKU per store from the live site and opens an issue if the response shape changes.
- **Build:** the site build runs over fixture Parquet data. The test asserts that the pages render and that the chart JSON is valid.

## 8. Tooling

- Python 3.12+, managed with `uv`.
- Dependencies: `curl_cffi`, `duckdb`, `pyarrow`, `jinja2`, `pyyaml`, `pydantic` (domain models and config validation).
- Dev dependencies: `pytest`, `ruff`.
- Generated artifacts, code, comments, and docs are in English. Only user-facing UI copy is in Spanish.

## 9. Known risks

| Risk | Mitigation |
|---|---|
| A store changes its API | Isolated adapters, a contract smoke test, and an automatic issue |
| GitHub Actions IPs get blocked (unverified) | Manual collect from a residential IP |
| Public API keys rotate (Cencosud) | Keys live in config; an explicit `ApiKeyRejected` error |
| A bad match pollutes the history | Human approval via PR; `sku` stored on every row; size-change detection |
| Lider anti-bot tightens | Lider is isolated; the site still publishes without it |
| Default store ids are not in Santiago | First implementation task: verify and pin a Santiago store per chain |
