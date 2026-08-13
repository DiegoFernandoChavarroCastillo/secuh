"""Horarios de vigilancia y zona de detección por cámara.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column("schedule_mode", sa.String(length=16), nullable=False, server_default="always"),
    )
    op.add_column("cameras", sa.Column("schedule_start", sa.Time(), nullable=True))
    op.add_column("cameras", sa.Column("schedule_end", sa.Time(), nullable=True))
    op.add_column("cameras", sa.Column("mask_polygon", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "mask_polygon")
    op.drop_column("cameras", "schedule_end")
    op.drop_column("cameras", "schedule_start")
    op.drop_column("cameras", "schedule_mode")
