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
from supermercado.pipeline.propose import propose, render_pr_body, render_proposals
from supermercado.pipeline.report import render_issue_body, report_to_dict
from supermercado.pipeline.storage import previous_unit_prices, write_week
from supermercado.site.build import build_site
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
    build_cmd = sub.add_parser("build", help="render the static site into --out")
    build_cmd.add_argument("--out", type=Path, default=Path("dist"))
    issue_cmd = sub.add_parser("issue-body", help="print the failure issue body for a report")
    issue_cmd.add_argument("--report", type=Path, default=Path("build/report.json"))
    propose_cmd = sub.add_parser("propose", help="write candidate matches into matches.yaml")
    propose_cmd.add_argument("--store", help="propose for a single store")
    propose_cmd.add_argument("--body", type=Path, help="also write the pull request body here")
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


def _cmd_build(args: argparse.Namespace) -> int:
    build_site(load_config(args.config), args.data, args.out)
    print(f"site written to {args.out}")
    return 0


def _cmd_issue_body(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    sys.stdout.write(render_issue_body(report))
    return 0


def _cmd_propose(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    adapters = build_adapters(config, only=args.store)
    now = _now()
    proposals, failures = propose(config, adapters, now=now)
    path = args.config / "matches.yaml"
    path.write_text(
        render_proposals(
            path.read_text(encoding="utf-8"), proposals, week=iso_week(now), today=now.date()
        ),
        encoding="utf-8",
    )
    if args.body is not None:
        manual = [
            config.stores[name].name
            for name, adapter in adapters.items()
            if not adapter.supports_search
        ]
        args.body.parent.mkdir(parents=True, exist_ok=True)
        args.body.write_text(render_pr_body(proposals, failures, manual), encoding="utf-8")
    print(f"{len(proposals)} candidates written to {path}")
    for failure in failures:
        print(f"FAILED {failure.store}: {failure.error_class}: {failure.message}", file=sys.stderr)
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "collect": _cmd_collect,
    "build": _cmd_build,
    "issue-body": _cmd_issue_body,
    "propose": _cmd_propose,
}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
