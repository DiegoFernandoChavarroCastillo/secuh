"""Tests de la anotación de escena, con fakes de los puertos.

La propiedad que más importa aquí no es que la escena se registre, sino que
**nunca pueda impedir una notificación**: registrar contexto es deseable,
avisar de que hay alguien en la casa es la razón de ser del sistema.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from sqlalchemy.orm import Session, sessionmaker

from secuh.core.handler import EventHandler
from secuh.core.models import (
    BoundingBox,
    Camera,
    Detection,
    Event,
    Notification,
    SceneObject,
    SourceType,
)
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


class FakeSnapshots(SnapshotStore):
    def save(self, event: Event, frame: Frame) -> str:
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


class FakeSceneInspector(SceneInspector):
    def __init__(self, objects: list[SceneObject] | None = None, fail: bool = False) -> None:
        self.objects = objects if objects is not None else []
        self.fail = fail
        self.calls = 0

    def inspect(self, frame: Frame) -> list[SceneObject]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("el modelo reventó")
        return list(self.objects)


class FakeRawSnapshots(RawSnapshotStore):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def save_raw(self, event: Event, frame: Frame) -> str:
        if self.fail:
            raise OSError("disco lleno")
        return f"/snapshots/{event.id}.raw.jpg"


def make_camera() -> Camera:
    return Camera.new("entrada", "puerta", SourceType.USB, "0")


def make_event(camera: Camera) -> Event:
    return Event.new(
        camera_id=camera.id,
        detections=(Detection(box=BoundingBox(0, 0, 5, 5), confidence=0.87),),
    )


def make_frame(height: int = 48, width: int = 64) -> Frame:
    return np.zeros((height, width, 3), dtype=np.uint8)


def build(
    camera: Camera,
    inspector: SceneInspector | None = None,
    raw: RawSnapshotStore | None = None,
    notifier: FakeNotifier | None = None,
) -> tuple[EventHandler, FakeEvents]:
    events = FakeEvents()
    handler = EventHandler(
        camera=camera,
        snapshots=FakeSnapshots(),
        clips=FakeClips(),
        notifiers=[notifier or FakeNotifier()],
        events=events,
        scene_inspector=inspector,
        raw_snapshots=raw,
    )
    return handler, events


def perro() -> SceneObject:
    return SceneObject(label="dog", confidence=0.81, box=BoundingBox(10, 10, 30, 30))


class TestRegistroDeEscena:
    def test_los_objetos_vistos_quedan_en_el_evento(self) -> None:
        camera = make_camera()
        handler, events = build(camera, inspector=FakeSceneInspector([perro()]))

        result = handler.handle(make_event(camera), make_frame())

        assert [o.label for o in result.scene] == ["dog"]
        assert events.saved == [result]

    def test_se_registra_la_resolucion_del_frame(self) -> None:
        camera = make_camera()
        handler, _ = build(camera, inspector=FakeSceneInspector())

        result = handler.handle(make_event(camera), make_frame(height=480, width=640))

        # Sin esto las cajas en píxeles no se pueden normalizar al analizar.
        assert (result.frame_width, result.frame_height) == (640, 480)

    def test_sin_inspector_el_comportamiento_es_el_de_siempre(self) -> None:
        camera = make_camera()
        handler, _ = build(camera, inspector=None)

        result = handler.handle(make_event(camera), make_frame())

        assert result.scene == ()
        assert result.snapshot_raw_path is None
        assert result.notified

    def test_la_escena_no_altera_el_texto_de_la_notificacion(self) -> None:
        camera = make_camera()
        notifier = FakeNotifier()
        handler, _ = build(camera, inspector=FakeSceneInspector([perro()]), notifier=notifier)

        handler.handle(make_event(camera), make_frame())

        [notification] = notifier.sent
        # Se notifica la persona; el perro se registra pero no se menciona.
        assert "1 persona" in notification.message
        assert "dog" not in notification.message
        assert "perro" not in notification.message


class TestToleranciaAFallos:
    def test_si_la_inspeccion_falla_la_notificacion_sale_igual(self) -> None:
        camera = make_camera()
        notifier = FakeNotifier()
        handler, events = build(camera, inspector=FakeSceneInspector(fail=True), notifier=notifier)

        result = handler.handle(make_event(camera), make_frame())

        assert result.scene == ()
        assert result.notified
        assert len(notifier.sent) == 1
        assert events.saved == [result]

    def test_si_falla_la_captura_cruda_el_evento_continua(self) -> None:
        camera = make_camera()
        handler, events = build(
            camera, inspector=FakeSceneInspector([perro()]), raw=FakeRawSnapshots(fail=True)
        )

        result = handler.handle(make_event(camera), make_frame())

        assert result.snapshot_raw_path is None
        assert result.snapshot_path is not None
        assert result.notified
        assert events.saved == [result]

    def test_se_inspecciona_una_sola_vez_por_evento(self) -> None:
        camera = make_camera()
        inspector = FakeSceneInspector([perro()])
        handler, _ = build(camera, inspector=inspector)

        handler.handle(make_event(camera), make_frame())

        # Una inferencia extra por evento es el presupuesto del diseño.
        assert inspector.calls == 1


class TestCapturaCruda:
    def test_se_guardan_las_dos_rutas(self) -> None:
        camera = make_camera()
        handler, _ = build(camera, inspector=FakeSceneInspector([perro()]), raw=FakeRawSnapshots())

        result = handler.handle(make_event(camera), make_frame())

        assert result.snapshot_path is not None
        assert result.snapshot_raw_path is not None
        assert result.snapshot_path != result.snapshot_raw_path


class TestPersistenciaReal:
    """El puente entre el dominio y la BD, con SQLAlchemy de verdad.

    El resto de los tests del handler usan un ``EventStore`` falso, así que sin
    esto la traducción de ``Event.scene`` a filas de ``event_objects`` —donde
    un error perdería en silencio todo lo que registramos— no la mira nadie.
    """

    def test_la_escena_llega_a_event_objects(self, session_factory: sessionmaker[Session]) -> None:
        from secuh.db.event_store import DbEventStore
        from secuh.db.models import CameraRow, EventObjectRow

        with session_factory() as session:
            row = CameraRow(name="entrada", source_type="usb", source_url="0")
            session.add(row)
            session.commit()
            camera_id = row.id

        event = replace(
            Event.new(
                camera_id=camera_id,
                detections=(Detection(box=BoundingBox(1, 2, 3, 4), confidence=0.91),),
            ),
            scene=(perro(),),
            frame_width=640,
            frame_height=480,
        )
        DbEventStore(session_factory).save(event)

        with session_factory() as session:
            objects = session.query(EventObjectRow).all()
            assert {(o.source, o.label) for o in objects} == {
                ("trigger", "person"),
                ("scene", "dog"),
            }
            perro_row = next(o for o in objects if o.label == "dog")
            assert (perro_row.x1, perro_row.y1, perro_row.x2, perro_row.y2) == (10, 10, 30, 30)

    def test_borrar_el_evento_borra_sus_objetos(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from secuh.db.event_store import DbEventStore
        from secuh.db.models import CameraRow, EventObjectRow, EventRow

        with session_factory() as session:
            row = CameraRow(name="entrada", source_type="usb", source_url="0")
            session.add(row)
            session.commit()
            camera_id = row.id

        event = replace(
            Event.new(
                camera_id=camera_id,
                detections=(Detection(box=BoundingBox(1, 2, 3, 4), confidence=0.9),),
            ),
            scene=(perro(),),
        )
        DbEventStore(session_factory).save(event)

        with session_factory() as session:
            session.delete(session.get(EventRow, event.id))
            session.commit()
            # Sin delete-orphan quedarían filas huérfanas, que es el bug que
            # ya apareció una vez con cameras/events en la 0.6.1.
            assert session.query(EventObjectRow).count() == 0
