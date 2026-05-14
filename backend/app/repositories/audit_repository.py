from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import AuditAction, AuditSeverity


class AuditRepository:
    def record(
        self,
        session: Session,
        *,
        actor_user_id: str | None,
        action: AuditAction,
        target_type: str,
        target_id: str | None,
        severity: AuditSeverity,
        details: dict[str, object],
    ) -> AuditLog:
        entry = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            severity=severity,
            details=details,
            created_at=datetime.now(UTC),
        )
        session.add(entry)
        session.flush()
        return entry
