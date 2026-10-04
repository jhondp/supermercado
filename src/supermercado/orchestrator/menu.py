"""Interactive menu loop. Input, output, the CLI runner and the browser are injectable."""

from __future__ import annotations

import argparse
import json
import webbrowser
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from supermercado import cli
from supermercado.config import ConfigError, load_config
from supermercado.domain.models import BasketItem, Match
from supermercado.orchestrator.approve import ApproveError, NewMatch, write_matches
from supermercado.orchestrator.paths import Paths
from supermercado.orchestrator.proposals import Candidate, parse_proposals
from supermercado.orchestrator.report_view import collect_summary, render_report
from supermercado.orchestrator.serve import serve_directory
from supermercado.orchestrator.status import (
    APPROVE,
    BUILD,
    COLLECT,
    PROPOSE,
    STORE_ORDER,
    VIEW,
    Status,
    compute_status,
    recommend_next,
)
from supermercado.site.format import format_clp

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]
CliRunner = Callable[[list[str]], int]
Serve = Callable[[Path], tuple[str, Callable[[], None]]]

MAX_CANDIDATES = 5
YES = {"s", "si", "sí", "y", "yes"}

MENU = (
    (1, "Proponer candidatos", "scraping de búsqueda en los súper"),
    (2, "Aprobar productos", "interactivo, uno por uno"),
    (3, "Recolectar precios", "todos o un súper"),
    (4, "Generar sitio HTML", ""),
    (5, "Ver sitio en el navegador", "servidor local + abre el browser"),
    (6, "Verificar súper (smoke)", "¿responden las APIs?"),
    (7, "Flujo completo", "3 → 4 → 5, o 1 → 2 → 3 → 4 → 5 si no hay aprobados"),
    (8, "Ver último reporte", "qué falló, qué se descartó"),
)
LABELS = {number: label for number, label, _ in MENU}

_SKIP, _QUIT = "skip", "quit"


