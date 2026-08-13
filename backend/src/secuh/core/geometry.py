"""Geometría pura para zonas de detección (sin OpenCV)."""

from __future__ import annotations

from secuh.core.models import Polygon


def point_in_polygon(x: float, y: float, polygon: Polygon) -> bool:
    """Ray casting: ¿está el punto dentro del polígono?

    Coordenadas normalizadas (0..1). Un polígono degenerado (< 3 puntos)
    no restringe nada: devuelve True.
    """
    if len(polygon) < 3:
        return True
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside
