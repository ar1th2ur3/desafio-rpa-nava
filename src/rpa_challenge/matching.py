"""Identificação dos campos pela legenda visível, não pela posição."""

from __future__ import annotations

import re

CANONICAL_FIELDS: tuple[str, ...] = (
    "First Name",
    "Last Name",
    "Company Name",
    "Role in Company",
    "Address",
    "Email",
    "Phone Number",
)


class UnknownLabelError(ValueError):
    """A legenda da tela ou do Excel não corresponde a um campo do desafio."""


def normalize_label(value: object) -> str:
    text = str(value if value is not None else "").replace("\xa0", " ")
    return " ".join(text.split()).casefold()


_ALIASES = {normalize_label(name): name for name in CANONICAL_FIELDS}


def canonical_label(raw: object) -> str:
    key = normalize_label(raw)
    try:
        return _ALIASES[key]
    except KeyError as exc:
        raise UnknownLabelError(str(raw)) from exc


def xpath_string(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    inner = ", \"'\", ".join(f"'{part}'" for part in parts)
    return f"concat({inner})"


_SCORE_RE = re.compile(
    r"success rate is\s+([0-9]+(?:\.[0-9]+)?)%\s*"
    r"\(\s*(\d+)\s+out of\s+(\d+)\s+fields\)\s*"
    r"in\s+(\d+)\s+milliseconds",
    re.IGNORECASE,
)


def parse_score_message(message: str) -> dict[str, float | int | str] | None:
    """Interpreta a frase final publicada pelo site, sem inventar a nota."""
    if not message:
        return None
    match = _SCORE_RE.search(" ".join(message.split()))
    if not match:
        return None
    percent_text, correct, total, elapsed = match.groups()
    return {
        "mensagem_bruta": " ".join(message.split()),
        "percentual": float(percent_text),
        "campos_corretos": int(correct),
        "campos_totais": int(total),
        "tempo_site_ms": int(elapsed),
    }
