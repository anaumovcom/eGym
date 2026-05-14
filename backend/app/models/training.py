from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserExerciseState(TimestampMixin, Base):
    __tablename__ = "user_exercise_states"
    __table_args__ = (UniqueConstraint("user_id", "exercise_slug", name="uq_user_exercise_state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise_slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blacklisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    working_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    working_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    working_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calibration_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calibration_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    last_performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExerciseHistoryRecord(Base):
    __tablename__ = "exercise_history_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise_slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_kg: Mapped[float] = mapped_column(Float, nullable=False)
    rpe: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String(255), nullable=False)


class WorkoutProgram(TimestampMixin, Base):
    __tablename__ = "workout_programs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="template")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(160), nullable=False)
    program_type: Mapped[str] = mapped_column(String(80), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(24), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    exercise_count: Mapped[int] = mapped_column(Integer, nullable=False)
    set_count: Mapped[int] = mapped_column(Integer, nullable=False)
    focus_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_today: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    structure: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WorkoutScheduleEntry(TimestampMixin, Base):
    __tablename__ = "workout_schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    badges: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exercise_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    set_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    readiness_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_muscles: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("workout_programs.id", ondelete="SET NULL"), nullable=True, index=True)
    recurrence_rule: Mapped[str | None] = mapped_column(String(80), nullable=True)
    continued_from_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)