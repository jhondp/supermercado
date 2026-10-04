from datetime import UTC, datetime

from factories import make_item, make_listing, make_match, make_obs
from supermercado.domain.models import Status, Unit
from supermercado.domain.validation import (
    apply_clearances,
    build_observation,
    effective_price,
    is_suspicious,
)

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)


def observe(listing, *, match=None, item=None, previous=None):
    return build_observation(
        week="2026-W40",
        scraped_at=NOW,
        store="jumbo",
        item=item or make_item(),
        match=match or make_match(),
        listing=listing,
        previous_unit_price=previous,
    )


def test_effective_price_uses_regular_price_without_promo() -> None:
    assert effective_price(make_listing(price=1810)) == 1810


def test_effective_price_uses_lower_unconditional_promo() -> None:
    assert effective_price(make_listing(price=1590, promo_price=1290)) == 1290


def test_effective_price_ignores_promo_not_below_price() -> None:
    assert effective_price(make_listing(price=1590, promo_price=1590)) == 1590
    assert effective_price(make_listing(price=1590, promo_price=0)) == 1590


def test_effective_price_is_none_for_missing_or_non_positive_price() -> None:
    assert effective_price(make_listing(price=None)) is None
    assert effective_price(make_listing(price=0)) is None


def test_card_price_never_becomes_effective() -> None:
    assert effective_price(make_listing(price=1590, card_price=1150)) == 1590


def test_build_observation_ok_row() -> None:
    obs = observe(make_listing(price=1590, promo_price=1290, card_price=1150))
    assert obs is not None
    assert obs.status is Status.OK
    assert obs.week == "2026-W40"
    assert obs.price == 1590
    assert obs.promo_price == 1290
    assert obs.card_price == 1150
    assert obs.effective_price == 1290
    assert obs.unit_price == 1290
    assert obs.unit == "kg"
    assert obs.location == "santiago"


def test_build_observation_drops_row_without_price() -> None:
    assert observe(make_listing(price=None)) is None
    assert observe(make_listing(price=-5)) is None


def test_promo_not_stored_when_not_effective() -> None:
    obs = observe(make_listing(price=1590, promo_price=1700))
    assert obs is not None
    assert obs.promo_price is None


def test_size_change_beyond_tolerance_is_flagged() -> None:
    obs = observe(make_listing(size=0.9, price=1800), match=make_match(size=1.0))
    assert obs is not None
    assert obs.status is Status.SIZE_CHANGED
    assert obs.size == 0.9
    assert obs.unit_price == 2000


def test_size_within_tolerance_is_ok() -> None:
    obs = observe(make_listing(size=0.995), match=make_match(size=1.0))
    assert obs is not None
    assert obs.status is Status.OK


def test_unknown_listing_size_falls_back_to_approved_size() -> None:
    obs = observe(make_listing(size=None, unit=None, price=990), match=make_match(size=0.4))
    assert obs is not None
    assert obs.size == 0.4
    assert obs.unit_price == 2475
    assert obs.status is Status.OK


def test_listing_in_other_unit_falls_back_to_approved_size() -> None:
    item = make_item("toilet_paper", unit=Unit.M, reference_qty=120.0)
    obs = observe(
        make_listing(size=4.0, unit=Unit.UNIT, price=3000),
        item=item,
        match=make_match(size=120.0),
    )
    assert obs is not None
    assert obs.size == 120.0
    assert obs.unit == "m"
    assert obs.unit_price == 25


def test_jump_over_fifty_percent_is_suspicious() -> None:
    obs = observe(make_listing(price=1610), previous=1000)
    assert obs is not None
    assert obs.status is Status.SUSPICIOUS


def test_exactly_fifty_percent_is_not_suspicious() -> None:
    assert is_suspicious(1500, 1000) is False
    assert is_suspicious(500, 1000) is False
    assert is_suspicious(499, 1000) is True


def test_no_previous_week_is_not_suspicious() -> None:
    assert is_suspicious(5000, None) is False


def test_size_change_takes_precedence_over_suspicious() -> None:
    obs = observe(make_listing(size=0.5, price=1810), previous=1000)
    assert obs is not None
    assert obs.status is Status.SIZE_CHANGED


def test_apply_clearances_marks_cleared_rows_ok() -> None:
    flagged = make_obs(status=Status.SUSPICIOUS)
    other = make_obs(store="lider", status=Status.SUSPICIOUS)
    result = apply_clearances([flagged, other], {("2026-W40", "jumbo", "rice")})
    assert [o.status for o in result] == [Status.OK, Status.SUSPICIOUS]
