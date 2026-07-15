"""Orquestación del pipeline de detección.

Flujo por frame: movimiento -> detección de personas -> umbral de confianza
-> cooldown -> evento. La implementación completa (grabación de clips,
notificación, persistencia) se integra en la Fase 1; aquí vive la lógica
pura que ya es testeable sin hardware.
"""

from __future__ import annotations

from dataclasses import dataclass

from secuh.core.models import Camera, Detection, Event
from secuh.core.ports import Clock, Frame, MotionDetector, PersonDetector


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


class DetectionPipeline:
    """Decide, frame a frame, si hay un evento de persona que reportar."""

    def __init__(
        self,
        camera: Camera,
        motion_detector: MotionDetector,
        person_detector: PersonDetector,
        cooldown: CooldownGate,
    ) -> None:
        self._camera = camera
        self._motion = motion_detector
        self._detector = person_detector
        self._cooldown = cooldown

    def process_frame(self, frame: Frame) -> FrameResult:
        if not self._motion.has_motion(frame):
            return FrameResult(motion=False)

        detections = tuple(
            d
            for d in self._detector.detect(frame)
            if d.confidence >= self._camera.confidence_threshold
        )
        if not detections:
            return FrameResult(motion=True)

        if not self._cooldown.allow(self._camera.id, self._camera.cooldown_seconds):
            return FrameResult(motion=True, detections=detections)

        event = Event.new(camera_id=self._camera.id, detections=detections)
        return FrameResult(motion=True, detections=detections, event=event)
