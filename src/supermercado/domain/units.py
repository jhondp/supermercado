"""Unit normalization and price parsing. Pure functions, no I/O."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from supermercado.domain.models import Unit


class UnknownUnitError(ValueError):
    """Raised when a unit string cannot be mapped to a canonical Unit."""


_ALIASES: dict[str, tuple[Unit, float]] = {
    "kg": (Unit.KG, 1.0),
    "kgs": (Unit.KG, 1.0),
    "kilo": (Unit.KG, 1.0),
    "kilos": (Unit.KG, 1.0),
    "g": (Unit.KG, 0.001),
    "gr": (Unit.KG, 0.001),
    "grs": (Unit.KG, 0.001),
    "gramos": (Unit.KG, 0.001),
    "l": (Unit.L, 1.0),
    "lt": (Unit.L, 1.0),
    "lts": (Unit.L, 1.0),
    "litro": (Unit.L, 1.0),
    "litros": (Unit.L, 1.0),
    "ml": (Unit.L, 0.001),
    "cc": (Unit.L, 0.001),
    "m": (Unit.M, 1.0),
    "mt": (Unit.M, 1.0),
    "mts": (Unit.M, 1.0),
    "metros": (Unit.M, 1.0),
    "un": (Unit.UNIT, 1.0),
    "und": (Unit.UNIT, 1.0),
    "unid": (Unit.UNIT, 1.0),
    "unidad": (Unit.UNIT, 1.0),
    "unidades": (Unit.UNIT, 1.0),
    "u": (Unit.UNIT, 1.0),
    "unit": (Unit.UNIT, 1.0),
}

_NUM = r"(\d+(?:[.,]\d+)?)"
_MEASURE = r"(kgs?|kilos?|gramos|grs?|g|ml|cc|litros?|lts?|l|metros|mts?|m)"
_ROLLS_RE = re.compile(
    rf"(\d+)\s*(?:rollos?|un\b\.?|unid\w*)\D*?{_NUM}\s*(?:metros|mts?|m)\b", re.IGNORECASE
)
_PACK_RE = re.compile(rf"(\d+)\s*x\s*{_NUM}\s*{_MEASURE}\b", re.IGNORECASE)
_SIZE_RE = re.compile(rf"{_NUM}\s*{_MEASURE}\b", re.IGNORECASE)
_COUNT_RE = re.compile(
    r"\bx\s*(\d+)\b|\b(\d+)\s*(?:un|unid|unidades|bolsitas|sobres|huevos)\b", re.IGNORECASE
)
_THOUSANDS_RE = re.compile(r"\d{1,3}\.\d{3}")
_CLP_RE = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+")


def normalize(size: float, raw_unit: str) -> tuple[float, Unit]:
    """Convert a size in any supported unit to (size, canonical unit)."""
    key = raw_unit.strip().lower().rstrip(".")
    if key not in _ALIASES:
        raise UnknownUnitError(raw_unit)
    unit, factor = _ALIASES[key]
    return round(size * factor, 6), unit


def _number(raw: str, unit_key: str) -> float:
    # "1.000 ml" means one thousand millilitres, not one.
    if _THOUSANDS_RE.fullmatch(raw) and _ALIASES[unit_key.lower()][1] < 1:
        return float(raw.replace(".", ""))
    return float(raw.replace(",", "."))


def parse_size(text: str) -> tuple[float, Unit] | None:
    """Extract the package size from a product name or format string."""
    if match := _ROLLS_RE.search(text):
        meters = int(match.group(1)) * float(match.group(2).replace(",", "."))
        return normalize(meters, "m")
    if match := _PACK_RE.search(text):
        count = int(match.group(1))
        return normalize(count * _number(match.group(2), match.group(3)), match.group(3))
    if match := _SIZE_RE.search(text):
        return normalize(_number(match.group(1), match.group(2)), match.group(2))
    if match := _COUNT_RE.search(text):
        return normalize(float(match.group(1) or match.group(2)), "un")
    return None


def parse_clp(value: str | int | float) -> int:
    """Parse a CLP amount such as "1.890" or "$2.790 x Kg" into an int."""
    if isinstance(value, bool):
        raise TypeError("bool is not a price")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    match = _CLP_RE.search(value)
    if match is None:
        raise ValueError(f"no CLP amount in {value!r}")
    return int(match.group(0).replace(".", ""))


def compute_unit_price(effective_price: int, size: float) -> int:
    """Price per canonical unit, rounded half-up to whole CLP."""
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    ratio = Decimal(effective_price) / Decimal(str(size))
    return int(ratio.quantize(Decimal(1), rounding=ROUND_HALF_UP))
