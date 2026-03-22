"""Add booking strategy to watch targets.

Revision ID: 20260322_0002
Revises: 20260322_0001
Create Date: 2026-03-22 19:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260322_0002"
down_revision = "20260322_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "watch_targets",
        sa.Column(
            "booking_strategy",
            sa.String(length=48),
            nullable=False,
            server_default="nearest_date_latest_time",
        ),
    )


def downgrade() -> None:
    op.drop_column("watch_targets", "booking_strategy")
