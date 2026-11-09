"""Relógio com fuso explícito. O desafio pede America/Sao_Paulo."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/Sao_Paulo"


def now(tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def now_iso(tz_name: str = DEFAULT_TIMEZONE) -> str:
    return now(tz_name).isoformat(timespec="milliseconds")
