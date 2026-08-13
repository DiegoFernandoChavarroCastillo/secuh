"""Pre-filtro de movimiento por sustracción de fondo (MOG2)."""

from __future__ import annotations

import cv2
import numpy as np

from secuh.core.models import Polygon
from secuh.core.ports import Frame, MotionDetector


class Mog2MotionDetector(MotionDetector):
    """Marca movimiento cuando la fracción de píxeles cambiados supera el umbral.

    Es deliberadamente barato: decide en ~1 ms si vale la pena invocar YOLO.
    Con ``mask_polygon``, el movimiento fuera de la zona se ignora (y el
    umbral se calcula sobre el área de la zona, no del frame completo).
    """

    def __init__(
        self,
        history: int = 500,
        var_threshold: float = 16.0,
        min_area_ratio: float = 0.01,
        mask_polygon: Polygon | None = None,
    ) -> None:
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history, varThreshold=var_threshold, detectShadows=False
        )
        self._min_area_ratio = min_area_ratio
        self._polygon = mask_polygon
        self._zone_mask: Frame | None = None  # se construye al conocer la resolución

    def has_motion(self, frame: Frame) -> bool:
        mask = self._subtractor.apply(frame)
        mask = cv2.medianBlur(mask, 5)
        if self._polygon is not None:
            zone = self._zone_mask_for(frame)
            mask = cv2.bitwise_and(mask, zone)
            total_pixels = max(1, int(cv2.countNonZero(zone)))
        else:
            total_pixels = int(frame.shape[0]) * int(frame.shape[1])
        motion_pixels = int(cv2.countNonZero(mask))
        return (motion_pixels / total_pixels) > self._min_area_ratio

    def _zone_mask_for(self, frame: Frame) -> Frame:
        height, width = int(frame.shape[0]), int(frame.shape[1])
        if self._zone_mask is None or self._zone_mask.shape[:2] != (height, width):
            assert self._polygon is not None
            points = np.array(
                [[round(x * width), round(y * height)] for x, y in self._polygon],
                dtype=np.int32,
            )
            zone = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(zone, [points], 255)
            self._zone_mask = zone
        return self._zone_mask
