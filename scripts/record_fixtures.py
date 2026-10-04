"""Record live store responses into tests/fixtures/<store>/.

Run manually, once per store, from a residential IP (never from CI):

    uv run python scripts/record_fixtures.py jumbo --query "arroz grado 2" --sku 1626
    uv run python scripts/record_fixtures.py lider --sku 00780142021013

Writes recorded_search.(json|html) and/or recorded_fetch.(json|html). Commit the files;
tests that parse them are skipped until they exist.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from supermercado.config import load_config
from supermercado.stores import build_adapters

ROOT = Path(__file__).resolve().parents[1]


def _save(directory: Path, stem: str, text: str) -> Path:
    suffix = ".html" if text.lstrip().startswith("<") else ".json"
    path = directory / f"{stem}{suffix}"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("store")
    parser.add_argument("--query", help="search text to record (stores with search only)")
    parser.add_argument("--sku", help="single SKU to record through the fetch path")
    parser.add_argument("--config", type=Path, default=ROOT / "config")
    args = parser.parse_args()

    adapter = build_adapters(load_config(args.config), only=args.store)[args.store]
    out_dir = ROOT / "tests" / "fixtures" / args.store
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.query:
        print("saved", _save(out_dir, "recorded_search", adapter.raw_search(args.query).text))
    if args.sku:
        print("saved", _save(out_dir, "recorded_fetch", adapter.raw_fetch(args.sku).text))


if __name__ == "__main__":
    main()
