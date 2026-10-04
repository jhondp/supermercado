"""Machine-readable collection report consumed by the weekly workflow."""

from __future__ import annotations

from collections.abc import Mapping
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


def _cell(text: object) -> str:
    cleaned = str(text).replace("\r", " ").replace("\n", " ").replace("`", "'")
    return cleaned.replace("|", "\\|").replace("@", "@\u200b")[:300]


def render_issue_body(report: Mapping[str, Any]) -> str:
    failures = report.get("failures") or []
    alerts = report.get("alerts") or []
    if not failures and not alerts:
        return ""
    lines = [f"## Weekly collection {report.get('week', '?')}", ""]
    if failures:
        lines += [
            "### Store failures",
            "",
            "| Store | Error class | Time (UTC) | Message |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {_cell(f['store'])} | `{_cell(f['error_class'])}` | {_cell(f['at'])} | {_cell(f['message'])} |"
            for f in failures
        ]
        lines += [
            "",
            "Manual fallback from a residential IP: "
            "`uv run python -m supermercado collect --store <id>`, then commit `data/prices/`.",
            "",
        ]
    if alerts:
        lines += [
            "### Size changes (possible shrinkflation)",
            "",
            "| Store | Item | Detail |",
            "|---|---|---|",
        ]
        lines += [
            f"| {_cell(a['store'])} | {_cell(a['item_id'])} | {_cell(a['message'])} |"
            for a in alerts
        ]
        lines += ["", "Confirm the product and update `size` in `config/matches.yaml`."]
    return "\n".join(lines).rstrip() + "\n"
