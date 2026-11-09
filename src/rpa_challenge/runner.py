"""Preenche o formulário público do RPA Challenge no navegador real."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Browser, Page, Playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from rpa_challenge.clock import now_iso
from rpa_challenge.excel_reader import ChallengeRow
from rpa_challenge.matching import CANONICAL_FIELDS, parse_score_message, xpath_string
from rpa_challenge.results_writer import row_payload
from rpa_challenge.step_log import StepLog

MAX_SCORED_ROUNDS = 10


@dataclass
class Settings:
    challenge_url: str
    output_dir: Path
    timezone: str = "America/Sao_Paulo"
    headless: bool = True
    browser_channel: str = "chrome"
    viewport_width: int = 1440
    viewport_height: int = 1100
    navigation_timeout_ms: int = 45000
    action_timeout_ms: int = 15000
    screenshot_every_round: bool = True


@dataclass
class RunOutput:
    rows: list[dict[str, object]]
    summary: dict[str, object]


def launch_browser(playwright: Playwright, settings: Settings) -> tuple[Browser, str]:
    launch_args = ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"]
    errors: list[str] = []
    if settings.browser_channel:
        try:
            browser = playwright.chromium.launch(
                channel=settings.browser_channel,
                headless=settings.headless,
                args=launch_args,
            )
            return browser, settings.browser_channel
        except Exception as exc:
            errors.append(f"{settings.browser_channel}: {exc}")
    try:
        browser = playwright.chromium.launch(headless=settings.headless, args=launch_args)
    except Exception as exc:
        errors.append(f"chromium: {exc}")
        raise RuntimeError(
            "Não foi possível abrir o navegador. " + " | ".join(errors)
        ) from exc
    return browser, "playwright-chromium"


def _round_label(page: Page) -> str:
    return page.evaluate(
        """() => {
            const buttons = [...document.querySelectorAll('button')];
            for (const button of buttons) {
                const text = (button.textContent || '').trim();
                if (button.offsetParent !== null && /^Round\\s+\\d+/.test(text)) {
                    return text;
                }
            }
            return '';
        }"""
    )


def _input_ids(page: Page) -> list[str]:
    return page.evaluate(
        "() => [...document.querySelectorAll('rpa1-field input')].map((el) => el.id)"
    )


def _read_fields(page: Page) -> list[dict[str, object]]:
    return page.evaluate(
        """() => {
            const nodes = [...document.querySelectorAll('rpa1-field')];
            return nodes.map((node) => {
                const label = node.querySelector('label');
                const input = node.querySelector('input');
                const rect = node.getBoundingClientRect();
                return {
                    label: label ? label.textContent.replace(/\\s+/g, ' ').trim() : '',
                    control: input ? (input.getAttribute('formcontrolname') || '') : '',
                    x: rect.x,
                    y: rect.y,
                };
            });
        }"""
    )


def _visual_order(fields: list[dict[str, object]]) -> list[str]:
    ordered = sorted(
        fields,
        key=lambda item: (round(float(item["y"]), 1), round(float(item["x"]), 1)),
    )
    return [str(item["label"]) for item in ordered]


def _input_locator(page: Page, label: str):
    return page.locator(
        "xpath=//rpa1-field[normalize-space(.//label)=" + xpath_string(label) + "]//input"
    )


def _write_input(locator, value: str) -> str:
    """Digita no campo visível. Se o site o esconder, grava o valor no input real e dispara os eventos."""
    try:
        locator.fill(value, timeout=3000)
    except Exception:
        locator.evaluate(
            """(element, nextValue) => {
                element.focus();
                element.value = nextValue;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            value,
        )
    return locator.input_value()


