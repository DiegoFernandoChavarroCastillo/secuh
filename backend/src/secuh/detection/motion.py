"""Pre-filtro de movimiento por sustracción de fondo (MOG2)."""

from __future__ import annotations

import cv2

from secuh.core.ports import Frame, MotionDetector


class Mog2MotionDetector(MotionDetector):
    """Marca movimiento cuando la fracción de píxeles cambiados supera el umbral.

    Es deliberadamente barato: decide en ~1 ms si vale la pena invocar YOLO.
    """

    def __init__(
        self,
        history: int = 500,
        var_threshold: float = 16.0,
        min_area_ratio: float = 0.01,
    ) -> None:
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history, varThreshold=var_threshold, detectShadows=False
        )
        self._min_area_ratio = min_area_ratio

    def has_motion(self, frame: Frame) -> bool:
        mask = self._subtractor.apply(frame)
        mask = cv2.medianBlur(mask, 5)
        motion_pixels = int(cv2.countNonZero(mask))
        total_pixels = int(frame.shape[0]) * int(frame.shape[1])
        return (motion_pixels / total_pixels) > self._min_area_ratio
