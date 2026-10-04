"""Static site build: Parquet (read with DuckDB) -> Jinja templates -> dist/."""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb
from jinja2 import Environment, FileSystemLoader, select_autoescape

from supermercado.config import AppConfig
from supermercado.domain.models import BasketItem, Category, PriceObservation, Status, Unit
from supermercado.domain.ranking import MIN_COVERAGE, rank_stores
from supermercado.domain.validation import apply_clearances
from supermercado.site.format import format_change, format_clp, format_date_es

PACKAGE_DIR = Path(__file__).parent
UNIT_LABELS = {Unit.KG: "kg", Unit.L: "L", Unit.M: "m", Unit.UNIT: "un"}
CATEGORY_LABELS = {
    Category.PANTRY: "Despensa",
    Category.DAIRY_EGGS: "Lácteos y huevos",
    Category.BAKERY: "Panadería",
    Category.MEAT: "Carnes",
    Category.CLEANING: "Limpieza",
    Category.HYGIENE: "Higiene",
}


@dataclass(frozen=True)
class Cell:
    text: str
    css: str = ""


def load_observations(data_dir: Path) -> list[PriceObservation]:
    prices = data_dir / "prices"
    if not any(prices.glob("*.parquet")):
        return []
    pattern = str(prices / "*.parquet").replace("'", "''")
    con = duckdb.connect()
    try:
        table = con.execute(
            f"SELECT * FROM read_parquet('{pattern}') ORDER BY week, store, item_id"
        ).to_arrow_table()
    finally:
        con.close()
    return [PriceObservation.model_validate(row) for row in table.to_pylist()]


def chart_data(
    item_id: str,
    observations: Sequence[PriceObservation],
    stores: Sequence[str],
    names: dict[str, str],
) -> dict[str, Any]:
    rows = [o for o in observations if o.item_id == item_id]
    series = []
    for store in stores:
        points: list[dict[str, Any]] = []
        # Compared against the last *plotted* SKU so a change that happens in a week
        # that is not plotted (under review, out of stock) still marks the next point.
        plotted_sku: str | None = None
        for obs in sorted((o for o in rows if o.store == store), key=lambda o: o.week):
            if obs.status != Status.OK or not obs.available:
                continue
            changed = plotted_sku is not None and obs.sku != plotted_sku
            plotted_sku = obs.sku
            points.append(
                {
                    "week": obs.week,
                    "unit_price": obs.unit_price,
                    "sku": obs.sku,
                    "sku_changed": changed,
                    "status": obs.status.value,
                }
            )
        if points:
            series.append({"store": store, "label": names[store], "points": points})
    weeks = sorted({p["week"] for entry in series for p in entry["points"]})
    return {"weeks": weeks, "series": series}


def _sku_changes(chart: dict[str, Any]) -> list[dict[str, str]]:
    changes = []
    for series in chart["series"]:
        points = series["points"]
        for before, after in zip(points, points[1:], strict=False):
            if after["sku_changed"]:
                changes.append(
                    {
                        "store": series["store"],
                        "week": after["week"],
                        "previous": before["sku"],
                        "sku": after["sku"],
                    }
                )
    return changes


def _safe_url(url: str | None) -> str | None:
    return url if url and urlparse(url).scheme in ("http", "https") else None


def _latest_rows(
    item_id: str, observations: Sequence[PriceObservation], stores: Sequence[str]
) -> list[dict[str, Any]]:
    latest: dict[str, PriceObservation] = {}
    for obs in sorted(observations, key=lambda o: o.week):
        if obs.item_id == item_id:
            latest[obs.store] = obs
    rows = []
    for store in stores:
        obs = latest.get(store)
        if obs is None:
            continue
        label = (
            "agotado" if not obs.available else "en revisión" if obs.status != Status.OK else None
        )
        rows.append({"obs": obs, "label": label, "url": _safe_url(obs.url)})
    return rows