def _screenshot(page: Page, directory: Path, name: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    page.screenshot(path=str(path), full_page=True)
    return str(Path("screenshots") / name)


def _score_visible(page: Page) -> bool:
    message = page.locator(".message2")
    if message.count() == 0:
        return False
    try:
        text = message.inner_text()
    except Exception:
        return False
    return "success rate" in text.lower()


def _wait_for_fresh_fields(
    page: Page,
    previous_round: str,
    previous_ids: list[str],
    timeout_ms: int,
) -> str:
    """Espera a rodada mudar e os inputs serem recriados.

    O site embaralha os campos no mesmo ciclo em que troca o texto do botão.
    Comparar os ids evita preencher o formulário antigo.
    """
    page.wait_for_function(
        """([previousRound, previousIds]) => {
            const message = document.querySelector('.message2');
            if (message && /success rate/i.test(message.textContent || '')) {
                return true;
            }
            const roundChanged = [...document.querySelectorAll('button')].some((button) => {
                const text = (button.textContent || '').trim();
                return button.offsetParent !== null
                    && /^Round\\s+\\d+/.test(text)
                    && text !== previousRound;
            });
            const ids = [...document.querySelectorAll('rpa1-field input')].map((el) => el.id);
            const changed = ids.length === 7 && ids.join('|') !== previousIds.join('|');
            return roundChanged && changed;
        }""",
        arg=[previous_round, previous_ids],
        timeout=timeout_ms,
    )
    if _score_visible(page):
        return "concluido"
    return _round_label(page)


def _fill_row(
    page: Page, row: ChallengeRow, log: StepLog, round_name: str
) -> tuple[str, str, list[str]]:
    fields = _read_fields(page)
    labels = [str(item["label"]) for item in fields]
    order = _visual_order(fields)
    log.event(
        "ordem_dos_campos",
        rodada=round_name,
        linha_excel=row.excel_row,
        ordem_visual=order,
        ordem_dom=labels,
        controles=[str(item["control"]) for item in fields],
    )
    if len(fields) != 7:
        return (
            "NOK",
            f"A tela apresentou {len(fields)} campos; eram esperados 7. "
            f"Ordem lida: {' | '.join(labels) or 'nenhuma'}.",
            order,
        )

    problems: list[str] = []
    seen: set[str] = set()
    expected = {name.casefold(): name for name in CANONICAL_FIELDS}
    for label in labels:
        canonical = expected.get(" ".join(label.split()).casefold())
        if canonical is None:
            problems.append(f"legenda desconhecida '{label}'")
            continue
        if canonical in seen:
            problems.append(f"legenda duplicada '{label}'")
            continue
        seen.add(canonical)
        value = row.values.get(canonical, "")
        if not value:
            problems.append(f"valor vazio no Excel para {canonical}")
            continue
        locator = _input_locator(page, label)
        if locator.count() != 1:
            problems.append(f"não foi possível apontar o input de {canonical}")
            continue
        actual = _write_input(locator, value)
        if actual != value:
            actual = _write_input(locator, value)
        if actual != value:
            problems.append(
                f"{canonical} não reteve o valor do Excel (lido no DOM: {actual!r})"
            )

    for name in CANONICAL_FIELDS:
        if name not in seen:
            problems.append(f"campo ausente na tela: {name}")

    if problems:
        return (
            "NOK",
            "Falha no preenchimento: "
            + "; ".join(problems)
            + f". Ordem visual: {' | '.join(order)}.",
            order,
        )
    return (
        "OK",
        "Campos localizados pela legenda, preenchidos com o Excel e conferidos no DOM. "
        f"Ordem visual: {' | '.join(order)}.",
        order,
    )


def _mark_not_sent(
    results: list[dict[str, object]],
    rows: list[ChallengeRow],
    start_index: int,
    tz_name: str,
    observacao: str,
) -> None:
    for offset, pending in enumerate(rows[start_index - 1 :], start=start_index):
        results.append(
            row_payload(
                indice=offset,
                linha_excel=pending.excel_row,
                valores=pending.values,
                ordem=[],
                status="NOK",
                observacao=observacao,
                timestamp=now_iso(tz_name),
                duracao_ms=0,
            )
        )


def run_challenge(
    rows: list[ChallengeRow],
    settings: Settings,
    log: StepLog,
) -> RunOutput:
    output_dir = Path(settings.output_dir)
    screenshot_dir = output_dir / "screenshots"
    screenshots: dict[str, object] = {"rodadas": []}
    results: list[dict[str, object]] = []
    blockers: list[str] = []
    started = now_iso(settings.timezone)
    wall_start: float | None = None
    score: dict[str, object] | None = None
    raw_message = ""
    browser_name = ""
    distinct_orders: set[str] = set()

    with sync_playwright() as playwright:
        browser, browser_name = launch_browser(playwright, settings)
        log.event("navegador_aberto", navegador=browser_name, headless=settings.headless)
        context = browser.new_context(
            viewport={"width": settings.viewport_width, "height": settings.viewport_height},
            locale="en-US",
            timezone_id=settings.timezone,
        )
        page = context.new_page()
        page.set_default_timeout(settings.action_timeout_ms)
        page.set_default_navigation_timeout(settings.navigation_timeout_ms)
        page.on(
            "pageerror",
            lambda exc: log.event("erro_javascript_da_pagina", nivel="warning", mensagem=str(exc)),
        )
        try:
            log.event("abrindo_pagina", url=settings.challenge_url)
            page.goto(settings.challenge_url, wait_until="domcontentloaded")
            page.get_by_role("button", name="Start", exact=True).wait_for(state="visible")
            page.locator("rpa1-field input").nth(6).wait_for(state="attached")
            screenshots["inicial"] = _screenshot(page, screenshot_dir, "00-pagina-inicial.png")
            log.event("pagina_pronta", screenshot=screenshots["inicial"])

            ids_before_start = _input_ids(page)
            wall_start = time.perf_counter()
            page.get_by_role("button", name="Start", exact=True).click()
            _wait_for_fresh_fields(page, "", ids_before_start, settings.action_timeout_ms)
            screenshots["apos_start"] = _screenshot(page, screenshot_dir, "01-desafio-iniciado.png")
            log.event(
                "desafio_iniciado",
                rodada=_round_label(page),
                screenshot=screenshots["apos_start"],
            )

            submissions = 0
            for index, row in enumerate(rows, start=1):
                timestamp = now_iso(settings.timezone)
                row_started = time.perf_counter()
                if submissions >= MAX_SCORED_ROUNDS or _score_visible(page):
                    results.append(
                        row_payload(
                            indice=index,
                            linha_excel=row.excel_row,
                            valores=row.values,
                            ordem=[],
                            status="NOK",
                            observacao=(
                                "Linha não enviada: o desafio público encerra a pontuação em 10 envios."
                            ),
                            timestamp=timestamp,
                            duracao_ms=0,
                        )
                    )
                    log.event(
                        "linha_nao_enviada",
                        nivel="warning",
                        linha_excel=row.excel_row,
                        motivo="limite_de_10_rodadas",
                    )
                    continue

                round_name = _round_label(page) or f"Round {index}"
                log.event(
                    "rodada_iniciada",
                    rodada=round_name,
                    linha_excel=row.excel_row,
                    indice=index,
                )
                try:
                    status, observacao, order = _fill_row(page, row, log, round_name)
                except PlaywrightTimeoutError as exc:
                    status, observacao, order = (
                        "NOK",
                        f"Tempo esgotado ao preencher a rodada {round_name}: {exc}",
                        [],
                    )
                if order:
                    distinct_orders.add(" | ".join(order))

                shot = ""
                if settings.screenshot_every_round:
                    try:
                        shot = _screenshot(
                            page,
                            screenshot_dir,
                            f"rodada-{index:02d}-preenchida.png",
                        )
                        rodadas = screenshots["rodadas"]
                        assert isinstance(rodadas, list)
                        rodadas.append(shot)
                    except Exception as exc:
                        log.event(
                            "captura_falhou",
                            nivel="warning",
                            linha_excel=row.excel_row,
                            mensagem=str(exc),
                        )

                try:
                    previous_round = _round_label(page)
                    previous_ids = _input_ids(page)
                    page.locator('input[type="submit"]').click()
                    outcome = _wait_for_fresh_fields(
                        page,
                        previous_round,
                        previous_ids,
                        settings.action_timeout_ms,
                    )
                    submissions += 1
                    log.event(
                        "formulario_enviado",
                        rodada=round_name,
                        linha_excel=row.excel_row,
                        resultado_espera=outcome,
                        status_preenchimento=status,
                    )
                except PlaywrightTimeoutError as exc:
                    status = "NOK"
                    observacao = (
                        f"{observacao} O envio não avançou a rodada dentro do tempo limite."
                    ).strip()
                    blockers.append(f"Linha {row.excel_row}: envio não confirmado.")
                    log.event(
                        "falha_de_envio",
                        nivel="error",
                        linha_excel=row.excel_row,
                        mensagem=str(exc),
                    )
                    results.append(
                        row_payload(
                            indice=index,
                            linha_excel=row.excel_row,
                            valores=row.values,
                            ordem=order,
                            status=status,
                            observacao=observacao,
                            timestamp=timestamp,
                            duracao_ms=int((time.perf_counter() - row_started) * 1000),
                        )
                    )
                    _mark_not_sent(
                        results,
                        rows,
                        index + 1,
                        settings.timezone,
                        "Não enviada: a rodada anterior não avançou e o contador do site ficaria fora de ordem.",
                    )
                    break

                if status == "NOK":
                    observacao += " O formulário foi enviado para manter a sequência de rodadas."
                if shot:
                    observacao += f" Captura: {shot}."
                results.append(
                    row_payload(
                        indice=index,
                        linha_excel=row.excel_row,
                        valores=row.values,
                        ordem=order,
                        status=status,
                        observacao=observacao,
                        timestamp=timestamp,
                        duracao_ms=int((time.perf_counter() - row_started) * 1000),
                    )
                )

            if _score_visible(page):
                raw_message = page.locator(".message2").inner_text().strip()
                parsed = parse_score_message(raw_message)
                score = parsed
                screenshots["final"] = _screenshot(page, screenshot_dir, "pontuacao-final.png")
                try:
                    page.locator(".congratulations").screenshot(
                        path=str(screenshot_dir / "pontuacao-final-recorte.png")
                    )
                    screenshots["final_recorte"] = "screenshots/pontuacao-final-recorte.png"
                except Exception as exc:
                    log.event("recorte_indisponivel", nivel="warning", mensagem=str(exc))
                log.event(
                    "pontuacao_capturada",
                    mensagem=raw_message,
                    pontuacao=parsed,
                    screenshot=screenshots.get("final"),
                )
            else:
                blockers.append(
                    "O site não publicou a frase final de pontuação após os envios."
                )
                screenshots["final_ausente"] = _screenshot(
                    page, screenshot_dir, "pontuacao-ausente.png"
                )
                log.event(
                    "pontuacao_ausente",
                    nivel="warning",
                    screenshot=screenshots["final_ausente"],
                )
        finally:
            context.close()
            browser.close()
            log.event("navegador_fechado")

    finished = now_iso(settings.timezone)
    wall_ms = None
    if wall_start is not None:
        wall_ms = int((time.perf_counter() - wall_start) * 1000)
    summary: dict[str, object] = {
        "inicio": started,
        "fim": finished,
        "navegador": browser_name,
        "headless": settings.headless,
        "linhas_total": len(results),
        "linhas_ok": sum(1 for row in results if row["Status"] == "OK"),
        "linhas_nok": sum(1 for row in results if row["Status"] == "NOK"),
        "pontuacao": score,
        "mensagem_pontuacao": raw_message,
        "duracao_parede_ms": wall_ms,
        "ordens_distintas": sorted(item for item in distinct_orders if item),
        "quantidade_ordens_distintas": len([item for item in distinct_orders if item]),
        "screenshots": screenshots,
        "bloqueios": blockers,
        "challenge_url": settings.challenge_url,
    }
    return RunOutput(rows=results, summary=summary)
