from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class ModbusConnectionParamsSchema(BaseModel):
    port: str = Field(description="Serial port, e.g. /dev/ttyUSB0")
    baud_rate: int = Field(default=115200, description="Baud rate")
    data_bits: int = Field(default=8)
    parity: Literal["N", "E", "O"] = Field(default="E", description="N=None, E=Even, O=Odd")
    stop_bits: int = Field(default=1)
    slave_id: int = Field(default=1, description="Modbus slave address (1–247)")
    right_slave_id: int = Field(default=2, ge=1, le=247)
    timeout_ms: int = Field(default=300, ge=50, le=5000)

    model_config = {"populate_by_name": True}


class ModbusConnectionStatusSchema(BaseModel):
    connected: bool
    port: str | None = None
    baud_rate: int | None = None
    parity: str | None = None
    slave_id: int | None = None
    right_slave_id: int | None = None
    last_success_at: datetime | None = None
    ok_count: int = 0
    error_count: int = 0
    error_message: str | None = None
    simulation_mode: bool = False


# ---------------------------------------------------------------------------
# Read / Write
# ---------------------------------------------------------------------------

class ModbusReadRequestSchema(BaseModel):
    address: int = Field(description="Register address (decimal)")
    count: int = Field(default=1, ge=1, le=125)
    slave_id: int | None = Field(default=None, ge=1, le=247)


class ModbusWriteRequestSchema(BaseModel):
    address: int = Field(description="Register address (decimal)")
    value: int = Field(description="16-bit register value")
    slave_id: int | None = Field(default=None, ge=1, le=247)


class ModbusBatchReadRequestSchema(BaseModel):
    addresses: list[int]
    slave_id: int | None = None


class ModbusRegisterValueSchema(BaseModel):
    address: int
    address_hex: str
    value: int
    raw_bytes: str | None = None
    error: str | None = None
    read_at: datetime | None = None


class ModbusReadResultSchema(BaseModel):
    success: bool
    registers: list[ModbusRegisterValueSchema]
    elapsed_ms: float | None = None
    error: str | None = None
    raw_request: str | None = None
    raw_response: str | None = None


class ModbusPositionSideSchema(BaseModel):
    slave_id: int
    current_pulses: int | None = None
    zero_pulses: int | None = None
    position_mm: float | None = None


class ModbusPositionsSchema(BaseModel):
    connected: bool
    simulation_mode: bool = False
    zeroed: bool
    left_zero_pulses: int | None = None
    right_zero_pulses: int | None = None
    left_position_mm: float | None = None
    right_position_mm: float | None = None
    left: ModbusPositionSideSchema
    right: ModbusPositionSideSchema
    skew_mm: float | None = None
    error: str | None = None


class ModbusWriteResultSchema(BaseModel):
    success: bool
    address: int
    value: int
    elapsed_ms: float | None = None
    error: str | None = None
    raw_request: str | None = None
    raw_response: str | None = None


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

class SerialPortInfoSchema(BaseModel):
    device: str
    description: str
    hardware_id: str | None = None


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class DriverDiagnosticsSchema(BaseModel):
    responding: bool
    slave_id: int | None = None
    baud_rate_code: int | None = None
    control_mode: int | None = None
    extended_mode: int | None = None
    alarm_code: int | None = None
    has_alarm: bool = False
    motion_safe: bool = False
    status_summary: str = ""
    checked_at: datetime | None = None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

class ModbusCommandRequestSchema(BaseModel):
    command: Literal[
        "servo_on",
        "servo_off",
        "alarm_reset",
        "emergency_stop",
        "pos_load",
        "jog_start",
        "jog_stop",
        "homing",
        "save_parameters",
        "clear_alarm_history",
    ]
    params: dict[str, int] | None = None
    confirmed: bool = Field(default=False, description="User confirmed dangerous operation")
    slave_id: int | None = Field(default=None, ge=1, le=247)


class ModbusCommandResultSchema(BaseModel):
    success: bool
    command: str
    message: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Exchange log
# ---------------------------------------------------------------------------

class ExchangeLogEntrySchema(BaseModel):
    id: int
    ts: datetime
    direction: Literal["TX", "RX", "INFO", "ERROR"]
    slave_id: int | None = None
    action: str
    parameter: str | None = None
    address: int | None = None
    value: int | None = None
    result: str | None = None
    raw_request: str | None = None
    raw_response: str | None = None
    error: str | None = None
    elapsed_ms: float | None = None


class ExchangeLogResponseSchema(BaseModel):
    entries: list[ExchangeLogEntrySchema]
    total: int


# ---------------------------------------------------------------------------
# Parameter profile
# ---------------------------------------------------------------------------

class ParameterValueSchema(BaseModel):
    address: int
    name: str
    value: int


class ParameterProfileSchema(BaseModel):
    id: str | None = None
    name: str
    driver_model: str = "Lichuan A6"
    slave_id: int = 1
    baud_rate: int = 115200
    parameters: list[ParameterValueSchema] = Field(default_factory=list)
    comment: str = ""
    created_at: datetime | None = None


class ProfileSaveRequestSchema(BaseModel):
    name: str
    comment: str = ""
    addresses: list[int] | None = None  # None = all known addresses


class ProfileCompareResultSchema(BaseModel):
    differences: list[dict]  # [{address, name, driver_value, profile_value}]
    matching: int
    differing: int


# ---------------------------------------------------------------------------
# Torque mode (PA_002 = 2, reference in PA_12C)
# ---------------------------------------------------------------------------

class ModbusTorqueInitRequestSchema(BaseModel):
    torque_limit: int = Field(default=400, ge=0, le=3000, description="PA_05E, 0.1 % of rated torque")
    speed_limit_rpm: int = Field(default=300, ge=0, le=3000, description="PA_056, rpm")


class ModbusTorqueInitResultSchema(BaseModel):
    success: bool
    errors: list[str] = Field(default_factory=list)


class ModbusTorqueCommandRequestSchema(BaseModel):
    slave_id: int = Field(ge=1, le=247)
    torque_raw: int = Field(ge=-3000, le=3000, description="PA_12C, 0.1 % of rated torque (signed)")


class ModbusTorqueResultSchema(BaseModel):
    success: bool
    error: str | None = None


class ModbusTorqueTelemetrySchema(BaseModel):
    slave_id: int
    feedback_position: int | None = None
    position_mm: float | None = None
    position_error: int | None = None
    command_speed_rpm: int | None = None
    feedback_speed_rpm: int | None = None
    command_torque_raw: int | None = None
    feedback_torque_raw: int | None = None
    alarm: int | None = None
    torque_written_raw: int | None = None
    torque_limit_raw: int | None = None
    speed_limit_rpm: int | None = None
    status_pa1db: int | None = None
    reason_pa1de: int | None = None
    error: str | None = None
