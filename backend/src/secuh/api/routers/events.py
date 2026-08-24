"""Listado de eventos, descarga de evidencia y exportación (solo autenticado).

La evidencia se sirve por endpoint autenticado, nunca como directorio
estático: las capturas de vigilancia no deben quedar accesibles sin sesión.
La exportación se rige por la misma regla — es el histórico entero en un
archivo, así que si acaso merece *más* cuidado, no menos.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from secuh.api.deps import SessionDep, get_current_user
from secuh.api.schemas import EventDetailOut, EventOut, EventPage, SceneObjectOut
from secuh.db.export import (
    EVENT_COLUMNS,
    OBJECT_COLUMNS,
    csv_safe,
    event_rows,
    filtered,
    object_rows,
)
from secuh.db.models import CameraRow, EventObjectRow, EventRow

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(get_current_user)])


def _object_counts(row: EventRow) -> dict[str, int]:
    """Conteo por clase del barrido de escena.

    Solo cuenta las filas ``scene``: las ``trigger`` son las mismas personas
    vistas por el pipeline, y sumarlas las contaría dos veces.
    """
    counts: dict[str, int] = {}
    for obj in row.objects:
        if obj.source != EventObjectRow.SOURCE_SCENE:
            continue
        counts[obj.label] = counts.get(obj.label, 0) + 1
    return counts


def _to_out(row: EventRow, camera_name: str) -> EventOut:
    return EventOut(
        id=row.id,
        camera_id=row.camera_id,
        camera_name=camera_name,
        timestamp=row.timestamp,
        confidence=row.confidence,
        person_count=row.person_count,
        notified=row.notified,
        has_snapshot=bool(row.snapshot_path),
        has_clip=bool(row.clip_path),
        object_counts=_object_counts(row),
    )


@router.get("", response_model=EventPage)
def list_events(
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    camera_id: UUID | None = None,
    label: str | None = Query(default=None, max_length=32),
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> EventPage:
    count_stmt = filtered(select(EventRow), camera_id, label, since, until)
    total = session.execute(select(func.count()).select_from(count_stmt.subquery())).scalar_one()
    rows = session.execute(
        filtered(
            select(EventRow, CameraRow.name).join(CameraRow, EventRow.camera_id == CameraRow.id),
            camera_id,
            label,
            since,
            until,
        )
        # selectinload evita una consulta por evento para traer sus objetos.
        .options(selectinload(EventRow.objects))
        .order_by(EventRow.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return EventPage(
        items=[_to_out(event, name) for event, name in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _get_or_404(session: SessionDep, event_id: UUID) -> EventRow:
    row = session.get(EventRow, event_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento no encontrado")
    return row


# --------------------------------------------------------------- exportación
#
# Las columnas y el armado de filas viven en ``secuh.db.export``, compartidos
# con ``scripts/export_dataset.py``: si estuvieran aquí, los dos exports
# acabarían divergiendo.


def _csv_stream(header: tuple[str, ...], rows: Iterator[tuple[object, ...]]) -> Iterator[str]:
    """Genera el CSV fila a fila: el histórico no se materializa en memoria."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow([csv_safe(value) for value in row])
        yield buffer.getvalue()


def _csv_response(
    filename: str, header: tuple[str, ...], rows: Iterator[tuple[object, ...]]
) -> StreamingResponse:
    return StreamingResponse(
        _csv_stream(header, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Las rutas de exportación se declaran **antes** que ``/{event_id}``: FastAPI
# resuelve por orden de registro, y si no, "export.csv" se intentaría leer como
# un UUID de evento.
@router.get("/export.csv")
def export_events_csv(
    session: SessionDep,
    camera_id: UUID | None = None,
    label: str | None = Query(default=None, max_length=32),
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> StreamingResponse:
    """Un evento por fila."""
    return _csv_response(
        "secuh-eventos.csv",
        EVENT_COLUMNS,
        event_rows(session, camera_id=camera_id, label=label, since=since, until=until),
    )


@router.get("/objects.csv")
def export_objects_csv(
    session: SessionDep,
    camera_id: UUID | None = None,
    label: str | None = Query(default=None, max_length=32),
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> StreamingResponse:
    """Un objeto por fila: el formato largo que espera pandas."""
    return _csv_response(
        "secuh-objetos.csv",
        OBJECT_COLUMNS,
        object_rows(session, camera_id=camera_id, label=label, since=since, until=until),
    )


@router.get("/{event_id}", response_model=EventDetailOut)
def get_event(event_id: UUID, session: SessionDep) -> EventDetailOut:
    row = _get_or_404(session, event_id)
    base = _to_out(row, row.camera.name)
    return EventDetailOut(
        **base.model_dump(),
        frame_width=row.frame_width,
        frame_height=row.frame_height,
        has_raw_snapshot=bool(row.snapshot_raw_path),
        objects=[
            SceneObjectOut(
                label=obj.label,
                confidence=obj.confidence,
                x1=obj.x1,
                y1=obj.y1,
                x2=obj.x2,
                y2=obj.y2,
            )
            for obj in row.objects
            if obj.source == EventObjectRow.SOURCE_SCENE
        ],
    )


def _serve(path_str: str | None, media_type: str) -> FileResponse:
    if not path_str or not Path(path_str).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidencia no disponible (¿expiró?)")
    return FileResponse(path_str, media_type=media_type)


@router.get("/{event_id}/snapshot")
def get_snapshot(event_id: UUID, session: SessionDep) -> FileResponse:
    return _serve(_get_or_404(session, event_id).snapshot_path, "image/jpeg")


@router.get("/{event_id}/snapshot/raw")
def get_raw_snapshot(event_id: UUID, session: SessionDep) -> FileResponse:
    """La captura sin cajas dibujadas, para reprocesarla con otro modelo."""
    return _serve(_get_or_404(session, event_id).snapshot_raw_path, "image/jpeg")


@router.get("/{event_id}/clip")
def get_clip(event_id: UUID, session: SessionDep) -> FileResponse:
    return _serve(_get_or_404(session, event_id).clip_path, "video/mp4")
