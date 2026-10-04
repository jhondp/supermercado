# MVP Decision Log — 2026-10-04

Branch `feat/mvp` (40 commits on top of `main` 1c4c683). Final state: 361 tests passing, 1 expected xfail. Ruff is clean. The final whole-branch review and its fix wave are both closed.

This log lists every decision taken while building the MVP. Each entry includes what it costs if it turns out to be wrong.

## 1. Product decisions (made by the user)

| Decision | Choice |
|---|---|
| Audience | Public shoppers: "where is the basket cheapest this week?" Price history is secondary. |
| Comparison model | Cheapest **equivalent** product per store, any brand, normalized to unit price ($/kg, $/L, $/unit, $/m). |
| Product matching | Hybrid: automated search proposes candidates, a human approves them through a PR, and an approved SKU stays pinned until changed. |
| Hosting | GitHub Actions weekly cron + GitHub Pages ($0). Manual `collect --store X` from a home IP is the fallback. |
| Location | Santiago only. A `location` field is kept for future expansion. |
| Basket | 23 items (see `config/basket.yaml`). |
| Stores (v1) | Jumbo, Santa Isabel, Tottus, aCuenta, Unimarc, Lider. Mayorista 10 was dropped because it has no online catalog. Alvi was dropped because it covers few fresh and bulk items. |
| Card prices | Never ranked. Stored in `card_price` only. |
| Ranking coverage | A store is ranked only if it has at least **80%** of the basket items (19 of 23). Stores below that appear as "cobertura insuficiente". |
| Workflow | Development happens on `feat/mvp` with one commit per task. The formal `gentle-ai` review runs once over the whole branch before push or PR, not per commit. |
| Autonomy | The controller decided open questions and resumes automatically after usage limits. Fable was used for hard items, with Opus as the fallback. |

## 2. Architecture decisions

- **Static site plus Parquet snapshots.** There is one immutable Parquet file per ISO week in `data/prices/`. DuckDB is used only at build time, and Jinja renders the HTML. Rejected alternatives: committing a `.duckdb` binary to git (it grows and causes merge conflicts), and a Supabase backend (overkill for weekly data).
- **Light hexagonal layout.** `domain/` is pure Python. `stores/` has one adapter per chain behind the `StoreAdapter` port. `pipeline/` holds collect, propose and smoke. `site/` builds the HTML.
- **HTTP client.** All HTTP goes through `curl_cffi` with `impersonate="chrome"`. The feasibility spike showed that blocking is based on the TLS fingerprint, so plain `httpx` gets blocked.
- **Prices are integer CLP.** Rounding uses `Decimal` half-up. Floats are never used for money.

## 3. Rulings made during implementation

