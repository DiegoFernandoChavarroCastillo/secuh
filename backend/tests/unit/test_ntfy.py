"""Tests del notificador ntfy con requests simulado (sin red)."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from secuh.core.models import Notification
from secuh.core.ports import NotificationError
from secuh.notifications import ntfy as ntfy_module
from secuh.notifications.ntfy import NtfyNotifier


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def test_texto_va_por_post_con_params(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(ntfy_module.requests, "post", fake_post)
    notifier = NtfyNotifier("https://ntfy.sh/test")

    notifier.send(Notification(title="t", message="hay alguien", priority="high"))

    [call] = calls
    assert call["url"] == "https://ntfy.sh/test"
    assert call["params"]["message"] == "hay alguien"
    assert call["params"]["priority"] == "high"


def test_con_imagen_va_por_put_adjunto(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    image = tmp_path / "captura.jpg"
    image.write_bytes(b"jpeg")
    calls: list[dict[str, Any]] = []

    def fake_put(url: str, **kwargs: Any) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(ntfy_module.requests, "put", fake_put)
    notifier = NtfyNotifier("https://ntfy.sh/test")

    notifier.send(Notification(title="t", message="m", image_path=str(image)))

    [call] = calls
    assert call["params"]["filename"] == "captura.jpg"


def test_reintenta_y_lanza_notification_error(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def failing_post(url: str, **kwargs: Any) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(ntfy_module.requests, "post", failing_post)
    monkeypatch.setattr(ntfy_module.time, "sleep", lambda _: None)
    notifier = NtfyNotifier("https://ntfy.sh/test", retries=3)

    with pytest.raises(NotificationError):
        notifier.send(Notification(title="t", message="m"))
    assert attempts == 3


def test_status_http_de_error_cuenta_como_fallo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ntfy_module.requests, "post", lambda url, **kw: FakeResponse(500))
    monkeypatch.setattr(ntfy_module.time, "sleep", lambda _: None)
    notifier = NtfyNotifier("https://ntfy.sh/test", retries=2)

    with pytest.raises(NotificationError):
        notifier.send(Notification(title="t", message="m"))
