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
