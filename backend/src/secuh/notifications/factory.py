"""Fábrica de notificadores a partir de la configuración de un canal (BD).

Añadir un tipo de canal nuevo = implementar el ``Notifier`` + registrar aquí
su constructor y su redacción de secretos. Nada más cambia.
"""

from __future__ import annotations

from typing import Any

from secuh.core.ports import Notifier
from secuh.notifications.ntfy import NtfyNotifier
from secuh.notifications.telegram import TelegramNotifier

CHANNEL_TYPES = ("ntfy", "telegram")


class ChannelConfigError(ValueError):
    """Configuración de canal inválida o incompleta."""


def build_notifier(channel_type: str, config: dict[str, Any]) -> Notifier:
    if channel_type == "ntfy":
        topic_url = config.get("topic_url")
        if not topic_url:
            raise ChannelConfigError("ntfy requiere 'topic_url'")
        return NtfyNotifier(topic_url=str(topic_url))
    if channel_type == "telegram":
        bot_token, chat_id = config.get("bot_token"), config.get("chat_id")
        if not bot_token or not chat_id:
            raise ChannelConfigError("telegram requiere 'bot_token' y 'chat_id'")
        return TelegramNotifier(bot_token=str(bot_token), chat_id=str(chat_id))
    raise ChannelConfigError(f"Tipo de canal desconocido: {channel_type!r}")


def redact_config(channel_type: str, config: dict[str, Any]) -> dict[str, str]:
    """Versión mostrable de la configuración: los secretos nunca salen de la API."""
    if channel_type == "ntfy":
        topic_url = str(config.get("topic_url", ""))
        base, _, topic = topic_url.rpartition("/")
        visible = topic[:3] + "…" if len(topic) > 3 else "…"
        return {"topic_url": f"{base}/{visible}" if base else visible}
    if channel_type == "telegram":
        token = str(config.get("bot_token", ""))
        return {
            "bot_token": f"•••{token[-4:]}" if len(token) >= 4 else "•••",
            "chat_id": str(config.get("chat_id", "")),
        }
    return dict.fromkeys(config, "•••")
