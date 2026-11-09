import json
from pathlib import Path

from rpa_challenge.report_pdf import build_pdf


def test_pdf_is_written_with_real_png(tmp_path: Path):
    png = tmp_path / "pontuacao-final.png"
    png.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000c4944415408d763f8ffff3f0005fe02fea3a9a0c00000000049454e44ae426082"
        )
    )
    summary = {
        "challenge_url": "https://rpachallenge.com/",
        "excel": {"caminho": "/tmp/challenge.xlsx", "sha256": "abc"},
        "linhas_excel": 1,
        "linhas_ok": 1,
        "linhas_nok": 0,
        "linhas_total": 1,
        "mensagem_pontuacao": "Your success rate is 100% ( 7 out of 7 fields) in 10 milliseconds",
        "pontuacao": {
            "percentual": 100.0,
            "campos_corretos": 7,
            "campos_totais": 7,
            "tempo_site_ms": 10,
        },
        "duracao_parede_ms": 20,
        "inicio": "2026-11-06T18:00:00.000-03:00",
        "fim": "2026-11-06T18:00:01.000-03:00",
        "fuso": "America/Sao_Paulo",
        "navegador": "chrome",
        "headless": True,
        "quantidade_ordens_distintas": 1,
        "screenshots": {"final": "pontuacao-final.png"},
        "bloqueios": [],
        "forms": {"acessivel": False, "preenchido": False, "enviado": False, "motivo": "teste"},
        "testes": {"executado": True, "passou": True, "comando": "pytest", "saida": "1 passed"},
        "limitacoes": ["Limitação de teste."],
        "eventos_ordem": 1,
        "arquivos_gerados": True,
        "cabecalho_last_name_com_espaco": True,
        "artefatos": {"pdf": "/opt/cursor/artifacts/relatorio-desafio-rpa.pdf"},
    }
    rows = [{
        "Indice": 1,
        "Linha Excel": 2,
        "First Name": "Ana",
        "Last Name": "Souza",
        "Status": "OK",
        "Timestamp": "2026-11-06T18:00:00.000-03:00",
        "Observação": "Preenchido.",
    }]
    pdf = build_pdf(summary, rows, tmp_path / "relatorio.pdf", tmp_path)
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 2000
    json.dumps(summary)
