# Store locations (Santiago reference)

Prices differ by branch and delivery zone, so each chain is pinned to one explicit store or zone
in `config/stores.yaml`. Re-verify when a chain changes its website or when prices look off.

Status on 2026-10-04 (headless verification from a residential connection, no browser):

| Chain | `store_ref` | Comuna | How it was verified | Verified on |
|---|---|---|---|---|
| Jumbo | `jumboclj512` | pending-verification | `jumboclj512` is the seller the jumbo.cl home page uses before any address is chosen, and every `POST bff.jumbo.cl/catalog/plp` answer echoes it as the `storeId` filter in `metadata.searchEngineRequest`. No public endpoint maps the id to a branch (`bff.jumbo.cl/stores`, `/catalog/stores` and `www.jumbo.cl/api/stores` answer 404), so the comuna is unknown. | not yet |
| Santa Isabel | `pedrofontova` | Huechuraba | `pedrofontova` is in the seller list embedded in the santaisabel.cl home page; the `pedrofontova` slug matches the branch at Av. Pedro Fontova Norte 7789, Huechuraba (third-party listings: Waze, Tiendeo, Uber Eats). No store-id lookup confirms it. `sku:7665` on `bff.santaisabel.cl/catalog/plp` with this store returns the product with a price. | 2026-10-04 |
| Tottus | (empty) | pending-verification | `GET /s/browse/v1/search/cl?Ntt=arroz grado 2` with and without `politicalId=13` returned the same 48 products with identical prices, so the default answer looks chain-wide, but no zone id could be confirmed without the browser flow. Treat prices as Tottus online (default zone). | not yet |
| aCuenta | `580` | pending-verification | `storeReference: "580"` is accepted by `searchProducts` and `getProductsBySKU` (clientId `SUPER_BODEGA`) and returns stock per store, but the API exposes no store catalogue (`getStores` is not in the schema), so the branch behind `580` is unknown. | not yet |
| Unimarc | (none) | pending-verification | `POST /catalog/product/search` takes no store or sales-channel field and the answer carries none; prices may still depend on the address chosen in the browser. Follow-up: capture the browser request after choosing a Santiago address. | not yet |
| Lider | `0000000057` | Santiago | Product page fetched with the cookie `walmart.nearestLatLng=-33.4521,-70.6536` (Santiago Centro): `__NEXT_DATA__ ... pageMetadata.location` = `{"storeId": "0000000057", "city": "Santiago", "stateOrProvinceCode": "Región Metropolitana"}` and the fulfillment text reads "Despacho desde local a Santiago". | 2026-10-04 |

Smoke SKUs (`smoke_sku` in `config/stores.yaml`), all returned live with a price on 2026-10-04:
Jumbo `1626` (Arroz Grado 2 Tucapel 1 kg), Santa Isabel `7665` (Arroz Grado 2 Máxima 1 kg),
Tottus `110609848` (Arroz Tucapel G2 1 kg), aCuenta `2411` (Arroz Grado 2 Tucapel 1 kg),
Unimarc `7732` (Arroz Tucapel gran selección G2 1 kg), Lider `00780142021013`
(Arroz Grado 2 Grano Largo Bolsa 1 kg, `smoke_url` points at its product page).

Lider note: super.lider.cl sits behind Akamai Bot Manager. On 2026-10-04 a bare request got the
"Robot or human?" challenge, a request with full browser navigation headers got the page, and
after a dozen requests every request was challenged for a while. The adapter raises
`BlockedError` on the challenge; expect intermittent Lider failures in the weekly issue.

## Judgment calls

Both rest on live observation on 2026-10-04 (Task 17 report), not yet on recorded fixtures that
contain such promotions:

- **aCuenta `specialPrice`** is treated as an unconditional promotion (its condition carries
  quantity 0, aCuenta has no loyalty card, and the schema has no payment-method field). Disable it
  by clearing `unconditional_promo_types` for aCuenta in `config/stores.yaml`.
- **Unimarc "Exclusivo .cl"** is treated as an open web offer (`promo_price`); every other
  promotional tag, including "Club Unimarc", stays `card_price` and is never ranked.

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

When a pending chain gets pinned, set `comuna` and `location_verified` in `config/stores.yaml`
and remove the store from `LOCATION_PENDING` in `tests/test_store_locations.py`.
