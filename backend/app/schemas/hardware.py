from datetime import datetime

from app.schemas.base import SchemaModel
from app.schemas.machine import MachineHealthSchema, SafetyStatusSchema


class DriveTelemetrySchema(SchemaModel):
    side: str
    status: str
    connected: bool
    position_mm: float
    speed_mm_per_sec: float
    acceleration_mm_per_sec2: float
    jerk_mm_per_sec3: float
    torque_limit_percent: int
    current_a: float
    temperature_c: float
    error_code: str | None = None
    error_message: str | None = None


class MotionTelemetrySchema(SchemaModel):
    moving: bool
    motion_profile: str
    bar_position_mm: float
    left_position_mm: float
    right_position_mm: float
    sync_delta_mm: float
    amplitude_percent: int
    tempo_label: str
    repetition_count: int
    current_set: int
    target_set: int
    target_reps: int
    direction: str
    lower_bound_mm: float
    upper_bound_mm: float


class CommandSummarySchema(SchemaModel):
    id: int
    action: str
    status: str
    created_at: str
    payload: dict[str, object]


class HardwareSnapshotSchema(SchemaModel):
    event_type: str = "hardware.snapshot"
    emitted_at: str
    machine: MachineHealthSchema
    safety: SafetyStatusSchema
    emulator_mode: bool
    service_mode: bool
    selected_user_id: str | None = None
    user_selected: bool
    drives: list[DriveTelemetrySchema]
    motion: MotionTelemetrySchema
    calibration_required: bool
    calibration_actual: bool
    active_calibration_id: int | None = None
    command_queue_depth: int
    last_command: CommandSummarySchema | None = None
    diagnostics_status: str
    last_diagnostics_at: str | None = None
    alerts: list[str]


class CalibrationSummarySchema(SchemaModel):
    id: int
    user_id: str
    exercise_slug: str
    lower_point_mm: float
    upper_point_mm: float
    zero_position_mm: float
    movement_range_confirmed: bool
    calibration_required: bool
    is_active: bool
    captured_at: datetime
    expires_at: datetime | None = None
    note: str | None = None


class CalibrationSaveSchema(SchemaModel):
    user_id: str
    exercise_slug: str
    lower_point_mm: float
    upper_point_mm: float
    zero_position_mm: float = 0.0
    movement_range_confirmed: bool = True
    calibration_required: bool = True
    expires_at: datetime | None = None
    note: str | None = None


class CalibrationListResponseSchema(SchemaModel):
    items: list[CalibrationSummarySchema]


class SafetyGateCheckSchema(SchemaModel):
    id: str
    label: str
    passed: bool
    severity: str
    message: str


class SafetyGateRequestSchema(SchemaModel):
    user_id: str | None = None
    exercise_slug: str
    calibration_required: bool = True
    range_confirmed: bool = False
    weight_kg: float = 0.0
    mode: str = "machine"


class SafetyGateResponseSchema(SchemaModel):
    allowed: bool
    checks: list[SafetyGateCheckSchema]
    blocking_reasons: list[str]
    calibration_id: int | None = None


class HardwareCommandRequestSchema(SchemaModel):
    action: str
    user_id: str | None = None
    exercise_slug: str | None = None
    calibration_required: bool = False
    range_confirmed: bool = False
    weight_kg: float = 0.0
    mode: str = "machine"
    target_set: int = 1
    target_reps: int = 10
    direction: str | None = None
    distance_mm: float | None = None
    service_mode: bool | None = None


class HardwareCommandResponseSchema(SchemaModel):
    command_id: int
    status: str
    message: str
    snapshot: HardwareSnapshotSchema
    safety_gate: SafetyGateResponseSchema | None = None


class HardwareDiagnosticRecordSchema(SchemaModel):
    id: int
    category: str
    title: str
    status: str
    severity: str
    description: str
    ran_at: datetime
    payload_json: dict[str, object]


class HardwareSafetySettingsSchema(SchemaModel):
    child_lock: bool
    workout_pin: bool
    service_pin: bool
    idle_lock_minutes: str
    guest_mode: bool
    guest_weight_limit: str
    max_load: str
    max_speed: str
    sync_limit: str
    desync_action: str