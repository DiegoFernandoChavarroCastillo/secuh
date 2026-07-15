"""Guarda la captura JPEG del frame donde se detectó a la persona."""

from __future__ import annotations

from pathlib import Path

import cv2

from secuh.core.models import Event
from secuh.core.ports import Frame, SnapshotStore


class FileSnapshotStore(SnapshotStore):
    def __init__(self, base_dir: Path, camera_name: str) -> None:
        self._dir = base_dir / "snapshots" / camera_name
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, event: Event, frame: Frame) -> str:
        path = self._dir / f"{event.timestamp:%Y%m%d-%H%M%S}-{str(event.id)[:8]}.jpg"
        if not cv2.imwrite(str(path), frame):
            raise OSError(f"cv2.imwrite falló para {path}")
        return str(path)
