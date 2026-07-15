"""Tests del pre-filtro de movimiento con frames sintéticos."""

from __future__ import annotations

import numpy as np

from secuh.core.ports import Frame
from secuh.detection.motion import Mog2MotionDetector


def frame(value: int) -> Frame:
    return np.full((120, 160, 3), value, dtype=np.uint8)


def test_escena_estatica_no_reporta_movimiento() -> None:
    detector = Mog2MotionDetector()
    for _ in range(30):  # deja que el modelo de fondo aprenda la escena
        detector.has_motion(frame(0))

    assert not detector.has_motion(frame(0))


def test_cambio_brusco_reporta_movimiento() -> None:
    detector = Mog2MotionDetector()
    for _ in range(30):
        detector.has_motion(frame(0))

    assert detector.has_motion(frame(255))
