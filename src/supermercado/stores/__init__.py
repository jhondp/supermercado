"""Store adapters behind the StoreAdapter port, plus the registry that builds them."""

from __future__ import annotations

from collections.abc import Callable

from supermercado.config import AppConfig, ConfigError, StoreConfig
from supermercado.stores.base import HttpClient, StoreAdapter, Transport, curl_transport
from supermercado.stores.jumbo import JumboAdapter

AdapterFactory = Callable[[HttpClient, StoreConfig, AppConfig], StoreAdapter]

FACTORIES: dict[str, AdapterFactory] = {
    "jumbo": lambda client, store, app: JumboAdapter(client, store),
}


def build_adapters(
    config: AppConfig,
    *,
    only: str | None = None,
    transport_factory: Callable[[], Transport] = curl_transport,
) -> dict[str, StoreAdapter]:
    """One adapter (with its own polite HttpClient) per enabled store."""
    if only is not None and only not in config.stores:
        raise ConfigError(f"unknown store {only!r}")
    adapters: dict[str, StoreAdapter] = {}
    for store_id, store_cfg in config.stores.items():
        if only is not None and store_id != only:
            continue
        if not store_cfg.enabled:
            if only is not None:
                raise ConfigError(f"store {only!r} is disabled in config/stores.yaml")
            continue
        factory = FACTORIES.get(store_id)
        if factory is None:
            raise ConfigError(f"no adapter registered for enabled store {store_id!r}")
        adapters[store_id] = factory(HttpClient(transport_factory()), store_cfg, config)
    return adapters
