from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ExerciseCalibration(TimestampMixin, Base):
    __tablename__ = "exercise_calibrations"
    __table_args__ = (UniqueConstraint("user_id", "exercise_slug", name="uq_exercise_calibration_user_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exercise_slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    lower_point_mm: Mapped[float] = mapped_column(Float, nullable=False)
    upper_point_mm: Mapped[float] = mapped_column(Float, nullable=False)
    zero_position_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    movement_range_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    calibration_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class HardwareDiagnosticRecord(Base):
    __tablename__ = "hardware_diagnostic_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)