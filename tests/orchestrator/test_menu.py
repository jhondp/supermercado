import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from supermercado.config import load_config
from supermercado.orchestrator.menu import App
from supermercado.orchestrator.paths import Paths

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


class Script:
    """Feeds scripted answers to `input`; an exception instance is raised instead of returned."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str = "") -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return str(answer)


class FakeCli:
    def __init__(self, code: int = 0, on_call: Callable[[list[str]], None] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.code = code
        self.on_call = on_call

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(argv)
        if self.on_call:
            self.on_call(argv)
        return self.code


@pytest.fixture
def paths(tmp_path: Path, config_dir: Path) -> Paths:
    return Paths.from_root(tmp_path)


def make_app(paths: Paths, script: Script, cli: FakeCli | None = None, **kw: object):
    out: list[str] = []
    app = App(
        paths,
        input_fn=script,
        output_fn=out.append,
        run_cli=cli or FakeCli(),
        now=lambda: NOW,
        **kw,  # type: ignore[arg-type]
    )
    return app, out


def text(out: list[str]) -> str:
    return "\n".join(out)


def base_args(paths: Paths) -> list[str]:
    return ["--config", str(paths.config), "--data", str(paths.data)]


def test_menu_shows_status_and_recommendation_then_exits(paths: Paths) -> None:
    app, out = make_app(paths, Script("0"))
    assert app.run() == 0
    shown = text(out)
    assert "Canasta Santiago · Orquestador" in shown
    assert "Propuestas pendientes: 4 (semana 2026-W40)" in shown
    assert "Siguiente paso recomendado: 2)" in shown
    assert " 8) Ver último reporte" in shown


def test_invalid_menu_input_is_reported_and_the_menu_repeats(paths: Paths) -> None:
    app, out = make_app(paths, Script("9", "abc", "0"))
    assert app.run() == 0
    assert text(out).count("Opción no válida") == 2


def test_ctrl_c_and_eof_at_the_menu_exit_cleanly(paths: Paths) -> None:
    assert make_app(paths, Script(KeyboardInterrupt()))[0].run() == 0
    assert make_app(paths, Script())[0].run() == 0


def write_report(paths: Paths, failures: list[dict[str, str]]) -> None:
    paths.report.parent.mkdir(parents=True, exist_ok=True)
    paths.report.write_text(
        json.dumps(
            {
                "week": "2026-W40",
                "observations": 40,
                "collected_stores": ["jumbo"],
                "failures": failures,
                "alerts": [{"store": "jumbo", "item_id": "rice", "message": "size 1.0 -> 0.9"}],
                "dropped": ["jumbo/sugar: missing price"],
            }
        ),
        encoding="utf-8",
    )


def test_collect_all_stores_calls_the_cli_and_explains_ip_blocks(paths: Paths) -> None:
    failure = {"store": "lider", "error_class": "BlockedError", "message": "captcha", "at": "x"}
    cli = FakeCli(on_call=lambda _argv: write_report(paths, [failure]))
    app, out = make_app(paths, Script("3", "", "0"), cli)
    assert app.run() == 0
    assert cli.calls == [[*base_args(paths), "collect", "--report", str(paths.report)]]
    shown = text(out)
    assert "lider: BlockedError" in shown
    assert "bloqueo de IP" in shown
    assert "Descartados: 1" in shown


def test_collect_one_store_passes_the_store_flag(paths: Paths) -> None:
    cli = FakeCli(on_call=lambda _argv: write_report(paths, []))
    app, _ = make_app(paths, Script("3", "2", "0"), cli)
    app.run()
    assert cli.calls[0][-2:] == ["--store", "santa_isabel"]


def test_http_403_is_also_explained_as_an_ip_block(paths: Paths) -> None:
    failure = {
        "store": "jumbo",
        "error_class": "HttpError",
        "message": "HTTP 403 from x",
        "at": "x",
    }
    cli = FakeCli(on_call=lambda _argv: write_report(paths, [failure]))
    app, out = make_app(paths, Script("3", "", "0"), cli)
    app.run()
    assert "bloqueo de IP" in text(out)


def test_propose_warns_and_calls_the_cli(paths: Paths) -> None:
    cli = FakeCli()
    app, out = make_app(paths, Script("1", "s", "1", "0"), cli)
    app.run()
    assert cli.calls == [[*base_args(paths), "propose", "--store", "jumbo"]]
    assert "reescribe la sección de propuestas" in text(out)


def test_propose_can_be_cancelled_before_scraping(paths: Paths) -> None:
    cli = FakeCli()
    app, _ = make_app(paths, Script("1", "n", "0"), cli)
    app.run()
    assert cli.calls == []


def test_build_writes_into_dist(paths: Paths) -> None:
    cli = FakeCli()
    app, _ = make_app(paths, Script("4", "0"), cli)
    app.run()
    assert cli.calls == [[*base_args(paths), "build", "--out", str(paths.dist)]]


def test_smoke_calls_the_cli(paths: Paths) -> None:
    cli = FakeCli(code=1)
    app, out = make_app(paths, Script("6", "0"), cli)
    app.run()
    assert cli.calls == [[*base_args(paths), "smoke"]]
    assert "falló" in text(out)


def test_approve_suggested_skip_and_manual(paths: Paths) -> None:
    script = Script(
        "2",  # menu
        "n",  # review already approved?
        "",  # all stores
        "n",  # lider manual entry?
        "",  # rice/jumbo -> suggested (sku 100)
        "s",  # rice/acuenta -> skip
        "m",  # spaghetti/jumbo -> manual
        "999",
        "0.4",
        "0",
    )
    app, out = make_app(paths, script)
    app.run()
    config = load_config(paths.config)
    assert config.matches["rice"]["jumbo"].sku == "100"
    assert config.matches["spaghetti"]["jumbo"].sku == "999"
    assert config.matches["spaghetti"]["jumbo"].size == 0.4
    assert "acuenta" not in config.matches["rice"]
    shown = text(out)
    assert "Arroz Uno 1 kg" in shown
    assert "$870/kg" in shown
    assert "Jumbo: 2/23" in shown


def test_approve_choose_number_then_quit_saves_what_was_chosen(paths: Paths) -> None:
    app, _ = make_app(paths, Script("2", "n", "", "n", "2", "q", "0"))
    app.run()
    config = load_config(paths.config)
    assert config.matches == {"rice": {"jumbo": config.matches["rice"]["jumbo"]}}
    assert config.matches["rice"]["jumbo"].sku == "101"


def test_approve_invalid_key_reprompts(paths: Paths) -> None:
    app, out = make_app(paths, Script("2", "n", "1", "7", "x", "1", "q", "0"))
    app.run()
    assert text(out).count("Respuesta no válida") == 2
    assert load_config(paths.config).matches["rice"]["jumbo"].sku == "100"


def test_lider_manual_entry_includes_the_url(paths: Paths) -> None:
    script = Script(
        "2",
        "n",
        "6",  # only lider
        "m",
        "007",
        "",  # default size = reference quantity
        "https://super.lider.cl/ip/x/007",
        "q",
        "0",
    )
    app, _ = make_app(paths, script)
    app.run()
    match = load_config(paths.config).matches["rice"]["lider"]
    assert (match.sku, match.size, match.url) == ("007", 1.0, "https://super.lider.cl/ip/x/007")


def test_replacing_an_approved_pair_requires_confirmation(paths: Paths) -> None:
    text_before = paths.matches.read_text(encoding="utf-8")
    paths.matches.write_text(
        'rice:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-01 }\n' + text_before,
        encoding="utf-8",
    )
    # first pass refuses the replacement, second pass confirms it
    app, _ = make_app(paths, Script("2", "s", "1", "", "n", "s", "0"))
    app.run()
    assert load_config(paths.config).matches["rice"]["jumbo"].sku == "1"
    app, _ = make_app(paths, Script("2", "s", "1", "", "s", "s", "0"))
    app.run()
    assert load_config(paths.config).matches["rice"]["jumbo"].sku == "100"


def test_approved_pairs_are_skipped_by_default(paths: Paths) -> None:
    text_before = paths.matches.read_text(encoding="utf-8")
    paths.matches.write_text(
        'rice:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-01 }\n' + text_before,
        encoding="utf-8",
    )
    app, out = make_app(paths, Script("2", "n", "1", "q", "0"))
    app.run()
    assert "Arroz Uno 1 kg" not in text(out)
    assert "Spaghetti N° 5 400 g" in text(out)
    assert load_config(paths.config).matches["rice"]["jumbo"].sku == "1"


def test_ctrl_c_inside_a_step_returns_to_the_menu(paths: Paths) -> None:
    cli = FakeCli()
    app, out = make_app(paths, Script("3", KeyboardInterrupt(), "0"), cli)
    assert app.run() == 0
    assert cli.calls == []
    assert "Cancelado" in text(out)


def test_full_flow_stops_when_a_step_fails_and_the_user_declines(paths: Paths) -> None:
    cli = FakeCli(code=1)
    script = Script("7", "s", "", "n", "0")
    app, _ = make_app(paths, script, cli)
    app.run()
    assert [call[4] for call in cli.calls] == ["propose"]
    assert any("¿Continuar" in prompt for prompt in script.prompts)


def test_full_flow_with_approvals_collects_builds_and_serves(paths: Paths) -> None:
    text_before = paths.matches.read_text(encoding="utf-8")
    paths.matches.write_text(
        'rice:\n  jumbo: { sku: "1", size: 1.0, approved: 2026-10-01 }\n' + text_before,
        encoding="utf-8",
    )

    def fake_cli(argv: list[str]) -> None:
        if "collect" in argv:
            write_report(paths, [])
        if "build" in argv:
            paths.dist.mkdir(exist_ok=True)
            (paths.dist / "index.html").write_text("<html>", encoding="utf-8")

    cli = FakeCli(on_call=fake_cli)
    opened: list[str] = []
    stopped: list[bool] = []
    app, _ = make_app(
        paths,
        Script("7", "", "", "0"),
        cli,
        open_browser=opened.append,
        serve=lambda _dir: ("http://127.0.0.1:9999/", lambda: stopped.append(True)),
    )
    app.run()
    assert [call[4] for call in cli.calls] == ["collect", "build"]
    assert opened == ["http://127.0.0.1:9999/"]
    assert stopped == [True]


def test_view_site_requires_a_built_site(paths: Paths) -> None:
    opened: list[str] = []
    app, out = make_app(paths, Script("5", "0"), open_browser=opened.append)
    app.run()
    assert opened == []
    assert "Genera el sitio primero" in text(out)


def test_last_report_is_pretty_printed(paths: Paths) -> None:
    failure = {"store": "tottus", "error_class": "ApiKeyRejected", "message": "401", "at": "x"}
    write_report(paths, [failure])
    app, out = make_app(paths, Script("8", "0"))
    app.run()
    shown = text(out)
    assert "Semana 2026-W40" in shown
    assert "tottus: ApiKeyRejected" in shown
    assert "size 1.0 -> 0.9" in shown
    assert "jumbo/sugar: missing price" in shown


def test_missing_report_is_explained(paths: Paths) -> None:
    app, out = make_app(paths, Script("8", "0"))
    app.run()
    assert "No hay reporte" in text(out)


@pytest.mark.parametrize("stop", [KeyboardInterrupt(), EOFError()])
def test_interrupting_approval_saves_the_choices_made_so_far(
    paths: Paths, stop: BaseException
) -> None:
    # rice/jumbo -> suggested, then interrupt at rice/acuenta
    app, out = make_app(paths, Script("2", "n", "", "n", "", stop, "0"))
    assert app.run() == 0
    assert load_config(paths.config).matches["rice"]["jumbo"].sku == "100"
    shown = text(out)
    assert "Interrumpido: se guardaron 1 elecciones" in shown
    assert list(paths.config.glob("matches.yaml.*.bak"))


def test_interrupting_a_manual_entry_keeps_earlier_choices(paths: Paths) -> None:
    script = Script("2", "n", "1", "", "m", KeyboardInterrupt(), "0")
    app, _ = make_app(paths, script)
    app.run()
    config = load_config(paths.config)
    assert config.matches == {"rice": {"jumbo": config.matches["rice"]["jumbo"]}}


def test_interrupting_before_any_choice_leaves_the_file_untouched(paths: Paths) -> None:
    before = paths.matches.read_bytes()
    app, out = make_app(paths, Script("2", "n", "", "n", KeyboardInterrupt(), "0"))
    app.run()
    assert paths.matches.read_bytes() == before
    assert "Cancelado" in text(out)
