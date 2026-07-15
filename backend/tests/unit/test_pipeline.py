"""Tests del pipeline de detección usando fakes de los puertos."""

from __future__ import annotations

import numpy as np

from secuh.core.models import BoundingBox, Camera, CameraState, Detection, SourceType
from secuh.core.pipeline import CooldownGate, DetectionPipeline
from secuh.core.ports import Clock, Frame, MotionDetector, PersonDetector


class FakeClock(Clock):
    def __init__(self) -> None:
        self.time = 0.0

    def now(self) -> float:
        return self.time

    def advance(self, seconds: float) -> None:
        self.time += seconds


class FakeMotion(MotionDetector):
    def __init__(self, motion: bool) -> None:
        self.motion = motion
        self.calls = 0

    def has_motion(self, frame: Frame) -> bool:
        self.calls += 1
        return self.motion


class FakeDetector(PersonDetector):
    def __init__(self, detections: list[Detection]) -> None:
        self.detections = detections
        self.calls = 0

    def detect(self, frame: Frame) -> list[Detection]:
        self.calls += 1
        return self.detections


def make_frame() -> Frame:
    return np.zeros((10, 10, 3), dtype=np.uint8)


def make_camera(confidence_threshold: float = 0.5, cooldown_seconds: int = 60) -> Camera:
    camera = Camera.new(
        name="entrada",
        zone="puerta",
        source_type=SourceType.IP_WEBCAM,
        source_url="http://192.0.2.1:8080/video",
    )
    return Camera(
        id=camera.id,
        name=camera.name,
        zone=camera.zone,
        source_type=camera.source_type,
        source_url=camera.source_url,
        state=CameraState.ARMED,
        confidence_threshold=confidence_threshold,
        cooldown_seconds=cooldown_seconds,
    )


def person(confidence: float) -> Detection:
    return Detection(box=BoundingBox(0, 0, 5, 5), confidence=confidence)


def make_pipeline(
    camera: Camera,
    motion: bool = True,
    detections: list[Detection] | None = None,
    clock: FakeClock | None = None,
) -> tuple[DetectionPipeline, FakeMotion, FakeDetector]:
    fake_motion = FakeMotion(motion)
    fake_detector = FakeDetector(detections or [])
    pipeline = DetectionPipeline(
        camera=camera,
        motion_detector=fake_motion,
        person_detector=fake_detector,
        cooldown=CooldownGate(clock or FakeClock()),
    )
    return pipeline, fake_motion, fake_detector


class TestMotionPrefilter:
    def test_sin_movimiento_no_invoca_al_detector(self) -> None:
        pipeline, _, detector = make_pipeline(make_camera(), motion=False)

        result = pipeline.process_frame(make_frame())

        assert not result.motion
        assert result.event is None
        assert detector.calls == 0

    def test_con_movimiento_invoca_al_detector(self) -> None:
        pipeline, _, detector = make_pipeline(make_camera(), motion=True)

        pipeline.process_frame(make_frame())

        assert detector.calls == 1


class TestConfidenceThreshold:
    def test_deteccion_bajo_el_umbral_se_descarta(self) -> None:
        pipeline, _, _ = make_pipeline(
            make_camera(confidence_threshold=0.5), detections=[person(0.4)]
        )

        result = pipeline.process_frame(make_frame())

        assert result.detections == ()
        assert result.event is None

    def test_deteccion_sobre_el_umbral_genera_evento(self) -> None:
        camera = make_camera(confidence_threshold=0.5)
        pipeline, _, _ = make_pipeline(camera, detections=[person(0.9)])

        result = pipeline.process_frame(make_frame())

        assert result.event is not None
        assert result.event.camera_id == camera.id
        assert result.event.max_confidence == 0.9


class TestCooldown:
    def test_evento_repetido_dentro_del_cooldown_se_silencia(self) -> None:
        clock = FakeClock()
        pipeline, _, _ = make_pipeline(
            make_camera(cooldown_seconds=60), detections=[person(0.9)], clock=clock
        )

        first = pipeline.process_frame(make_frame())
        clock.advance(30)
        second = pipeline.process_frame(make_frame())

        assert first.event is not None
        assert second.event is None
        # Las detecciones siguen reportándose aunque no haya evento nuevo.
        assert second.detections != ()

    def test_pasado_el_cooldown_se_permite_un_nuevo_evento(self) -> None:
        clock = FakeClock()
        pipeline, _, _ = make_pipeline(
            make_camera(cooldown_seconds=60), detections=[person(0.9)], clock=clock
        )

        pipeline.process_frame(make_frame())
        clock.advance(61)
        result = pipeline.process_frame(make_frame())

        assert result.event is not None

    def test_camaras_distintas_no_comparten_cooldown(self) -> None:
        clock = FakeClock()
        gate = CooldownGate(clock)

        assert gate.allow("cam-a", 60)
        assert gate.allow("cam-b", 60)
        assert not gate.allow("cam-a", 60)
