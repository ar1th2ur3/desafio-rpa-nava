"""Log de etapas em JSON Lines, com carimbo America/Sao_Paulo."""

from __future__ import annotations

import json
from pathlib import Path

from rpa_challenge.clock import now_iso


class StepLog:
    def __init__(self, path: Path, tz_name: str) -> None:
        self.path = Path(path)
        self.tz_name = tz_name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")

    def event(self, etapa: str, nivel: str = "info", **details: object) -> dict[str, object]:
        record: dict[str, object] = {
            "timestamp": now_iso(self.tz_name),
            "nivel": nivel,
            "etapa": etapa,
        }
        record.update(details)
        self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._handle.flush()
        print(f"[{record['timestamp']}] {nivel.upper():5} {etapa}")
        return record

    def close(self) -> None:
        self._handle.close()
