from sqlalchemy.orm import Session

from app.models.enums import AuditAction, AuditSeverity, DriveState, MachineState, NotificationTone, SafetyState
from app.repositories.audit_repository import AuditRepository
from app.repositories.machine_repository import MachineRepository
from app.schemas.machine import (
    DriveStatusesResponseSchema,
    DriveStatusSchema,
    EmergencyStopResponseSchema,
    MachineHealthSchema,
    SafetyStatusSchema,
)


class MachineService:
    def __init__(self) -> None:
        self.machine_repository = MachineRepository()
        self.audit_repository = AuditRepository()

    def get_machine_health(self, session: Session, scenario_name: str | None = None) -> MachineHealthSchema:
        snapshot = self.machine_repository.get_machine_status(session, scenario_name)
        if snapshot is None:
            raise LookupError("Machine status is not configured")

        safety_event = self.machine_repository.get_latest_active_safety_event(session, snapshot.id)
        drives = {drive.side: drive.drive_state for drive in snapshot.drives}
        return MachineHealthSchema(
            machine_state=snapshot.machine_state,
            machine_label=snapshot.machine_label,
            left_drive=drives.get("left", DriveState.connected),
            right_drive=drives.get("right", DriveState.connected),
            safety=safety_event.safety_state if safety_event else SafetyState.enabled,
            calibration=snapshot.calibration,
        )

    def get_drive_statuses(self, session: Session, scenario_name: str | None = None) -> DriveStatusesResponseSchema:
        snapshot = self.machine_repository.get_machine_status(session, scenario_name)
        if snapshot is None:
            raise LookupError("Machine status is not configured")
        drives = [
            DriveStatusSchema(
                side=drive.side,
                status=drive.drive_state,
                label="Левый привод" if drive.side == "left" else "Правый привод",
                message=drive.message,
            )
            for drive in sorted(snapshot.drives, key=lambda item: item.side)
        ]
        return DriveStatusesResponseSchema(machine_state=snapshot.machine_state, drives=drives)

    def get_safety_status(self, session: Session, scenario_name: str | None = None) -> SafetyStatusSchema:
        snapshot = self.machine_repository.get_machine_status(session, scenario_name)
        if snapshot is None:
            raise LookupError("Machine status is not configured")
        safety_event = self.machine_repository.get_latest_active_safety_event(session, snapshot.id)
        state = safety_event.safety_state if safety_event else SafetyState.enabled
        return SafetyStatusSchema(
            state=state,
            label=self._safety_label(state),
            message=safety_event.description if safety_event else "Система безопасности готова к тренировке.",
            requires_service=state == SafetyState.emergency_stop or snapshot.machine_state == MachineState.blocked,
            active_event_id=safety_event.id if safety_event else None,
        )

    def trigger_emergency_stop(
        self,
        session: Session,
        actor_user_id: str | None,
    ) -> EmergencyStopResponseSchema:
        event = self.machine_repository.trigger_emergency_stop(session)
        self.audit_repository.record(
            session,
            actor_user_id=actor_user_id,
            action=AuditAction.emergency_stop,
            target_type="machine",
            target_id=str(event.machine_status_id) if event.machine_status_id is not None else None,
            severity=AuditSeverity.critical,
            details={"source": "api", "tone": NotificationTone.blocked.value},
        )
        session.commit()
        return EmergencyStopResponseSchema(
            status="emergency_stop_activated", safety=self.get_safety_status(session, "blocked")
        )

    @staticmethod
    def _safety_label(state: SafetyState) -> str:
        return {
            SafetyState.enabled: "Безопасность включена",
            SafetyState.disabled: "Защита отключена",
            SafetyState.emergency_stop: "Аварийная остановка",
        }[state]
