from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScaleReading(Base):
    """BLE provenance for the existing body_measurements history."""

    __tablename__ = "scale_readings"
    __table_args__ = (UniqueConstraint("device_id", "measurement_key", name="uq_scale_reading_packet"),)

    measurement_id: Mapped[int] = mapped_column(
        ForeignKey("body_measurements.id", ondelete="CASCADE"), primary_key=True,
    )
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    measurement_key: Mapped[str] = mapped_column(String(64), nullable=False)
    impedance_ohm: Mapped[int | None] = mapped_column(Integer, nullable=True)