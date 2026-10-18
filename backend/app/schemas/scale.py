from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import SchemaModel


class ScaleMeasurement(SchemaModel):
    id: int
    user_id: str
    weight_kg: float
    timestamp: datetime
    stable: bool = True
    device_id: str
    impedance_ohm: int | None = None


class ScaleSettings(SchemaModel):
    enabled: bool = True
    device_id: str | None = Field(default=None, min_length=1, max_length=128)


class ScaleActivity(SchemaModel):
    client_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=0)
    phase: Literal["idle", "setup", "exercise", "rest"]


class ScaleDevice(SchemaModel):
    device_id: str
    name: str
    rssi: int
    last_seen: datetime


class ScaleStatus(ScaleSettings):
    paused: bool = False
    pause_reason: str | None = None
    bluetooth_available: bool = False
    scanning: bool = False
    scanning_mode: str | None = None
    measuring: bool = False
    last_seen: datetime | None = None
    last_measurement: ScaleMeasurement | None = None
    devices: list[ScaleDevice] = Field(default_factory=list)
    error: str | None = None
    warning: str | None = None


class ScaleHistory(SchemaModel):
    measurements: list[ScaleMeasurement]