from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    DiscomfortLevel,
    ExerciseSessionStatus,
    FatigueEventSource,
    FeelingLevel,
    MuscleRole,
    RuntimeExerciseKind,
    RuntimeFlowSource,
    RuntimePhotoMode,
    RuntimePhotoView,
    WorkoutSessionStatus,
)


class WorkoutSession(TimestampMixin, Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[RuntimeFlowSource] = mapped_column(SqlEnum(RuntimeFlowSource, name="runtime_flow_source"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[WorkoutSessionStatus] = mapped_column(SqlEnum(WorkoutSessionStatus, name="workout_session_status"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feeling: Mapped[FeelingLevel | None] = mapped_column(SqlEnum(FeelingLevel, name="feeling_level"), nullable=True)
    discomfort: Mapped[DiscomfortLevel | None] = mapped_column(SqlEnum(DiscomfortLevel, name="discomfort_level"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    exercise_sessions: Mapped[list["ExerciseSession"]] = relationship(back_populates="workout_session", cascade="all, delete-orphan")
    photos: Mapped[list["ProgressPhoto"]] = relationship(back_populates="workout_session")


class ExerciseSession(TimestampMixin, Base):
    __tablename__ = "exercise_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workout_session_id: Mapped[int | None] = mapped_column(ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise_slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    exercise_name: Mapped[str] = mapped_column(String(160), nullable=False)
    exercise_secondary_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    kind: Mapped[RuntimeExerciseKind] = mapped_column(SqlEnum(RuntimeExerciseKind, name="runtime_exercise_kind"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[ExerciseSessionStatus] = mapped_column(SqlEnum(ExerciseSessionStatus, name="exercise_session_status"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calibration_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_sets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    muscle_targets: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)

    workout_session: Mapped[WorkoutSession | None] = relationship(back_populates="exercise_sessions")
    set_results: Mapped[list["SetResult"]] = relationship(back_populates="exercise_session", cascade="all, delete-orphan")


class SetResult(TimestampMixin, Base):
    __tablename__ = "set_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exercise_session_id: Mapped[int] = mapped_column(ForeignKey("exercise_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_value: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_value: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tempo_label: Mapped[str] = mapped_column(String(80), nullable=False)
    amplitude_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    rest_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subjective_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discomfort_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sync_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    machine_metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    exercise_session: Mapped[ExerciseSession] = relationship(back_populates="set_results")


class MuscleFatigueEvent(Base):
    __tablename__ = "muscle_fatigue_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    muscle_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source: Mapped[FatigueEventSource] = mapped_column(SqlEnum(FatigueEventSource, name="fatigue_event_source"), nullable=False)
    workout_session_id: Mapped[int | None] = mapped_column(ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    exercise_session_id: Mapped[int | None] = mapped_column(ForeignKey("exercise_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    set_result_id: Mapped[int | None] = mapped_column(ForeignKey("set_results.id", ondelete="SET NULL"), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fatigue_delta: Mapped[float] = mapped_column(Float, nullable=False)
    role: Mapped[MuscleRole] = mapped_column(SqlEnum(MuscleRole, name="muscle_role"), nullable=False)
    recovery_half_life_hours: Mapped[float] = mapped_column(Float, nullable=False, default=24.0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class MuscleFatigueSnapshot(Base):
    __tablename__ = "muscle_fatigue_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    muscle_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    fatigue_score: Mapped[float] = mapped_column(Float, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recovery_half_life_hours: Mapped[float] = mapped_column(Float, nullable=False, default=24.0)
    last_load_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProgressPhoto(TimestampMixin, Base):
    __tablename__ = "progress_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workout_session_id: Mapped[int | None] = mapped_column(ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    mode: Mapped[RuntimePhotoMode] = mapped_column(SqlEnum(RuntimePhotoMode, name="runtime_photo_mode"), nullable=False)
    view: Mapped[RuntimePhotoView] = mapped_column(SqlEnum(RuntimePhotoView, name="runtime_photo_view"), nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail_path: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    workout_session: Mapped[WorkoutSession | None] = relationship(back_populates="photos")