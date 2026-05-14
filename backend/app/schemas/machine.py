from app.models.enums import DriveState, MachineState, SafetyState
from app.schemas.base import SchemaModel


class MachineHealthSchema(SchemaModel):
    machine_state: MachineState
    machine_label: str
    left_drive: DriveState
    right_drive: DriveState
    safety: SafetyState
    calibration: str


class DriveStatusSchema(SchemaModel):
    side: str
    status: DriveState
    label: str
    message: str | None


class DriveStatusesResponseSchema(SchemaModel):
    machine_state: MachineState
    drives: list[DriveStatusSchema]


class SafetyStatusSchema(SchemaModel):
    state: SafetyState
    label: str
    message: str
    requires_service: bool
    active_event_id: int | None


class EmergencyStopResponseSchema(SchemaModel):
    status: str
    safety: SafetyStatusSchema
