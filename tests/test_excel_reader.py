import math
from pathlib import Path

import openpyxl
import pytest

from rpa_challenge.excel_reader import ExcelSchemaError, cell_to_text, load_challenge_rows

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "data" / "challenge.xlsx"
OFFICIAL_SHA256 = "cf1a8c04a298cc12cb481a0a6c88b078b209dc59c4983f6ca78714d611c04d37"


def _save(path: Path, header: list[object], data_rows: list[list[object]]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(header)
    for row in data_rows:
        sheet.append(row)
    workbook.save(path)


HEADER = [
    "First Name",
    "Last Name ",
    "Company Name",
    "Role in Company",
    "Address",
    "Email",
    "Phone Number",
]


def test_cell_to_text_preserves_phone_digits():
    assert cell_to_text(40716543298) == "40716543298"
    assert cell_to_text(40716543298.0) == "40716543298"
    assert cell_to_text("  Ana  ") == "Ana"
    assert cell_to_text(None) == ""
    with pytest.raises(ExcelSchemaError):
        cell_to_text(math.nan)


def test_official_workbook_has_ten_rows_and_is_not_hardcoded():
    loaded = load_challenge_rows(OFFICIAL)
    assert loaded.sha256 == OFFICIAL_SHA256
    assert loaded.raw_headers[1] == "Last Name "
    assert len(loaded.rows) == 10
    assert all(row.complete for row in loaded.rows)
    assert all(row.values["Phone Number"].isdigit() for row in loaded.rows)
    assert all("@" in row.values["Email"] for row in loaded.rows)

    workbook = openpyxl.load_workbook(OFFICIAL, read_only=True, data_only=False)
    try:
        sheet = workbook.worksheets[0]
        independent = []
        for index, row in enumerate(sheet.iter_rows(min_row=2, max_row=11, values_only=True), start=2):
            independent.append((index, str(row[0]), str(int(row[6]))))
    finally:
        workbook.close()
    assert [(row.excel_row, row.values["First Name"], row.values["Phone Number"]) for row in loaded.rows] == independent


def test_blank_rows_and_trailing_header_space(tmp_path: Path):
    path = tmp_path / "book.xlsx"
    _save(
        path,
        HEADER + [None],
        [
            ["Ana", "Souza", "Nava", "Dev", "Rua 1", "ana@example.com", 11988887777],
            [None, None, None, None, None, None, None],
            ["Bruno", "Lima", "Nava", "QA", "Rua 2", "bruno@example.com", 11977776666.0],
        ],
    )
    loaded = load_challenge_rows(path)
    assert [row.excel_row for row in loaded.rows] == [2, 4]
    assert loaded.rows[0].values["Last Name"] == "Souza"
    assert loaded.rows[1].values["Phone Number"] == "11977776666"


def test_collapsed_header_spaces_still_match(tmp_path: Path):
    path = tmp_path / "spaces.xlsx"
    header = HEADER.copy()
    header[3] = "Role   in   Company"
    _save(path, header, [["Ana", "Souza", "Nava", "Dev", "Rua 1", "ana@example.com", "1"]])
    loaded = load_challenge_rows(path)
    assert loaded.rows[0].values["Role in Company"] == "Dev"


def test_missing_value_is_flagged_without_dropping_the_row(tmp_path: Path):
    path = tmp_path / "gap.xlsx"
    _save(path, HEADER, [["Ana", "Souza", "Nava", "Dev", "Rua 1", "", 123]])
    loaded = load_challenge_rows(path)
    assert loaded.rows[0].missing_fields == ("Email",)


def test_schema_errors(tmp_path: Path):
    with pytest.raises(ExcelSchemaError, match="não encontrado"):
        load_challenge_rows(tmp_path / "ausente.xlsx")

    empty = tmp_path / "vazio.xlsx"
    openpyxl.Workbook().save(empty)
    with pytest.raises(ExcelSchemaError, match="vazia|dados"):
        load_challenge_rows(empty)

    unknown = tmp_path / "unknown.xlsx"
    _save(unknown, HEADER + ["Apelido"], [["Ana", "Souza", "Nava", "Dev", "Rua 1", "a@b.co", 1, "x"]])
    with pytest.raises(ExcelSchemaError, match="desconhecido"):
        load_challenge_rows(unknown)

    duplicate = tmp_path / "dup.xlsx"
    _save(
        duplicate,
        ["First Name", "Last Name", "Company Name", "Role in Company", "Address", "Email", "Phone Number", "Email"],
        [["Ana", "Souza", "Nava", "Dev", "Rua 1", "a@b.co", 1, "b@b.co"]],
    )
    with pytest.raises(ExcelSchemaError, match="duplicado"):
        load_challenge_rows(duplicate)

    missing_column = tmp_path / "missing-col.xlsx"
    _save(missing_column, HEADER[:-1], [["Ana", "Souza", "Nava", "Dev", "Rua 1", "a@b.co"]])
    with pytest.raises(ExcelSchemaError, match="ausentes"):
        load_challenge_rows(missing_column)

    only_header = tmp_path / "so-cabecalho.xlsx"
    _save(only_header, HEADER, [])
    with pytest.raises(ExcelSchemaError, match="não tem linhas"):
        load_challenge_rows(only_header)
