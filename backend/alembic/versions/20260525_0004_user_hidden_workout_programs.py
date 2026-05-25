"""Add per-user hidden workout programs.

Revision ID: 20260525_0004
Revises: 20260514_0003
Create Date: 2026-05-25 16:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260525_0004"
down_revision: str | None = "20260514_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_hidden_workout_programs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("program_id", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("user_id", "program_id", name="uq_user_hidden_workout_program"),
    )
    op.create_index("ix_user_hidden_workout_programs_user_id", "user_hidden_workout_programs", ["user_id"])
    op.create_index("ix_user_hidden_workout_programs_program_id", "user_hidden_workout_programs", ["program_id"])


def downgrade() -> None:
    op.drop_index("ix_user_hidden_workout_programs_program_id", table_name="user_hidden_workout_programs")
    op.drop_index("ix_user_hidden_workout_programs_user_id", table_name="user_hidden_workout_programs")
    op.drop_table("user_hidden_workout_programs")