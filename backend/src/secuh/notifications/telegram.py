"""Notificador sobre la Bot API de Telegram.

Requiere un bot (crear con @BotFather) y el chat_id del chat/grupo destino.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import requests

from secuh.core.models import Notification
from secuh.core.ports import NotificationError, Notifier

logger = logging.getLogger(__name__)


class TelegramNotifier(Notifier):
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = 10.0,
        retries: int = 3,
    ) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = chat_id
        self._timeout = timeout_seconds
        self._retries = retries

    def send(self, notification: Notification) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                self._send_once(notification)
                return
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Fallo enviando a Telegram (intento %d/%d): %s",
                    attempt,
                    self._retries,
                    exc,
                )
                if attempt < self._retries:
                    time.sleep(attempt)
        raise NotificationError(
            f"Telegram no respondió tras {self._retries} intentos"
        ) from last_error

    def _send_once(self, notification: Notification) -> None:
        text = f"{notification.title}\n{notification.message}"
        if notification.image_path and Path(notification.image_path).is_file():
            with open(notification.image_path, "rb") as image:
                response = requests.post(
                    f"{self._base_url}/sendPhoto",
                    data={"chat_id": self._chat_id, "caption": text},
                    files={"photo": image},
                    timeout=self._timeout,
                )
        else:
            response = requests.post(
                f"{self._base_url}/sendMessage",
                data={"chat_id": self._chat_id, "text": text},
                timeout=self._timeout,
            )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        if not body.get("ok", False):
            raise NotificationError(f"Telegram rechazó el mensaje: {body.get('description')}")