def _cell(
    item: BasketItem, store: str, obs: PriceObservation | None, config: AppConfig, best: int | None
) -> Cell:
    if store not in config.matches.get(item.id, {}):
        return Cell("sin match", "muted")
    if obs is None:
        return Cell("sin datos", "muted")
    if not obs.available:
        return Cell("agotado", "muted")
    if obs.status != Status.OK:
        return Cell("en revisión", "warn")
    text = f"{format_clp(obs.unit_price)}/{UNIT_LABELS[item.unit]}"
    return Cell(text, "best" if obs.unit_price == best else "")


def _product_rows(
    config: AppConfig, current: Sequence[PriceObservation], stores: Sequence[str]
) -> list[dict[str, Any]]:
    by_key = {(o.store, o.item_id): o for o in current}
    rows = []
    for item in config.basket:
        usable = [
            o.unit_price
            for s in stores
            if (o := by_key.get((s, item.id))) is not None and o.status == Status.OK and o.available
        ]
        best = min(usable, default=None)
        cells = [_cell(item, s, by_key.get((s, item.id)), config, best) for s in stores]
        rows.append({"item": item, "category": item.category.value, "cells": cells})
    return rows


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(PACKAGE_DIR / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["clp"] = format_clp
    env.filters["change"] = format_change
    return env


def _script_json(data: dict[str, Any]) -> str:
    # Escaping every "<" covers "</script>" and "<!--" (which would switch the HTML parser
    # into the script-data-escaped state) while staying valid JSON.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def _write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def render_site(config: AppConfig, observations: Sequence[PriceObservation], out_dir: Path) -> None:
    stores = config.enabled_stores()
    names = {store: cfg.name for store, cfg in config.stores.items()}
    weeks = sorted({o.week for o in observations})
    latest_week = weeks[-1] if weeks else None
    previous_week = weeks[-2] if len(weeks) > 1 else None
    current = [o for o in observations if o.week == latest_week]
    previous = [o for o in observations if o.week == previous_week]
    common: dict[str, Any] = {
        "week": latest_week,
        "updated": format_date_es(max(o.scraped_at for o in current)) if current else None,
        "store_names": names,
        "stores": stores,
        "comunas": {store: config.stores[store].comuna for store in stores},
        "basket_size": len(config.basket),
        "min_items": math.ceil(MIN_COVERAGE * len(config.basket)),
    }
    env = _environment()
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PACKAGE_DIR / "static", out_dir / "static", dirs_exist_ok=True)

    ranking = rank_stores(current, previous, config.basket, stores, min_coverage=MIN_COVERAGE)
    _write(
        out_dir / "index.html",
        env.get_template("index.html").render(root="./", page="home", ranking=ranking, **common),
    )
    _write(
        out_dir / "productos" / "index.html",
        env.get_template("products.html").render(
            root="../",
            page="products",
            rows=_product_rows(config, current, stores),
            categories=[(c.value, CATEGORY_LABELS[c]) for c in Category],
            **common,
        ),
    )
    product_template = env.get_template("product.html")
    for item in config.basket:
        chart = chart_data(item.id, observations, stores, names)
        _write(
            out_dir / "producto" / item.id / "index.html",
            product_template.render(
                root="../../",
                page="product",
                item=item,
                unit_label=UNIT_LABELS[item.unit],
                category_label=CATEGORY_LABELS[item.category],
                chart=chart,
                chart_json=_script_json(chart),
                latest=_latest_rows(item.id, observations, stores),
                sku_changes=_sku_changes(chart),
                **common,
            ),
        )
    _write(
        out_dir / "metodologia" / "index.html",
        env.get_template("methodology.html").render(root="../", page="methodology", **common),
    )


def build_site(config: AppConfig, data_dir: Path, out_dir: Path) -> None:
    cleared = {(c.week, c.store, c.item_id) for c in config.cleared}
    render_site(config, apply_clearances(load_observations(data_dir), cleared), out_dir)
