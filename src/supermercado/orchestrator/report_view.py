"""Human-readable (Spanish) summaries of build/report.json."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

IP_BLOCK_CLASSES = frozenset({"ApiKeyRejected", "BlockedError"})
MAX_LISTED = 20


def looks_ip_blocked(failure: Mapping[str, Any]) -> bool:
    if failure.get("error_class") in IP_BLOCK_CLASSES:
        return True
    return failure.get("error_class") == "HttpError" and "HTTP 403" in str(failure.get("message"))


def _failures(report: Mapping[str, Any]) -> list[str]:
    failures = report.get("failures") or []
    if not failures:
        return ["Fallas: ninguna."]
    lines = [f"Fallas ({len(failures)}):"]
    for failure in failures:
        lines.append(
            f"  - {failure.get('store')}: {failure.get('error_class')}: {failure.get('message')}"
        )
    blocked = sorted({str(f.get("store")) for f in failures if looks_ip_blocked(f)})
    for store in blocked:
        lines.append(
            f"  → {store}: probablemente es un bloqueo de IP (el súper rechaza la conexión de "
            "este equipo o servidor). Desde una conexión doméstica suele funcionar; vuelve a "
            f"recolectar solo ese súper (opción 3 → {store})."
        )
    return lines


def _listed(title: str, rows: list[str]) -> list[str]:
    if not rows:
        return []
    lines = [f"{title} ({len(rows)}):"] + [f"  - {row}" for row in rows[:MAX_LISTED]]
    if len(rows) > MAX_LISTED:
        lines.append(f"  … y {len(rows) - MAX_LISTED} más.")
    return lines


def collect_summary(report: Mapping[str, Any]) -> list[str]:
    """Short summary printed right after a collection run."""
    stores = ", ".join(report.get("collected_stores") or []) or "ninguno"
    return [
        f"Semana {report.get('week', '?')}: {report.get('observations', 0)} precios "
        f"guardados (súper recolectados: {stores}).",
        *_failures(report),
        f"Descartados: {len(report.get('dropped') or [])}.",
    ]


def render_report(report: Mapping[str, Any]) -> list[str]:
    """Full listing of failures, size alerts and dropped rows."""
    alerts = [
        f"{a.get('store')}/{a.get('item_id')}: {a.get('message')}"
        for a in report.get("alerts") or []
    ]
    dropped = [str(row) for row in report.get("dropped") or []]
    lines = [
        f"Semana {report.get('week', '?')} · {report.get('observations', 0)} precios · "
        f"súper recolectados: {', '.join(report.get('collected_stores') or []) or 'ninguno'}",
        *_failures(report),
        *_listed("Alertas de tamaño (posible reduflación)", alerts),
        *_listed("Filas descartadas", dropped),
    ]
    if not alerts and not dropped:
        lines.append("Sin alertas de tamaño ni filas descartadas.")
    return lines
