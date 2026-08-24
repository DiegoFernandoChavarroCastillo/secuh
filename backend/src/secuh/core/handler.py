"""Manejo de un evento confirmado: evidencia, notificación y persistencia.

El orden importa: primero la anotación de escena (que la captura necesita para
dibujar las cajas), luego la captura (rápida, va adjunta a la notificación),
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
    RawSnapshotStore,
    SceneInspector,
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
        scene_inspector: SceneInspector | None = None,
        raw_snapshots: RawSnapshotStore | None = None,
    ) -> None:
        self._camera = camera
        self._snapshots = snapshots
        self._clips = clips
        self._notifiers = notifiers
        self._events = events
        # Ambos opcionales a propósito: sin ellos, el manejo del evento es
        # exactamente el de antes de la Fase 7.
        self._scene_inspector = scene_inspector
        self._raw_snapshots = raw_snapshots

    def handle(self, event: Event, frame: Frame) -> Event:
        event = self._describe_scene(event, frame)

        raw_snapshot_path = self._save_raw_snapshot(event, frame)

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

        event = replace(
            event,
            snapshot_path=snapshot_path,
            snapshot_raw_path=raw_snapshot_path,
            clip_path=clip_path,
            notified=notified,
        )
        try:
            self._events.save(event)
        except Exception:
            logger.exception("No se pudo persistir el evento", extra={"event_id": str(event.id)})
        return event

    def _describe_scene(self, event: Event, frame: Frame) -> Event:
        """Anota qué más había en la escena. Nunca puede tumbar el evento.

        Registrar el contexto es deseable; notificar es obligatorio. Si la
        inferencia de escena falla, el evento sigue su curso con ``scene``
        vacío y la captura sale sin cajas.
        """
        height, width = int(frame.shape[0]), int(frame.shape[1])
        event = replace(event, frame_width=width, frame_height=height)
        if self._scene_inspector is None:
            return event
        try:
            scene = tuple(self._scene_inspector.inspect(frame))
        except Exception:
            logger.exception(
                "No se pudo describir la escena; el evento continúa sin anotar",
                extra={"event_id": str(event.id)},
            )
            return event
        return replace(event, scene=scene)

    def _save_raw_snapshot(self, event: Event, frame: Frame) -> str | None:
        if self._raw_snapshots is None:
            return None
        try:
            return self._raw_snapshots.save_raw(event, frame)
        except Exception:
            logger.exception(
                "No se pudo guardar la captura cruda", extra={"event_id": str(event.id)}
            )
            return None

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
