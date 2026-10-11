# Basket Expansion Decision Log — 2026-10-11

Branch `feat/basket-expansion`. The basket grows from 23 to 36 items. This entry follows the format of `2026-10-04-mvp-decisions.md`.

## 1. What changed

| Category | New items (id) |
|---|---|
| Produce (new `produce` category, "Frutas y verduras") | `potato`, `onion`, `tomato`, `carrot`, `banana`, `apple` (bulk, priced per kg), `lettuce` (per unit) |
| Pantry | `oats` (1 kg, accepts 0.5–1 kg), `canned_mackerel` (425 g) |
| Dairy and eggs | `butter` (250 g), `yogurt` (125 g cup, accepts 110–125 g) |
| Bakery | `sliced_bread` (white, 600 g, accepts 0.5–0.75 kg) |
| Hygiene | `diapers` (size G, 50 units, normalized per unit, accepts packs of 20–120) |

Every existing item stays, so the price history keeps going.

## 2. Decisions

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| 1 | Add fresh produce. | Fruit and vegetables are a large share of real household spending. Leaving them out made the basket favor chains that are cheap on packaged goods. | Bulk produce changes in quality and season more than packaged goods do, so weekly totals get noisier. |
| 2 | Keep `deodorant`. | Removing an item breaks the history of past totals. Continuity matters more than how essential the item is. | None. |
| 3 | Produce follows the existing bulk-item pattern (`bread`, `chicken_thigh`, `posta`): unit `kg`, `reference_qty: 1.0`, no `size_range`, and exclusions only. | Bulk listings are normalized to 1 kg by the adapters. | Pre-packed bags (for example a 2 kg potato bag) can also match. They are compared by unit price, but a reviewer may prefer the bulk SKU. |
| 4 | Ranking coverage counts only basket items that have **an approved match in at least one enabled store** (`AppConfig.matched_items()`). The 80% rule and `rank_stores` are unchanged. | With all 36 items counted, the threshold rises to 29. No store reaches it on the 2026-W40 data, so the ranking would be empty. Items nobody has matched yet cannot be priced anywhere, so leaving them out is fair to every store. The rule depends on config, not on that week's observations, so a week where a scraper fails still counts against the store. | See section 3. |
| 5 | The methodology page shows the effective base ("19 de 23 productos" today). The home page still says "Comparando N de 36 productos". | Visitors see the real threshold and also see that the basket is larger than what is compared so far. | Copy tweak. |
| 6 | The orchestrator's approval target stays at 80% of the **full** basket (29 of 36). | It is a to-do target. It should push reviewers to approve the new items. | The menu shows every store as short until the new items are approved. |

## 3. Known transitional effect

When a new item gets its first approved match, it enters the coverage base for **every** store. For example, approving `potato` only at Jumbo raises the base to 24 and the threshold to 20. Santa Isabel prices 19 items today, so it would drop out until it also has `potato`.

**Mitigation:** approve each new item across all stores in the same PR, or accept that the ranking can be thin for a week. If this happens often, the next step is an explicit per-item flag (for example `ranked_since: <week>`).

## 4. Still to do

- **Matches for the 13 new items are not approved yet.** `config/matches.yaml` is unchanged. The weekly bot will propose candidates, and a person approves them as usual (Lider by hand, with a URL).
- Check the exclusion lists against the first real proposals:
  - `lettuce` (`size_range: [1, 1]`) assumes each adapter reports lettuce as 1 unit.
  - `diapers` assumes each adapter parses the unit count of the pack.
  - `yogurt` assumes each adapter reports the size of a single cup, not a multipack.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` still say 23 items. They are dated snapshots and were left as they are.
