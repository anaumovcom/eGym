from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import AccessRole, UserAccent


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[AccessRole] = mapped_column(SqlEnum(AccessRole, name="access_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    readiness_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    last_workout: Mapped[str] = mapped_column(Text, nullable=False)
    today_focus: Mapped[str] = mapped_column(Text, nullable=False)
    week_progress: Mapped[str] = mapped_column(Text, nullable=False)
    accent: Mapped[UserAccent] = mapped_column(SqlEnum(UserAccent, name="user_accent"), nullable=False)

    profile: Mapped["UserProfile | None"] = relationship(back_populates="user", uselist=False)
    goals: Mapped[list["UserGoal"]] = relationship(back_populates="user")
    body_measurements: Mapped[list["BodyMeasurement"]] = relationship(back_populates="user")


from app.models.profile import BodyMeasurement, UserGoal, UserProfile  # noqa: E402
