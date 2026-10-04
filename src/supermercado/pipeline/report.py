"""Machine-readable collection report consumed by the weekly workflow."""

from __future__ import annotations

from typing import Any

from supermercado.pipeline.collect import CollectResult


def report_to_dict(result: CollectResult) -> dict[str, Any]:
    return {
        "week": result.week,
        "observations": len(result.observations),
        "collected_stores": sorted(result.collected_stores),
        "failures": [
            {
                "store": f.store,
                "error_class": f.error_class,
                "message": f.message,
                "at": f.at.isoformat(),
            }
            for f in result.failures
        ],
        "alerts": [
            {"store": a.store, "item_id": a.item_id, "message": a.message} for a in result.alerts
        ],
        "dropped": list(result.dropped),
    }
