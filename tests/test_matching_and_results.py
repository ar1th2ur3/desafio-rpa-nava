import csv
import json
from pathlib import Path

import pytest

from rpa_challenge.matching import UnknownLabelError, canonical_label, parse_score_message
from rpa_challenge.results_writer import row_payload, write_results


def test_canonical_label_ignores_outer_space_and_case():
    assert canonical_label("Last Name ") == "Last Name"
    assert canonical_label("  PHONE   NUMBER ") == "Phone Number"
    with pytest.raises(UnknownLabelError):
        canonical_label("Apelido")


def test_parse_score_message_from_the_live_sentence():
    parsed = parse_score_message(
        "Your success rate is 100% ( 70 out of 70 fields) in 5234 milliseconds"
    )
    assert parsed is not None
    assert parsed["percentual"] == 100
    assert parsed["campos_corretos"] == 70
    assert parsed["campos_totais"] == 70
    assert parsed["tempo_site_ms"] == 5234

    fractional = parse_score_message(
        "Your success rate is 98.57142857142857% ( 69 out of 70 fields) in 10 milliseconds"
    )
    assert fractional is not None
    assert fractional["campos_corretos"] == 69
    assert parse_score_message("Congratulations") is None
    assert parse_score_message("") is None


def test_results_keep_status_note_and_sao_paulo_timestamp(tmp_path: Path):
    timestamp = "2026-11-06T18:20:01.123-03:00"
    row = row_payload(
        indice=1,
        linha_excel=2,
        valores={"First Name": "Ana", "Last Name": "Souza", "Email": "ana@example.com"},
        ordem=["Email", "First Name"],
        status="OK",
        observacao="Preenchido com o Excel.",
        timestamp=timestamp,
        duracao_ms=120,
    )
    csv_path, json_path = write_results(tmp_path / "resultados", [row], "America/Sao_Paulo")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        saved = list(csv.DictReader(handle))
    assert saved[0]["Status"] == "OK"
    assert saved[0]["Observação"] == "Preenchido com o Excel."
    assert saved[0]["Timestamp"].endswith("-03:00")
    assert saved[0]["First Name"] == "Ana"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["fuso"] == "America/Sao_Paulo"
    assert payload["linhas"][0]["Status"] == "OK"
    with pytest.raises(ValueError):
        row_payload(
            indice=1,
            linha_excel=2,
            valores={},
            ordem=[],
            status="MAYBE",
            observacao="",
            timestamp=timestamp,
            duracao_ms=0,
        )
