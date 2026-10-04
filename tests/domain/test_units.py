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
