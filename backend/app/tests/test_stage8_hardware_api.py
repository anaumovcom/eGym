from sqlalchemy import select

from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.services.hardware_runtime import hardware_runtime


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


def test_keyboard_simulation_moves_and_stops_bar(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "true")
    get_settings.cache_clear()
    hardware_runtime.reset()

    try:
        start_position = hardware_runtime.snapshot_payload()["motion"]["bar_position_mm"]

        monkeypatch.setattr(hardware_runtime, "_get_keyboard_direction", lambda: "up")
        assert hardware_runtime._tick_motion() is True
        moved_up = hardware_runtime.snapshot_payload()["motion"]
        assert moved_up["moving"] is True
        assert moved_up["bar_position_mm"] > start_position

        monkeypatch.setattr(hardware_runtime, "_get_keyboard_direction", lambda: None)
        assert hardware_runtime._tick_motion() is True
        stopped = hardware_runtime.snapshot_payload()["motion"]
        assert stopped["moving"] is False

        monkeypatch.setattr(hardware_runtime, "_get_keyboard_direction", lambda: "down")
        assert hardware_runtime._tick_motion() is True
        moved_down = hardware_runtime.snapshot_payload()["motion"]
        assert moved_down["moving"] is True
        assert moved_down["bar_position_mm"] < moved_up["bar_position_mm"]
    finally:
        get_settings.cache_clear()
        hardware_runtime.reset()


def test_keyboard_simulation_counts_rep_only_after_full_range(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "true")
    get_settings.cache_clear()
    hardware_runtime.reset()

    try:
        hardware_runtime.start_motion(
            calibration_id=None,
            lower_bound_mm=840,
            upper_bound_mm=880,
            target_set=1,
            target_reps=3,
            motion_profile="training",
        )

        monkeypatch.setattr(hardware_runtime, "_get_keyboard_direction", lambda: "down")
        assert hardware_runtime._tick_motion() is True
        partial_range = hardware_runtime.snapshot_payload()["motion"]
        assert partial_range["bar_position_mm"] == 840
        assert partial_range["repetition_count"] == 0

        monkeypatch.setattr(hardware_runtime, "_get_keyboard_direction", lambda: "up")
        assert hardware_runtime._tick_motion() is True
        assert hardware_runtime._tick_motion() is True
        completed = hardware_runtime.snapshot_payload()["motion"]
        assert completed["bar_position_mm"] == 880
        assert completed["repetition_count"] == 1
    finally:
        get_settings.cache_clear()
        hardware_runtime.reset()


def test_auto_motion_counts_rep_on_upper_boundary_after_lower_boundary(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "false")
    get_settings.cache_clear()
    hardware_runtime.reset()

    try:
        hardware_runtime.start_motion(
            calibration_id=None,
            lower_bound_mm=840,
            upper_bound_mm=880,
            target_set=1,
            target_reps=3,
            motion_profile="training",
        )

        assert hardware_runtime._tick_motion() is True
        first_top = hardware_runtime.snapshot_payload()["motion"]
        assert first_top["bar_position_mm"] == 880
        assert first_top["repetition_count"] == 0

        assert hardware_runtime._tick_motion() is True
        at_bottom = hardware_runtime.snapshot_payload()["motion"]
        assert at_bottom["bar_position_mm"] == 840
        assert at_bottom["repetition_count"] == 0

        assert hardware_runtime._tick_motion() is True
        counted = hardware_runtime.snapshot_payload()["motion"]
        assert counted["bar_position_mm"] == 880
        assert counted["repetition_count"] == 1
    finally:
        get_settings.cache_clear()
        hardware_runtime.reset()


def test_start_motion_refreshes_initial_amplitude_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "false")
    get_settings.cache_clear()
    hardware_runtime.reset()

    try:
      hardware_runtime.state.motion.amplitude_percent = 0

      hardware_runtime.start_motion(
          calibration_id=None,
          lower_bound_mm=840,
          upper_bound_mm=880,
          target_set=1,
          target_reps=3,
          motion_profile="training",
      )

      snapshot = hardware_runtime.snapshot_payload()["motion"]
      assert snapshot["bar_position_mm"] == 860
      assert snapshot["amplitude_percent"] == 50
      assert snapshot["repetition_count"] == 0
    finally:
        get_settings.cache_clear()
        hardware_runtime.reset()
