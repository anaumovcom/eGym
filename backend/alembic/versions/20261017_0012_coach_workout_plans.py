"""Optional declared workout-plan baselines (no runtime schema dependency).

Revision ID: 20261017_0012
Revises: 20261016_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261017_0012"
down_revision: str | None = "20261016_0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coach_workout_plans",
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workout_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(120), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("current", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("coach_workout_plans")