class App:
    def __init__(
        self,
        paths: Paths,
        *,
        input_fn: InputFn = input,
        output_fn: OutputFn = print,
        run_cli: CliRunner = cli.main,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        open_browser: Callable[[str], object] = webbrowser.open,
        serve: Serve = serve_directory,
    ) -> None:
        self.paths = paths
        self._input = input_fn
        self._output = output_fn
        self._run_cli = run_cli
        self._now = now
        self._open_browser = open_browser
        self._serve = serve
        self.steps: dict[int, Callable[[], bool]] = {
            1: self.propose,
            2: self.approve,
            3: self.collect,
            4: self.build,
            5: self.view_site,
            6: self.smoke,
            7: self.full_flow,
            8: self.show_report,
        }

    # ── small I/O helpers ──────────────────────────────────────────────

    def say(self, *lines: str) -> None:
        for line in lines:
            self._output(line)

    def ask(self, prompt: str) -> str:
        return self._input(prompt).strip()

    def confirm(self, prompt: str) -> bool:
        return self.ask(prompt).lower() in YES

    def status(self) -> Status:
        return compute_status(self.paths, now=self._now())

    def _base_args(self) -> list[str]:
        return ["--config", str(self.paths.config), "--data", str(self.paths.data)]

    def _cli(self, *args: str) -> int:
        argv = [*self._base_args(), *args]
        try:
            return self._run_cli(argv)
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1
        except Exception as exc:  # the menu must survive any pipeline crash
            self.say(f"Error inesperado: {type(exc).__name__}: {exc}")
            return 1

    def _choose_store(self, stores: tuple[str, ...] | list[str]) -> str | None:
        names = self.status().store_names
        self.say("  Enter) todos")
        self.say(*(f"  {i}) {names.get(store, store)}" for i, store in enumerate(stores, 1)))
        while True:
            answer = self.ask("¿Todos los súper (Enter) o uno (número)? ")
            if not answer:
                return None
            if answer.isdigit() and 1 <= int(answer) <= len(stores):
                return stores[int(answer) - 1]
            self.say("Respuesta no válida.")

    # ── menu loop ──────────────────────────────────────────────────────

    def _show_menu(self, status: Status) -> None:
        names = status.store_names
        approved = " · ".join(f"{names[s]} {status.approved[s]}" for s in status.approved)
        week = f" (semana {status.proposal_week})" if status.proposal_week else ""
        last = status.last_week or "ninguna"
        self.say(
            "",
            "══ Canasta Santiago · Orquestador ══",
            "Estado:",
            f"  Aprobados (meta {status.threshold}/{status.basket_size}): {approved}",
            f"  Propuestas pendientes: {status.pending}{week}",
            f"  Última semana recolectada: {last} (semana actual {status.current_week})",
            f"  Sitio generado: {'sí' if status.site_built else 'no'}",
        )
        if status.config_error:
            self.say(f"  ⚠ Configuración inválida: {status.config_error}")
        self._recommend(status)
        for number, label, hint in MENU:
            self.say(f" {number}) {label:<28}({hint})" if hint else f" {number}) {label}")
        self.say(" 0) Salir")

    def _recommend(self, status: Status | None = None) -> None:
        number = recommend_next(status or self.status())
        self.say(f"👉 Siguiente paso recomendado: {number}) {LABELS[number]}")

    def run(self) -> int:
        while True:
            self._show_menu(self.status())
            try:
                choice = self.ask("Elige una opción: ")
            except (KeyboardInterrupt, EOFError):
                self.say("", "Hasta luego.")
                return 0
            if choice == "0":
                self.say("Hasta luego.")
                return 0
            step = self.steps.get(int(choice)) if choice.isdigit() else None
            if step is None:
                self.say(f"Opción no válida: {choice!r}. Elige un número del 0 al 8.")
                continue
            self._run_step(step)

    def _run_step(self, step: Callable[[], bool]) -> None:
        try:
            ok = step()
        except (KeyboardInterrupt, EOFError):
            self.say("", "Cancelado, volviendo al menú.")
            return
        self.say("", "Resultado: completado." if ok else "Resultado: el paso falló.")
        self._recommend()

    # ── steps ──────────────────────────────────────────────────────────

    def propose(self) -> bool:
        self.say(
            "Busca candidatos para los productos sin aprobar en Jumbo, Santa Isabel, Tottus, "
            "aCuenta y Unimarc (Lider es manual).",
            "Es lento a propósito (~1,5 s por solicitud): ~35 s por súper, unos 3 min en total.",
            "Atención: reescribe la sección de propuestas de config/matches.yaml "
            "(lo ya aprobado, sobre el marcador, se conserva).",
        )
        if not self.confirm("¿Continuar? (s/N) "):
            self.say("Sin cambios.")
            return True
        store = self._choose_store([s for s in STORE_ORDER if s != "lider"])
        code = self._cli("propose", *(["--store", store] if store else []))
        if code == 0:
            self.say(f"Propuestas pendientes ahora: {self.status().pending}.")
        return code == 0

    def collect(self) -> bool:
        self.say(
            "Consulta el precio de cada SKU aprobado y guarda la semana en data/prices/.",
            "~1,5 s por solicitud: unos 35 s por súper con 23 productos.",
        )
        store = self._choose_store(STORE_ORDER)
        before = self._report_mtime()
        code = self._cli(
            "collect", "--report", str(self.paths.report), *(["--store", store] if store else [])
        )
        report = self._read_report()
        if report is None or self._report_mtime() == before:
            self.say("No se generó un reporte nuevo.")
            return False
        self.say(*collect_summary(report))
        return code == 0 and not report.get("failures")

    def build(self) -> bool:
        self.say("Genera el sitio estático en dist/ a partir de data/prices/ (unos segundos).")
        code = self._cli("build", "--out", str(self.paths.dist))
        return code == 0

    def view_site(self) -> bool:
        index = self.paths.dist / "index.html"
        if not index.is_file():
            self.say("No existe dist/index.html. Genera el sitio primero (opción 4).")
            return False
        self.say("Levanta un servidor local con dist/ y abre el navegador (instantáneo).")
        url, stop = self._serve(self.paths.dist)
        try:
            self.say(f"Sirviendo {url}")
            self._open_browser(url)
            self.ask("Presiona Enter para detener el servidor… ")
        finally:
            stop()
            self.say("Servidor detenido.")
        return True

    def smoke(self) -> bool:
        self.say("Pide un producto conocido a cada súper y revisa la respuesta (~10-20 s).")
        return self._cli("smoke") == 0

    def full_flow(self) -> bool:
        status = self.status()
        plan = (
            [COLLECT, BUILD, VIEW]
            if status.total_approved
            else [PROPOSE, APPROVE, COLLECT, BUILD, VIEW]
        )
        self.say("Flujo completo: " + " → ".join(str(n) for n in plan) + ".")
        ok = True
        for position, number in enumerate(plan):
            self.say("", f"── Paso {number}) {LABELS[number]} ──")
            if self.steps[number]():
                continue
            ok = False
            if position == len(plan) - 1:
                break
            if not self.confirm("El paso falló. ¿Continuar con el siguiente? (s/N) "):
                return False
        return ok

    def show_report(self) -> bool:
        report = self._read_report()
        if report is None:
            self.say("No hay reporte todavía: se genera al recolectar precios (opción 3).")
            return True
        self.say(*render_report(report))
        return True

    # ── approval ───────────────────────────────────────────────────────

    def approve(self) -> bool:
        try:
            config = load_config(self.paths.config)
        except ConfigError as exc:
            self.say(f"La configuración no es válida, corrígela antes de aprobar: {exc}")
            return False
        section = parse_proposals(self.paths.matches.read_text(encoding="utf-8"))
        self.say(
            f"Revisa los {section.total} candidatos propuestos"
            + (f" (semana {section.week})" if section.week else "")
            + " y elige un SKU por producto y súper. Toma unos minutos; no hace scraping.",
        )
        if section.malformed:
            self.say(f"Aviso: {section.malformed} líneas de propuestas no se pudieron leer.")
        review = self.confirm("¿Revisar también los ya aprobados? (s/N) ")
        only = self._choose_store(STORE_ORDER)
        stores = [only] if only else [s for s in STORE_ORDER if s in config.stores]
        lider_manual = only == "lider"
        if "lider" in stores and not lider_manual:
            lider_manual = self.confirm(
                "Lider no tiene búsqueda automática. "
                "¿Ingresar SKUs de Lider a mano, producto por producto? (s/N) "
            )
        pairs = [
            (item, store)
            for item in config.basket
            for store in stores
            if (store == "lider" and lider_manual)
            or (store != "lider" and section.candidates.get((item.id, store)))
            if review or store not in config.matches.get(item.id, {})
        ]
        if not pairs:
            self.say("No hay pares producto/súper para revisar.")
            return True
        chosen: list[NewMatch] = []
        replace: set[tuple[str, str]] = set()
        names = self.status().store_names
        interrupted = False
        try:
            for index, (item, store) in enumerate(pairs, 1):
                current = config.matches.get(item.id, {}).get(store)
                self.say("", f"[{index}/{len(pairs)}] {item.name} · {names.get(store, store)}")
                decision = self._review_pair(
                    item, store, section.candidates.get((item.id, store), []), current
                )
                if decision == _QUIT:
                    break
                if isinstance(decision, NewMatch):
                    chosen.append(decision)
                    if current is not None:
                        replace.add((item.id, store))
        except (KeyboardInterrupt, EOFError):
            if not chosen:
                raise  # nothing to keep: plain cancellation back to the menu
            interrupted = True
        saved = self._save(chosen, replace)
        if interrupted and saved:
            self.say(f"Interrumpido: se guardaron {len(chosen)} elecciones hechas hasta ahora.")
        return saved

    def _review_pair(
        self, item: BasketItem, store: str, candidates: list[Candidate], current: Match | None
    ) -> NewMatch | str:
        if current is not None:
            self.say(f"   Aprobado actual: SKU {current.sku} (tamaño {current.size:g})")
        shown = candidates[:MAX_CANDIDATES]
        for number, candidate in enumerate(shown, 1):
            brand = f" · {candidate.brand}" if candidate.brand else ""
            suggested = "  ← sugerido" if number == 1 else ""
            self.say(
                f"  {number}) {candidate.name}{brand} · {format_clp(candidate.price)} · "
                f"{format_clp(candidate.unit_price)}/{candidate.unit}{suggested}"
            )
        if shown:
            self.say(
                f"  Enter=sugerido · 1-{len(shown)}=elegir · s=saltar · m=SKU manual · "
                "q o Ctrl+C=guardar y salir"
            )
        else:
            self.say("  m=SKU manual · Enter/s=saltar · q o Ctrl+C=guardar y salir")
        while True:
            answer = self.ask("> ").lower()
            if answer == "q":
                return _QUIT
            if answer == "s" or (answer == "" and not shown):
                return _SKIP
            if answer == "m":
                match = self._manual(item, store)
            elif answer == "":
                match = self._from_candidate(shown[0])
            elif answer.isdigit() and 1 <= int(answer) <= len(shown):
                match = self._from_candidate(shown[int(answer) - 1])
            else:
                self.say("Respuesta no válida.")
                continue
            if current is not None and not self.confirm(
                f"Ya hay un SKU aprobado ({current.sku}). ¿Reemplazarlo? (s/N) "
            ):
                return _SKIP
            return match

    def _today(self) -> date:
        return self._now().astimezone().date()

    def _from_candidate(self, candidate: Candidate) -> NewMatch:
        return NewMatch(
            item_id=candidate.item_id,
            store=candidate.store,
            sku=candidate.sku,
            size=candidate.size,
            approved=self._today(),
            url=candidate.url if candidate.store == "lider" else None,
        )

    def _manual(self, item: BasketItem, store: str) -> NewMatch:
        sku = ""
        while not sku:
            sku = self.ask("SKU: ")
        size: float | None = None
        while size is None:
            raw = self.ask(f"Tamaño en {item.unit.value} [{item.reference_qty:g}]: ")
            try:
                size = float(raw.replace(",", ".")) if raw else item.reference_qty
            except ValueError:
                size = None
            if size is not None and size <= 0:
                size = None
            if size is None:
                self.say("Tamaño no válido: escribe un número mayor que 0.")
        url: str | None = None
        while store == "lider" and not url:
            raw = self.ask("URL del producto en Lider: ")
            url = raw if raw.startswith(("https://", "http://")) else None
            if url is None:
                self.say("URL no válida: debe empezar con https://")
        return NewMatch(item.id, store, sku, size, self._today(), url)

    def _save(self, chosen: list[NewMatch], replace: set[tuple[str, str]]) -> bool:
        if not chosen:
            self.say("", "No se eligió ningún producto; matches.yaml no cambió.")
        else:
            try:
                result = write_matches(
                    self.paths.config,
                    chosen,
                    confirm_replace=lambda item, store: (item, store) in replace,
                    now=self._now(),
                )
            except ApproveError as exc:
                self.say("", f"No se pudo guardar: {exc}")
                return False
            self.say(
                "",
                f"Guardado en config/matches.yaml: {len(result.added)} nuevos, "
                f"{len(result.replaced)} reemplazados"
                + (f" (respaldo: {result.backup.name})" if result.backup else "")
                + ".",
            )
        status = self.status()
        self.say(f"Aprobados por súper (meta {status.threshold}):")
        for store, count in status.approved.items():
            missing = status.threshold - count
            verdict = "✔ cumple la meta" if missing <= 0 else f"faltan {missing}"
            self.say(f"  {status.store_names[store]}: {count}/{status.basket_size} {verdict}")
        return True

    # ── report helpers ─────────────────────────────────────────────────

    def _read_report(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.paths.report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _report_mtime(self) -> int | None:
        try:
            return self.paths.report.stat().st_mtime_ns
        except OSError:
            return None


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orchestrator", description="Menú interactivo de Canasta Santiago."
    )
    parser.add_argument("--config", type=Path, help="carpeta de configuración (config/)")
    parser.add_argument("--data", type=Path, help="carpeta de datos (data/)")
    args = parser.parse_args(argv)
    base = (root or Path.cwd()).resolve()
    paths = Paths.from_root(
        base,
        config=args.config.resolve() if args.config else None,
        data=args.data.resolve() if args.data else None,
    )
    return App(paths).run()
