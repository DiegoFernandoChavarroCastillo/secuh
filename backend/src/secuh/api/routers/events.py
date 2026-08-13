"""Listado de eventos y descarga de evidencia (solo autenticado).

La evidencia se sirve por endpoint autenticado, nunca como directorio
estático: las capturas de vigilancia no deben quedar accesibles sin sesión.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from secuh.api.deps import SessionDep, get_current_user
from secuh.api.schemas import EventOut, EventPage
from secuh.db.models import CameraRow, EventRow

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(get_current_user)])


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
    )


@router.get("", response_model=EventPage)
def list_events(
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    camera_id: UUID | None = None,
) -> EventPage:
    filters = [EventRow.camera_id == camera_id] if camera_id is not None else []
    total = session.execute(select(func.count()).select_from(EventRow).where(*filters)).scalar_one()
    rows = session.execute(
        select(EventRow, CameraRow.name)
        .join(CameraRow, EventRow.camera_id == CameraRow.id)
        .where(*filters)
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


def _serve(path_str: str | None, media_type: str) -> FileResponse:
    if not path_str or not Path(path_str).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidencia no disponible (¿expiró?)")
    return FileResponse(path_str, media_type=media_type)


@router.get("/{event_id}/snapshot")
def get_snapshot(event_id: UUID, session: SessionDep) -> FileResponse:
    return _serve(_get_or_404(session, event_id).snapshot_path, "image/jpeg")


@router.get("/{event_id}/clip")
def get_clip(event_id: UUID, session: SessionDep) -> FileResponse:
    return _serve(_get_or_404(session, event_id).clip_path, "video/mp4")
