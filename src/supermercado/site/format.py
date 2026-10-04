"""Spanish (Chile) display formatting for the site."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SANTIAGO = ZoneInfo("America/Santiago")
MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def format_clp(amount: int | None) -> str:
    if amount is None:
        return "—"
    sign = "−" if amount < 0 else ""
    return f"{sign}${abs(amount):,}".replace(",", ".")


def format_change(delta: int | None) -> str:
    if delta is None:
        return "sin semana anterior"
    if delta == 0:
        return "sin cambio vs semana anterior"
    sign = "+" if delta > 0 else "−"
    return f"{sign}{format_clp(abs(delta))} vs semana anterior"


def format_date_es(moment: datetime) -> str:
    local = moment.astimezone(SANTIAGO)
    return f"{local.day} de {MONTHS_ES[local.month - 1]} de {local.year}"
