import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factories import make_config, make_item, make_match, make_obs
from supermercado.config import load_config
from supermercado.domain.models import Category, Status, Unit
from supermercado.pipeline.storage import write_week
from supermercado.site import build as site_build
from supermercado.site.build import build_site, chart_data, load_observations

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
ITEMS = [
    make_item("rice", name="Arroz grado 2 (1 kg)"),
    make_item("spaghetti", reference_qty=0.4, name="Fideos spaghetti (400 g)"),
    make_item("whole_milk", unit=Unit.L, category=Category.DAIRY_EGGS, name="Leche entera (1 L)"),
]
W39 = {"week": "2026-W39", "scraped_at": datetime(2026, 9, 21, 9, 0, tzinfo=UTC)}


def site_config(stores=("jumbo", "tottus", "lider")):
    lider = "https://super.lider.cl/ip/x/"
    return make_config(
        items=ITEMS,
        stores=stores,
        matches={
            "rice": {
                "jumbo": make_match("1626"),
                "lider": make_match("00780142021013", url=lider + "1"),
            },
            "spaghetti": {
                "jumbo": make_match("2001", size=0.4),
                "lider": make_match("3001", size=0.4, url=lider + "2"),
            },
            "whole_milk": {
                "jumbo": make_match("4001"),
                "lider": make_match("5001", url=lider + "3"),
            },
        },
    )


def observations(*, lider_milk: bool = False):
    """Partial data: Lider lacks milk (2 of 3 items). With lider_milk it has full coverage."""
    rows = [
        make_obs(**W39, store="jumbo", item_id="rice", unit_price=1790),
        make_obs(**W39, store="jumbo", item_id="spaghetti", sku="2001", unit_price=2475),
        make_obs(**W39, store="lider", item_id="rice", sku="00780142021000", unit_price=1290),
        make_obs(**W39, store="lider", item_id="spaghetti", sku="3001", unit_price=2600),
        make_obs(store="jumbo", item_id="rice", unit_price=1810),
        make_obs(store="jumbo", item_id="spaghetti", sku="2001", unit_price=2475),
        make_obs(store="jumbo", item_id="whole_milk", sku="4001", unit="l", unit_price=990),
        make_obs(store="lider", item_id="rice", sku="00780142021013", unit_price=1190),
        make_obs(store="lider", item_id="spaghetti", sku="3001", unit_price=2600),
    ]
    if lider_milk:
        rows += [
            make_obs(
                **W39, store="jumbo", item_id="whole_milk", sku="4001", unit="l", unit_price=990
            ),
            make_obs(
                **W39, store="lider", item_id="whole_milk", sku="5001", unit="l", unit_price=1100
            ),
            make_obs(store="lider", item_id="whole_milk", sku="5001", unit="l", unit_price=1100),
        ]
    return rows


def write_fixture_parquet(data: Path, rows) -> None:
    for week in ("2026-W39", "2026-W40"):
        write_week(
            data, week, [o for o in rows if o.week == week], replace_stores={"jumbo", "lider"}
        )


def build(tmp_path: Path, rows, config=None) -> Path:
    write_fixture_parquet(tmp_path / "data", rows)
    build_site(config or site_config(), tmp_path / "data", tmp_path / "dist")
    return tmp_path / "dist"


@pytest.fixture
def built(tmp_path: Path) -> Path:
    return build(tmp_path, observations(lider_milk=True))


@pytest.fixture
def built_partial(tmp_path: Path) -> Path:
    return build(tmp_path, observations())


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_load_observations_reads_every_week_through_duckdb(tmp_path: Path) -> None:
    rows = observations()
    write_fixture_parquet(tmp_path / "data", rows)
    loaded = load_observations(tmp_path / "data")
    assert loaded == sorted(rows, key=lambda o: (o.week, o.store, o.item_id))


