from sqlalchemy import select

from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.services.hardware_runtime import hardware_runtime
from app.services.motion.controller import ControlMode


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
    assert payload["allowed"] is True
    assert "Для запуска нужна актуальная калибровка." not in payload["blockingReasons"]


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
    assert client.post("/api/hardware/commands", json={**command, "positionMm": 1500}).status_code == 400
    assert client.post("/api/hardware/commands", json={**command, "userId": "elena"}).status_code == 409
    started = client.post("/api/hardware/commands", json=command)
    assert started.status_code == 200
    assert started.json()["snapshot"]["motion"]["fixedPositionMm"] == 1550
    assert client.post("/api/hardware/commands", json={**command, "action": "start_motion"}).status_code == 409

    updated = client.post(url, json={**fixed, "fixedPositionMm": 1600})
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert client.get(f"{url}/current", params={"userId": "alexey", "exerciseSlug": "bodyweight-pull-up"}).json()["fixedPositionMm"] == 1600

    switched = client.post(url, json={"userId": "alexey", "exerciseSlug": "bodyweight-pull-up", "setupType": "bar_range", "lowerPointMm": 600, "upperPointMm": 1200})
    assert switched.status_code == 200
    assert switched.json()["fixedPositionMm"] is None
    assert client.post("/api/hardware/commands", json=command).status_code == 409


def test_bar_setup_rejects_mixed_or_incomplete_parameters(client) -> None:
    url = "/api/hardware/calibrations"
    base = {"userId": "alexey", "exerciseSlug": "bodyweight-pull-up"}
    assert client.post(url, json={**base, "setupType": "fixed_position", "fixedPositionMm": 900, "lowerPointMm": 500}).status_code == 422
    assert client.post(url, json={**base, "setupType": "fixed_position"}).status_code == 422
    assert client.post(url, json={**base, "lowerPointMm": 900, "upperPointMm": 800}).status_code == 422
    assert client.post(url, json={**base, "lowerPointMm": 900}).status_code == 422


def test_calibration_can_be_adjusted_and_used_during_a_set(client) -> None:
    saved = client.post("/api/hardware/calibrations", json={
        "userId": "alexey", "exerciseSlug": "barbell-floor-press",
        "setupType": "bar_range", "lowerPointMm": 700, "upperPointMm": 1100,
    })
    assert saved.status_code == 200
    command = {"userId": "alexey", "exerciseSlug": "barbell-floor-press", "calibrationRequired": True, "rangeConfirmed": True}
    started = client.post("/api/hardware/commands", json={**command, "action": "start_motion"})
    assert started.status_code == 200
    move = {**command, "action": "manual_move", "mode": "service", "direction": "up", "distanceMm": 10}
    assert client.post("/api/hardware/commands", json=move).status_code == 409
    assert client.post("/api/hardware/commands", json={**command, "action": "pause"}).status_code == 200
    assert client.post("/api/hardware/commands", json=move).status_code == 200
    for _ in range(300):
        hardware_runtime._tick_motion()
        if hardware_runtime.controller.state.mode == ControlMode.paused:
            break
    assert hardware_runtime.controller.state.mode == ControlMode.paused
    new_lower = hardware_runtime.controller.state.position_mm
    assert client.post("/api/hardware/calibrations", json={
        "userId": "alexey", "exerciseSlug": "barbell-floor-press", "setupType": "bar_range",
        "lowerPointMm": new_lower, "upperPointMm": 1100,
    }).status_code == 200
    resumed = client.post("/api/hardware/commands", json={**command, "action": "resume"})
    assert resumed.status_code == 200
    assert hardware_runtime.controller.config.lower_mm == new_lower
    assert client.get("/api/hardware/calibrations/current", params={"userId": "alexey", "exerciseSlug": "barbell-floor-press"}).json()["lowerPointMm"] == new_lower


def test_fixed_height_can_be_changed_during_a_set(client) -> None:
    saved = client.post("/api/hardware/calibrations", json={
        "userId": "alexey", "exerciseSlug": "bodyweight-pull-up", "setupType": "fixed_position", "fixedPositionMm": 860,
    })
    assert saved.status_code == 200
    command = {"userId": "alexey", "exerciseSlug": "bodyweight-pull-up", "calibrationRequired": True}
    assert client.post("/api/hardware/commands", json={**command, "action": "start_fixed_position"}).status_code == 200
    for _ in range(300):
        hardware_runtime._tick_motion()
        if hardware_runtime.controller.state.mode == ControlMode.fixed_hold:
            break
    assert hardware_runtime.controller.state.mode == ControlMode.fixed_hold
    assert client.post("/api/hardware/commands", json={**command, "action": "pause"}).status_code == 200
    assert client.post("/api/hardware/commands", json={**command, "action": "manual_move", "direction": "up", "distanceMm": 10, "mode": "service"}).status_code == 200
    for _ in range(300):
        hardware_runtime._tick_motion()
        if hardware_runtime.controller.state.mode == ControlMode.paused:
            break
    position = hardware_runtime.controller.state.position_mm
    assert position > 865
    assert client.post("/api/hardware/calibrations", json={
        "userId": "alexey", "exerciseSlug": "bodyweight-pull-up", "setupType": "fixed_position", "fixedPositionMm": position,
    }).status_code == 200
    assert client.post("/api/hardware/commands", json={**command, "action": "resume"}).status_code == 200
    assert hardware_runtime.controller.config.fixed_position_mm == position
    assert hardware_runtime.controller.state.mode == ControlMode.fixed_hold


def test_hold_to_jog_api_requires_owner_and_stops_on_release(client) -> None:
    command = {"userId": "alexey", "exerciseSlug": "barbell-floor-press", "jogId": "press-1"}
    start = client.post("/api/hardware/commands", json={**command, "action": "jog_start", "direction": "up", "mode": "service"})
    assert start.status_code == 200
    assert client.post("/api/hardware/commands", json={**command, "action": "jog_keepalive", "userId": "elena"}).status_code == 409
    assert client.post("/api/hardware/commands", json={**command, "action": "jog_stop", "jogId": "another"}).status_code == 409
    assert client.post("/api/hardware/commands", json={**command, "action": "start_motion"}).status_code == 409
    assert client.post("/api/hardware/commands", json={**command, "action": "jog_keepalive"}).status_code == 200
    stopped = client.post("/api/hardware/commands", json={**command, "action": "jog_stop"})
    assert stopped.status_code == 200
    assert stopped.json()["snapshot"]["control"]["mode"] == "weightless"


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
    assert payload["snapshot"]["motion"]["lowerBoundMm"] == 620.0
    assert payload["snapshot"]["motion"]["upperBoundMm"] == 1290.0
    assert payload["safetyGate"]["allowed"] is True

    actions = list(db_session.scalars(select(AuditLog.action).order_by(AuditLog.id.asc())))
    assert AuditAction.calibration_saved in actions
    assert AuditAction.hardware_command in actions


def test_start_motion_allows_band_without_calibration(client) -> None:
    response = client.post(
        "/api/hardware/commands",
        json={
            "action": "start_motion",
            "userId": "alexey",
            "exerciseSlug": "band-chest-press",
            "calibrationRequired": True,
            "rangeConfirmed": True,
            "weightKg": 36,
            "targetSet": 1,
            "targetReps": 8,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["snapshot"]["motion"]["lowerBoundMm"] == 640.0
    assert payload["snapshot"]["motion"]["upperBoundMm"] == 1320.0
    assert payload["safetyGate"]["allowed"] is True


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

