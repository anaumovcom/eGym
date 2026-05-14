from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.enums import AuditAction


def test_safety_gate_requires_calibration(client) -> None:
    response = client.post(
        "/api/hardware/safety-gate/check",
        json={
            "userId": "alexey",
            "exerciseSlug": "band-chest-press",
            "calibrationRequired": True,
            "rangeConfirmed": True,
            "weightKg": 32,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is False
    assert "Для запуска нужна актуальная калибровка." in payload["blockingReasons"]


def test_calibration_lifecycle_and_recreate_after_delete(client) -> None:
    save_payload = {
        "userId": "alexey",
        "exerciseSlug": "band-chest-press",
        "lowerPointMm": 610,
        "upperPointMm": 1280,
        "zeroPositionMm": 845,
        "movementRangeConfirmed": True,
        "calibrationRequired": True,
    }
    first_save = client.post("/api/hardware/calibrations", json=save_payload)

    assert first_save.status_code == 200
    calibration_id = first_save.json()["id"]

    delete_response = client.delete(f"/api/hardware/calibrations/{calibration_id}?confirm=true&actorUserId=alexey")
    assert delete_response.status_code == 204

    recreated = client.post(
        "/api/hardware/calibrations",
        json={
            **save_payload,
            "lowerPointMm": 600,
            "upperPointMm": 1275,
        },
    )
    assert recreated.status_code == 200
    recreated_payload = recreated.json()
    assert recreated_payload["id"] == calibration_id
    assert recreated_payload["isActive"] is True
    assert recreated_payload["lowerPointMm"] == 600.0

    listed = client.get("/api/hardware/calibrations", params={"userId": "alexey"})
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1


def test_start_motion_records_audit_log(client, db_session) -> None:
    calibration_response = client.post(
        "/api/hardware/calibrations",
        json={
            "userId": "alexey",
            "exerciseSlug": "band-chest-press",
            "lowerPointMm": 620,
            "upperPointMm": 1290,
            "zeroPositionMm": 850,
            "movementRangeConfirmed": True,
            "calibrationRequired": True,
        },
    )
    assert calibration_response.status_code == 200

    response = client.post(
        "/api/hardware/commands",
        json={
            "action": "start_motion",
            "userId": "alexey",
            "exerciseSlug": "band-chest-press",
            "calibrationRequired": True,
            "rangeConfirmed": True,
            "weightKg": 36,
            "targetSet": 2,
            "targetReps": 8,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["snapshot"]["motion"]["moving"] is True
    assert payload["safetyGate"]["allowed"] is True

    actions = list(db_session.scalars(select(AuditLog.action).order_by(AuditLog.id.asc())))
    assert AuditAction.calibration_saved in actions
    assert AuditAction.hardware_command in actions


def test_realtime_stream_receives_command_updates(client) -> None:
    with client.websocket_connect("/api/hardware/realtime?userId=alexey") as websocket:
        initial = websocket.receive_json()
        assert initial["eventType"] == "hardware.snapshot"
        assert initial["selectedUserId"] == "alexey"

        response = client.post(
            "/api/hardware/commands",
            json={
                "action": "trigger_emergency_stop",
                "userId": "alexey",
            },
        )
        assert response.status_code == 200

        updated = websocket.receive_json()
        assert updated["safety"]["state"] == "emergency_stop"
        assert updated["machine"]["machineLabel"] == "СТОП активирован"
