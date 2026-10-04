"""Load and cross-validate YAML configuration (basket, matches, stores, clearances)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from supermercado.domain.models import BasketItem, Match


class ConfigError(ValueError):
    """Configuration is missing, malformed, or inconsistent."""


class StoreConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    enabled: bool = True
    base_url: str
    api_key: str | None = None
    store_ref: str | None = None
    comuna: str
    location_verified: date | None = None
    cookies: dict[str, str] = Field(default_factory=dict)
    smoke_sku: str | None = None
    smoke_url: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class Clearance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    week: str
    store: str
    item_id: str


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    basket: list[BasketItem]
    matches: dict[str, dict[str, Match]] = Field(default_factory=dict)
    stores: dict[str, StoreConfig]
    cleared: list[Clearance] = Field(default_factory=list)

    def item(self, item_id: str) -> BasketItem:
        for item in self.basket:
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def matches_for_store(self, store: str) -> dict[str, Match]:
        return {
            item.id: self.matches[item.id][store]
            for item in self.basket
            if store in self.matches.get(item.id, {})
        }

    def enabled_stores(self) -> list[str]:
        return [store for store, cfg in self.stores.items() if cfg.enabled]


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently keeping the last."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if key in seen:
                raise ConfigError(f"duplicate key {key!r} (line {key_node.start_mark.line + 1})")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    with path.open(encoding="utf-8") as handle:
        try:
            return yaml.load(handle, Loader=_UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path.name}: invalid YAML: {exc}") from exc
        except ConfigError as exc:
            raise ConfigError(f"{path.name}: {exc}") from exc


def load_config(config_dir: Path) -> AppConfig:
    basket = _read_yaml(config_dir / "basket.yaml") or []
    stores = _read_yaml(config_dir / "stores.yaml") or {}
    matches = _read_yaml(config_dir / "matches.yaml") or {}
    cleared_path = config_dir / "cleared.yaml"
    cleared = (_read_yaml(cleared_path) or []) if cleared_path.exists() else []
    try:
        config = AppConfig(basket=basket, stores=stores, matches=matches, cleared=cleared)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration in {config_dir}:\n{exc}") from exc
    _check_consistency(config)
    return config


def _check_consistency(config: AppConfig) -> None:
    ids = [item.id for item in config.basket]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ConfigError(f"basket.yaml: duplicate item ids {duplicates}")
    for item_id, per_store in config.matches.items():
        if item_id not in ids:
            raise ConfigError(f"matches.yaml: unknown item {item_id!r}")
        for store, match in per_store.items():
            if store not in config.stores:
                raise ConfigError(f"matches.yaml: unknown store {store!r} for item {item_id!r}")
            if store == "lider" and not match.url:
                raise ConfigError(f"matches.yaml: lider match for {item_id!r} needs a url")
