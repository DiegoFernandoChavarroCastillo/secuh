"""Guarda la captura JPEG del frame donde se detectó a la persona.

Hay tres piezas y se combinan según la configuración:

- ``FileSnapshotStore``: escribe el frame tal cual llega (comportamiento
  original, y el que usa el modo standalone).
- ``AnnotatedSnapshotStore``: decorador que dibuja las cajas del evento antes
  de delegar. Al ser un decorador del mismo puerto, ni el dominio ni la API se
  enteran de que la imagen viene anotada.
- ``FileRawSnapshotStore``: guarda además el original sin cajas, para poder
  reprocesar el histórico con un modelo mejor en el futuro.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

import cv2

from secuh.core.models import Event
from secuh.core.ports import Frame, RawSnapshotStore, SnapshotStore
from secuh.storage.annotate import annotate_event


def _write_jpeg(path: Path, frame: Frame) -> str:
    if not cv2.imwrite(str(path), frame):
        raise OSError(f"cv2.imwrite falló para {path}")
    return str(path)


def _stem(event: Event) -> str:
    return f"{event.timestamp:%Y%m%d-%H%M%S}-{str(event.id)[:8]}"


class FileSnapshotStore(SnapshotStore):
    def __init__(self, base_dir: Path, camera_name: str) -> None:
        self._dir = base_dir / "snapshots" / camera_name
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, event: Event, frame: Frame) -> str:
        return _write_jpeg(self._dir / f"{_stem(event)}.jpg", frame)


class FileRawSnapshotStore(RawSnapshotStore):
    """El frame original, junto a la anotada y con el mismo nombre base.

    Comparte carpeta y extensión con la anotada a propósito: la retención barre
    ``snapshots/**/*.jpg`` (``storage/retention.py``), así que las dos expiran
    juntas sin tocar nada más.
    """

    def __init__(self, base_dir: Path, camera_name: str) -> None:
        self._dir = base_dir / "snapshots" / camera_name
        self._dir.mkdir(parents=True, exist_ok=True)

    def save_raw(self, event: Event, frame: Frame) -> str:
        return _write_jpeg(self._dir / f"{_stem(event)}.raw.jpg", frame)


class AnnotatedSnapshotStore(SnapshotStore):
    """Dibuja las cajas del evento y delega el guardado.

    Funciona porque para cuando el handler llama a ``save()`` el evento ya
    lleva dentro su ``scene``: la inspección corre antes justamente para esto.
    """

    def __init__(
        self,
        inner: SnapshotStore,
        min_confidence: float = 0.0,
        labels: Collection[str] | None = None,
    ) -> None:
        self._inner = inner
        self._min_confidence = min_confidence
        self._labels = labels

    def save(self, event: Event, frame: Frame) -> str:
        annotated = annotate_event(
            frame, event, min_confidence=self._min_confidence, labels=self._labels
        )
        return self._inner.save(event, annotated)
