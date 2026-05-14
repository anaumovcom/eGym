from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import SafetySeverity, SafetyState
from app.models.machine import DriveStatusSnapshot, MachineStatusSnapshot, SafetyEvent


class MachineRepository:
    def get_machine_status(self, session: Session, scenario_name: str | None = None) -> MachineStatusSnapshot | None:
        desired_scenario = scenario_name or "ready"
        statement = (
            select(MachineStatusSnapshot)
            .where(MachineStatusSnapshot.scenario_name == desired_scenario)
            .options(selectinload(MachineStatusSnapshot.drives), selectinload(MachineStatusSnapshot.safety_events))
        )
        return session.scalars(statement).first()

    def get_drives(self, session: Session, machine_status_id: int) -> list[DriveStatusSnapshot]:
        statement = (
            select(DriveStatusSnapshot)
            .where(DriveStatusSnapshot.machine_status_id == machine_status_id)
            .order_by(DriveStatusSnapshot.side)
        )
        return list(session.scalars(statement))

    def get_latest_active_safety_event(
        self, session: Session, machine_status_id: int | None = None
    ) -> SafetyEvent | None:
        statement = select(SafetyEvent).where(SafetyEvent.is_active.is_(True)).order_by(SafetyEvent.created_at.desc())
        if machine_status_id is not None:
            statement = statement.where(SafetyEvent.machine_status_id == machine_status_id)
        return session.scalars(statement).first()

    def trigger_emergency_stop(self, session: Session) -> SafetyEvent:
        blocked_status = self.get_machine_status(session, "blocked")
        event = SafetyEvent(
            machine_status_id=blocked_status.id if blocked_status else None,
            safety_state=SafetyState.emergency_stop,
            severity=SafetySeverity.critical,
            title="Аварийная остановка активирована",
            description="Система переведена в аварийный режим до сервисной проверки.",
            is_active=True,
            created_at=datetime.now(UTC),
            cleared_at=None,
        )
        session.add(event)
        session.flush()
        return event
