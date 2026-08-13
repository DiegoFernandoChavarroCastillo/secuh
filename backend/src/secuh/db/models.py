"""Modelos SQLAlchemy (tablas). Mapean hacia/desde las entidades del dominio.

Nota de tipos: se usa ``Uuid(as_uuid=True)`` y ``DateTime(timezone=True)``
para que funcionen igual en PostgreSQL (producción) y SQLite (tests).
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import time as dtime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Time,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from secuh.core.models import (
    Camera,
    CameraState,
    Detection,
    Event,
    Schedule,
    ScheduleMode,
    SourceType,
)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


camera_channels = Table(
    "camera_channels",
    Base.metadata,
    Column(
        "camera_id",
        Uuid(as_uuid=True),
        ForeignKey("cameras.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "channel_id",
        Uuid(as_uuid=True),
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class NotificationChannelRow(Base):
    __tablename__ = "notification_channels"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(16))  # ntfy | telegram
    # Configuración específica del tipo (incluye secretos: jamás sale cruda de la API).
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    cameras: Mapped[list[CameraRow]] = relationship(
        secondary=camera_channels, back_populates="channels"
    )


class CameraRow(Base):
    __tablename__ = "cameras"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    zone: Mapped[str] = mapped_column(String(128), default="")
    source_type: Mapped[str] = mapped_column(String(16))
    source_url: Mapped[str] = mapped_column(String(512))
    state: Mapped[str] = mapped_column(String(16), default=CameraState.DISARMED.value)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60)
    analysis_fps: Mapped[float] = mapped_column(Float, default=5.0)
    schedule_mode: Mapped[str] = mapped_column(
        String(16), default=ScheduleMode.ALWAYS.value, server_default=ScheduleMode.ALWAYS.value
    )
    schedule_start: Mapped[dtime | None] = mapped_column(Time, nullable=True)
    schedule_end: Mapped[dtime | None] = mapped_column(Time, nullable=True)
    # Lista de [x, y] normalizados (0..1); null = frame completo.
    mask_polygon: Mapped[list[list[float]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    # cascade="all, delete-orphan": borrar una cámara borra también sus
    # eventos históricos. Sin esto, SQLAlchemy intenta poner camera_id=NULL
    # en los eventos al borrar la cámara (en vez de borrarlos), lo cual
    # revienta porque esa columna es NOT NULL.
    events: Mapped[list[EventRow]] = relationship(
        back_populates="camera", cascade="all, delete-orphan"
    )
    channels: Mapped[list[NotificationChannelRow]] = relationship(
        secondary=camera_channels, back_populates="cameras"
    )

    def to_domain(self) -> Camera:
        return Camera(
            id=self.id,
            name=self.name,
            zone=self.zone,
            source_type=SourceType(self.source_type),
            source_url=self.source_url,
            state=CameraState(self.state),
            confidence_threshold=self.confidence_threshold,
            cooldown_seconds=self.cooldown_seconds,
            schedule=Schedule(
                mode=ScheduleMode(self.schedule_mode),
                start=self.schedule_start,
                end=self.schedule_end,
            ),
            mask_polygon=(
                tuple((float(x), float(y)) for x, y in self.mask_polygon)
                if self.mask_polygon
                else None
            ),
        )


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    camera_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    person_count: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notified: Mapped[bool] = mapped_column(default=False)

    camera: Mapped[CameraRow] = relationship(back_populates="events")

    @staticmethod
    def from_domain(event: Event) -> EventRow:
        return EventRow(
            id=event.id,
            camera_id=event.camera_id,
            timestamp=event.timestamp,
            confidence=event.max_confidence,
            person_count=len(event.detections),
            snapshot_path=event.snapshot_path,
            clip_path=event.clip_path,
            notified=event.notified,
        )


__all__ = ["Base", "CameraRow", "Detection", "EventRow", "UserRow", "utcnow"]
