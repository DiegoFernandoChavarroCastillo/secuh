"""Tests de canales de notificación: fábrica, Telegram y API."""

from __future__ import annotations

from typing import Any

import pytest
import requests
from fastapi.testclient import TestClient

from secuh.core.models import Notification
from secuh.core.ports import NotificationError
from secuh.notifications import telegram as telegram_module
from secuh.notifications.factory import ChannelConfigError, build_notifier, redact_config
from secuh.notifications.ntfy import NtfyNotifier
from secuh.notifications.telegram import TelegramNotifier


class TestFactory:
    def test_construye_ntfy(self) -> None:
        notifier = build_notifier("ntfy", {"topic_url": "https://ntfy.sh/x"})
        assert isinstance(notifier, NtfyNotifier)

    def test_construye_telegram(self) -> None:
        notifier = build_notifier("telegram", {"bot_token": "123:abc", "chat_id": "42"})
        assert isinstance(notifier, TelegramNotifier)

    def test_config_incompleta_falla(self) -> None:
        with pytest.raises(ChannelConfigError):
            build_notifier("telegram", {"bot_token": "123:abc"})

    def test_tipo_desconocido_falla(self) -> None:
        with pytest.raises(ChannelConfigError):
            build_notifier("palomas", {})

    def test_redaccion_no_expone_secretos(self) -> None:
        redacted = redact_config("telegram", {"bot_token": "123456:AAAA-secreto", "chat_id": "42"})
        assert "secreto" not in redacted["bot_token"]
        assert redacted["chat_id"] == "42"

        redacted_ntfy = redact_config("ntfy", {"topic_url": "https://ntfy.sh/topic-privado"})
        assert "topic-privado" not in redacted_ntfy["topic_url"]


class FakeResponse:
    def __init__(self, status_code: int = 200, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body if body is not None else {"ok": True}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._body


class TestTelegramNotifier:
    def test_texto_usa_send_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            calls.append({"url": url, **kwargs})
            return FakeResponse()

        monkeypatch.setattr(telegram_module.requests, "post", fake_post)
        notifier = TelegramNotifier(bot_token="123:abc", chat_id="42")

        notifier.send(Notification(title="secuh", message="hay alguien"))

        [call] = calls
        assert call["url"].endswith("/sendMessage")
        assert call["data"]["chat_id"] == "42"
        assert "hay alguien" in call["data"]["text"]

    def test_con_imagen_usa_send_photo(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        image = tmp_path / "captura.jpg"
        image.write_bytes(b"jpeg")
        calls: list[dict[str, Any]] = []

        def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            calls.append({"url": url, **kwargs})
            return FakeResponse()

        monkeypatch.setattr(telegram_module.requests, "post", fake_post)
        notifier = TelegramNotifier(bot_token="123:abc", chat_id="42")

        notifier.send(Notification(title="secuh", message="m", image_path=str(image)))

        [call] = calls
        assert call["url"].endswith("/sendPhoto")
        assert "photo" in call["files"]

    def test_respuesta_no_ok_lanza_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            telegram_module.requests,
            "post",
            lambda url, **kw: FakeResponse(body={"ok": False, "description": "chat not found"}),
        )
        notifier = TelegramNotifier(bot_token="123:abc", chat_id="42", retries=1)

        with pytest.raises(NotificationError):
            notifier.send(Notification(title="t", message="m"))


CHANNEL = {"name": "ntfy-negocio", "type": "ntfy", "config": {"topic_url": "https://ntfy.sh/x"}}


class TestChannelsApi:
    def test_requiere_autenticacion(self, client: TestClient) -> None:
        assert client.get("/api/channels").status_code == 401

    def test_crear_y_listar_con_config_redactada(self, logged_client: TestClient) -> None:
        created = logged_client.post("/api/channels", json=CHANNEL)
        assert created.status_code == 201

        [channel] = logged_client.get("/api/channels").json()
        assert channel["name"] == "ntfy-negocio"
        assert "config" not in channel
        assert "https://ntfy.sh/x" not in str(channel["config_redacted"])

    def test_config_invalida_da_422(self, logged_client: TestClient) -> None:
        bad = {"name": "roto", "type": "telegram", "config": {"bot_token": "solo-token"}}
        assert logged_client.post("/api/channels", json=bad).status_code == 422

    def test_boton_de_prueba_reporta_fallo_sin_romper(
        self, logged_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        channel_id = logged_client.post("/api/channels", json=CHANNEL).json()["id"]

        def failing_send(self: Any, notification: Any) -> None:
            raise NotificationError("canal caído")

        monkeypatch.setattr(NtfyNotifier, "send", failing_send)
        result = logged_client.post(f"/api/channels/{channel_id}/test").json()

        assert result["ok"] is False
        assert "caído" in result["detail"]

    def test_boton_de_prueba_exitoso(
        self, logged_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        channel_id = logged_client.post("/api/channels", json=CHANNEL).json()["id"]
        monkeypatch.setattr(NtfyNotifier, "send", lambda self, n: None)

        assert logged_client.post(f"/api/channels/{channel_id}/test").json()["ok"] is True

    def test_asignar_canal_a_camara(self, logged_client: TestClient) -> None:
        channel_id = logged_client.post("/api/channels", json=CHANNEL).json()["id"]
        camera = logged_client.post(
            "/api/cameras",
            json={
                "name": "entrada",
                "source_type": "usb",
                "source_url": "0",
                "channel_ids": [channel_id],
            },
        ).json()

        assert camera["channel_ids"] == [channel_id]

        removed = logged_client.patch(
            f"/api/cameras/{camera['id']}", json={"channel_ids": []}
        ).json()
        assert removed["channel_ids"] == []

    def test_canal_inexistente_en_camara_da_422(self, logged_client: TestClient) -> None:
        response = logged_client.post(
            "/api/cameras",
            json={
                "name": "entrada",
                "source_type": "usb",
                "source_url": "0",
                "channel_ids": ["00000000-0000-0000-0000-000000000001"],
            },
        )
        assert response.status_code == 422
