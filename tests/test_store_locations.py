from pathlib import Path

import pytest

from supermercado.config import load_config

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

# Chains reachable but not yet pinned to a Santiago branch with evidence; see
# docs/store-locations.md. Remove a store from this set once it is pinned (the strict xfail
# below then flips and must be removed too).
LOCATION_PENDING = {"jumbo", "tottus", "acuenta", "unimarc"}


@pytest.mark.xfail(
    strict=True,
    reason="four chains are not pinned to a verified branch yet (docs/store-locations.md)",
)
def test_every_enabled_store_pins_a_verified_santiago_location() -> None:
    config = load_config(CONFIG_DIR)
    assert config.enabled_stores(), "at least one store must be enabled"
    for store_id in config.enabled_stores():
        store = config.stores[store_id]
        assert store.comuna != "pending-verification", f"{store_id}: comuna not verified"
        assert store.location_verified is not None, f"{store_id}: location_verified missing"
        assert store.smoke_sku, f"{store_id}: smoke_sku missing"
    assert config.stores["lider"].smoke_url


def test_pinned_stores_are_verified_and_every_store_has_a_smoke_sku() -> None:
    config = load_config(CONFIG_DIR)
    pending = set()
    for store_id in config.enabled_stores():
        store = config.stores[store_id]
        assert store.smoke_sku, f"{store_id}: smoke_sku missing"
        if store.comuna == "pending-verification":
            pending.add(store_id)
            assert store.location_verified is None, f"{store_id}: pending yet dated"
        else:
            assert store.location_verified is not None, f"{store_id}: location_verified missing"
    assert pending == LOCATION_PENDING
    assert config.stores["lider"].smoke_url
