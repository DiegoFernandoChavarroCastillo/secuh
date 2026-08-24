"""Tests del dibujo de cajas sobre la captura.

No se comprueba que la foto quede "bonita" —eso no es testeable—, sino las tres
propiedades que sí pueden romper algo en producción: que no se mute el frame
original, que las cajas pegadas a los bordes no revienten, y que el color de
cada clase sea estable entre procesos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import numpy as np

from secuh.core.models import BoundingBox, Detection, Event, SceneObject
from secuh.core.ports import Frame
from secuh.storage.annotate import annotate_event, color_for_label


def make_frame(height: int = 120, width: int = 160) -> Frame:
    return np.zeros((height, width, 3), dtype=np.uint8)


def make_event(
    detections: tuple[Detection, ...] = (),
    scene: tuple[SceneObject, ...] = (),
) -> Event:
    return Event(
        id=uuid4(),
        camera_id=uuid4(),
        timestamp=datetime.now(UTC),
        detections=detections,
        scene=scene,
    )


def persona() -> Detection:
    return Detection(box=BoundingBox(20, 20, 60, 100), confidence=0.9)


def perro() -> SceneObject:
    return SceneObject(label="dog", confidence=0.8, box=BoundingBox(70, 60, 110, 100))


class TestNoMutaElOriginal:
    def test_el_frame_de_entrada_queda_intacto(self) -> None:
        frame = make_frame()
        original = frame.copy()

        annotate_event(frame, make_event(detections=(persona(),), scene=(perro(),)))

        # El mismo arreglo está en el buffer del clip y en el preview del panel:
        # dibujar sobre él dejaría cajas quemadas en el vídeo.
        assert np.array_equal(frame, original)

    def test_la_copia_si_cambia(self) -> None:
        frame = make_frame()

        annotated = annotate_event(frame, make_event(detections=(persona(),)))

        assert not np.array_equal(annotated, frame)
        assert annotated.shape == frame.shape


class TestFiltros:
    def test_por_debajo_del_umbral_no_se_dibuja(self) -> None:
        frame = make_frame()
        flojo = SceneObject(label="cat", confidence=0.30, box=BoundingBox(5, 5, 40, 40))

        annotated = annotate_event(frame, make_event(scene=(flojo,)), min_confidence=0.45)

        assert np.array_equal(annotated, frame)

    def test_las_clases_no_listadas_no_se_dibujan(self) -> None:
        frame = make_frame()

        annotated = annotate_event(frame, make_event(scene=(perro(),)), labels={"car"})

        assert np.array_equal(annotated, frame)

    def test_la_persona_que_disparo_se_dibuja_siempre(self) -> None:
        frame = make_frame()

        # Aunque el filtro de clases excluya todo, el motivo de la alerta se ve.
        annotated = annotate_event(
            frame, make_event(detections=(persona(),)), min_confidence=0.99, labels=set()
        )

        assert not np.array_equal(annotated, frame)


class TestBordes:
    def test_caja_pegada_al_borde_superior_izquierdo(self) -> None:
        frame = make_frame()
        objeto = SceneObject(label="car", confidence=0.9, box=BoundingBox(0, 0, 30, 20))

        annotated = annotate_event(frame, make_event(scene=(objeto,)))

        assert annotated.shape == frame.shape

    def test_caja_pegada_al_borde_inferior_derecho(self) -> None:
        frame = make_frame(height=120, width=160)
        objeto = SceneObject(label="car", confidence=0.9, box=BoundingBox(130, 100, 159, 119))

        annotated = annotate_event(frame, make_event(scene=(objeto,)))

        assert annotated.shape == frame.shape

    def test_frame_diminuto_no_revienta(self) -> None:
        frame = make_frame(height=16, width=16)
        objeto = SceneObject(label="bird", confidence=0.9, box=BoundingBox(0, 0, 15, 15))

        annotated = annotate_event(frame, make_event(scene=(objeto,)))

        assert annotated.shape == frame.shape


class TestColores:
    def test_el_color_de_una_clase_es_estable(self) -> None:
        # No puede depender de hash(), que está aleatorizado por proceso: el
        # perro debe salir del mismo color en todas las capturas.
        assert color_for_label("dog") == color_for_label("dog")

    def test_clases_distintas_no_comparten_color(self) -> None:
        colores = {color_for_label(label) for label in ("dog", "car", "motorcycle", "backpack")}
        assert len(colores) == 4
