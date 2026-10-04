"""Jumbo adapter (Cencosud BFF)."""

from supermercado.stores.cencosud import CencosudAdapter


class JumboAdapter(CencosudAdapter):
    store_id = "jumbo"
    site_url = "https://www.jumbo.cl"
