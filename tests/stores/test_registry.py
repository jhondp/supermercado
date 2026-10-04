import pytest

from factories import make_config, make_store_config
from fakes import FakeTransport
from supermercado.config import AppConfig, ConfigError
from supermercado.stores import build_adapters
from supermercado.stores.jumbo import JumboAdapter


def config_with(**stores):
    base = make_config()
    return AppConfig(basket=base.basket, stores=stores, matches={})


def jumbo_cfg(**overrides):
    return make_store_config("Jumbo", api_key="k", store_ref="s", **overrides)


def test_builds_enabled_registered_stores() -> None:
    config = config_with(jumbo=jumbo_cfg(), lider=make_store_config("Lider", enabled=False))
    adapters = build_adapters(config, transport_factory=lambda: FakeTransport([]))
    assert list(adapters) == ["jumbo"]
    assert isinstance(adapters["jumbo"], JumboAdapter)


def test_only_selects_a_single_store() -> None:
    config = config_with(jumbo=jumbo_cfg())
    assert list(
        build_adapters(config, only="jumbo", transport_factory=lambda: FakeTransport([]))
    ) == ["jumbo"]


def test_only_rejects_unknown_or_disabled_store() -> None:
    config = config_with(jumbo=jumbo_cfg(enabled=False))
    with pytest.raises(ConfigError, match="disabled"):
        build_adapters(config, only="jumbo", transport_factory=lambda: FakeTransport([]))
    with pytest.raises(ConfigError, match="unknown store"):
        build_adapters(config, only="alvi", transport_factory=lambda: FakeTransport([]))


def test_enabled_store_without_adapter_is_a_config_error() -> None:
    config = config_with(alvi=make_store_config("Alvi"))
    with pytest.raises(ConfigError, match="no adapter"):
        build_adapters(config, transport_factory=lambda: FakeTransport([]))
