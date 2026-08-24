"""Extracción del histórico en formato analizable.

Vive aquí, y no en el router, porque tiene **dos consumidores**: la descarga
por la API y el script ``scripts/export_dataset.py``. Duplicar las columnas en
los dos sitios sería garantizar que algún día dejen de coincidir, y entonces
"datos limpios" pasaría a ser una promesa falsa.

Contrato del formato (lo que el análisis puede dar por hecho):

- Formato largo: una fila por observación.
- ``timestamp_utc`` en ISO 8601 **siempre con zona**, en UTC.
- ``label`` es la clase COCO en inglés — identificador estable del dataset, no
  texto de interfaz.
- Cajas en píxeles junto a la resolución del frame; lo normalizado se deriva.
- Ausencia se representa vacía (``NaN`` al leer), nunca como ``0`` ni ``"-"``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from secuh.db.models import CameraRow, EventObjectRow, EventRow

EVENT_COLUMNS = (
    "event_id",
    "timestamp_utc",
    "camera_name",
    "camera_zone",
    "confidence",
    "person_count",
    "notified",
    "frame_width",
    "frame_height",
    "has_snapshot",
    "has_clip",
)

OBJECT_COLUMNS = (
    "event_id",
    "timestamp_utc",
    "camera_name",
    "camera_zone",
    "source",
    "label",
    "confidence",
    "x1",
    "y1",
    "x2",
    "y2",
    "frame_width",
    "frame_height",
    "box_cx_norm",
    "box_cy_norm",
    "box_area_ratio",
)

#: Caracteres que Excel y LibreOffice interpretan como inicio de fórmula. Los
#: nombres y zonas de cámara los escribe un usuario, así que un nombre como
#: ``=WEBSERVICE(...)`` se ejecutaría al abrir el CSV descargado. Se neutraliza
#: al exportar, no al guardar: el dato en la base debe quedar tal cual se metió.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> object:
    """Neutraliza la inyección de fórmulas en campos de texto del CSV."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def iso_utc(value: datetime) -> str:
    """ISO 8601 **siempre con zona**, sea cual sea el motor de base de datos.

    PostgreSQL devuelve el ``timestamptz`` con zona, pero SQLite no guarda
    zonas y lo devuelve ingenuo. Los eventos se sellan en UTC al crearse
    (``Event.new``), así que un valor sin zona es UTC: se marca como tal en vez
    de exportar una hora ambigua que el análisis leería como local.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def norm(value: int, size: int | None) -> float | None:
    """Normaliza una coordenada; ``None`` si no se conoce la resolución."""
    return round(value / size, 6) if size else None


def filtered[S: Select[Any]](
    statement: S,
    camera_id: UUID | None = None,
    label: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> S:
    """Aplica los filtros comunes conservando el tipo del ``select``.

    Los listados y los dos exports filtran igual pero seleccionan columnas
    distintas.
    """
    if camera_id is not None:
        statement = statement.where(EventRow.camera_id == camera_id)
    if since is not None:
        statement = statement.where(EventRow.timestamp >= since)
    if until is not None:
        statement = statement.where(EventRow.timestamp <= until)
    if label is not None:
        statement = statement.where(
            EventRow.objects.any(
                (EventObjectRow.label == label)
                & (EventObjectRow.source == EventObjectRow.SOURCE_SCENE)
            )
        )
    return statement


def _base_query() -> Select[tuple[EventRow, str, str]]:
    return (
        select(EventRow, CameraRow.name, CameraRow.zone)
        .join(CameraRow, EventRow.camera_id == CameraRow.id)
        .order_by(EventRow.timestamp.asc())
    )


def event_rows(
    session: Session,
    camera_id: UUID | None = None,
    label: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Iterator[tuple[object, ...]]:
    """Una fila por evento."""
    statement = filtered(_base_query(), camera_id, label, since, until)
    for event, name, zone in session.execute(statement).all():
        yield (
            str(event.id),
            iso_utc(event.timestamp),
            name,
            zone,
            round(event.confidence, 4),
            event.person_count,
            event.notified,
            event.frame_width,
            event.frame_height,
            bool(event.snapshot_path),
            bool(event.clip_path),
        )


def object_rows(
    session: Session,
    camera_id: UUID | None = None,
    label: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Iterator[tuple[object, ...]]:
    """Una fila por objeto observado: el formato largo que espera pandas.

    Cuidado al agregar: ``source`` separa las personas que dispararon el evento
    (``trigger``) del barrido completo de la escena (``scene``), que las
    incluye otra vez. Filtra por una de las dos o contarás personas doble.
    """
    statement = filtered(_base_query(), camera_id, label, since, until).options(
        # selectinload evita una consulta por evento para traer sus objetos.
        selectinload(EventRow.objects)
    )
    for event, name, zone in session.execute(statement).all():
        width, height = event.frame_width, event.frame_height
        timestamp = iso_utc(event.timestamp)
        for obj in event.objects:
            area_ratio = (
                round(abs(obj.x2 - obj.x1) * abs(obj.y2 - obj.y1) / (width * height), 6)
                if width and height
                else None
            )
            yield (
                str(event.id),
                timestamp,
                name,
                zone,
                obj.source,
                obj.label,
                round(obj.confidence, 4),
                obj.x1,
                obj.y1,
                obj.x2,
                obj.y2,
                width,
                height,
                norm((obj.x1 + obj.x2) // 2, width),
                norm((obj.y1 + obj.y2) // 2, height),
                area_ratio,
            )
