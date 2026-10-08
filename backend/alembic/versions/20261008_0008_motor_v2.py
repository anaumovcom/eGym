"""Motor control v2 storage: machine profiles, calibration runs, exercise feel profiles.

Revision ID: 20261008_0008
Revises: 20261007_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261008_0008"
down_revision: str | None = "20261007_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "machine_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("source_run_id", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
    )
    op.create_index("ix_machine_profiles_active", "machine_profiles", ["active"])
    op.create_table(
        "calibration_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("procedure", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("estimate", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("samples_path", sa.String(length=255), nullable=True),
        sa.Column("operator_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_calibration_runs_procedure", "calibration_runs", ["procedure"])
    op.create_table(
        "exercise_feel_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("exercise_slug", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "exercise_slug", name="uq_exercise_feel_user_slug"),
    )
    op.create_index("ix_exercise_feel_profiles_user_id", "exercise_feel_profiles", ["user_id"])
    op.create_index("ix_exercise_feel_profiles_exercise_slug", "exercise_feel_profiles", ["exercise_slug"])


def downgrade() -> None:
    op.drop_table("exercise_feel_profiles")
    op.drop_table("calibration_runs")
    op.drop_table("machine_profiles")
