"""Store the start point of a set (lower / upper point of the bar range) per user and exercise.

Revision ID: 20261014_0009
Revises: 20261008_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0009"
down_revision: str | None = "20261008_0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("exercise_calibrations") as batch:
        batch.add_column(sa.Column("start_point", sa.String(length=16), nullable=False, server_default="lower"))


def downgrade() -> None:
    with op.batch_alter_table("exercise_calibrations") as batch:
        batch.drop_column("start_point")
