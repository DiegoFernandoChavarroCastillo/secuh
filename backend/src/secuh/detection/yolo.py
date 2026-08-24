"""Detector de personas e inspector de escena sobre Ultralytics YOLO."""

from __future__ import annotations

import logging
from typing import Any, cast

import numpy as np
from ultralytics.models import YOLO

from secuh.core.models import BoundingBox, Detection, SceneObject
from secuh.core.ports import Frame, PersonDetector, SceneInspector

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

    @property
    def model(self) -> YOLO:
        """El modelo cargado, para poder compartirlo (ver ``YoloSceneInspector``)."""
        return self._model

    @property
    def imgsz(self) -> int:
        return self._imgsz

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


class YoloSceneInspector(SceneInspector):
    """Inventario de todas las clases que el modelo sabe ver en un frame.

    **Reutiliza el modelo ya cargado por el detector de personas**: cargar un
    segundo ``YOLO`` duplicaría los cientos de MB que ocupa, y la regla del
    proyecto es un modelo por proceso. Quien lo construya es responsable de
    serializar el acceso al modelo compartido (lo hace el supervisor con un
    único lock para detector e inspector).

    No aplica filtro de clases: eso es justamente lo que lo distingue del
    detector, que sigue viendo solo personas.
    """

    def __init__(self, model: YOLO, imgsz: int = 640, min_confidence: float = 0.25) -> None:
        self._model = model
        self._imgsz = imgsz
        self._min_confidence = min_confidence

    @classmethod
    def sharing_model_with(
        cls, detector: YoloPersonDetector, min_confidence: float = 0.25
    ) -> YoloSceneInspector:
        """Construye el inspector sobre el modelo (ya calentado) del detector."""
        return cls(model=detector.model, imgsz=detector.imgsz, min_confidence=min_confidence)

    def inspect(self, frame: Frame) -> list[SceneObject]:
        results = cast(
            "list[Any]",
            self._model.predict(frame, imgsz=self._imgsz, conf=self._min_confidence, verbose=False),
        )
        names: dict[int, str] = self._model.names
        objects: list[SceneObject] = []
        boxes = results[0].boxes
        for box in [] if boxes is None else boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            class_id = int(box.cls[0])
            objects.append(
                SceneObject(
                    label=names.get(class_id, str(class_id)),
                    confidence=float(box.conf[0]),
                    box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                )
            )
        return objects
