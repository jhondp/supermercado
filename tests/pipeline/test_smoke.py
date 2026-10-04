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


def test_table_cells_cannot_break_the_row() -> None:
    cfg = config(jumbo=make_store_config("Jumbo", smoke_sku="1626"))
    error = ResponseShapeError("bad | shape\n<script>x</script>\r\nsecond line")
    table = render_smoke_table(smoke(cfg, {"jumbo": FakeAdapter("jumbo", error=error)}))
    assert len(table.splitlines()) == 3
    assert "bad \\| shape" in table
