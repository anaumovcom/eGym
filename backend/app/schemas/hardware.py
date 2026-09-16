from datetime import datetime
from typing import Any

from pydantic import Field

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
    control_mode: str = "idle"
    partial_reps: int = 0
    load_target_kg: float = 0.0
    load_effective_kg: float = 0.0
    load_mode: str = "normal_weight"
    user_force_kg: float = 0.0
    velocity_mm_per_sec: float = 0.0
    start_point: str = "lower"
    fixed_position_mm: float | None = None


class ProcedureStatusSchema(SchemaModel):
    name: str | None = None
    label: str = ""
    status: str = "idle"
    step: str = ""
    progress_ticks: int = 0
    result: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None


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
    control: dict[str, Any] = Field(default_factory=dict)
    procedure: ProcedureStatusSchema = Field(default_factory=ProcedureStatusSchema)
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
    # motion-control extensions
    load_mode: str | None = None
    start_point: str | None = None
    position_mm: float | None = None
    lower_mm: float | None = None
    upper_mm: float | None = None
    which: str | None = None
    wait_for_grip: bool = False
    warmup: bool = False
    guest: bool = False
    asymmetric_allowed: bool = False
    rep_count_source: str | None = None
    body_weight_kg: float = 0.0
    isometric_duration_s: float | None = None
    auto_user: bool | None = None


class HardwareCommandResponseSchema(SchemaModel):
    command_id: int
    status: str
    message: str
    snapshot: HardwareSnapshotSchema
    safety_gate: SafetyGateResponseSchema | None = None
    captured_position_mm: float | None = None


# ---------------------------------------------------------------- tuning API


class TuningValuesSchema(SchemaModel):
    values: dict[str, Any]
    persisted: dict[str, Any]
    temporary: dict[str, Any]
    service_mode: bool
    adapter: str


class TuningUpdateSchema(SchemaModel):
    values: dict[str, Any]
    apply: str = "temporary"  # temporary | persist
    actor_user_id: str | None = None


class TuningUpdateResultSchema(SchemaModel):
    changed: dict[str, dict[str, Any]]
    values: dict[str, Any]
    temporary: dict[str, Any]


class TuningPresetSchema(SchemaModel):
    id: str
    title: str
    description: str = ""
    created_at: str
    values: dict[str, Any]
    builtin: bool = False


class TuningPresetSaveSchema(SchemaModel):
    title: str
    description: str = ""
    values: dict[str, Any] | None = None  # None → snapshot of current effective values
    actor_user_id: str | None = None


class TuningPresetDiffSchema(SchemaModel):
    preset_id: str
    differences: list[dict[str, Any]]


class ProcedureStartSchema(SchemaModel):
    args: dict[str, Any] = Field(default_factory=dict)
    actor_user_id: str | None = None


class EmulatorControlSchema(SchemaModel):
    action: str  # user_force | scenario | fault | clear_faults | physics
    force_kg: float | None = None
    bias: float | None = None
    name: str | None = None
    strength_kg: float | None = None
    period_s: float | None = None
    lower_mm: float | None = None
    upper_mm: float | None = None
    fail_after_reps: int | None = None
    tilt_bias: float | None = None
    jerk_kg: float | None = None
    release_after_s: float | None = None
    fault: str | None = None
    side: str | None = None
    value: float | None = None
    physics: dict[str, float] | None = None


class RecordingControlSchema(SchemaModel):
    action: str  # start | stop | snapshot
    title: str | None = None
    comment: str | None = None
    seconds: float | None = None


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