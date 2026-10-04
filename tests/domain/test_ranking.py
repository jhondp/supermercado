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
    ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"], min_coverage=0.0)
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
    ranking = rank_stores(current, [], BASKET, STORES, min_coverage=0.0)
    assert ranking.no_data == ["tottus"]
    assert [t.store for t in ranking.ranked] == ["lider", "jumbo"]
    assert ranking.comparable_items == ["rice"]


def test_no_comparable_items_means_no_ranking() -> None:
    current = [obs("jumbo", "rice", 1810), obs("lider", "milk", 950)]
    ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"], min_coverage=0.0)
    assert ranking.ranked == []
    assert ranking.comparable_items == []


def test_change_vs_previous_week_uses_the_same_items() -> None:
    current = [obs("jumbo", "rice", 1810), obs("lider", "rice", 1190)]
    previous = [
        obs("jumbo", "rice", 1790, week="2026-W39"),
        obs("jumbo", "milk", 900, week="2026-W39"),
    ]
    ranking = rank_stores(current, previous, BASKET, ["jumbo", "lider"], min_coverage=0.0)
    changes = {t.store: t.change for t in ranking.ranked}
    assert changes == {"jumbo": 20, "lider": None}


def test_ties_keep_configured_store_order() -> None:
    current = [obs("lider", "rice", 1000), obs("jumbo", "rice", 1000)]
    ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"], min_coverage=0.0)
    assert [t.store for t in ranking.ranked] == ["jumbo", "lider"]


def test_basket_total_rounds_half_up_and_returns_none_when_item_missing() -> None:
    current = [obs("jumbo", "rice", 1001), obs("jumbo", "spaghetti", 2501)]
    half = make_item("rice", reference_qty=0.5)
    assert basket_total(current, "jumbo", [half]) == 501
    assert basket_total(current, "jumbo", [RICE, MILK]) is None


def test_store_below_coverage_threshold_is_not_ranked_and_does_not_shrink_basket() -> None:
    current = [
        obs("jumbo", "rice", 1810),
        obs("jumbo", "spaghetti", 2475),
        obs("jumbo", "milk", 990),
        obs("tottus", "rice", 1700),
        obs("tottus", "spaghetti", 2400),
        obs("tottus", "milk", 950),
        obs("lider", "rice", 1190),
    ]
    ranking = rank_stores(current, [], BASKET, STORES)
    assert [t.store for t in ranking.ranked] == ["tottus", "jumbo"]
    assert ranking.insufficient_coverage == ["lider"]
    assert ranking.comparable_items == ["rice", "spaghetti", "milk"]


def test_coverage_counts_only_ok_and_available_rows() -> None:
    current = [
        obs("jumbo", "rice", 1810),
        obs("jumbo", "spaghetti", 2475),
        obs("jumbo", "milk", 990),
        obs("lider", "rice", 1190),
        obs("lider", "spaghetti", 2600, available=False),
        obs("lider", "milk", 950, status=Status.SUSPICIOUS),
    ]
    ranking = rank_stores(current, [], BASKET, ["jumbo", "lider"])
    assert ranking.insufficient_coverage == ["lider"]
    assert [t.store for t in ranking.ranked] == ["jumbo"]
