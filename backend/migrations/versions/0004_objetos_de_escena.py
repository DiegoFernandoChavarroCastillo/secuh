"""Objetos observados en la escena de cada evento (Fase 7).

Añade ``event_objects`` (una fila por objeto detectado, formato largo para
análisis) y las columnas de contexto que necesita: la resolución del frame para
poder normalizar las cajas, y la ruta de la captura sin anotar.

Las columnas nuevas de ``events`` son nullable a propósito: los eventos
anteriores a esta migración no tienen esos datos y no hay forma honesta de
inventarlos. Un NULL dice "no se sabe", que es exactamente lo que pasa.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("snapshot_raw_path", sa.String(length=512), nullable=True))
    op.add_column("events", sa.Column("frame_width", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("frame_height", sa.Integer(), nullable=True))

    op.create_table(
        "event_objects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("x1", sa.Integer(), nullable=False),
        sa.Column("y1", sa.Integer(), nullable=False),
        sa.Column("x2", sa.Integer(), nullable=False),
        sa.Column("y2", sa.Integer(), nullable=False),
    )
    op.create_index("ix_event_objects_event_id", "event_objects", ["event_id"])
    op.create_index("ix_event_objects_label", "event_objects", ["label"])


def downgrade() -> None:
    op.drop_index("ix_event_objects_label", table_name="event_objects")
    op.drop_index("ix_event_objects_event_id", table_name="event_objects")
    op.drop_table("event_objects")
    op.drop_column("events", "frame_height")
    op.drop_column("events", "frame_width")
    op.drop_column("events", "snapshot_raw_path")
