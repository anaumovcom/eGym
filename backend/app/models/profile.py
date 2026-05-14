from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import GoalType


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="profile")


class UserGoal(TimestampMixin, Base):
    __tablename__ = "user_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_type: Mapped[GoalType] = mapped_column(nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="goals")


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    body_fat_percent: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    chest_cm: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    waist_cm: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    hips_cm: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    user: Mapped["User"] = relationship(back_populates="body_measurements")


from app.models.user import User  # noqa: E402
