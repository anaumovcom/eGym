"""Store LOAD direction independently of the exercise start point.

Revision ID: 20261016_0010
Revises: 20261014_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261016_0010"
down_revision: str | None = "20261014_0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("exercise_calibrations") as batch:
        batch.add_column(sa.Column("load_direction", sa.String(length=16), nullable=False, server_default="down"))


def downgrade() -> None:
    with op.batch_alter_table("exercise_calibrations") as batch:
        batch.drop_column("load_direction")