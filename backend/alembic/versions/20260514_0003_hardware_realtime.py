"""Add hardware calibration and diagnostics persistence.

Revision ID: 20260514_0003
Revises: 20260514_0002
Create Date: 2026-05-14 21:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260514_0003"
down_revision: str | None = "20260514_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


OLD_AUDIT_ACTION = sa.Enum(
    "user_selected",
    "emergency_stop",
    "settings_changed",
    name="audit_action",
)

NEW_AUDIT_ACTION = sa.Enum(
    "user_selected",
    "emergency_stop",
    "settings_changed",
    "hardware_command",
    "calibration_saved",
    "calibration_deleted",
    "zero_position_reset",
    "diagnostics_run",
    name="audit_action",
)


def upgrade() -> None:
    op.create_table(
        "exercise_calibrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_slug", sa.String(length=160), nullable=False),
        sa.Column("lower_point_mm", sa.Float(), nullable=False),
        sa.Column("upper_point_mm", sa.Float(), nullable=False),
        sa.Column("zero_position_mm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("movement_range_confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("calibration_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "exercise_slug", name="uq_exercise_calibration_user_slug"),
    )
    op.create_index("ix_exercise_calibrations_user_id", "exercise_calibrations", ["user_id"])
    op.create_index("ix_exercise_calibrations_exercise_slug", "exercise_calibrations", ["exercise_slug"])

    op.create_table(
        "hardware_diagnostic_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hardware_diagnostic_records_category", "hardware_diagnostic_records", ["category"])
    op.create_index("ix_hardware_diagnostic_records_ran_at", "hardware_diagnostic_records", ["ran_at"])

    with op.batch_alter_table("audit_log", recreate="always") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=OLD_AUDIT_ACTION,
            type_=NEW_AUDIT_ACTION,
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_log", recreate="always") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=NEW_AUDIT_ACTION,
            type_=OLD_AUDIT_ACTION,
            existing_nullable=False,
        )

    op.drop_index("ix_hardware_diagnostic_records_ran_at", table_name="hardware_diagnostic_records")
    op.drop_index("ix_hardware_diagnostic_records_category", table_name="hardware_diagnostic_records")
    op.drop_table("hardware_diagnostic_records")

    op.drop_index("ix_exercise_calibrations_exercise_slug", table_name="exercise_calibrations")
    op.drop_index("ix_exercise_calibrations_user_id", table_name="exercise_calibrations")
    op.drop_table("exercise_calibrations")
