"""Bucle de procesamiento de una cámara.

Lee frames a la tasa nativa (necesario para el buffer del clip), pero solo
analiza a ``analysis_fps``: los frames intermedios se descartan sin costo.
"""

from __future__ import annotations

import logging
import threading
import time

from secuh.core.handler import EventHandler
from secuh.core.models import Camera
from secuh.core.pipeline import DetectionPipeline
from secuh.core.ports import ClipRecorder, Frame, VideoSource

logger = logging.getLogger(__name__)


class CameraWorker:
    def __init__(
        self,
        camera: Camera,
        source: VideoSource,
        pipeline: DetectionPipeline,
        handler: EventHandler,
        clip_recorder: ClipRecorder,
        analysis_fps: float = 5.0,
    ) -> None:
        self._camera = camera
        self._source = source
        self._pipeline = pipeline
        self._handler = handler
        self._clips = clip_recorder
        self._analysis_interval = 1.0 / analysis_fps
        self._stop = threading.Event()
        self._last_frame_at: float | None = None
        self._last_frame: Frame | None = None
        self._started_at: float | None = None
        self._frames_read = 0
        self._frames_analyzed = 0
        self._events_count = 0

    @property
    def last_frame_at(self) -> float | None:
        """``time.monotonic()`` del último frame recibido (None si aún no hay)."""
        return self._last_frame_at

    @property
    def last_frame(self) -> Frame | None:
        """Último frame recibido (para el preview del panel)."""
        return self._last_frame

    @property
    def metrics(self) -> dict[str, float | int]:
        """Contadores de operación (para el panel y el diagnóstico)."""
        uptime = time.monotonic() - self._started_at if self._started_at is not None else 0.0
        return {
            "uptime_seconds": round(uptime, 1),
            "frames_read": self._frames_read,
            "frames_analyzed": self._frames_analyzed,
            "events": self._events_count,
            "achieved_analysis_fps": (
                round(self._frames_analyzed / uptime, 2) if uptime > 0 else 0.0
            ),
        }

    def run(self) -> None:
        """Bloqueante: procesa hasta ``stop()``, fin de la fuente, o error fatal.

        Un error inesperado (p. ej. sin memoria en OpenCV) se loggea y termina
        el worker limpiamente; el supervisor detecta el hilo muerto y lo
        reinicia en su siguiente pasada.
        """
        try:
            self._run()
        except Exception:
            logger.exception(
                "Worker de cámara terminó por un error inesperado",
                extra={"camera": self._camera.name},
            )
            self._source.close()

    def _run(self) -> None:
        logger.info(
            "Iniciando vigilancia",
            extra={"camera": self._camera.name, "zone": self._camera.zone},
        )
        last_analysis = 0.0
        self._started_at = time.monotonic()
        for frame in self._source.frames():
            if self._stop.is_set():
                break
            self._clips.push_frame(frame)

            now = time.monotonic()
            self._last_frame_at = now
            self._last_frame = frame
            self._frames_read += 1
            if (now - last_analysis) < self._analysis_interval:
                continue
            last_analysis = now
            self._frames_analyzed += 1

            result = self._pipeline.process_frame(frame)
            if result.event is not None:
                self._events_count += 1
                logger.info(
                    "Persona detectada",
                    extra={
                        "camera": self._camera.name,
                        "event_id": str(result.event.id),
                        "confidence": round(result.event.max_confidence, 2),
                    },
                )
                self._handler.handle(result.event, frame)
        self._source.close()
        logger.info("Vigilancia detenida", extra={"camera": self._camera.name})

    def stop(self) -> None:
        self._stop.set()
        self._source.close()
