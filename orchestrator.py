"""Interactive orchestrator for Canasta Santiago: `uv run orchestrator.py`."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:
    from supermercado.orchestrator.menu import main
except ImportError:  # plain `python orchestrator.py` outside the project environment
    sys.path.insert(0, str(ROOT / "src"))
    from supermercado.orchestrator.menu import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], root=ROOT))
