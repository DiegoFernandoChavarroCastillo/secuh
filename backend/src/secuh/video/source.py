"""Fuente de video sobre OpenCV: webcam USB, RTSP o MJPEG (IP Webcam).

Responsable de la reconexión: si el stream se cae, reintenta con backoff
exponencial y solo loggea (nunca lanza) — la cámara puede volver.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from typing import cast
from urllib.parse import urlparse, urlunparse

import cv2

from secuh.core.ports import Frame, VideoSource

logger = logging.getLogger(__name__)


def redact_url(source: str) -> str:
    """Oculta credenciales embebidas (rtsp://user:pass@host) para logs."""
    try:
        parsed = urlparse(source)
    except ValueError:
        return "<url inválida>"
    if parsed.username is None and parsed.password is None:
        return source
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=f"***:***@{host}"))


class OpenCvVideoSource(VideoSource):
    def __init__(
        self,
        source: str,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 60.0,
    ) -> None:
        self._source = source
        self._reconnect_initial = reconnect_initial_seconds
        self._reconnect_max = reconnect_max_seconds
        self._capture: cv2.VideoCapture | None = None
        self._closed = threading.Event()

    @property
    def display_name(self) -> str:
        return redact_url(self._source)

    def _open(self) -> cv2.VideoCapture:
        raw: int | str = int(self._source) if self._source.isdigit() else self._source
        return cv2.VideoCapture(raw)

    def frames(self) -> Iterator[Frame]:
        backoff = self._reconnect_initial
        while not self._closed.is_set():
            self._capture = self._open()
            if not self._capture.isOpened():
                logger.warning(
                    "No se pudo abrir la fuente; reintentando en %.0fs",
                    backoff,
                    extra={"source": self.display_name},
                )
                self._capture.release()
                if self._closed.wait(backoff):
                    break
                backoff = min(backoff * 2, self._reconnect_max)
                continue

            logger.info("Fuente de video conectada", extra={"source": self.display_name})
            backoff = self._reconnect_initial
            misses = 0
            while not self._closed.is_set():
                ok, frame = self._capture.read()
                if not ok:
                    misses += 1
                    if misses >= 5:
                        logger.warning(
                            "Stream perdido; reconectando",
                            extra={"source": self.display_name},
                        )
                        break
                    time.sleep(0.2)
                    continue
                misses = 0
                yield cast(Frame, frame)
            self._capture.release()

    def close(self) -> None:
        self._closed.set()
