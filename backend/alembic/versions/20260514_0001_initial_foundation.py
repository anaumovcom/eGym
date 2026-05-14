"""Initial backend foundation schema.

Revision ID: 20260514_0001
Revises:
Create Date: 2026-05-14 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260514_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.Enum("member", "coach", "admin", "service", name="access_role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("readiness_percent", sa.Integer(), nullable=False),
        sa.Column("last_workout", sa.Text(), nullable=False),
        sa.Column("today_focus", sa.Text(), nullable=False),
        sa.Column("week_progress", sa.Text(), nullable=False),
        sa.Column("accent", sa.Enum("gold", "green", name="user_accent"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("photo_url", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_goals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal_type", sa.Enum("strength", "body_composition", "habit", name="goal_type"), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("target_unit", sa.String(length=32), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_goals_user_id", "user_goals", ["user_id"])
    op.create_table(
        "body_measurements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("body_fat_percent", sa.Numeric(4, 2), nullable=True),
        sa.Column("chest_cm", sa.Numeric(5, 2), nullable=True),
        sa.Column("waist_cm", sa.Numeric(5, 2), nullable=True),
        sa.Column("hips_cm", sa.Numeric(5, 2), nullable=True),
    )
    op.create_index("ix_body_measurements_user_id", "body_measurements", ["user_id"])
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_app_settings_key", "app_settings", ["key"])
    op.create_index("ix_app_settings_user_id", "app_settings", ["user_id"])
    op.create_table(
        "machine_status_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scenario_name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("machine_state", sa.Enum("ready", "warning", "blocked", name="machine_state"), nullable=False),
        sa.Column("machine_label", sa.String(length=160), nullable=False),
        sa.Column("calibration", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "drive_status_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "machine_status_id",
            sa.Integer(),
            sa.ForeignKey("machine_status_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("drive_state", sa.Enum("connected", "warning", "error", name="drive_state"), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=True),
    )
    op.create_table(
        "safety_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "machine_status_id",
            sa.Integer(),
            sa.ForeignKey("machine_status_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "safety_state", sa.Enum("enabled", "disabled", "emergency_stop", name="safety_state"), nullable=False
        ),
        sa.Column("severity", sa.Enum("info", "warning", "critical", name="safety_severity"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "action",
            sa.Enum("user_selected", "emergency_stop", "settings_changed", name="audit_action"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.Enum("info", "warning", "critical", name="audit_severity"), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("safety_events")
    op.drop_table("drive_status_snapshots")
    op.drop_table("machine_status_snapshots")
    op.drop_index("ix_app_settings_user_id", table_name="app_settings")
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.drop_table("app_settings")
    op.drop_index("ix_body_measurements_user_id", table_name="body_measurements")
    op.drop_table("body_measurements")
    op.drop_index("ix_user_goals_user_id", table_name="user_goals")
    op.drop_table("user_goals")
    op.drop_table("user_profiles")
    op.drop_table("users")
