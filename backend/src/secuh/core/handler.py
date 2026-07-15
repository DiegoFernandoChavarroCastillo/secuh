"""Manejo de un evento confirmado: evidencia, notificación y persistencia.

El orden importa: primero la captura (rápida, va adjunta a la notificación),
luego la notificación (la razón de ser del sistema: debe salir en segundos),
después el clip (tarda ``post_seconds`` en completarse) y al final el registro
del evento. Un fallo en un paso se loggea y no impide los siguientes.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace

from secuh.core.models import Camera, Event, Notification
from secuh.core.ports import (
    ClipRecorder,
    EventStore,
    Frame,
    NotificationError,
    Notifier,
    SnapshotStore,
)

logger = logging.getLogger(__name__)


class EventHandler:
    def __init__(
        self,
        camera: Camera,
        snapshots: SnapshotStore,
        clips: ClipRecorder,
        notifiers: Sequence[Notifier],
        events: EventStore,
    ) -> None:
        self._camera = camera
        self._snapshots = snapshots
        self._clips = clips
        self._notifiers = notifiers
        self._events = events

    def handle(self, event: Event, frame: Frame) -> Event:
        snapshot_path: str | None = None
        try:
            snapshot_path = self._snapshots.save(event, frame)
        except Exception:
            logger.exception("No se pudo guardar la captura", extra={"event_id": str(event.id)})

        notified = self._notify(event, snapshot_path)

        clip_path: str | None = None
        try:
            clip_path = self._clips.record_event(event)
        except Exception:
            logger.exception("No se pudo grabar el clip", extra={"event_id": str(event.id)})

        event = replace(event, snapshot_path=snapshot_path, clip_path=clip_path, notified=notified)
        try:
            self._events.save(event)
        except Exception:
            logger.exception("No se pudo persistir el evento", extra={"event_id": str(event.id)})
        return event

    def _notify(self, event: Event, snapshot_path: str | None) -> bool:
        notification = self._build_notification(event, snapshot_path)
        notified = False
        for notifier in self._notifiers:
            try:
                notifier.send(notification)
                notified = True
            except NotificationError:
                logger.exception(
                    "Fallo al notificar",
                    extra={"event_id": str(event.id), "notifier": type(notifier).__name__},
                )
        return notified

    def _build_notification(self, event: Event, snapshot_path: str | None) -> Notification:
        confidence_pct = round(event.max_confidence * 100)
        local_time = event.timestamp.astimezone().strftime("%H:%M:%S")
        n_personas = len(event.detections)
        quien = "1 persona" if n_personas == 1 else f"{n_personas} personas"
        return Notification(
            title=f"secuh: {self._camera.name}",
            message=(
                f"{quien} detectada(s) en {self._camera.name} ({self._camera.zone}) "
                f"a las {local_time} — confianza {confidence_pct}%"
            ),
            priority="high",
            image_path=snapshot_path,
        )
