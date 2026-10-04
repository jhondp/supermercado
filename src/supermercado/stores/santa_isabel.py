"""Santa Isabel adapter (Cencosud BFF; `store` is mandatory in the request body)."""

from supermercado.stores.cencosud import CencosudAdapter


class SantaIsabelAdapter(CencosudAdapter):
    store_id = "santa_isabel"
    site_url = "https://www.santaisabel.cl"
