"""Command line entry point: python -m supermercado <command>."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from supermercado.config import ConfigError, load_config
from supermercado.pipeline.collect import collect, iso_week
from supermercado.pipeline.report import report_to_dict
from supermercado.pipeline.storage import previous_unit_prices, write_week
from supermercado.stores import build_adapters


def _now() -> datetime:
    return datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="supermercado")
    parser.add_argument("--config", type=Path, default=Path("config"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    sub = parser.add_subparsers(dest="command", required=True)

    collect_cmd = sub.add_parser(
        "collect", help="fetch approved SKUs and write this week's snapshot"
    )
    collect_cmd.add_argument("--store", help="collect a single store (manual fallback)")
    collect_cmd.add_argument("--report", type=Path, default=Path("build/report.json"))
    return parser


def _cmd_collect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    adapters = build_adapters(config, only=args.store)
    now = _now()
    week = iso_week(now)
    cleared = {(c.week, c.store, c.item_id) for c in config.cleared}
    previous = previous_unit_prices(args.data, week, cleared=cleared)
    result = collect(config, adapters, now=now, previous=previous)
    path = write_week(args.data, week, result.observations, replace_stores=result.collected_stores)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report_to_dict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{week}: {len(result.observations)} observations, {len(result.failures)} store failures")
    if path is not None:
        print(f"written {path}")
    for failure in result.failures:
        print(f"FAILED {failure.store}: {failure.error_class}: {failure.message}", file=sys.stderr)
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "collect": _cmd_collect,
}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
