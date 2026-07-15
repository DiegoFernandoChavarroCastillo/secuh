"""Detector de personas sobre Ultralytics YOLO."""

from __future__ import annotations

import logging
from typing import Any, cast

import numpy as np
from ultralytics.models import YOLO

from secuh.core.models import BoundingBox, Detection
from secuh.core.ports import Frame, PersonDetector

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0  # índice de "person" en COCO


class YoloPersonDetector(PersonDetector):
    def __init__(self, model_path: str = "yolov8n.pt", imgsz: int = 640) -> None:
        logger.info("Cargando modelo YOLO", extra={"model": model_path})
        self._model = YOLO(model_path)
        self._imgsz = imgsz
        # La primera inferencia paga la inicialización de torch (medida: ~30 s
        # en CPU modesta). Se calienta aquí para que la primera detección real
        # tenga la misma latencia que las demás.
        warmup = np.zeros((480, 640, 3), dtype=np.uint8)
        self._model.predict(warmup, imgsz=imgsz, classes=[PERSON_CLASS_ID], verbose=False)
        logger.info("Modelo YOLO listo")

    def detect(self, frame: Frame) -> list[Detection]:
        # El tipado de Ultralytics para predict/Boxes es impreciso; se cruza
        # la frontera con Any y se construyen entidades propias bien tipadas.
        results = cast(
            "list[Any]",
            self._model.predict(frame, imgsz=self._imgsz, classes=[PERSON_CLASS_ID], verbose=False),
        )
        detections: list[Detection] = []
        boxes = results[0].boxes
        for box in [] if boxes is None else boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            detections.append(
                Detection(
                    box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    confidence=float(box.conf[0]),
                )
            )
        return detections
