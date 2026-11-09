"""Linha de comando da execução e da remontagem do PDF."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

from rpa_challenge import __version__
from rpa_challenge.clock import now_iso
from rpa_challenge.excel_reader import ExcelSchemaError, load_challenge_rows
from rpa_challenge.forms_inspect import inspect_forms
from rpa_challenge.report_pdf import build_pdf
from rpa_challenge.results_writer import write_results
from rpa_challenge.runner import Settings, launch_browser, run_challenge
from rpa_challenge.step_log import StepLog

LIMITATIONS = [
    "O site compara os dez envios com a própria lista interna do idioma inglês. A automação digita o que está na planilha; ela não corrige célula para forçar a nota.",
    "A pontuação do site só aparece depois de dez envios. Uma planilha com outra quantidade é registrada, mas não produz o mesmo encerramento.",
    "O tempo exibido pelo site inclui capturas de tela feitas antes de cada envio. A porcentagem mede acerto dos campos, não velocidade.",
    "A consulta ao Microsoft Forms é só leitura. Se a página pedir login, o conteúdo das perguntas fica inacessível e nada é preenchido.",
    "A execução depende do site público e de um Chrome local. Uma falha de rede ou uma mudança do HTML aparece como NOK ou como bloqueio, sem nota inventada.",
]


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Configuração não encontrada: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Configuração inválida: {path}")
    return data


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa o RPA Challenge a partir do Excel.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--excel")
    parser.add_argument("--output")
    parser.add_argument("--url")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--skip-forms", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--pytest-report", default="")
    return parser


def _settings(config: dict, args: argparse.Namespace) -> tuple[Settings, Path, bool, str]:
    excel = Path(args.excel or config["excel_path"])
    output = Path(args.output or config["output_dir"])
    settings = Settings(
        challenge_url=args.url or config["challenge_url"],
        output_dir=output,
        timezone=config.get("timezone", "America/Sao_Paulo"),
        headless=not args.headed and bool(config.get("headless", True)),
        browser_channel=str(config.get("browser_channel") or "chrome"),
        viewport_width=int(config.get("viewport_width", 1440)),
        viewport_height=int(config.get("viewport_height", 1100)),
        navigation_timeout_ms=int(config.get("navigation_timeout_ms", 45000)),
        action_timeout_ms=int(config.get("action_timeout_ms", 15000)),
        screenshot_every_round=bool(config.get("screenshot_every_round", True)),
    )
    inspect = bool(config.get("inspect_forms", True)) and not args.skip_forms
    forms_url = str(config.get("forms_url") or "")
    return settings, excel, inspect, forms_url


def _count_order_events(path: Path) -> int:
    if not path.is_file():
        return 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if '"ordem_dos_campos"' in line:
            total += 1
    return total


def _read_pytest(path: str) -> dict[str, object]:
    if not path:
        return {"executado": False}
    file = Path(path)
    if not file.is_file():
        return {"executado": False, "motivo": f"Arquivo de teste ausente: {file}"}
    text = file.read_text(encoding="utf-8", errors="replace").strip()
    passed = "failed" not in text.lower() and "error" not in text.lower() and text != ""
    # pytest -q ends with "N passed". A failure also contains "failed".
    if "passed" in text and "failed" not in text and "error" not in text:
        passed = True
    elif "failed" in text or "error" in text:
        passed = False
    return {
        "executado": True,
        "passou": passed,
        "comando": "PYTHONPATH=src .venv/bin/python -m pytest",
        "saida": text[-1500:],
        "arquivo": str(file.resolve()),
    }


def _base_summary(excel_data, settings: Settings) -> dict[str, object]:
    return {
        "versao": __version__,
        "ferramentas": [
            f"Python {platform.python_version()}",
            "Playwright",
            "openpyxl",
            "reportlab",
            settings.browser_channel or "chromium",
        ],
        "autoria": "Agente de automação. Sem autoria humana e sem relato de experiência pessoal.",
        "dados_fixos_no_codigo": False,
        "fuso": settings.timezone,
        "challenge_url": settings.challenge_url,
        "excel": {
            "caminho": excel_data.path,
            "sha256": excel_data.sha256,
            "planilha": excel_data.sheet_name,
            "cabecalhos_brutos": list(excel_data.raw_headers),
        },
        "linhas_excel": len(excel_data.rows),
        "cabecalho_last_name_com_espaco": any(header == "Last Name " for header in excel_data.raw_headers),
        "limitacoes": LIMITATIONS,
        "forms": {
            "consultado": False,
            "preenchido": False,
            "enviado": False,
            "acessivel": False,
            "motivo": "Consulta não realizada.",
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _inspect(settings: Settings, forms_url: str, output_dir: Path, log: StepLog) -> dict[str, object]:
    if not forms_url:
        return {
            "consultado": False,
            "preenchido": False,
            "enviado": False,
            "acessivel": False,
            "motivo": "URL do Forms ausente.",
        }
    log.event("forms_consulta_iniciada", url=forms_url)
    with sync_playwright() as playwright:
        browser, _name = launch_browser(playwright, settings)
        context = browser.new_context(
            viewport={"width": settings.viewport_width, "height": settings.viewport_height},
            locale="pt-BR",
            timezone_id=settings.timezone,
        )
        page = context.new_page()
        try:
            result = inspect_forms(
                page,
                forms_url,
                output_dir / "screenshots" / "forms-somente-leitura.png",
                settings.navigation_timeout_ms,
            )
        finally:
            context.close()
            browser.close()
    log.event(
        "forms_consulta_encerrada",
        acessivel=result.get("acessivel"),
        preenchido=result.get("preenchido"),
        enviado=result.get("enviado"),
        motivo=result.get("motivo"),
    )
    return result


def execute(args: argparse.Namespace) -> int:
    config = _load_yaml(Path(args.config))
    settings, excel_path, do_forms, forms_url = _settings(config, args)
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log = StepLog(output_dir / "passos.jsonl", settings.timezone)
    exit_code = 0
    try:
        try:
            workbook = load_challenge_rows(excel_path)
        except ExcelSchemaError as exc:
            log.event("excel_invalido", nivel="error", mensagem=str(exc))
            raise
        log.event(
            "excel_lido",
            caminho=workbook.path,
            sha256=workbook.sha256,
            linhas=len(workbook.rows),
            cabecalhos=list(workbook.raw_headers),
        )
        summary = _base_summary(workbook, settings)
        run = run_challenge(list(workbook.rows), settings, log)
        summary.update(run.summary)
        csv_path, json_path = write_results(
            output_dir / "resultados",
            run.rows,
            settings.timezone,
        )
        if do_forms:
            try:
                summary["forms"] = _inspect(settings, forms_url, output_dir, log)
            except Exception as exc:
                summary["forms"] = {
                    "consultado": True,
                    "preenchido": False,
                    "enviado": False,
                    "acessivel": False,
                    "motivo": f"Consulta somente leitura falhou: {exc}",
                }
                log.event("forms_consulta_falhou", nivel="warning", mensagem=str(exc))
        summary["testes"] = _read_pytest(args.pytest_report)
        summary["eventos_ordem"] = _count_order_events(output_dir / "passos.jsonl")
        summary["arquivos_gerados"] = True
        summary["comando"] = "PYTHONPATH=src .venv/bin/python -m rpa_challenge --config config.yaml"
        summary["gerado_em"] = now_iso(settings.timezone)
        _write_json(output_dir / "resumo.json", summary)
        (output_dir / "resultados.meta.json").write_text(
            json.dumps({"csv": str(csv_path), "json": str(json_path)}, indent=2),
            encoding="utf-8",
        )
        if not args.skip_pdf:
            try:
                pdf = build_pdf(summary, run.rows, output_dir / "relatorio-desafio-rpa.pdf", output_dir)
                log.event("pdf_gerado", caminho=str(pdf))
            except Exception as exc:
                summary.setdefault("bloqueios", [])
                if isinstance(summary["bloqueios"], list):
                    summary["bloqueios"].append(f"Falha ao gerar o PDF: {exc}")
                _write_json(output_dir / "resumo.json", summary)
                log.event("pdf_falhou", nivel="error", mensagem=str(exc))
                exit_code = 1
        if summary.get("linhas_nok"):
            exit_code = 2
        score = summary.get("pontuacao")
        if not isinstance(score, dict):
            exit_code = 2
    except Exception as exc:
        exit_code = 1
        log.event("falha_geral", nivel="error", mensagem=str(exc))
        failure = {
            "falha": str(exc),
            "fuso": settings.timezone,
            "fim": now_iso(settings.timezone),
            "bloqueios": [str(exc)],
            "forms": {"preenchido": False, "enviado": False, "consultado": False},
            "limitacoes": LIMITATIONS,
        }
        _write_json(output_dir / "resumo.json", failure)
        print(f"Falha: {exc}", file=sys.stderr)
    finally:
        log.close()
    return exit_code


def report_only(args: argparse.Namespace) -> int:
    config = _load_yaml(Path(args.config))
    output_dir = Path(args.output or config["output_dir"])
    summary_path = output_dir / "resumo.json"
    rows_path = output_dir / "resultados.json"
    if not summary_path.is_file() or not rows_path.is_file():
        raise SystemExit("resultado ausente; execute o desafio antes de remontar o PDF.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = json.loads(rows_path.read_text(encoding="utf-8"))
    rows = payload["linhas"] if isinstance(payload, dict) else payload
    if args.pytest_report:
        summary["testes"] = _read_pytest(args.pytest_report)
    summary["eventos_ordem"] = _count_order_events(output_dir / "passos.jsonl")
    summary["arquivos_gerados"] = True
    pdf = build_pdf(summary, rows, output_dir / "relatorio-desafio-rpa.pdf", output_dir)
    _write_json(summary_path, summary)
    print(f"PDF remontado: {pdf}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.report_only:
        return report_only(args)
    return execute(args)
