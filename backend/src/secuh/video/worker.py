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
from secuh.core.ports import ClipRecorder, VideoSource

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

    def run(self) -> None:
        """Bloqueante: procesa hasta que se llame a ``stop()`` o se agote la fuente."""
        logger.info(
            "Iniciando vigilancia",
            extra={"camera": self._camera.name, "zone": self._camera.zone},
        )
        last_analysis = 0.0
        for frame in self._source.frames():
            if self._stop.is_set():
                break
            self._clips.push_frame(frame)

            now = time.monotonic()
            if (now - last_analysis) < self._analysis_interval:
                continue
            last_analysis = now

            result = self._pipeline.process_frame(frame)
            if result.event is not None:
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
