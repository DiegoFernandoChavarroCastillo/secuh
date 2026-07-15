"""Notificador de consola: imprime en el log. Útil para desarrollo y pruebas
locales sin depender de un servicio externo."""

from __future__ import annotations

import logging

from secuh.core.models import Notification
from secuh.core.ports import Notifier

logger = logging.getLogger(__name__)


class ConsoleNotifier(Notifier):
    def send(self, notification: Notification) -> None:
        logger.info(
            "NOTIFICACIÓN [%s] %s | %s (imagen: %s)",
            notification.priority,
            notification.title,
            notification.message,
            notification.image_path or "-",
        )
