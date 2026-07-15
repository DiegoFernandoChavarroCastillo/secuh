"""Tests de carga y validación de configuración."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from secuh.config import ENV_NTFY_TOPIC, load_config

MINIMAL = """
camera:
  name: entrada
  source: "0"
"""


def write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_config_minima_aplica_defaults(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, MINIMAL))

    assert config.camera.name == "entrada"
    assert config.camera.confidence_threshold == 0.5
    assert config.detection.model == "yolov8n.pt"
    assert config.storage.retention_days == 7
    assert config.notifications.console
    assert config.notifications.ntfy is None


def test_umbral_fuera_de_rango_falla(tmp_path: Path) -> None:
    invalid = MINIMAL + "  confidence_threshold: 1.5\n"
    with pytest.raises(ValidationError):
        load_config(write(tmp_path, invalid))


def test_topic_de_ntfy_por_variable_de_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_NTFY_TOPIC, "https://ntfy.sh/secreto")

    config = load_config(write(tmp_path, MINIMAL))

    assert config.notifications.ntfy is not None
    assert config.notifications.ntfy.topic_url == "https://ntfy.sh/secreto"


def test_variable_de_entorno_tiene_prioridad_sobre_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_NTFY_TOPIC, "https://ntfy.sh/del-entorno")
    yaml_with_ntfy = (
        MINIMAL + "\nnotifications:\n  ntfy:\n    topic_url: https://ntfy.sh/del-yaml\n"
    )

    config = load_config(write(tmp_path, yaml_with_ntfy))

    assert config.notifications.ntfy is not None
    assert config.notifications.ntfy.topic_url == "https://ntfy.sh/del-entorno"
