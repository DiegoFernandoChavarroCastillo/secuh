"""Registro de eventos en JSONL (Fase 1). En Fase 2 lo reemplaza PostgreSQL."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from secuh.core.models import Event
from secuh.core.ports import EventStore


class JsonlEventStore(EventStore):
    def __init__(self, base_dir: Path) -> None:
        base_dir.mkdir(parents=True, exist_ok=True)
        self._path = base_dir / "events.jsonl"

    def save(self, event: Event) -> None:
        record = asdict(event)
        record["id"] = str(event.id)
        record["camera_id"] = str(event.camera_id)
        record["timestamp"] = event.timestamp.isoformat()
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
