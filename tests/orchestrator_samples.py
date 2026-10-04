"""Sample matches.yaml content and a throwaway config dir for the orchestrator tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from supermercado.pipeline.propose import MANUAL_NOTE, MARKER

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"

HEAD = """\
# Approved SKU per (basket item, store).
# Always quote SKUs.
#
# Example:
# rice:
#   jumbo: { sku: "1626", size: 1.0, approved: 2026-10-04 }
"""

PROPOSALS = f"""\
{MARKER}
# week: 2026-W40
{MANUAL_NOTE}
# rice:
#   jumbo: {{ sku: "100", size: 1, approved: 2026-10-04 }}  # Arroz Uno 1 kg | Marca A | $870 -> $870/kg | https://www.jumbo.cl/arroz-uno/p
#   jumbo: {{ sku: "101", size: 1, approved: 2026-10-04 }}  # Arroz Dos 1 kg | Marca B | $1.050 -> $1.050/kg | https://www.jumbo.cl/arroz-dos/p
#   acuenta: {{ sku: "200", size: 1, approved: 2026-10-04 }}  # Arroz Acuenta 1 kg | Acuenta | $850 -> $850/kg
# spaghetti:
#   jumbo: {{ sku: "300", size: 0.4, approved: 2026-10-04 }}  # Spaghetti N° 5 400 g | Máxima | $450 -> $1.125/kg | https://www.jumbo.cl/spaghetti/p
"""


def make_config_dir(tmp_path: Path) -> Path:
    """Repository basket and stores plus a small matches.yaml with a proposals section."""
    target = tmp_path / "config"
    target.mkdir()
    for name in ("basket.yaml", "stores.yaml"):
        shutil.copy(REPO_CONFIG / name, target / name)
    (target / "matches.yaml").write_text(f"{HEAD}\n{PROPOSALS}", encoding="utf-8")
    return target
