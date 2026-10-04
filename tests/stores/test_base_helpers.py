import math

import pytest

from supermercado.stores.base import positive_multiplier


def test_missing_multiplier_defaults_to_one() -> None:
    assert positive_multiplier(None, "unitMultiplier") == 1.0


@pytest.mark.parametrize("value", [1, 0.5, 2.25])
def test_positive_finite_multiplier_is_returned_as_float(value) -> None:
    result = positive_multiplier(value, "unitMultiplier")
    assert isinstance(result, float)
    assert result == value


@pytest.mark.parametrize("value", [True, "1.5", "abc", [1]])
def test_non_numeric_multiplier_is_a_type_error(value) -> None:
    with pytest.raises(TypeError, match="averageWeight"):
        positive_multiplier(value, "averageWeight")


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf, -math.inf])
def test_non_positive_or_non_finite_multiplier_is_a_value_error(value) -> None:
    with pytest.raises(ValueError, match="clickMultiplier"):
        positive_multiplier(value, "clickMultiplier")
