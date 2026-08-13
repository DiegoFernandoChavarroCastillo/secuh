"""CRUD de canales de notificación + botón de prueba.

La configuración de un canal contiene secretos (tokens): entra por la API
pero solo sale redactada.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from secuh.api.deps import SessionDep, get_current_user
from secuh.api.schemas import ChannelIn, ChannelOut, ChannelPatch, ChannelTestResult
from secuh.core.models import Notification
from secuh.core.ports import NotificationError
from secuh.db.models import NotificationChannelRow
from secuh.notifications.factory import ChannelConfigError, build_notifier, redact_config

router = APIRouter(prefix="/channels", tags=["channels"], dependencies=[Depends(get_current_user)])


def to_out(row: NotificationChannelRow) -> ChannelOut:
    return ChannelOut(
        id=row.id,
        name=row.name,
        type=row.type,
        active=row.active,
        config_redacted=redact_config(row.type, row.config),
    )


def _get_or_404(session: SessionDep, channel_id: UUID) -> NotificationChannelRow:
    row = session.get(NotificationChannelRow, channel_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Canal no encontrado")
    return row


def _validate_config(channel_type: str, config: dict[str, str]) -> None:
    try:
        build_notifier(channel_type, config)
    except ChannelConfigError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("", response_model=list[ChannelOut])
def list_channels(session: SessionDep) -> list[ChannelOut]:
    rows = (
        session.execute(select(NotificationChannelRow).order_by(NotificationChannelRow.created_at))
        .scalars()
        .all()
    )
    return [to_out(row) for row in rows]


@router.post("", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
def create_channel(body: ChannelIn, session: SessionDep) -> ChannelOut:
    exists = session.execute(
        select(NotificationChannelRow).where(NotificationChannelRow.name == body.name)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un canal con ese nombre")
    _validate_config(body.type, body.config)
    row = NotificationChannelRow(
        name=body.name, type=body.type, config=body.config, active=body.active
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return to_out(row)


@router.patch("/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: UUID, body: ChannelPatch, session: SessionDep) -> ChannelOut:
    row = _get_or_404(session, channel_id)
    changes = body.model_dump(exclude_unset=True)
    if "config" in changes:
        _validate_config(row.type, changes["config"])
    if "name" in changes and changes["name"] != row.name:
        duplicate = session.execute(
            select(NotificationChannelRow).where(NotificationChannelRow.name == changes["name"])
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un canal con ese nombre")
    for field, value in changes.items():
        setattr(row, field, value)
    session.commit()
    session.refresh(row)
    return to_out(row)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: UUID, session: SessionDep) -> None:
    row = _get_or_404(session, channel_id)
    session.delete(row)
    session.commit()


@router.post("/{channel_id}/test", response_model=ChannelTestResult)
def test_channel(channel_id: UUID, session: SessionDep) -> ChannelTestResult:
    """Envía una notificación de prueba real por el canal.

    Clave para el modelo producto+servicio: validar un canal en sitio antes
    de confiarle las alertas del negocio.
    """
    row = _get_or_404(session, channel_id)
    try:
        notifier = build_notifier(row.type, row.config)
        notifier.send(
            Notification(
                title="secuh: prueba de canal",
                message=f"El canal '{row.name}' está configurado correctamente.",
            )
        )
    except (ChannelConfigError, NotificationError) as exc:
        return ChannelTestResult(ok=False, detail=str(exc))
    return ChannelTestResult(ok=True)
