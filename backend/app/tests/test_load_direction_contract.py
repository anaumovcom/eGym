"""Offline API/persistence tests: no app lifespan, drive, movement or live database."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_session
from app.api.routes.hardware import router
from app.schemas.hardware import CalibrationSaveSchema, HardwareCommandRequestSchema, MotionTelemetrySchema
from app.services import hardware_runtime as runtime_module
from app.services import hardware_service as service_module
from app.services.hardware_runtime import HardwareRuntime, MotionRuntimeState
from app.services.hardware_service import HardwareService
from app.motor.workout import WorkoutError


def calibration(**extra):
    return {"userId": "alexey", "exerciseSlug": "barbell-floor-press",
            "lowerPointMm": 300, "upperPointMm": 900, **extra}


def test_defaults_validation_and_aliases():
    assert CalibrationSaveSchema.model_validate(calibration()).load_direction == "down"
    assert HardwareCommandRequestSchema(action="start_motion").load_direction == "down"
    for value in ("left", "UP", "", None, 1):
        with pytest.raises(ValidationError):
            CalibrationSaveSchema.model_validate(calibration(loadDirection=value))
        with pytest.raises(ValidationError):
            HardwareCommandRequestSchema.model_validate({"action": "set_load", "loadDirection": value})
    for direction in ("down", "up"):
        parsed = HardwareCommandRequestSchema(action="start_motion", load_direction=direction)
        assert parsed.model_dump(by_alias=True)["loadDirection"] == direction


def test_calibration_api_roundtrip_and_old_update_preserves_choice(db_session, monkeypatch):
    # Router-only app intentionally has no startup/lifespan or hardware IO.
    monkeypatch.setattr(service_module.hardware_runtime, "set_calibration_state", Mock())
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        saved = client.post("/api/hardware/calibrations", json=calibration())
        assert saved.status_code == 200, saved.text
        assert saved.json()["loadDirection"] == "down"
        changed = client.post("/api/hardware/calibrations", json=calibration(loadDirection="up", startPoint="lower"))
        assert changed.json()["loadDirection"] == "up"
        assert changed.json()["startPoint"] == "lower"
        old_update = client.post("/api/hardware/calibrations", json=calibration(upperPointMm=950))
        assert old_update.json()["loadDirection"] == "up"
        current = client.get("/api/hardware/calibrations/current", params={"userId": "alexey", "exerciseSlug": "barbell-floor-press"}).json()
        assert current["loadDirection"] == "up"
        assert client.get("/api/hardware/calibrations", params={"userId": "alexey"}).json()["items"][0]["loadDirection"] == "up"
        assert client.post("/api/hardware/calibrations", json=calibration(loadDirection="invalid")).status_code == 422
    setup = HardwareService()._set_calibration(db_session, HardwareCommandRequestSchema(action="start_motion", user_id="alexey", exercise_slug="barbell-floor-press"))
    assert setup["load_direction"] == "up"


def test_set_plan_adapter_precedence_without_drives(monkeypatch):
    # Isolate the adapter from the independently owned motor SetPlan implementation.
    monkeypatch.setattr(runtime_module, "SetPlan", lambda **values: SimpleNamespace(**values))
    runtime = HardwareRuntime.__new__(HardwareRuntime)
    setup = {"lower_point_mm": 300, "upper_point_mm": 900, "start_point": "lower"}
    assert runtime._set_plan("start_motion", {}, setup).load_direction == "down"
    plan = runtime._set_plan("start_motion", {}, {**setup, "load_direction": "up"})
    assert (plan.load_direction, plan.start_point) == ("up", "lower")
    assert runtime._set_plan("start_motion", {"load_direction": "down"}, {**setup, "load_direction": "up"}).load_direction == "down"
    assert runtime._set_plan("start_fixed_position", {}, {"fixed_position_mm": 500, "load_direction": "up"}).load_direction == "up"
    with pytest.raises(WorkoutError):
        runtime._set_plan("start_motion", {"load_direction": "invalid"}, setup)


def test_real_set_plan_appended_direction_contract():
    from dataclasses import fields
    from app.motor.workout import SetPlan

    assert fields(SetPlan)[-1].name == "load_direction"
    runtime = HardwareRuntime.__new__(HardwareRuntime)
    setup = {"lower_point_mm": 300, "upper_point_mm": 900}
    assert runtime._set_plan("start_motion", {}, setup).load_direction == "down"
    plan = runtime._set_plan("start_motion", {"load_direction": "up"}, setup)
    assert (plan.load_direction, plan.start_point) == ("up", "lower")


@pytest.mark.parametrize("action", ["start_motion", "start_fixed_position", "resume", "set_load", "move_to_start"])
def test_active_set_cannot_change_direction(action):
    import threading

    runtime = HardwareRuntime.__new__(HardwareRuntime)
    runtime._lock = threading.RLock()
    runtime.motion_block_reason = lambda: None
    runtime.workout = SimpleNamespace(active=True, mode="training", load_n=20, completed_rest=False, plan=SimpleNamespace(load_direction="down"))
    with pytest.raises(WorkoutError, match="после завершения"):
        runtime.workout_command(action, {"load_direction": "up"})
    assert runtime.workout.plan.load_direction == "down"


def test_unloaded_between_sets_accepts_new_direction_without_mutating_old_plan():
    import threading

    runtime = HardwareRuntime.__new__(HardwareRuntime)
    runtime._lock = threading.RLock()
    runtime.motion_block_reason = lambda: None
    old_plan = SimpleNamespace(load_direction="down")
    start = Mock()
    runtime.workout = SimpleNamespace(active=True, mode="weightless", load_n=0, plan=old_plan, start_set=start)
    runtime._sync_state = Mock()
    runtime._record_command = Mock()
    runtime._schedule_broadcast = Mock()
    runtime.workout_command("start_motion", {"load_direction": "up"}, {"lower_point_mm": 300, "upper_point_mm": 900})
    assert start.call_args.args[0].load_direction == "up"
    assert old_plan.load_direction == "down"


def test_snapshot_direction_is_from_active_plan_not_saved_calibration():
    runtime = HardwareRuntime.__new__(HardwareRuntime)
    plan = SimpleNamespace(load_n=20, lower_mm=300, upper_mm=900, target_reps=10,
                           target_set=1, start_point="lower", fixed_mm=None, load_mode="constant", load_direction="up")
    runtime.workout = SimpleNamespace(plan=plan, active=True, load_n=20, mode="training",
                                     repetitions=lambda: (0, 0), amplitude_percent=lambda: 0, user_force_n=lambda: -40)
    motion = MotionRuntimeState()
    runtime._sync_workout(motion)
    from dataclasses import asdict
    assert MotionTelemetrySchema.model_validate(asdict(motion)).model_dump(by_alias=True)["loadDirection"] == "up"