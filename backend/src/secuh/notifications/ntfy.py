"""Notificador sobre ntfy (https://ntfy.sh o servidor propio).

Título, mensaje y prioridad van como query params (URL-encoded, soporta UTF-8
sin problemas de headers); la captura va como cuerpo binario de un PUT, que
ntfy interpreta como adjunto.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from secuh.core.models import Notification
from secuh.core.ports import NotificationError, Notifier

logger = logging.getLogger(__name__)


class NtfyNotifier(Notifier):
    def __init__(self, topic_url: str, timeout_seconds: float = 10.0, retries: int = 3) -> None:
        self._topic_url = topic_url
        self._timeout = timeout_seconds
        self._retries = retries

    def send(self, notification: Notification) -> None:
        params = {
            "title": notification.title,
            "message": notification.message,
            "priority": notification.priority,
        }
        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                self._send_once(notification, params)
                return
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Fallo enviando a ntfy (intento %d/%d): %s", attempt, self._retries, exc
                )
                if attempt < self._retries:
                    time.sleep(attempt)  # backoff lineal: 1s, 2s...
        raise NotificationError(f"ntfy no respondió tras {self._retries} intentos") from last_error

    def _send_once(self, notification: Notification, params: dict[str, str]) -> None:
        if notification.image_path and Path(notification.image_path).is_file():
            with open(notification.image_path, "rb") as image:
                response = requests.put(
                    self._topic_url,
                    params={**params, "filename": Path(notification.image_path).name},
                    data=image,
                    timeout=self._timeout,
                )
        else:
            response = requests.post(self._topic_url, params=params, timeout=self._timeout)
        response.raise_for_status()
