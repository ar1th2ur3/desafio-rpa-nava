"""Grava o resultado por linha em CSV e JSON."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from rpa_challenge.matching import CANONICAL_FIELDS

CSV_COLUMNS = (
    "Indice",
    "Linha Excel",
    *CANONICAL_FIELDS,
    "Ordem dos campos",
    "Status",
    "Observação",
    "Timestamp",
    "Duracao ms",
)


def write_results(path_stem: Path, rows: list[dict[str, object]], tz_name: str) -> tuple[Path, Path]:
    path_stem.parent.mkdir(parents=True, exist_ok=True)
    csv_path = path_stem.with_suffix(".csv")
    json_path = path_stem.with_suffix(".json")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    payload = {
        "fuso": tz_name,
        "linhas": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def row_payload(
    *,
    indice: int,
    linha_excel: int,
    valores: dict[str, str],
    ordem: list[str],
    status: str,
    observacao: str,
    timestamp: str,
    duracao_ms: int | None,
) -> dict[str, object]:
    if status not in {"OK", "NOK"}:
        raise ValueError(f"Status inválido: {status}")
    payload: dict[str, object] = {
        "Indice": indice,
        "Linha Excel": linha_excel,
        "Ordem dos campos": " | ".join(ordem),
        "Status": status,
        "Observação": observacao,
        "Timestamp": timestamp,
        "Duracao ms": duracao_ms if duracao_ms is not None else "",
    }
    for name in CANONICAL_FIELDS:
        payload[name] = valores.get(name, "")
    return payload
