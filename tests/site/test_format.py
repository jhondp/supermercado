from datetime import UTC, datetime

import pytest

from supermercado.site.format import format_change, format_clp, format_date_es


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(1890, "$1.890"), (0, "$0"), (1234567, "$1.234.567"), (-100, "−$100"), (None, "—")],
)
def test_format_clp(amount, expected) -> None:
    assert format_clp(amount) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (None, "sin semana anterior"),
        (0, "sin cambio vs semana anterior"),
        (20, "+$20 vs semana anterior"),
        (-1500, "−$1.500 vs semana anterior"),
    ],
)
def test_format_change(delta, expected) -> None:
    assert format_change(delta) == expected


def test_format_date_uses_santiago_time() -> None:
    assert format_date_es(datetime(2026, 9, 28, 9, 0, tzinfo=UTC)) == "28 de septiembre de 2026"
    assert format_date_es(datetime(2026, 10, 5, 2, 0, tzinfo=UTC)) == "4 de octubre de 2026"