def test_home_ranks_stores_and_highlights_the_winner(built: Path) -> None:
    html = read(built / "index.html")
    assert "¿Dónde sale más barata la canasta esta semana?" in html
    assert "Actualizado: 28 de septiembre de 2026 · Precios de referencia Santiago" in html
    assert "Comparando 3 de 3 productos" in html
    assert html.index("Lider") < html.index("Jumbo")
    assert 'class="rank-card is-winner"' in html
    assert "$3.330" in html and "$3.790" in html
    assert "−$100 vs semana anterior" in html
    assert "+$20 vs semana anterior" in html
    assert "Tottus: sin datos esta semana" in html
    assert "cobertura insuficiente esta semana" not in html


def test_store_below_coverage_threshold_is_listed_and_not_ranked(built_partial: Path) -> None:
    html = read(built_partial / "index.html")
    assert "Lider: cobertura insuficiente esta semana" in html
    ranking = html.split('<ol class="ranking">')[1].split("</ol>")[0]
    assert "Jumbo" in ranking
    assert "Lider" not in ranking


def test_home_says_no_store_reached_minimum_coverage(tmp_path: Path) -> None:
    rows = [
        make_obs(store="jumbo", item_id="rice", unit_price=1810),
        make_obs(store="lider", item_id="rice", sku="00780142021013", unit_price=1190),
    ]
    dist = build(tmp_path, rows)
    html = read(dist / "index.html")
    assert "Ningún supermercado alcanzó la cobertura mínima esta semana" in html
    assert "no hay productos comparables" not in html
    assert "Jumbo: cobertura insuficiente esta semana" in html
    assert "Lider: cobertura insuficiente esta semana" in html


def test_methodology_explains_the_coverage_rule(built: Path) -> None:
    html = read(built / "metodologia" / "index.html")
    assert "80 %" in html
    assert "3 de 3 productos" in html
    assert "todos los supermercados con datos" not in html


def test_products_table_highlights_cheapest_and_explains_gaps(built: Path) -> None:
    html = read(built / "productos" / "index.html")
    assert '<td class="best">$1.190/kg</td>' in html
    assert '<td class="">$1.810/kg</td>' in html
    assert "sin match" in html
    assert 'data-category="dairy_eggs"' in html
    assert 'data-filter="meat"' in html


def test_product_page_embeds_valid_chart_json_and_marks_sku_changes(built: Path) -> None:
    html = read(built / "producto" / "rice" / "index.html")
    match = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', html, re.S)
    assert match is not None
    chart = json.loads(match.group(1))
    assert chart["weeks"] == ["2026-W39", "2026-W40"]
    lider = next(s for s in chart["series"] if s["store"] == "lider")
    assert [p["sku_changed"] for p in lider["points"]] == [False, True]
    assert "SKU 00780142021000 → 00780142021013" in html


def test_every_page_exists(built: Path) -> None:
    for item in ITEMS:
        assert (built / "producto" / item.id / "index.html").exists()
    assert "Metodología" in read(built / "metodologia" / "index.html")
    assert (built / "static" / "style.css").exists()
    assert (built / "static" / "app.js").exists()


def test_build_with_no_data_renders_empty_state(tmp_path: Path) -> None:
    config = load_config(CONFIG_DIR)
    build_site(config, tmp_path / "data", tmp_path / "dist")
    assert "Aún no hay datos" in read(tmp_path / "dist" / "index.html")
    assert len(list((tmp_path / "dist" / "producto").iterdir())) == 23


def _rice_page(tmp_path: Path, extra, *, config=None) -> str:
    rows = [
        o for o in observations(lider_milk=True) if not (o.store == "lider" and o.item_id == "rice")
    ]
    dist = build(tmp_path, rows + extra, config)
    return read(dist / "producto" / "rice" / "index.html")


