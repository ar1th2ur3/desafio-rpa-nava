"""Leitura da planilha do desafio. Os valores não ficam no código."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from rpa_challenge.matching import CANONICAL_FIELDS, UnknownLabelError, canonical_label


class ExcelSchemaError(ValueError):
    """A planilha não tem o formato exigido pelo desafio."""


@dataclass(frozen=True)
class ChallengeRow:
    excel_row: int
    values: dict[str, str]
    missing_fields: tuple[str, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return not self.missing_fields


@dataclass(frozen=True)
class WorkbookData:
    path: str
    sha256: str
    sheet_name: str
    raw_headers: tuple[str, ...]
    rows: tuple[ChallengeRow, ...]


def cell_to_text(value: object) -> str:
    """Converte célula para o texto exato que o formulário compara.

    Telefones da planilha oficial são numéricos. Eles precisam virar dígitos,
    sem notação científica e sem casa decimal.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExcelSchemaError(f"Número inválido na planilha: {value!r}")
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    return str(value).strip()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_challenge_rows(path: Path) -> WorkbookData:
    path = Path(path)
    if not path.is_file():
        raise ExcelSchemaError(f"Arquivo Excel não encontrado: {path}")

    sha256 = _file_sha256(path)
    workbook = openpyxl.load_workbook(path, data_only=False, read_only=True)
    sheet_name = ""
    try:
        worksheet = workbook.worksheets[0]
        sheet_name = worksheet.title
        row_iter = worksheet.iter_rows(values_only=True)
        try:
            header = next(row_iter)
        except StopIteration as exc:
            raise ExcelSchemaError("A planilha está vazia.") from exc

        index_by_field: dict[str, int] = {}
        raw_headers: list[str] = []
        for column, cell in enumerate(header):
            if cell is None or str(cell).strip() == "":
                continue
            raw = str(cell)
            raw_headers.append(raw)
            try:
                name = canonical_label(raw)
            except UnknownLabelError as exc:
                raise ExcelSchemaError(
                    f"Cabeçalho desconhecido na coluna {column + 1}: {raw!r}"
                ) from exc
            if name in index_by_field:
                raise ExcelSchemaError(f"Cabeçalho duplicado: {name}")
            index_by_field[name] = column

        missing_columns = [name for name in CANONICAL_FIELDS if name not in index_by_field]
        if missing_columns:
            raise ExcelSchemaError(
                "Colunas obrigatórias ausentes: " + ", ".join(missing_columns)
            )

        records: list[ChallengeRow] = []
        for excel_row, row in enumerate(row_iter, start=2):
            values: dict[str, str] = {}
            any_value = False
            for name, column in index_by_field.items():
                cell = row[column] if column < len(row) else None
                text = cell_to_text(cell)
                if text:
                    any_value = True
                values[name] = text
            if not any_value:
                continue
            missing = tuple(name for name in CANONICAL_FIELDS if not values[name])
            records.append(
                ChallengeRow(excel_row=excel_row, values=values, missing_fields=missing)
            )
    finally:
        workbook.close()

    if not records:
        raise ExcelSchemaError("A planilha não tem linhas de dados.")

    return WorkbookData(
        path=str(path.resolve()),
        sha256=sha256,
        sheet_name=sheet_name,
        raw_headers=tuple(raw_headers),
        rows=tuple(records),
    )
