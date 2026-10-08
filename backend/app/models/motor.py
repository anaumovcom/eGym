from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MachineProfileRecord(TimestampMixin, Base):
    """Versioned motor v2 profile: MachineProfile + Tunables + SafetyEnvelope."""

    __tablename__ = "machine_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class CalibrationRun(Base):
    __tablename__ = "calibration_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    procedure: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    estimate: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    samples_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ExerciseFeelProfile(TimestampMixin, Base):
    __tablename__ = "exercise_feel_profiles"
    __table_args__ = (UniqueConstraint("user_id", "exercise_slug", name="uq_exercise_feel_user_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    exercise_slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
