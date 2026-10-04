from pathlib import Path

import pytest

from factories import make_config, make_item, make_match
from supermercado.config import ConfigError, load_config
from supermercado.domain.models import Category

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

BASKET = """
- id: rice
  name: Arroz
  category: pantry
  unit: kg
  reference_qty: 1.0
  search: arroz
- id: milk
  name: Leche
  category: dairy_eggs
  unit: l
  reference_qty: 1.0
  search: leche
"""

STORES = """
jumbo: {name: Jumbo, base_url: "https://bff.jumbo.cl", comuna: Santiago}
lider: {name: Lider, base_url: "https://super.lider.cl", comuna: Santiago}
"""


def write_config(tmp_path: Path, *, matches: str = "", basket: str = BASKET) -> Path:
    (tmp_path / "basket.yaml").write_text(basket, encoding="utf-8")
    (tmp_path / "stores.yaml").write_text(STORES, encoding="utf-8")
    (tmp_path / "matches.yaml").write_text(matches, encoding="utf-8")
    return tmp_path


def test_repository_config_loads_the_full_basket() -> None:
    config = load_config(CONFIG_DIR)
    assert len(config.basket) == 23
    assert {item.category for item in config.basket} == set(Category)
    assert len({item.id for item in config.basket}) == 23
    assert all(item.search.strip() for item in config.basket)
    assert isinstance(config.matches, dict)
    assert list(config.stores) == ["jumbo", "santa_isabel", "tottus", "acuenta", "unimarc", "lider"]


def test_comment_only_matches_file_means_no_matches(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, matches="# nothing approved yet\n"))
    assert config.matches == {}


def test_matches_are_parsed(tmp_path: Path) -> None:
    matches = 'rice:\n  jumbo: { sku: "1626", size: 1.0, approved: 2026-10-04 }\n'
    config = load_config(write_config(tmp_path, matches=matches))
    assert config.matches["rice"]["jumbo"].sku == "1626"
    assert config.matches_for_store("jumbo") == {"rice": config.matches["rice"]["jumbo"]}
    assert config.matches_for_store("lider") == {}


def test_unquoted_numeric_sku_is_rejected(tmp_path: Path) -> None:
    matches = "rice:\n  jumbo: { sku: 1626, size: 1.0, approved: 2026-10-04 }\n"
    with pytest.raises(ConfigError, match="sku"):
        load_config(write_config(tmp_path, matches=matches))


def test_unknown_item_in_matches_is_rejected(tmp_path: Path) -> None:
    matches = 'bread:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-04 }\n'
    with pytest.raises(ConfigError, match="unknown item 'bread'"):
        load_config(write_config(tmp_path, matches=matches))


def test_unknown_store_in_matches_is_rejected(tmp_path: Path) -> None:
    matches = 'rice:\n  alvi: { sku: "1", size: 1.0, approved: 2026-10-04 }\n'
    with pytest.raises(ConfigError, match="unknown store 'alvi'"):
        load_config(write_config(tmp_path, matches=matches))


def test_lider_match_requires_url(tmp_path: Path) -> None:
    matches = 'rice:\n  lider: { sku: "00780142021013", size: 1.0, approved: 2026-10-04 }\n'
    with pytest.raises(ConfigError, match="url"):
        load_config(write_config(tmp_path, matches=matches))


def test_duplicate_item_ids_are_rejected(tmp_path: Path) -> None:
    basket = BASKET + BASKET
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(write_config(tmp_path, basket=basket))


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="basket.yaml"):
        load_config(tmp_path)


def test_matches_for_store_follows_basket_order() -> None:
    config = make_config(
        items=[make_item("rice"), make_item("milk")],
        matches={"milk": {"jumbo": make_match("2")}, "rice": {"jumbo": make_match("1")}},
    )
    assert list(config.matches_for_store("jumbo")) == ["rice", "milk"]


def test_enabled_stores_keeps_file_order() -> None:
    config = load_config(CONFIG_DIR)
    assert config.enabled_stores() == [s for s, c in config.stores.items() if c.enabled]


def test_duplicate_mapping_keys_are_rejected(tmp_path: Path) -> None:
    matches = (
        'rice:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-04 }\n'
        'rice:\n  jumbo: { sku: "2", size: 1.0, approved: 2026-10-04 }\n'
    )
    with pytest.raises(ConfigError, match="duplicate key 'rice'"):
        load_config(write_config(tmp_path, matches=matches))


def test_store_params_load_from_stores_yaml() -> None:
    config = load_config(CONFIG_DIR)
    assert config.stores["acuenta"].params == {"client_id": "SUPER_BODEGA"}
    assert config.stores["unimarc"].params == {
        "channel": "UNIMARC",
        "source": "web",
        "version": "1.0.0",
    }
    assert config.stores["jumbo"].params == {}