| # | Ruling | Why | Cost if wrong |
|---|---|---|---|
| 1 | The `rank_stores` tests that predate the coverage rule pass `min_coverage=0.0`. `insufficient_coverage` is carried in every `Ranking`. | The 80% rule is binding. | None. |
| 2 | Home page copy says "Ningún supermercado alcanzó la cobertura mínima" when every store is below the threshold. The methodology page explains the 80% rule. | The UI must match the spec. | Copy tweak. |
| 3 | The YAML loader rejects duplicate keys. | PyYAML silently keeps the last duplicate, which would lose approved matches. | Small amount of loader code. |
| 4 | A same-week rerun replaces only the stores that produced at least one observation. | Re-running one store must not wipe another store's rows. | None. |
| 5 | The baseline for the suspicious check is the most recent ok-or-cleared observation across all prior weeks. | A persistent price jump must stay suspicious until a human clears it. | A real permanent price change needs one manual clearance in `config/cleared.yaml`. |
| 6 | Store-specific constants (aCuenta `client_id`, Unimarc headers, promo allowlists) live in `config/stores.yaml`. | Global constraint: no store config in code. | A few extra config fields. |
| 7 | Every adapter turns malformed per-item data into `ResponseShapeError`. A card price is accepted only when `0 < card < price`. | One bad payload must be reported, not crash the run. | None. |
| 8 | Points that are suspicious or unavailable are hidden from charts and labelled in tables. Product links must use `http(s)`. Chart.js is pinned with SRI (verified sha512). Chart JSON escapes every `<`. | Keep the history clean, and harden against XSS and supply-chain attacks. | None. |
| 9 | aCuenta promos use a config **allowlist**, not a denylist. Unknown promo types count as "no promo". A promo with no quantity counts as conditional. | Rankings must never include a conditional promo. | Some real promos are under-reported until they are added to the allowlist. |
| 10 | Unimarc does not send a hand-written User-Agent. | A live check on 2026-10-04 returned 200 with impersonation alone, and a stale UA can mismatch the TLS fingerprint. | If Unimarc starts blocking, re-add a UA derived from the impersonation target. |
| 11 | Lider never uses `/search` because of robots.txt. Its matches are manual and it is fetched through product pages only. A challenge page raises `BlockedError`. | Respect robots.txt and fail loudly. | More manual matching work for Lider. |
| 12 | All live verification was done in Task 17 from a residential IP. Real responses were recorded as test fixtures, and adapters were fixed where live data contradicted the hand-written fixtures. | Avoid scattered network use. One live pass verifies everything. | None. |
| 13 | Live-driven fixes: Cencosud card prices come from structured `paymentMethods`, ignoring multi-buy offers. Tottus looks up SKUs in batches of 8 (the batch size verified live) and follows single-SKU redirects. aCuenta treats `specialPrice` as unconditional. Unimarc treats "Exclusivo .cl" as an open offer and "Club Unimarc" as a card price. | Based on live evidence (see the Task 17 report). | The aCuenta and Unimarc calls are judgment calls. Each can be reverted in config or code. |
| 14 | Santa Isabel and Lider have verified comunas. Jumbo, Tottus, aCuenta and Unimarc stay `pending-verification`, enforced by a strict xfail test. | Nothing is claimed without evidence. | The site shows those comunas as pending. |
| 15 | Final-review fixes: one malformed listing is dropped instead of crashing collect. A store with no usable rows becomes an `EmptyResult` failure, and dropped rows are listed in the weekly issue. SKU changes stay visible across weeks that are not plotted. A shared `positive_multiplier` helper replaces per-adapter copies. A CI workflow runs on PRs. `MIN_COVERAGE` is a single constant. | Gaps between tasks that the per-task reviews could not see. | The weekly issue gets a comment every week while an approved SKU stays missing. |
| 16 | Third-party GitHub Actions are pinned to major-version tags, not commit SHAs. | SHA lookup needs your repository and network access. | Supply-chain risk from mutable tags until they are pinned. |
| 17 | The cron runs Monday at 09:00 UTC, which is 06:00 in Santiago in summer and 05:00 in winter. | GitHub cron runs in UTC. | None for weekly data. |

## 4. Live state verified on 2026-10-04

Smoke test: 6 of 6 stores OK. Each store returned a 1 kg grade-2 rice product:

| Store | Price |
|---|---|
| Jumbo | $1.810 |
| Santa Isabel | $870 |
| Tottus | $1.890 |
| aCuenta | $1.150 |
| Unimarc | $1.950 |
| Lider | $1.790 |

Lider is intermittently challenged by its bot protection (Akamai). Expect occasional `BlockedError` entries in the weekly issue.

## 5. What you need to do next

1. **Create the GitHub repository and push.**
   - In Settings → Pages, set Source to "GitHub Actions".
   - In Settings → Actions → General, enable "Allow GitHub Actions to create and approve pull requests".
   - Do not require PRs for the bot's snapshot push to `main`, or the weekly commit will fail.
2. **Seed `config/matches.yaml`. It is empty, so the first run publishes "Aún no hay datos".**
   - From home, run `uv run python -m supermercado propose`.
   - Review the candidates and approve at least 19 items for each store you want ranked.
   - Run `collect`, then commit `data/prices/`.
3. **Pin the 4 pending comunas.** Follow "How to verify" in `docs/store-locations.md`. Then update `config/stores.yaml` and `LOCATION_PENDING` in `tests/test_store_locations.py`.
4. **Check the site at mobile width (375px).** No subagent could check it visually.
5. Optional:
   - Pin the GitHub Actions to commit SHAs.
   - Self-host the Poppins font (Google Fonts exposes visitor IPs).
   - Verify Lider's weighted-item pricing (per kg or per piece).
6. **Run the formal review gate before pushing.** Run `gentle-ai review` on the `feat/mvp` branch, using the pre-push / pre-PR gates as agreed.

## 6. Deferred minor items

Minor findings from every task review are triaged in the final review as "follow-up, safe to merge". The main ones:
- Parsing edge cases for non-Chilean number formats.
- Missing retry tests in the HTTP client.
- Duplicate proposal entries when search results repeat a SKU.
- Issues never auto-close when a problem recovers.
- `dist/` is not cleaned between builds.
