from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class ModbusConnectionParamsSchema(BaseModel):
    port: str = Field(description="Serial port, e.g. /dev/ttyUSB0")
    baud_rate: int = Field(default=38400, description="Baud rate")
    data_bits: int = Field(default=8)
    parity: Literal["N", "E", "O"] = Field(default="E", description="N=None, E=Even, O=Odd")
    stop_bits: int = Field(default=1)
    slave_id: int = Field(default=1, description="Modbus slave address (1–247)")
    right_slave_id: int = Field(default=2, ge=1, le=247)
    timeout_ms: int = Field(default=300, ge=50, le=5000)
    left_direction: Literal[-1, 1] = 1
    right_direction: Literal[-1, 1] = 1

    model_config = {"populate_by_name": True}


class ModbusConnectionStatusSchema(BaseModel):
    connected: bool
    port: str | None = None
    baud_rate: int | None = None
    parity: str | None = None
    slave_id: int | None = None
    right_slave_id: int | None = None
    left_direction: Literal[-1, 1] = 1
    right_direction: Literal[-1, 1] = 1
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


class ModbusReadinessSchema(BaseModel):
    communication_ready: bool = False
    encoder_ready: bool = False
    torque_control_ready: bool = False
    motion_safety_ready: bool = False
    degraded_manual_mode: bool = True
    allow_encoder_read: bool = False
    allow_zero_offset: bool = False
    allow_status_read: bool = False
    allow_manual_torque_test: bool = False
    allow_automatic_motion: bool = False
    allow_position_auto_move: bool = False
    allow_program_workout: bool = False
    allow_homing: bool = False
    no_brake: bool = True
    no_limit_switches: bool = True
    no_hardware_stop: bool = True
    no_hardware_sync: bool = True
    warning: str = (
        "Автоматическое движение отключено: не настроены концевики, тормоз, аппаратный STOP "
        "и синхронизация двух сторон. Доступны чтение позиции и программное обнуление. "
        "Ручной тест момента требует проверенного управления Servo-ON/OFF и отдельного разрешения. "
        "Программный STOP не заменяет аппаратный E-STOP. (E-CTRL-UNAVAILABLE)"
    )


class ModbusPositionsSchema(BaseModel):
    connected: bool
    simulation_mode: bool = False
    zeroed: bool
    zero_generation: int = 0
    readiness: ModbusReadinessSchema = Field(default_factory=ModbusReadinessSchema)
    left_zero_pulses: int | None = None
    right_zero_pulses: int | None = None
    left_position_mm: float | None = None
    right_position_mm: float | None = None
    left: ModbusPositionSideSchema
    right: ModbusPositionSideSchema
    skew_mm: float | None = None
    error: str | None = None


class PositionExerciseSchema(BaseModel):
    exercise_key: str | None = Field(default=None, min_length=1)
    target_type: Literal["lower_boundary", "fixed_position"]
    lower_boundary_mm: float | None = None
    fixed_position_mm: float | None = None
    torque_limit: int = Field(ge=1, le=3000, description="0.1% of rated torque")
    speed_rpm: int = Field(ge=1, le=3000)
    min_mm: float = 0
    max_mm: float = 2000


class PositionMotionStatusSchema(BaseModel):
    state: Literal["idle", "exercise", "raising", "weightless", "holding", "fault"] = "idle"
    target_type: Literal["lower_boundary", "fixed_position", "stop_raise", "weightless", "hold"] | None = None
    target_mm: float | None = None
    torque_limit: int | None = None
    speed_rpm: int | None = None
    positions: ModbusPositionsSchema
    servo_on: dict[str, bool | None] = Field(default_factory=dict)
    pos_load: dict[str, bool | None] = Field(default_factory=dict)
    drives: dict[str, dict[str, int | float | None]] = Field(default_factory=dict)
    warning: str | None = None
    error: str | None = None
    simulation_only: bool = True


class PositionCalibrationCaptureSchema(BaseModel):
    exercise_key: str = Field(min_length=1)
    point: Literal["lower", "upper", "fixed"]


class PositionCalibrationSchema(BaseModel):
    exercise_key: str
    zero_generation: int
    lower_mm: float | None = None
    upper_mm: float | None = None
    fixed_mm: float | None = None


class WeightlessPositionSchema(BaseModel):
    # Commissioning threshold is a user-supplied upper bound, never inferred from
    # encoder readings. Zero load and no motion are NOT guaranteed by this field.
    torque_limit: int = Field(ge=1, le=3000)
    no_motion_threshold: int = Field(ge=2, le=3000)
    speed_rpm: int = Field(default=30, ge=1, le=3000)


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


class SoftwareStopResultSchema(BaseModel):
    success: bool = False
    torque_zeroed: dict[str, bool] = Field(default_factory=dict)
    servo_off_confirmed: dict[str, bool] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warning: str = "Нулевой момент может отпустить нагруженный гриф. Программный STOP не заменяет аппаратный E-STOP; при сомнении отключите приводы аппаратно."


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
    baud_rate: int = 38400
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
