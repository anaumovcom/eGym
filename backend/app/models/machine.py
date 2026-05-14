from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DriveState, MachineState, SafetySeverity, SafetyState


class MachineStatusSnapshot(Base):
    __tablename__ = "machine_status_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    machine_state: Mapped[MachineState] = mapped_column(SqlEnum(MachineState, name="machine_state"), nullable=False)
    machine_label: Mapped[str] = mapped_column(String(160), nullable=False)
    calibration: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    drives: Mapped[list["DriveStatusSnapshot"]] = relationship(
        back_populates="machine_status", cascade="all, delete-orphan"
    )
    safety_events: Mapped[list["SafetyEvent"]] = relationship(back_populates="machine_status")


class DriveStatusSnapshot(Base):
    __tablename__ = "drive_status_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_status_id: Mapped[int] = mapped_column(
        ForeignKey("machine_status_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    drive_state: Mapped[DriveState] = mapped_column(SqlEnum(DriveState, name="drive_state"), nullable=False)
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    machine_status: Mapped[MachineStatusSnapshot] = relationship(back_populates="drives")


class SafetyEvent(Base):
    __tablename__ = "safety_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_status_id: Mapped[int | None] = mapped_column(
        ForeignKey("machine_status_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    safety_state: Mapped[SafetyState] = mapped_column(SqlEnum(SafetyState, name="safety_state"), nullable=False)
    severity: Mapped[SafetySeverity] = mapped_column(SqlEnum(SafetySeverity, name="safety_severity"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    machine_status: Mapped[MachineStatusSnapshot | None] = relationship(back_populates="safety_events")
