from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.services.hardware_runtime import MOTION_DISABLED_MESSAGE, hardware_runtime


def test_current_calibration_returns_null_without_404(client) -> None:
    response = client.get(
        "/api/hardware/calibrations/current",
        params={"userId": "alexey", "exerciseSlug": "barbell-floor-press"},
    )

    assert response.status_code == 200
    assert response.json() is None


def test_safety_gate_skips_calibration_for_band_exercises(client) -> None:
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
    assert "Для запуска нужна актуальная калибровка." not in payload["blockingReasons"]
    # motor control v2 is not enabled yet: the gate stays closed for every exercise
    assert payload["allowed"] is False
    assert MOTION_DISABLED_MESSAGE in payload["blockingReasons"]


def test_safety_gate_requires_calibration_for_barbell(client) -> None:
    response = client.post(
        "/api/hardware/safety-gate/check",
        json={
            "userId": "alexey",
            "exerciseSlug": "barbell-floor-press",
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


def test_fixed_bar_setup_is_saved_per_user_and_exercise_and_used_for_start(client) -> None:
    url = "/api/hardware/calibrations"
    fixed = {"userId": "alexey", "exerciseSlug": "bodyweight-pull-up", "setupType": "fixed_position", "fixedPositionMm": 1550}
    created = client.post(url, json=fixed)
    assert created.status_code == 200
    assert created.json()["lowerPointMm"] is None
    assert created.json()["upperPointMm"] is None
    assert created.json()["fixedPositionMm"] == 1550
    assert client.get(f"{url}/current", params={"userId": "elena", "exerciseSlug": "bodyweight-pull-up"}).json() is None
    assert client.get(f"{url}/current", params={"userId": "alexey", "exerciseSlug": "barbell-floor-press"}).json() is None

    command = {"action": "start_fixed_position", "userId": "alexey", "exerciseSlug": "bodyweight-pull-up", "calibrationRequired": True}
    rejected = client.post("/api/hardware/commands", json=command)
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == MOTION_DISABLED_MESSAGE

    updated = client.post(url, json={**fixed, "fixedPositionMm": 1600})
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert client.get(f"{url}/current", params={"userId": "alexey", "exerciseSlug": "bodyweight-pull-up"}).json()["fixedPositionMm"] == 1600

    switched = client.post(url, json={"userId": "alexey", "exerciseSlug": "bodyweight-pull-up", "setupType": "bar_range", "lowerPointMm": 600, "upperPointMm": 1200})
    assert switched.status_code == 200
    assert switched.json()["fixedPositionMm"] is None


def test_bar_setup_rejects_mixed_or_incomplete_parameters(client) -> None:
    url = "/api/hardware/calibrations"
    base = {"userId": "alexey", "exerciseSlug": "bodyweight-pull-up"}
    assert client.post(url, json={**base, "setupType": "fixed_position", "fixedPositionMm": 900, "lowerPointMm": 500}).status_code == 422
    assert client.post(url, json={**base, "setupType": "fixed_position"}).status_code == 422
    assert client.post(url, json={**base, "lowerPointMm": 900, "upperPointMm": 800}).status_code == 422
    assert client.post(url, json={**base, "lowerPointMm": 900}).status_code == 422


def test_every_motion_command_is_rejected_until_motor_v2(client) -> None:
    base = {"userId": "alexey", "exerciseSlug": "band-chest-press", "calibrationRequired": False, "rangeConfirmed": True}
    for action in ("start_motion", "move_to_start", "enter_weightless", "jog_start", "manual_move", "capture_point", "pause", "resume", "set_load", "home", "park"):
        response = client.post("/api/hardware/commands", json={**base, "action": action, "direction": "up", "distanceMm": 10, "which": "lower"})
        assert response.status_code == 409, action
        assert response.json()["detail"] == MOTION_DISABLED_MESSAGE
    # releasing a hold-to-run button must never fail
    assert client.post("/api/hardware/commands", json={**base, "action": "jog_stop", "jogId": "x"}).status_code == 200


def test_emergency_stop_is_audited_and_keeps_support(client, db_session) -> None:
    response = client.post("/api/hardware/commands", json={"action": "trigger_emergency_stop", "userId": "alexey"})
    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["control"]["mode"] == "estop"
    assert all(raw is not None and raw != 0 for raw in snapshot["control"]["supportRaw"].values())
    assert client.post("/api/hardware/commands", json={"action": "clear_emergency_stop", "userId": "alexey"}).json()["snapshot"]["control"]["mode"] == "support"
    actions = list(db_session.scalars(select(AuditLog.action).order_by(AuditLog.id.asc())))
    assert AuditAction.emergency_stop in actions
    assert hardware_runtime.latch is None


def test_realtime_stream_receives_command_updates(client) -> None:
    with client.websocket_connect("/api/hardware/realtime?userId=alexey") as websocket:
        initial = websocket.receive_json()
        assert initial["eventType"] == "hardware.snapshot"
        assert initial["selectedUserId"] == "alexey"
        assert "barPositionMm" in initial["motion"]
        assert "lowerBoundMm" in initial["motion"]
        assert "upperBoundMm" in initial["motion"]
        assert "positionMm" in initial["drives"][0]

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

