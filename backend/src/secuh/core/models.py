"""Entidades del dominio.

Son estructuras de datos inmutables y sin comportamiento de infraestructura.
La persistencia (SQLAlchemy) y la API (Pydantic schemas) tendrán sus propias
representaciones y mapearán hacia/desde estas entidades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import time as dtime
from enum import StrEnum
from uuid import UUID, uuid4


class SourceType(StrEnum):
    """Tipo de fuente de video de una cámara."""

    RTSP = "rtsp"
    IP_WEBCAM = "ip_webcam"
    USB = "usb"


class CameraState(StrEnum):
    """Estado de vigilancia de una cámara."""

    ARMED = "armed"
    DISARMED = "disarmed"


class ScheduleMode(StrEnum):
    """Cuándo vigila una cámara armada."""

    ALWAYS = "always"
    NIGHT = "night"  # horario nocturno predefinido
    CUSTOM = "custom"


NIGHT_START = dtime(22, 0)
NIGHT_END = dtime(6, 0)


@dataclass(frozen=True, slots=True)
class Schedule:
    """Ventana horaria de vigilancia (hora local del servidor).

    Un rango cuyo inicio es mayor que el fin cruza la medianoche
    (ej. 22:00 → 06:00 vigila de noche).
    """

    mode: ScheduleMode = ScheduleMode.ALWAYS
    start: dtime | None = None
    end: dtime | None = None

    def is_active(self, at: dtime) -> bool:
        if self.mode == ScheduleMode.ALWAYS:
            return True
        if self.mode == ScheduleMode.NIGHT:
            start, end = NIGHT_START, NIGHT_END
        else:
            if self.start is None or self.end is None:
                return True  # personalizado sin rango completo: no bloquear
            start, end = self.start, self.end
        if start <= end:
            return start <= at < end
        return at >= start or at < end  # cruza medianoche


# Polígono en coordenadas normalizadas (0..1) relativas al frame.
Polygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class Camera:
    """Cámara registrada en el sistema."""

    id: UUID
    name: str
    zone: str
    source_type: SourceType
    source_url: str
    state: CameraState = CameraState.DISARMED
    # Umbral de confianza mínimo para aceptar una detección de YOLO (0..1).
    confidence_threshold: float = 0.5
    # Segundos de silencio tras notificar un evento en esta cámara.
    cooldown_seconds: int = 60
    # Ventana horaria de vigilancia (aplica solo si la cámara está armada).
    schedule: Schedule = field(default_factory=Schedule)
    # Zona de detección: fuera de este polígono se ignora todo. None = frame completo.
    mask_polygon: Polygon | None = None

    @staticmethod
    def new(name: str, zone: str, source_type: SourceType, source_url: str) -> Camera:
        return Camera(
            id=uuid4(), name=name, zone=zone, source_type=source_type, source_url=source_url
        )


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Caja delimitadora en píxeles sobre el frame analizado."""

    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True, slots=True)
class Detection:
    """Una persona detectada en un frame."""

    box: BoundingBox
    confidence: float


@dataclass(frozen=True, slots=True)
class Event:
    """Evento de detección de persona confirmado (tras cooldown y filtros)."""

    id: UUID
    camera_id: UUID
    timestamp: datetime
    detections: tuple[Detection, ...]
    snapshot_path: str | None = None
    clip_path: str | None = None
    notified: bool = False

    @staticmethod
    def new(camera_id: UUID, detections: tuple[Detection, ...]) -> Event:
        return Event(
            id=uuid4(),
            camera_id=camera_id,
            timestamp=datetime.now(UTC),
            detections=detections,
        )

    @property
    def max_confidence(self) -> float:
        return max((d.confidence for d in self.detections), default=0.0)


@dataclass(frozen=True, slots=True)
class Notification:
    """Mensaje listo para ser enviado por un canal de notificación."""

    title: str
    message: str
    priority: str = "default"
    image_path: str | None = None
    extra: dict[str, str] = field(default_factory=dict)
