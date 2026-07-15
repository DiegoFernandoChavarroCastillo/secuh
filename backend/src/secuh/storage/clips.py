"""Grabación de clips de evento con buffer circular en memoria.

``push_frame`` se llama con cada frame capturado y mantiene los últimos
``pre_seconds``. Al llegar un evento, ``record_event`` vuelca ese buffer a un
archivo y deja la grabación "activa": los siguientes ``push_frame`` se siguen
escribiendo hasta completar ``post_seconds``. Todo ocurre en el hilo del
worker de la cámara — no hay concurrencia interna.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path

import cv2

from secuh.core.models import Event
from secuh.core.ports import ClipRecorder, Frame

logger = logging.getLogger(__name__)

FALLBACK_FPS = 10.0


class FileClipRecorder(ClipRecorder):
    def __init__(
        self,
        base_dir: Path,
        camera_name: str,
        pre_seconds: float = 10.0,
        post_seconds: float = 10.0,
    ) -> None:
        self._dir = base_dir / "clips" / camera_name
        self._dir.mkdir(parents=True, exist_ok=True)
        self._pre_seconds = pre_seconds
        self._post_seconds = post_seconds
        self._buffer: deque[tuple[float, Frame]] = deque()
        self._writer: cv2.VideoWriter | None = None
        self._recording_until = 0.0
        self._active_path: Path | None = None

    def push_frame(self, frame: Frame) -> None:
        now = time.monotonic()
        self._buffer.append((now, frame))
        while self._buffer and self._buffer[0][0] < (now - self._pre_seconds):
            self._buffer.popleft()

        if self._writer is not None:
            self._writer.write(frame)
            if now >= self._recording_until:
                self._finish()

    def record_event(self, event: Event) -> str:
        if self._writer is not None:
            # Evento durante una grabación activa (p. ej. otra persona):
            # se extiende la grabación en curso en lugar de abrir otro archivo.
            self._recording_until = time.monotonic() + self._post_seconds
            assert self._active_path is not None
            return str(self._active_path)

        path = self._dir / f"{event.timestamp:%Y%m%d-%H%M%S}-{str(event.id)[:8]}.mp4"
        fps = self._estimate_fps()
        height, width = self._buffer[-1][1].shape[:2] if self._buffer else (480, 640)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise OSError(f"No se pudo abrir el VideoWriter para {path}")
        for _, frame in self._buffer:
            writer.write(frame)
        self._writer = writer
        self._active_path = path
        self._recording_until = time.monotonic() + self._post_seconds
        return str(path)

    def _estimate_fps(self) -> float:
        if len(self._buffer) < 2:
            return FALLBACK_FPS
        span = self._buffer[-1][0] - self._buffer[0][0]
        if span <= 0:
            return FALLBACK_FPS
        return max(1.0, (len(self._buffer) - 1) / span)

    def _finish(self) -> None:
        assert self._writer is not None
        self._writer.release()
        logger.info("Clip de evento guardado", extra={"clip": str(self._active_path)})
        self._writer = None
        self._active_path = None

    def close(self) -> None:
        """Cierra una grabación en curso (al apagar el worker)."""
        if self._writer is not None:
            self._finish()
