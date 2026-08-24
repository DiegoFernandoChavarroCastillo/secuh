"""Dibujo de las cajas de un evento sobre su captura.

Se hace con OpenCV puro (unas pocas primitivas de dibujo) en vez de con una
librería de anotación: aquí solo hacen falta rectángulos y texto, y las
alternativas arrastran cientos de MB de dependencias que no se usarían para
nada más.

Nota de seguridad de datos: la única entrada de texto que llega a la imagen son
las etiquetas de clase del modelo, que salen de un vocabulario fijo — no hay
texto de usuario que pueda acabar dibujado en la evidencia.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection

import cv2
import numpy as np

from secuh.core.models import BoundingBox, Event
from secuh.core.ports import Frame

# Color fijo (BGR) para las personas que dispararon el evento: se distinguen
# del resto de un vistazo, que es lo que se quiere ver primero en la foto.
TRIGGER_COLOR = (60, 60, 240)
TRIGGER_LABEL = "persona"

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def color_for_label(label: str) -> tuple[int, int, int]:
    """Color BGR estable para una clase.

    Se deriva de un hash criptográfico y no de ``hash()``, que en Python está
    aleatorizado por proceso: el perro debe salir del mismo color en todas las
    fotos y entre reinicios, o comparar capturas se vuelve confuso.
    """
    digest = hashlib.sha1(label.encode("utf-8")).digest()
    hue = digest[0] % 180  # OpenCV usa H en 0..179
    hsv = np.array([[[hue, 200, 255]]], dtype=np.uint8)
    blue, green, red = (int(v) for v in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])
    return blue, green, red


def annotate_event(
    frame: Frame,
    event: Event,
    min_confidence: float = 0.0,
    labels: Collection[str] | None = None,
) -> Frame:
    """Devuelve una **copia** del frame con las cajas del evento dibujadas.

    Copiar no es opcional: el mismo arreglo está en el buffer circular del clip
    y en ``CameraWorker.last_frame`` (el preview del panel). Dibujar sobre él
    dejaría cajas quemadas en el vídeo y en la vista previa.

    ``labels`` filtra qué clases se dibujan; ``None`` las dibuja todas. Las
    personas que dispararon el evento se dibujan siempre: son el motivo de la
    alerta.
    """
    canvas = frame.copy()
    thickness, font_scale = _scale_for(canvas)

    for scene_object in event.scene:
        if scene_object.confidence < min_confidence:
            continue
        if labels is not None and scene_object.label not in labels:
            continue
        color = color_for_label(scene_object.label)
        _draw_box(canvas, scene_object.box, color, thickness)
        _draw_label(
            canvas,
            scene_object.box,
            f"{scene_object.label} {round(scene_object.confidence * 100)}%",
            color,
            thickness,
            font_scale,
        )

    for detection in event.detections:
        _draw_box(canvas, detection.box, TRIGGER_COLOR, thickness + 1)
        _draw_label(
            canvas,
            detection.box,
            f"{TRIGGER_LABEL} {round(detection.confidence * 100)}%",
            TRIGGER_COLOR,
            thickness + 1,
            font_scale,
        )

    return canvas


def _scale_for(frame: Frame) -> tuple[int, float]:
    """Grosor y tamaño de fuente proporcionales, para que 480p y 1080p se lean igual."""
    height = int(frame.shape[0])
    thickness = max(1, round(height / 400))
    font_scale = min(1.0, max(0.35, height / 900))
    return thickness, font_scale


def _draw_box(frame: Frame, box: BoundingBox, color: tuple[int, int, int], thickness: int) -> None:
    cv2.rectangle(frame, (box.x1, box.y1), (box.x2, box.y2), color, thickness)


def _draw_label(
    frame: Frame,
    box: BoundingBox,
    text: str,
    color: tuple[int, int, int],
    thickness: int,
    font_scale: float,
) -> None:
    height, width = int(frame.shape[0]), int(frame.shape[1])
    text_thickness = max(1, thickness - 1)
    (text_w, text_h), baseline = cv2.getTextSize(text, _FONT, font_scale, text_thickness)
    padding = max(2, thickness)

    # Por defecto la etiqueta va encima de la caja; si no cabe (caja pegada al
    # borde superior), se mete dentro. Igual en horizontal con el borde derecho.
    top = box.y1 - text_h - baseline - padding
    if top < 0:
        top = min(box.y1, height - text_h - baseline - padding)
    top = max(0, top)
    left = max(0, min(box.x1, width - text_w - 2 * padding))

    cv2.rectangle(
        frame,
        (left, top),
        (left + text_w + 2 * padding, top + text_h + baseline + padding),
        color,
        cv2.FILLED,
    )
    cv2.putText(
        frame,
        text,
        (left + padding, top + text_h + padding // 2),
        _FONT,
        font_scale,
        _readable_text_color(color),
        text_thickness,
        cv2.LINE_AA,
    )


def _readable_text_color(background: tuple[int, int, int]) -> tuple[int, int, int]:
    """Negro o blanco según la luminancia del fondo, para que la etiqueta se lea."""
    blue, green, red = background
    luminance = 0.114 * blue + 0.587 * green + 0.299 * red
    return (0, 0, 0) if luminance > 140 else (255, 255, 255)
