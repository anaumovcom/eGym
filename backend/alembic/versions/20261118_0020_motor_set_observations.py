"""Passive observations of exercise mechanics for calibration review."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_0020"
down_revision = "20261104_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("motor_set_observations"):
        return
    op.create_table(
        "motor_set_observations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("exercise_slug", sa.String(160)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
    )
    op.create_index("ix_motor_set_observations_started_at", "motor_set_observations", ["started_at"])


def downgrade() -> None:
    op.drop_table("motor_set_observations")
