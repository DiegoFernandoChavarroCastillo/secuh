"""Tests de horarios de vigilancia y zonas de detección."""

from __future__ import annotations

from datetime import time as dtime

import numpy as np

from secuh.core.geometry import point_in_polygon
from secuh.core.models import (
    BoundingBox,
    Camera,
    CameraState,
    Detection,
    Schedule,
    ScheduleMode,
    SourceType,
)
from secuh.core.pipeline import CooldownGate, DetectionPipeline
from secuh.core.ports import Clock, Frame, MotionDetector, PersonDetector


class TestSchedule:
    def test_always_siempre_activo(self) -> None:
        schedule = Schedule(mode=ScheduleMode.ALWAYS)
        assert schedule.is_active(dtime(3, 0))
        assert schedule.is_active(dtime(15, 0))

    def test_nocturno_cruza_medianoche(self) -> None:
        schedule = Schedule(mode=ScheduleMode.NIGHT)  # 22:00 -> 06:00
        assert schedule.is_active(dtime(23, 30))
        assert schedule.is_active(dtime(2, 0))
        assert not schedule.is_active(dtime(12, 0))
        assert not schedule.is_active(dtime(21, 59))
        assert schedule.is_active(dtime(22, 0))  # inicio inclusivo
        assert not schedule.is_active(dtime(6, 0))  # fin exclusivo

    def test_personalizado_diurno(self) -> None:
        schedule = Schedule(mode=ScheduleMode.CUSTOM, start=dtime(9, 0), end=dtime(18, 0))
        assert schedule.is_active(dtime(12, 0))
        assert not schedule.is_active(dtime(20, 0))

    def test_personalizado_que_cruza_medianoche(self) -> None:
        schedule = Schedule(mode=ScheduleMode.CUSTOM, start=dtime(20, 0), end=dtime(4, 0))
        assert schedule.is_active(dtime(23, 0))
        assert schedule.is_active(dtime(1, 0))
        assert not schedule.is_active(dtime(10, 0))

    def test_personalizado_sin_rango_no_bloquea(self) -> None:
        schedule = Schedule(mode=ScheduleMode.CUSTOM)
        assert schedule.is_active(dtime(12, 0))


class TestPointInPolygon:
    SQUARE = ((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75))

    def test_dentro_y_fuera(self) -> None:
        assert point_in_polygon(0.5, 0.5, self.SQUARE)
        assert not point_in_polygon(0.1, 0.5, self.SQUARE)
        assert not point_in_polygon(0.5, 0.9, self.SQUARE)

    def test_poligono_degenerado_no_restringe(self) -> None:
        assert point_in_polygon(0.5, 0.5, ((0.0, 0.0), (1.0, 1.0)))


# ---------------------------------------------------------------- pipeline
class FixedClock(Clock):
    def now(self) -> float:
        return 0.0


class AlwaysMotion(MotionDetector):
    def has_motion(self, frame: Frame) -> bool:
        return True


class FixedDetector(PersonDetector):
    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections
        self.calls = 0

    def detect(self, frame: Frame) -> list[Detection]:
        self.calls += 1
        return self._detections


def person_at(x1: int, y1: int, x2: int, y2: int) -> Detection:
    return Detection(box=BoundingBox(x1, y1, x2, y2), confidence=0.9)


def make_camera(**overrides: object) -> Camera:
    base = Camera.new("entrada", "puerta", SourceType.USB, "0")
    from dataclasses import replace

    return replace(base, state=CameraState.ARMED, **overrides)  # type: ignore[arg-type]


def make_frame() -> Frame:
    return np.zeros((100, 100, 3), dtype=np.uint8)  # 100x100: coords fáciles


class TestScheduleInPipeline:
    def test_fuera_de_horario_no_analiza(self) -> None:
        camera = make_camera(
            schedule=Schedule(mode=ScheduleMode.CUSTOM, start=dtime(22, 0), end=dtime(6, 0))
        )
        detector = FixedDetector([person_at(0, 0, 50, 50)])
        pipeline = DetectionPipeline(
            camera=camera,
            motion_detector=AlwaysMotion(),
            person_detector=detector,
            cooldown=CooldownGate(FixedClock()),
            local_time=lambda: dtime(12, 0),  # mediodía: fuera del horario
        )

        result = pipeline.process_frame(make_frame())

        assert not result.in_schedule
        assert result.event is None
        assert detector.calls == 0  # ni siquiera se invocó YOLO

    def test_dentro_de_horario_analiza(self) -> None:
        camera = make_camera(
            schedule=Schedule(mode=ScheduleMode.CUSTOM, start=dtime(22, 0), end=dtime(6, 0))
        )
        pipeline = DetectionPipeline(
            camera=camera,
            motion_detector=AlwaysMotion(),
            person_detector=FixedDetector([person_at(0, 0, 50, 50)]),
            cooldown=CooldownGate(FixedClock()),
            local_time=lambda: dtime(23, 0),
        )

        result = pipeline.process_frame(make_frame())

        assert result.in_schedule
        assert result.event is not None


class TestZoneInPipeline:
    # Zona: mitad izquierda del frame.
    LEFT_HALF = ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))

    def test_persona_fuera_de_zona_se_ignora(self) -> None:
        camera = make_camera(mask_polygon=self.LEFT_HALF)
        pipeline = DetectionPipeline(
            camera=camera,
            motion_detector=AlwaysMotion(),
            person_detector=FixedDetector([person_at(60, 10, 90, 90)]),  # centro en x=0.75
            cooldown=CooldownGate(FixedClock()),
        )

        result = pipeline.process_frame(make_frame())

        assert result.event is None
        assert result.detections == ()

    def test_persona_dentro_de_zona_genera_evento(self) -> None:
        camera = make_camera(mask_polygon=self.LEFT_HALF)
        pipeline = DetectionPipeline(
            camera=camera,
            motion_detector=AlwaysMotion(),
            person_detector=FixedDetector([person_at(10, 10, 40, 90)]),  # centro en x=0.25
            cooldown=CooldownGate(FixedClock()),
        )

        result = pipeline.process_frame(make_frame())

        assert result.event is not None

    def test_sin_zona_todo_el_frame_cuenta(self) -> None:
        camera = make_camera(mask_polygon=None)
        pipeline = DetectionPipeline(
            camera=camera,
            motion_detector=AlwaysMotion(),
            person_detector=FixedDetector([person_at(60, 10, 90, 90)]),
            cooldown=CooldownGate(FixedClock()),
        )

        assert pipeline.process_frame(make_frame()).event is not None
