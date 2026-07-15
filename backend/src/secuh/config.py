"""Configuración de la aplicación: YAML validado con Pydantic.

Los secretos NUNCA van en el YAML: el topic de ntfy puede darse por la
variable de entorno ``SECUH_NTFY_TOPIC`` (tiene prioridad sobre el archivo).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ENV_NTFY_TOPIC = "SECUH_NTFY_TOPIC"


class CameraConfig(BaseModel):
    name: str
    zone: str = ""
    # URL http/rtsp, o índice de webcam USB como string (ej. "0")
    source: str
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    cooldown_seconds: int = Field(default=60, ge=0)
    analysis_fps: float = Field(default=5.0, gt=0.0)


class DetectionConfig(BaseModel):
    model: str = "yolov8n.pt"
    imgsz: int = Field(default=640, ge=160)
    motion_history: int = Field(default=500, ge=1)
    motion_var_threshold: float = Field(default=16.0, gt=0.0)
    motion_min_area_ratio: float = Field(default=0.01, gt=0.0, le=1.0)


class NtfyConfig(BaseModel):
    topic_url: str
    timeout_seconds: float = Field(default=10.0, gt=0.0)
    retries: int = Field(default=3, ge=1)


class NotificationsConfig(BaseModel):
    # Notificador de consola (log): útil en desarrollo, sin servicio externo.
    console: bool = True
    ntfy: NtfyConfig | None = None


class StorageConfig(BaseModel):
    data_dir: Path = Path("data")
    retention_days: int = Field(default=7, ge=1)
    clip_pre_seconds: float = Field(default=10.0, ge=0.0)
    clip_post_seconds: float = Field(default=10.0, ge=0.0)


class AppConfig(BaseModel):
    camera: CameraConfig
    detection: DetectionConfig = DetectionConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    storage: StorageConfig = StorageConfig()


def load_config(path: Path) -> AppConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    env_topic = os.environ.get(ENV_NTFY_TOPIC)
    if env_topic:
        raw.setdefault("notifications", {})
        ntfy = raw["notifications"].setdefault("ntfy", {})
        ntfy["topic_url"] = env_topic

    return AppConfig.model_validate(raw)