def _chart(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def test_non_ok_and_unavailable_points_are_not_plotted_and_are_labelled(tmp_path: Path) -> None:
    from supermercado.domain.models import Status

    html = _rice_page(
        tmp_path,
        [
            make_obs(**W39, store="lider", item_id="rice", sku="1", unit_price=1290),
            make_obs(
                store="lider", item_id="rice", sku="1", unit_price=9999, status=Status.SUSPICIOUS
            ),
        ],
    )
    chart = _chart(html)
    lider = next(s for s in chart["series"] if s["store"] == "lider")
    assert [p["week"] for p in lider["points"]] == ["2026-W39"]
    assert "en revisión" in html
    assert "$9.999" not in html


def test_unavailable_item_is_labelled_agotado(tmp_path: Path) -> None:
    html = _rice_page(
        tmp_path,
        [make_obs(store="lider", item_id="rice", sku="1", unit_price=5555, available=False)],
    )
    assert "agotado" in html
    assert "$5.555" not in html
    assert all(p["unit_price"] != 5555 for entry in _chart(html)["series"] for p in entry["points"])


def test_non_http_product_url_is_not_linked(tmp_path: Path) -> None:
    html = _rice_page(
        tmp_path,
        [make_obs(store="lider", item_id="rice", sku="1", url="javascript:alert(1)")],
    )
    assert "javascript:" not in html


def test_product_name_is_escaped_and_chart_json_survives(tmp_path: Path) -> None:
    evil = "</script><script>alert(1)</script>"
    html = _rice_page(
        tmp_path,
        [make_obs(store="lider", item_id="rice", sku="1", product_name=evil)],
    )
    assert evil not in html
    assert "&lt;/script&gt;" in html
    assert _chart(html)["series"]


def test_methodology_computes_threshold_from_real_basket(tmp_path: Path) -> None:
    build_site(load_config(CONFIG_DIR), tmp_path / "data", tmp_path / "dist")
    assert "19 de 23 productos" in read(tmp_path / "dist" / "metodologia" / "index.html")


def test_chartjs_script_has_subresource_integrity(built: Path) -> None:
    html = read(built / "producto" / "rice" / "index.html")
    assert (
        'integrity="sha512-CQBWl4fJHWbryGE+Pc7UAxWMUMNMWzWxF4SQo9CgkJIN1kx6djDQZjh3Y8SZ1d+6I+1zze6Z7kHXO7q3UyZAWw=="'
        in html
    )
    assert 'crossorigin="anonymous"' in html
    assert 'referrerpolicy="no-referrer"' in html


def test_methodology_and_ranking_share_the_coverage_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(site_build, "MIN_COVERAGE", 0.5)
    build_site(load_config(CONFIG_DIR), tmp_path / "data", tmp_path / "dist")
    assert "12 de 23 productos" in read(tmp_path / "dist" / "metodologia" / "index.html")


W41 = {"week": "2026-W41", "scraped_at": datetime(2026, 10, 5, 9, 0, tzinfo=UTC)}


def _sku_switch_rows():
    return [
        make_obs(**W39, store="lider", item_id="rice", sku="A", unit_price=1290),
        make_obs(store="lider", item_id="rice", sku="B", unit_price=9999, status=Status.SUSPICIOUS),
        make_obs(**W41, store="lider", item_id="rice", sku="B", unit_price=1300),
    ]


def test_sku_change_in_an_unplotted_week_marks_the_next_plotted_point() -> None:
    chart = chart_data("rice", _sku_switch_rows(), ["lider"], {"lider": "Lider"})
    [lider] = chart["series"]
    assert [(p["week"], p["sku"], p["sku_changed"]) for p in lider["points"]] == [
        ("2026-W39", "A", False),
        ("2026-W41", "B", True),
    ]


def test_sku_change_in_an_unplotted_week_is_listed(tmp_path: Path) -> None:
    rows = _sku_switch_rows()
    for week in ("2026-W39", "2026-W40", "2026-W41"):
        write_week(
            tmp_path / "data", week, [o for o in rows if o.week == week], replace_stores={"lider"}
        )
    build_site(site_config(), tmp_path / "data", tmp_path / "dist")
    html = read(tmp_path / "dist" / "producto" / "rice" / "index.html")
    assert "semana 2026-W41: SKU A → B" in html


def test_chart_json_neutralizes_html_comment_openers(tmp_path: Path) -> None:
    evil = "<!--<script>"
    config = site_config()
    config.stores["lider"] = config.stores["lider"].model_copy(update={"name": evil})
    html = _rice_page(tmp_path, [make_obs(store="lider", item_id="rice", sku=evil)], config=config)
    assert evil not in html
    chart = _chart(html)
    lider = next(s for s in chart["series"] if s["store"] == "lider")
    assert lider["label"] == evil
    assert lider["points"][-1]["sku"] == evil
