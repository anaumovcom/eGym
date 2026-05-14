from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import AuditAction


def test_machine_status_and_drive_statuses(client: TestClient) -> None:
    status_response = client.get("/api/machine/status", params={"scenario": "ready"})
    drives_response = client.get("/api/machine/drives", params={"scenario": "warning"})

    assert status_response.status_code == 200
    assert status_response.json()["machineState"] == "ready"
    assert drives_response.status_code == 200
    assert drives_response.json()["drives"][1]["status"] == "warning"


def test_emergency_stop_creates_audit_entry(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/machine/emergency-stop", params={"actorUserId": "alexey"})

    assert response.status_code == 200
    assert response.json()["safety"]["state"] == "emergency_stop"

    audit_actions = list(db_session.scalars(select(AuditLog.action).order_by(AuditLog.id.desc())))
    assert AuditAction.emergency_stop in audit_actions
