"""Esquemas de entrada/salida de la API (contrato con el panel web)."""

from __future__ import annotations

from datetime import datetime
from datetime import time as dtime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from secuh.core.models import CameraState, ScheduleMode, SourceType

# Polígono como lista de [x, y] normalizados.
PolygonIn = list[tuple[float, float]]


def _validate_polygon(polygon: PolygonIn | None) -> PolygonIn | None:
    if polygon is None:
        return None
    if len(polygon) < 3:
        raise ValueError("La zona necesita al menos 3 puntos")
    for x, y in polygon:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("Los puntos de la zona deben estar normalizados (0..1)")
    return polygon


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    username: str


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    zone: str = Field(default="", max_length=128)
    source_type: SourceType
    source_url: str = Field(min_length=1, max_length=512)
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    cooldown_seconds: int = Field(default=60, ge=0)
    analysis_fps: float = Field(default=5.0, gt=0.0, le=30.0)
    schedule_mode: ScheduleMode = ScheduleMode.ALWAYS
    schedule_start: dtime | None = None
    schedule_end: dtime | None = None
    mask_polygon: PolygonIn | None = None
    channel_ids: list[UUID] = Field(default_factory=list)

    _check_polygon = field_validator("mask_polygon")(_validate_polygon)


class CameraPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    zone: str | None = Field(default=None, max_length=128)
    source_type: SourceType | None = None
    source_url: str | None = Field(default=None, min_length=1, max_length=512)
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    cooldown_seconds: int | None = Field(default=None, ge=0)
    analysis_fps: float | None = Field(default=None, gt=0.0, le=30.0)
    schedule_mode: ScheduleMode | None = None
    schedule_start: dtime | None = None
    schedule_end: dtime | None = None
    mask_polygon: PolygonIn | None = None
    channel_ids: list[UUID] | None = None

    _check_polygon = field_validator("mask_polygon")(_validate_polygon)


class CameraOut(BaseModel):
    id: UUID
    name: str
    zone: str
    source_type: SourceType
    # La URL puede llevar credenciales (rtsp://user:pass@...): se devuelve
    # redactada; el valor real solo se escribe, nunca se lee desde el panel.
    source_url_redacted: str
    state: CameraState
    confidence_threshold: float
    cooldown_seconds: int
    analysis_fps: float
    schedule_mode: ScheduleMode
    schedule_start: dtime | None
    schedule_end: dtime | None
    mask_polygon: PolygonIn | None
    channel_ids: list[UUID]
    online: bool
    # Contadores del worker (None si la cámara no está corriendo).
    metrics: dict[str, float | int] | None = None


class EventOut(BaseModel):
    id: UUID
    camera_id: UUID
    camera_name: str
    timestamp: datetime
    confidence: float
    person_count: int
    notified: bool
    has_snapshot: bool
    has_clip: bool


class EventPage(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int


class HealthOut(BaseModel):
    status: str
    cameras_running: int


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str = Field(pattern="^(ntfy|telegram)$")
    # Config específica del tipo (ntfy: topic_url; telegram: bot_token, chat_id).
    config: dict[str, str]
    active: bool = True


class ChannelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    config: dict[str, str] | None = None
    active: bool | None = None


class ChannelOut(BaseModel):
    id: UUID
    name: str
    type: str
    active: bool
    # La config siempre sale redactada: los secretos no abandonan el servidor.
    config_redacted: dict[str, str]


class ChannelTestResult(BaseModel):
    ok: bool
    detail: str | None = None
