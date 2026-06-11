"""Persist runtime exercise strength mode.

Revision ID: 20260526_0005
Revises: 20260525_0004
Create Date: 2026-05-26 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260526_0005"
down_revision: str | None = "20260525_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("exercise_sessions", sa.Column("training_mode", sa.String(length=64), nullable=True))
    op.add_column("exercise_sessions", sa.Column("training_day_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("exercise_sessions", "training_day_type")
    op.drop_column("exercise_sessions", "training_mode")
