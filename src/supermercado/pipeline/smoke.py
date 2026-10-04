"""Contract smoke test: one known SKU per store must still parse with a price."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from supermercado.config import AppConfig
from supermercado.stores.base import StoreAdapter


@dataclass(frozen=True)
class SmokeResult:
    store: str
    ok: bool
    detail: str


def _check(store_id: str, sku: str | None, adapter: StoreAdapter) -> SmokeResult:
    if not sku:
        return SmokeResult(store_id, False, "smoke_sku not configured in config/stores.yaml")
    try:
        listings = adapter.fetch([sku])
    except Exception as exc:  # report every failure class, never crash the run
        return SmokeResult(store_id, False, f"{type(exc).__name__}: {exc}")
    listing = next((item for item in listings if item.sku == sku), None)
    if listing is None:
        return SmokeResult(store_id, False, f"sku {sku} missing from the response")
    if not listing.name or not listing.price or listing.price <= 0:
        return SmokeResult(store_id, False, f"sku {sku} parsed without a name or price")
    return SmokeResult(store_id, True, f"{listing.name} · ${listing.price}")


def smoke(config: AppConfig, adapters: Mapping[str, StoreAdapter]) -> list[SmokeResult]:
    return [
        _check(store_id, config.stores[store_id].smoke_sku, adapter)
        for store_id, adapter in adapters.items()
    ]


def _cell(text: str) -> str:
    """Store error text is untrusted: keep it on one line and inside its cell."""
    return " ".join(text.split()).replace("|", "\\|")


def render_smoke_table(results: Sequence[SmokeResult]) -> str:
    lines = ["| Store | Result | Detail |", "|---|---|---|"]
    for result in results:
        status = "ok" if result.ok else "FAILED"
        lines.append(f"| {_cell(result.store)} | {status} | {_cell(result.detail)} |")
    return "\n".join(lines) + "\n"
