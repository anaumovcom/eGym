"""Direction review regressions: in-process twin and mocked persistence, no IO/lifespan."""

import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.tests.motor import test_upward_load as fixtures
from app.motor.workout import WorkoutError
from app.schemas.hardware import HardwareCommandRequestSchema
from app.services import hardware_service as service_module
from app.services.hardware_runtime import HardwareRuntime
from app.services.hardware_service import HardwareService


def runtime_fixture():
    workout, _bench = fixtures._workout()
    runtime = HardwareRuntime.__new__(HardwareRuntime)
    runtime.workout = workout
    runtime._lock = threading.RLock()
    runtime.motion_block_reason = lambda: None
    runtime._sync_state = Mock()
    runtime._schedule_broadcast = Mock()
    runtime._record_command = Mock(side_effect=lambda action, payload: SimpleNamespace(id=1, status="accepted", payload=payload))
    return runtime


def moving_frame(workout):
    frame = fixtures._frame(.4, x=600)
    workout.frame = replace(frame, samples={side: replace(sample, speed_mm_s=-80) for side, sample in frame.samples.items()})


@pytest.mark.parametrize("action", ["start_motion", "start_fixed_position"])
@pytest.mark.parametrize("direction", ["down", "up"])
def test_completed_moving_rest_accepts_opposite_next_set_and_settles(action, direction):
    runtime = runtime_fixture()
    workout = runtime.workout
    workout.start_set(replace(workout.plan, load_direction=direction))
    moving_frame(workout)
    workout.complete_set()
    assert workout.mode == "paused" and workout.completed_rest and workout.load_n == 0
    old_plan = workout.plan
    opposite = "down" if direction == "up" else "up"
    command = runtime.workout_command(action, {"load_direction": opposite}, {
        "lower_point_mm": 300, "upper_point_mm": 700, "fixed_position_mm": 400,
    })
    assert old_plan.load_direction == direction
    assert workout.plan.load_direction == opposite
    assert command.payload["resolved_load_direction"] == opposite
    assert workout.mode == "moving" and workout._pending is not None
    assert workout.runner is None and workout.load_n == 0
    assert not workout.completed_rest


@pytest.mark.parametrize("action", ["start_motion", "start_fixed_position", "resume", "set_load", "move_to_start"])
def test_paused_current_set_still_rejects_direction_change(action):
    runtime = runtime_fixture()
    workout = runtime.workout
    moving_frame(workout)
    workout.pause()
    assert workout.mode == "paused" and not workout.completed_rest and workout.load_n == 0
    old_plan = workout.plan
    with pytest.raises(WorkoutError, match="после завершения"):
        runtime.workout_command(action, {"load_direction": "down"})
    assert workout.plan is old_plan and workout.plan.load_direction == "up"
    runtime._record_command.assert_not_called()


@pytest.mark.parametrize("action", ["resume", "set_load", "move_to_start"])
def test_rest_catch_does_not_allow_changing_current_plan(action):
    runtime = runtime_fixture()
    moving_frame(runtime.workout)
    runtime.workout.complete_set()
    with pytest.raises(WorkoutError, match="после завершения"):
        runtime.workout_command(action, {"load_direction": "down"})


def test_completion_must_finish_unloading_before_opposite_start():
    runtime = runtime_fixture()
    workout = runtime.workout
    fixtures._grip(workout)
    workout.complete_set()
    assert workout.mode == "training" and workout.load_n > 1 and not workout.completed_rest
    with pytest.raises(WorkoutError, match="после завершения"):
        runtime.workout_command("start_motion", {"load_direction": "down"})


@pytest.mark.parametrize("action", ["start_motion", "start_fixed_position", "resume", "set_load", "move_to_start"])
@pytest.mark.parametrize("requested", [None, "up", "down"])
def test_audit_distinguishes_explicit_direction_from_accepted_plan(monkeypatch, action, requested):
    runtime = runtime_fixture()
    # An unloaded completed rest, without application startup or a database connection.
    runtime.workout.complete_set()
    service = HardwareService()
    service.audit_repository = Mock()
    service.get_snapshot = Mock(return_value={})
    service._set_calibration = Mock(return_value={
        "lower_point_mm": 300, "upper_point_mm": 700, "fixed_position_mm": 700,
        "start_point": "upper", "load_direction": "up",
    })
    monkeypatch.setattr(service_module, "hardware_runtime", runtime)
    monkeypatch.setattr(service_module, "HardwareCommandResponseSchema", lambda **values: SimpleNamespace(**values))
    session = Mock()
    fields = {} if requested is None else {"load_direction": requested}
    service.execute_command(session, HardwareCommandRequestSchema(action=action, **fields))
    details = service.audit_repository.record.call_args.kwargs["details"]
    assert details["requested_load_direction"] == requested
    assert details["resolved_load_direction"] == runtime.workout.plan.load_direction
    expected = (requested or "up") if action.startswith("start_") else "up"
    assert details["resolved_load_direction"] == expected
    if requested is None:
        assert "load_direction" not in details
        assert "load_direction" not in runtime._record_command.call_args.args[1]
    else:
        assert details["load_direction"] == requested
    session.commit.assert_called_once()