"""CRUD de cámaras y armado/desarmado.

El supervisor reconcilia los cambios en ≤ ``supervisor_poll_seconds``:
la API solo escribe el estado deseado en la BD.
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select

from secuh.api.deps import SessionDep, SupervisorDep, get_current_user
from secuh.api.schemas import CameraIn, CameraOut, CameraPatch
from secuh.core.models import CameraState
from secuh.db.models import CameraRow, NotificationChannelRow
from secuh.runtime.supervisor import CameraSupervisor
from secuh.video.source import redact_url

router = APIRouter(prefix="/cameras", tags=["cameras"], dependencies=[Depends(get_current_user)])


def to_out(row: CameraRow, supervisor: CameraSupervisor) -> CameraOut:
    return CameraOut(
        id=row.id,
        name=row.name,
        zone=row.zone,
        source_type=row.source_type,  # type: ignore[arg-type]
        source_url_redacted=redact_url(row.source_url),
        state=CameraState(row.state),
        confidence_threshold=row.confidence_threshold,
        cooldown_seconds=row.cooldown_seconds,
        analysis_fps=row.analysis_fps,
        schedule_mode=row.schedule_mode,  # type: ignore[arg-type]
        schedule_start=row.schedule_start,
        schedule_end=row.schedule_end,
        mask_polygon=(
            [(float(x), float(y)) for x, y in row.mask_polygon] if row.mask_polygon else None
        ),
        channel_ids=[channel.id for channel in row.channels],
        online=supervisor.is_online(row.id),
        metrics=supervisor.metrics(row.id),
    )


def _resolve_channels(session: SessionDep, channel_ids: list[UUID]) -> list[NotificationChannelRow]:
    channels = (
        session.execute(
            select(NotificationChannelRow).where(NotificationChannelRow.id.in_(channel_ids))
        )
        .scalars()
        .all()
    )
    if len(channels) != len(set(channel_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Algún canal no existe")
    return list(channels)


def _get_or_404(session: SessionDep, camera_id: UUID) -> CameraRow:
    row = session.get(CameraRow, camera_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cámara no encontrada")
    return row


@router.get("", response_model=list[CameraOut])
def list_cameras(session: SessionDep, supervisor: SupervisorDep) -> list[CameraOut]:
    rows = session.execute(select(CameraRow).order_by(CameraRow.created_at)).scalars().all()
    return [to_out(row, supervisor) for row in rows]


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
def create_camera(body: CameraIn, session: SessionDep, supervisor: SupervisorDep) -> CameraOut:
    exists = session.execute(
        select(CameraRow).where(CameraRow.name == body.name)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cámara con ese nombre")
    row = CameraRow(
        name=body.name,
        zone=body.zone,
        source_type=body.source_type.value,
        source_url=body.source_url,
        confidence_threshold=body.confidence_threshold,
        cooldown_seconds=body.cooldown_seconds,
        analysis_fps=body.analysis_fps,
        schedule_mode=body.schedule_mode.value,
        schedule_start=body.schedule_start,
        schedule_end=body.schedule_end,
        mask_polygon=[[x, y] for x, y in body.mask_polygon] if body.mask_polygon else None,
    )
    row.channels = _resolve_channels(session, body.channel_ids)
    session.add(row)
    session.commit()
    session.refresh(row)
    return to_out(row, supervisor)


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(
    camera_id: UUID, body: CameraPatch, session: SessionDep, supervisor: SupervisorDep
) -> CameraOut:
    row = _get_or_404(session, camera_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] != row.name:
        duplicate = session.execute(
            select(CameraRow).where(CameraRow.name == changes["name"])
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cámara con ese nombre")
    if "channel_ids" in changes:
        row.channels = _resolve_channels(session, changes.pop("channel_ids"))
    for field, value in changes.items():
        if isinstance(value, Enum):
            value = value.value
        if field == "mask_polygon" and value is not None:
            value = [[x, y] for x, y in value]
        setattr(row, field, value)
    session.commit()
    session.refresh(row)
    return to_out(row, supervisor)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(camera_id: UUID, session: SessionDep) -> None:
    row = _get_or_404(session, camera_id)
    session.delete(row)
    session.commit()


@router.post("/{camera_id}/arm", response_model=CameraOut)
def arm_camera(camera_id: UUID, session: SessionDep, supervisor: SupervisorDep) -> CameraOut:
    row = _get_or_404(session, camera_id)
    row.state = CameraState.ARMED.value
    session.commit()
    session.refresh(row)
    return to_out(row, supervisor)


@router.post("/{camera_id}/disarm", response_model=CameraOut)
def disarm_camera(camera_id: UUID, session: SessionDep, supervisor: SupervisorDep) -> CameraOut:
    row = _get_or_404(session, camera_id)
    row.state = CameraState.DISARMED.value
    session.commit()
    session.refresh(row)
    return to_out(row, supervisor)


@router.get("/{camera_id}/preview")
def camera_preview(camera_id: UUID, session: SessionDep, supervisor: SupervisorDep) -> Response:
    """Frame actual de la cámara (para el editor de zona del panel).

    Si la cámara está armada usa el último frame del worker; si no, abre la
    fuente un instante para capturar uno.
    """
    row = _get_or_404(session, camera_id)
    jpeg = supervisor.preview_jpeg(row.id, row.source_url)
    if jpeg is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "La cámara no entrega señal en este momento"
        )
    return Response(content=jpeg, media_type="image/jpeg")
