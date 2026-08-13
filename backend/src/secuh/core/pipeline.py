"""Orquestación del pipeline de detección.

Flujo por frame: horario activo -> movimiento -> detección de personas ->
umbral de confianza -> zona -> cooldown -> evento. Lo que se hace *con* el
evento (captura, notificación, clip, persistencia) vive en ``handler.py``:
aquí solo hay lógica pura, testeable sin hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import time as dtime
from typing import Protocol

from secuh.core.geometry import point_in_polygon
from secuh.core.models import Camera, Detection, Event
from secuh.core.ports import Clock, Frame, MotionDetector, PersonDetector


class LocalTimeProvider(Protocol):
    """Hora local del servidor, inyectable para testear horarios."""

    def __call__(self) -> dtime: ...


def local_time_now() -> dtime:
    return datetime.now().time()


class CooldownGate:
    """Silencia eventos repetidos de una misma cámara durante un periodo.

    Evita el spam de notificaciones cuando una persona permanece en cuadro:
    tras dejar pasar un evento, los siguientes de la misma cámara se
    descartan hasta que transcurra ``cooldown_seconds``.
    """

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._last_event_at: dict[object, float] = {}

    def allow(self, key: object, cooldown_seconds: float) -> bool:
        now = self._clock.now()
        last = self._last_event_at.get(key)
        if last is not None and (now - last) < cooldown_seconds:
            return False
        self._last_event_at[key] = now
        return True


@dataclass(frozen=True, slots=True)
class FrameResult:
    """Resultado de procesar un frame: qué pasó y, si aplica, el evento."""

    motion: bool
    detections: tuple[Detection, ...] = ()
    event: Event | None = None
    # False cuando el horario de la cámara no está activo (no se analizó).
    in_schedule: bool = True


class DetectionPipeline:
    """Decide, frame a frame, si hay un evento de persona que reportar."""

    def __init__(
        self,
        camera: Camera,
        motion_detector: MotionDetector,
        person_detector: PersonDetector,
        cooldown: CooldownGate,
        local_time: LocalTimeProvider = local_time_now,
    ) -> None:
        self._camera = camera
        self._motion = motion_detector
        self._detector = person_detector
        self._cooldown = cooldown
        self._local_time = local_time

    def process_frame(self, frame: Frame) -> FrameResult:
        if not self._camera.schedule.is_active(self._local_time()):
            return FrameResult(motion=False, in_schedule=False)

        if not self._motion.has_motion(frame):
            return FrameResult(motion=False)

        detections = tuple(
            d
            for d in self._detector.detect(frame)
            if d.confidence >= self._camera.confidence_threshold and self._inside_zone(d, frame)
        )
        if not detections:
            return FrameResult(motion=True)

        if not self._cooldown.allow(self._camera.id, self._camera.cooldown_seconds):
            return FrameResult(motion=True, detections=detections)

        event = Event.new(camera_id=self._camera.id, detections=detections)
        return FrameResult(motion=True, detections=detections, event=event)

    def _inside_zone(self, detection: Detection, frame: Frame) -> bool:
        """La persona cuenta si el centro de su caja cae dentro de la zona."""
        polygon = self._camera.mask_polygon
        if polygon is None:
            return True
        height, width = int(frame.shape[0]), int(frame.shape[1])
        center_x = (detection.box.x1 + detection.box.x2) / 2 / width
        center_y = (detection.box.y1 + detection.box.y2) / 2 / height
        return point_in_polygon(center_x, center_y, polygon)
