import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import openpyxl
import pytest

from rpa_challenge.excel_reader import load_challenge_rows
from rpa_challenge.runner import Settings, run_challenge
from rpa_challenge.step_log import StepLog

FIXTURE = Path(__file__).resolve().parent / "fixtures"
HEADER = [
    "First Name",
    "Last Name ",
    "Company Name",
    "Role in Company",
    "Address",
    "Email",
    "Phone Number",
]


def _workbook(path: Path, rows: list[list[object]]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def _row(name: str, phone: int) -> list[object]:
    return [name, "Silva", "Oficina", "Analista", "Rua A", f"{name.lower()}@example.com", phone]


@pytest.fixture(scope="module")
def site():
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURE))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/mini_challenge.html"
    yield base
    server.shutdown()


def _run(tmp_path: Path, url: str, rows: list[list[object]], timeout_ms: int = 10000):
    workbook = tmp_path / "dados.xlsx"
    _workbook(workbook, rows)
    loaded = load_challenge_rows(workbook)
    settings = Settings(
        challenge_url=url,
        output_dir=tmp_path / "saida",
        headless=True,
        browser_channel="chrome",
        navigation_timeout_ms=timeout_ms,
        action_timeout_ms=timeout_ms,
        screenshot_every_round=True,
    )
    log = StepLog(settings.output_dir / "passos.jsonl", settings.timezone)
    try:
        return run_challenge(list(loaded.rows), settings, log)
    finally:
        log.close()


def test_local_form_reads_excel_and_scores_two_rounds(site: str, tmp_path: Path):
    result = _run(tmp_path, f"{site}?rounds=2", [_row("Ana", 11911111111), _row("Bruno", 11922222222)])
    assert result.summary["linhas_ok"] == 2
    assert result.summary["linhas_nok"] == 0
    score = result.summary["pontuacao"]
    assert score["percentual"] == 100
    assert score["campos_corretos"] == 14
    assert score["campos_totais"] == 14
    assert result.rows[0]["Status"] == "OK"
    assert result.rows[0]["Timestamp"].endswith("-03:00")
    assert "Excel" in result.rows[0]["Observação"]
    final = tmp_path / "saida" / "screenshots" / "pontuacao-final.png"
    assert final.is_file()
    assert final.read_bytes().startswith(b"\x89PNG")
    steps = (tmp_path / "saida" / "passos.jsonl").read_text(encoding="utf-8")
    assert steps.count('"ordem_dos_campos"') == 2


def test_unknown_label_is_nok_and_still_finishes(site: str, tmp_path: Path):
    url = f"{site}?rounds=1&renameFrom=Phone%20Number&renameTo=Apelido"
    result = _run(tmp_path, url, [_row("Carla", 11933333333)])
    assert result.summary["linhas_nok"] == 1
    assert result.rows[0]["Status"] == "NOK"
    note = result.rows[0]["Observação"]
    assert "Phone Number" in note or "Apelido" in note
    assert result.summary["pontuacao"]["campos_totais"] == 7


def test_value_that_does_not_stick_is_nok(site: str, tmp_path: Path):
    result = _run(tmp_path, f"{site}?rounds=1&wipe=labelEmail", [_row("Dora", 11944444444)])
    assert result.rows[0]["Status"] == "NOK"
    assert "Email" in result.rows[0]["Observação"]
    assert result.summary["pontuacao"]["percentual"] < 100


def test_row_after_the_challenge_ends_is_not_sent(site: str, tmp_path: Path):
    result = _run(tmp_path, f"{site}?rounds=1", [_row("Eva", 11955555555), _row("Fabio", 11966666666)])
    assert result.rows[0]["Status"] == "OK"
    assert result.rows[1]["Status"] == "NOK"
    assert "não enviada" in result.rows[1]["Observação"]


def test_unreachable_page_fails_without_inventing_a_score(tmp_path: Path):
    with pytest.raises(Exception):
        _run(tmp_path, "http://127.0.0.1:9/", [_row("Gabi", 11977777777)], timeout_ms=4000)
    assert not (tmp_path / "saida" / "screenshots" / "pontuacao-final.png").exists()
