"""One immutable Parquet file per ISO week: data/prices/YYYY-Www.parquet."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from supermercado.domain.models import PriceObservation, Status

SCHEMA = pa.schema(
    [
        ("week", pa.string()),
        ("scraped_at", pa.timestamp("us", tz="UTC")),
        ("location", pa.string()),
        ("store", pa.string()),
        ("item_id", pa.string()),
        ("sku", pa.string()),
        ("product_name", pa.string()),
        ("brand", pa.string()),
        ("url", pa.string()),
        ("size", pa.float64()),
        ("unit", pa.string()),
        ("price", pa.int64()),
        ("promo_price", pa.int64()),
        ("card_price", pa.int64()),
        ("effective_price", pa.int64()),
        ("unit_price", pa.int64()),
        ("available", pa.bool_()),
        ("status", pa.string()),
    ]
)


def week_path(data_dir: Path, week: str) -> Path:
    return data_dir / "prices" / f"{week}.parquet"


def list_weeks(data_dir: Path) -> list[str]:
    return sorted(path.stem for path in (data_dir / "prices").glob("*.parquet"))


def _record(obs: PriceObservation) -> dict[str, object]:
    data = obs.model_dump()
    data["status"] = obs.status.value
    return {name: data[name] for name in SCHEMA.names}


def read_week(data_dir: Path, week: str) -> list[PriceObservation]:
    path = week_path(data_dir, week)
    if not path.exists():
        return []
    return [PriceObservation.model_validate(row) for row in pq.read_table(path).to_pylist()]


def write_week(
    data_dir: Path,
    week: str,
    observations: Iterable[PriceObservation],
    *,
    replace_stores: set[str],
) -> Path | None:
    """Replace the rows of `replace_stores` in this week's file, keeping every other store."""
    kept = [obs for obs in read_week(data_dir, week) if obs.store not in replace_stores]
    fresh = [obs for obs in observations if obs.store in replace_stores]
    rows = sorted(kept + fresh, key=lambda obs: (obs.store, obs.item_id))
    if not rows:
        return None
    path = week_path(data_dir, week)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([_record(obs) for obs in rows], schema=SCHEMA)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)
    return path


def previous_unit_prices(
    data_dir: Path,
    week: str,
    *,
    cleared: Collection[tuple[str, str, str]] = (),
) -> dict[tuple[str, str], int]:
    """Baseline per (store, item): the latest earlier observation that is ok or manually cleared.

    Suspicious/size-changed rows never become the baseline, so a persistent jump
    keeps being flagged until it is cleared in config/cleared.yaml.
    """
    baseline: dict[tuple[str, str], int] = {}
    for earlier in (w for w in list_weeks(data_dir) if w < week):
        for obs in read_week(data_dir, earlier):
            if obs.status is Status.OK or (obs.week, obs.store, obs.item_id) in cleared:
                baseline[(obs.store, obs.item_id)] = obs.unit_price
    return baseline
