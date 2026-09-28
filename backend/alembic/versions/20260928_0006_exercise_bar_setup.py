"""Store the bar setup type and fixed height per user and exercise.

Revision ID: 20260928_0006
Revises: 20260526_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_0006"
down_revision: str | None = "20260526_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("exercise_calibrations") as batch:
        batch.add_column(sa.Column("setup_type", sa.String(length=32), nullable=False, server_default="bar_range"))
        batch.add_column(sa.Column("fixed_position_mm", sa.Float(), nullable=True))
        batch.alter_column("lower_point_mm", existing_type=sa.Float(), nullable=True)
        batch.alter_column("upper_point_mm", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM exercise_calibrations WHERE setup_type = 'fixed_position'")
    with op.batch_alter_table("exercise_calibrations") as batch:
        batch.alter_column("lower_point_mm", existing_type=sa.Float(), nullable=False)
        batch.alter_column("upper_point_mm", existing_type=sa.Float(), nullable=False)
        batch.drop_column("fixed_position_mm")
        batch.drop_column("setup_type")