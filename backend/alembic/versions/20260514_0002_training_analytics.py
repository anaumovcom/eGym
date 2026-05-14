"""Add training and analytics persistence.

Revision ID: 20260514_0002
Revises: 20260514_0001
Create Date: 2026-05-14 18:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260514_0002"
down_revision: str | None = "20260514_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_exercise_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_slug", sa.String(length=160), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blacklisted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("working_weight", sa.Float(), nullable=True),
        sa.Column("working_sets", sa.Integer(), nullable=True),
        sa.Column("working_reps", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("calibration_status", sa.String(length=32), nullable=True),
        sa.Column("calibration_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("last_performed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "exercise_slug", name="uq_user_exercise_state"),
    )
    op.create_index("ix_user_exercise_states_user_id", "user_exercise_states", ["user_id"])
    op.create_index("ix_user_exercise_states_exercise_slug", "user_exercise_states", ["exercise_slug"])

    op.create_table(
        "exercise_history_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_slug", sa.String(length=160), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("volume_kg", sa.Float(), nullable=False),
        sa.Column("rpe", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_exercise_history_records_user_id", "exercise_history_records", ["user_id"])
    op.create_index("ix_exercise_history_records_exercise_slug", "exercise_history_records", ["exercise_slug"])

    op.create_table(
        "workout_programs",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("subtitle", sa.String(length=160), nullable=False),
        sa.Column("program_type", sa.String(length=80), nullable=False),
        sa.Column("difficulty", sa.String(length=24), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("exercise_count", sa.Integer(), nullable=False),
        sa.Column("set_count", sa.Integer(), nullable=False),
        sa.Column("focus_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recommended_today", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("structure", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workout_programs_owner_user_id", "workout_programs", ["owner_user_id"])

    op.create_table(
        "workout_schedule_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("subtitle", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("badges", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("exercise_count", sa.Integer(), nullable=True),
        sa.Column("set_count", sa.Integer(), nullable=True),
        sa.Column("readiness_percent", sa.Integer(), nullable=True),
        sa.Column("target_muscles", sa.String(length=255), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("program_id", sa.String(length=80), sa.ForeignKey("workout_programs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recurrence_rule", sa.String(length=80), nullable=True),
        sa.Column("continued_from_date", sa.Date(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workout_schedule_entries_user_id", "workout_schedule_entries", ["user_id"])
    op.create_index("ix_workout_schedule_entries_scheduled_date", "workout_schedule_entries", ["scheduled_date"])
    op.create_index("ix_workout_schedule_entries_program_id", "workout_schedule_entries", ["program_id"])

    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.Enum("quick_start", "planned_workout", "today", "calendar", "programs", "builder", "catalog", "progress", name="runtime_flow_source"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("status", sa.Enum("completed", "partial", "aborted", "in_progress", name="workout_session_status"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feeling", sa.Enum("great", "easy", "strong", "normal", "tired", "hard", "exhausted", name="feeling_level"), nullable=True),
        sa.Column("discomfort", sa.Enum("none", "light", "minor", "moderate", "high", "reduce_next_time", name="discomfort_level"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workout_sessions_user_id", "workout_sessions", ["user_id"])

    op.create_table(
        "exercise_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workout_session_id", sa.Integer(), sa.ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_slug", sa.String(length=160), nullable=False),
        sa.Column("exercise_name", sa.String(length=160), nullable=False),
        sa.Column("exercise_secondary_name", sa.String(length=160), nullable=True),
        sa.Column("kind", sa.Enum("machine", "bodyweight", "timed", "stretch", "group", name="runtime_exercise_kind"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Enum("completed", "partial", "skipped", "aborted", name="exercise_session_status"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_state", sa.String(length=32), nullable=True),
        sa.Column("target_sets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("muscle_targets", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_exercise_sessions_workout_session_id", "exercise_sessions", ["workout_session_id"])
    op.create_index("ix_exercise_sessions_user_id", "exercise_sessions", ["user_id"])
    op.create_index("ix_exercise_sessions_exercise_slug", "exercise_sessions", ["exercise_slug"])

    op.create_table(
        "set_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exercise_session_id", sa.Integer(), sa.ForeignKey("exercise_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("planned_value", sa.Integer(), nullable=False),
        sa.Column("actual_value", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("tempo_label", sa.String(length=80), nullable=False),
        sa.Column("amplitude_percent", sa.Float(), nullable=True),
        sa.Column("rest_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("subjective_effort", sa.Integer(), nullable=True),
        sa.Column("discomfort_level", sa.Integer(), nullable=True),
        sa.Column("sync_label", sa.String(length=80), nullable=True),
        sa.Column("machine_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_set_results_exercise_session_id", "set_results", ["exercise_session_id"])

    op.create_table(
        "muscle_fatigue_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("muscle_id", sa.String(length=80), nullable=False),
        sa.Column("source", sa.Enum("exercise_set", "manual_adjustment", "recovery_snapshot", name="fatigue_event_source"), nullable=False),
        sa.Column("workout_session_id", sa.Integer(), sa.ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("exercise_session_id", sa.Integer(), sa.ForeignKey("exercise_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("set_result_id", sa.Integer(), sa.ForeignKey("set_results.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fatigue_delta", sa.Float(), nullable=False),
        sa.Column("role", sa.Enum("primary", "secondary", "assisting", "stabilizer", name="muscle_role"), nullable=False),
        sa.Column("recovery_half_life_hours", sa.Float(), nullable=False, server_default="24"),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_muscle_fatigue_events_user_id", "muscle_fatigue_events", ["user_id"])
    op.create_index("ix_muscle_fatigue_events_muscle_id", "muscle_fatigue_events", ["muscle_id"])
    op.create_index("ix_muscle_fatigue_events_workout_session_id", "muscle_fatigue_events", ["workout_session_id"])
    op.create_index("ix_muscle_fatigue_events_exercise_session_id", "muscle_fatigue_events", ["exercise_session_id"])
    op.create_index("ix_muscle_fatigue_events_set_result_id", "muscle_fatigue_events", ["set_result_id"])

    op.create_table(
        "muscle_fatigue_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("muscle_id", sa.String(length=80), nullable=False),
        sa.Column("fatigue_score", sa.Float(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovery_half_life_hours", sa.Float(), nullable=False, server_default="24"),
        sa.Column("last_load_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_muscle_fatigue_snapshots_user_id", "muscle_fatigue_snapshots", ["user_id"])
    op.create_index("ix_muscle_fatigue_snapshots_muscle_id", "muscle_fatigue_snapshots", ["muscle_id"])

    op.create_table(
        "progress_photos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workout_session_id", sa.Integer(), sa.ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mode", sa.Enum("pre_workout", "post_workout", "manual", name="runtime_photo_mode"), nullable=False),
        sa.Column("view", sa.Enum("front", "side", "back", name="runtime_photo_view"), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_path", sa.String(length=255), nullable=False),
        sa.Column("thumbnail_path", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_progress_photos_user_id", "progress_photos", ["user_id"])
    op.create_index("ix_progress_photos_workout_session_id", "progress_photos", ["workout_session_id"])


def downgrade() -> None:
    op.drop_index("ix_progress_photos_workout_session_id", table_name="progress_photos")
    op.drop_index("ix_progress_photos_user_id", table_name="progress_photos")
    op.drop_table("progress_photos")

    op.drop_index("ix_muscle_fatigue_snapshots_muscle_id", table_name="muscle_fatigue_snapshots")
    op.drop_index("ix_muscle_fatigue_snapshots_user_id", table_name="muscle_fatigue_snapshots")
    op.drop_table("muscle_fatigue_snapshots")

    op.drop_index("ix_muscle_fatigue_events_set_result_id", table_name="muscle_fatigue_events")
    op.drop_index("ix_muscle_fatigue_events_exercise_session_id", table_name="muscle_fatigue_events")
    op.drop_index("ix_muscle_fatigue_events_workout_session_id", table_name="muscle_fatigue_events")
    op.drop_index("ix_muscle_fatigue_events_muscle_id", table_name="muscle_fatigue_events")
    op.drop_index("ix_muscle_fatigue_events_user_id", table_name="muscle_fatigue_events")
    op.drop_table("muscle_fatigue_events")

    op.drop_index("ix_set_results_exercise_session_id", table_name="set_results")
    op.drop_table("set_results")

    op.drop_index("ix_exercise_sessions_exercise_slug", table_name="exercise_sessions")
    op.drop_index("ix_exercise_sessions_user_id", table_name="exercise_sessions")
    op.drop_index("ix_exercise_sessions_workout_session_id", table_name="exercise_sessions")
    op.drop_table("exercise_sessions")

    op.drop_index("ix_workout_sessions_user_id", table_name="workout_sessions")
    op.drop_table("workout_sessions")

    op.drop_index("ix_workout_schedule_entries_program_id", table_name="workout_schedule_entries")
    op.drop_index("ix_workout_schedule_entries_scheduled_date", table_name="workout_schedule_entries")
    op.drop_index("ix_workout_schedule_entries_user_id", table_name="workout_schedule_entries")
    op.drop_table("workout_schedule_entries")

    op.drop_index("ix_workout_programs_owner_user_id", table_name="workout_programs")
    op.drop_table("workout_programs")

    op.drop_index("ix_exercise_history_records_exercise_slug", table_name="exercise_history_records")
    op.drop_index("ix_exercise_history_records_user_id", table_name="exercise_history_records")
    op.drop_table("exercise_history_records")

    op.drop_index("ix_user_exercise_states_exercise_slug", table_name="user_exercise_states")
    op.drop_index("ix_user_exercise_states_user_id", table_name="user_exercise_states")
    op.drop_table("user_exercise_states")