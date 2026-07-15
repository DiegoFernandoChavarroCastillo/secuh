"""Tests del EventHandler con fakes de todos los puertos."""

from __future__ import annotations

import numpy as np

from secuh.core.handler import EventHandler
from secuh.core.models import (
    BoundingBox,
    Camera,
    Detection,
    Event,
    Notification,
    SourceType,
)
from secuh.core.ports import (
    ClipRecorder,
    EventStore,
    Frame,
    NotificationError,
    Notifier,
    SnapshotStore,
)


class FakeSnapshots(SnapshotStore):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def save(self, event: Event, frame: Frame) -> str:
        if self.fail:
            raise OSError("disco lleno")
        return f"/snapshots/{event.id}.jpg"


class FakeClips(ClipRecorder):
    def push_frame(self, frame: Frame) -> None:
        pass

    def record_event(self, event: Event) -> str:
        return f"/clips/{event.id}.mp4"


class FakeNotifier(Notifier):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        if self.fail:
            raise NotificationError("canal caído")
        self.sent.append(notification)


class FakeEvents(EventStore):
    def __init__(self) -> None:
        self.saved: list[Event] = []

    def save(self, event: Event) -> None:
        self.saved.append(event)


def make_event(camera: Camera) -> Event:
    return Event.new(
        camera_id=camera.id,
        detections=(Detection(box=BoundingBox(0, 0, 5, 5), confidence=0.87),),
    )


def make_camera() -> Camera:
    return Camera.new("entrada", "puerta", SourceType.USB, "0")


def make_frame() -> Frame:
    return np.zeros((10, 10, 3), dtype=np.uint8)


def build(
    camera: Camera,
    snapshots: FakeSnapshots | None = None,
    notifiers: list[Notifier] | None = None,
) -> tuple[EventHandler, FakeEvents]:
    events = FakeEvents()
    handler = EventHandler(
        camera=camera,
        snapshots=snapshots or FakeSnapshots(),
        clips=FakeClips(),
        notifiers=notifiers if notifiers is not None else [FakeNotifier()],
        events=events,
    )
    return handler, events


class TestHappyPath:
    def test_evento_completo_con_evidencia_y_notificacion(self) -> None:
        camera = make_camera()
        notifier = FakeNotifier()
        handler, events = build(camera, notifiers=[notifier])

        result = handler.handle(make_event(camera), make_frame())

        assert result.snapshot_path is not None
        assert result.clip_path is not None
        assert result.notified
        assert events.saved == [result]

    def test_la_notificacion_incluye_camara_confianza_e_imagen(self) -> None:
        camera = make_camera()
        notifier = FakeNotifier()
        handler, _ = build(camera, notifiers=[notifier])

        handler.handle(make_event(camera), make_frame())

        [notification] = notifier.sent
        assert "entrada" in notification.message
        assert "87%" in notification.message
        assert notification.image_path is not None
        assert notification.priority == "high"


class TestFallosParciales:
    def test_fallo_de_notificacion_no_impide_persistir_el_evento(self) -> None:
        camera = make_camera()
        handler, events = build(camera, notifiers=[FakeNotifier(fail=True)])

        result = handler.handle(make_event(camera), make_frame())

        assert not result.notified
        assert events.saved == [result]

    def test_basta_un_canal_exitoso_para_marcar_notificado(self) -> None:
        camera = make_camera()
        ok = FakeNotifier()
        handler, _ = build(camera, notifiers=[FakeNotifier(fail=True), ok])

        result = handler.handle(make_event(camera), make_frame())

        assert result.notified
        assert len(ok.sent) == 1

    def test_fallo_de_snapshot_notifica_sin_imagen(self) -> None:
        camera = make_camera()
        notifier = FakeNotifier()
        handler, _ = build(camera, snapshots=FakeSnapshots(fail=True), notifiers=[notifier])

        result = handler.handle(make_event(camera), make_frame())

        assert result.snapshot_path is None
        [notification] = notifier.sent
        assert notification.image_path is None
