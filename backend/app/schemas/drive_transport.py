from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings
from app.schemas.modbus import ModbusConnectionParamsSchema


class CanopenSettings(BaseModel):
    operation: Literal["diagnostics", "control"] = "control"  # Existing installations retain their operating mode.
    torque_mode: Literal["auto", "cst", "profile_torque"] = "auto"
    driver: Literal["usbcanfd", "socketcan"] = "usbcanfd"
    device: int = Field(default=0, ge=0, le=7)
    channel: int = Field(default=0, ge=0, le=1)
    interface: str = Field(default="can0", pattern=r"^[a-zA-Z0-9_.-]{1,15}$")
    bitrate: Literal[20000, 50000, 125000, 250000, 500000, 750000, 1000000] = 500000
    cycle_ms: Literal[20, 10, 5] = 20
    left_id: int = Field(default=1, ge=1, le=32)
    right_id: int = Field(default=2, ge=1, le=32)
    velocity_unit: Literal["rpm", "counts/s"] = "rpm"

    @model_validator(mode="after")
    def distinct_nodes(self) -> Self:
        if self.left_id == self.right_id:
            raise ValueError("Адреса приводов должны различаться")
        if self.operation == "control" and self.bitrate not in (500000, 1000000):
            raise ValueError("Для управления выберите 500 кбит/с или 1 Мбит/с")
        if self.driver == "usbcanfd" and self.bitrate < 100000:
            raise ValueError("Минимальная паспортная скорость USB-CAN-FD-B — 100 кбит/с")
        return self


class DriveTransportSettings(BaseModel):
    adapter: Literal["modbus", "canopen", "twin"]
    canopen: CanopenSettings = Field(default_factory=CanopenSettings)
    modbus: ModbusConnectionParamsSchema | None = None

    @classmethod
    def from_environment(cls) -> Self:
        adapter = get_settings().hardware_adapter
        if adapter == "canopen":
            return cls(adapter="canopen", canopen=CanopenSettings(operation="diagnostics"))
        return cls(adapter="modbus" if adapter == "modbus" else "twin")


class CanopenNodeStatus(BaseModel):
    node: int
    mode: int
    statusword: int
    position: int
    velocity: int
    torque: int


class CanopenTiming(BaseModel):
    intervals: int
    mean_hz: float
    p99_ms: float
    p99_feedback_ms: float | None = None


class CanAdapterInfo(BaseModel):
    model: str | None = None
    serial: str | None = None
    hardware: int | None = None
    firmware: int | None = None
    driver: int | None = None
    channels: int | None = None
    interface_bitrate: int | None = None
    link_state: str | None = None


class CanObjectReading(BaseModel):
    value: int | None
    abort: int | None = None
    issue: str | None = None
    age_ms: int


class CanAxisDiagnostics(BaseModel):
    node: int
    responding: bool | None
    last_seen_ms: int | None
    issue: str | None
    heartbeat_state: int | None
    heartbeat_age_ms: int | None
    bootups: int
    emcy: int | None
    emcy_register: int | None
    emcy_age_ms: int | None
    objects: dict[str, CanObjectReading]
    sent_controlword: int | None = None
    sent_target: int | None = None
    tpdo_latency_ms: float | None = None


class CanTraceFrame(BaseModel):
    seq: int
    elapsed_ms: float
    direction: Literal["TX", "RX"]
    identifier: int
    data: str


class CanopenDiagnostics(BaseModel):
    stage: str
    adapter_open: bool
    adapter: CanAdapterInfo | None
    tx: int
    rx: int
    sdo_timeouts: int
    sdo_aborts: int
    axes: list[CanAxisDiagnostics]
    frames: list[CanTraceFrame]


class DriveTransportStatus(BaseModel):
    config: DriveTransportSettings
    connected: bool
    error: str | None
    nodes: list[CanopenNodeStatus] = Field(default_factory=list)
    timing: CanopenTiming | None = None
    diagnostics: CanopenDiagnostics | None = None
