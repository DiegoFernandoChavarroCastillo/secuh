"""Tests de utilidades de la fuente de video (sin abrir streams reales)."""

from __future__ import annotations

from secuh.video.source import redact_url


def test_redacta_credenciales_rtsp() -> None:
    url = "rtsp://admin:secreta123@192.168.1.60:554/stream1"

    redacted = redact_url(url)

    assert "secreta123" not in redacted
    assert "admin" not in redacted
    assert "192.168.1.60:554" in redacted


def test_url_sin_credenciales_queda_igual() -> None:
    url = "http://192.168.1.50:8080/video"
    assert redact_url(url) == url


def test_indice_de_webcam_queda_igual() -> None:
    assert redact_url("0") == "0"
