"""Exercise-only load calibration and equal effort in both phases; no hardware I/O."""

from dataclasses import replace

import pytest

from app.motor.core import MotorCore
from app.motor.estimation.observer import ObservedState
from app.motor.force.load_models import LoadSetpoint
from app.motor.parameters import apply_changes
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, Tunables
from app.motor.store import ProfileBundle
from app.motor.twin.bench import TwinBench
from app.motor.twin.plant import PlantParams
from app.motor.units import G
from app.motor.workout import WorkoutController, per_side_n
from app.services.hardware_runtime import HardwareRuntime, MotionRuntimeState


@pytest.mark.parametrize("direction", ["up", "down"])
@pytest.mark.parametrize("weight", [0, 10, 20, 40])
def test_exercise_scale_applies_once_to_plan_change_and_display(direction, weight):
    tunables = replace(Tunables(), exercise_load_scale=0.5)
    bench = TwinBench(PlantParams(), x0_mm=500)
    workout = WorkoutController(bench.drives, MachineProfile(), tunables, SafetyEnvelope())
    # Only exercise plan / telemetry helpers: do not start a move or contact the real runtime singleton.
    runtime = object.__new__(HardwareRuntime)
    runtime.workout = workout
    calibration = {"lower_point_mm": 300, "upper_point_mm": 700, "load_direction": direction}
    plan = runtime._set_plan("start_motion", {"weight_kg": weight}, calibration)
    assert plan.load_n == pytest.approx(weight * G / 4)
    workout.plan = plan
    workout.set_load(weight)
    assert workout.plan.load_n == plan.load_n
    workout.core = MotorCore(workout.profile, tunables)
    workout._set_core_load(plan.load_n)
    workout.mode = "training"
    motion = MotionRuntimeState()
    runtime._sync_workout(motion)
    assert motion.load_target_kg == weight
    assert motion.load_effective_kg == weight
    assert workout.core.virtual_mass_kg == pytest.approx(weight / 4)
    # Repeated edits never multiply an already-scaled setpoint.
    workout.set_load(weight)
    assert workout.plan.load_n == plan.load_n


@pytest.mark.parametrize("direction", ["up", "down"])
@pytest.mark.parametrize("speed", [40.0, 100.0, 150.0])
def test_equal_training_effort_after_compensating_directional_friction(direction, speed):
    profile = MachineProfile()
    tunables = replace(Tunables(), train_friction_gain_resist=1, train_friction_gain_down=1)
    core = MotorCore(profile, tunables)
    core.set_load(LoadSetpoint(load_n=100, load_direction=direction))
    core._bar_x_mm = 500
    sign = 1 if direction == "down" else -1
    felt = []
    for velocity in [speed, -speed]:
        core._bar_v_mm_s = velocity
        state = ObservedState(500, velocity, 0, 0)
        force = core._law("train", "left", state, state, 0)
        friction = core.friction["left"].force(velocity)
        # At constant velocity the user supplies W + F_friction - F_motor.
        felt.append(sign * (profile.left.weight_n(500) + friction - force))
    # The smooth sign at reversal leaves <0.01 N at 40 mm/s; do not remove that smoothing.
    assert felt == pytest.approx([100, 100], abs=0.01)


def test_exercise_settings_do_not_change_weightless_or_calibration_scale():
    profile = replace(MachineProfile(), weightless_gain_up=Measured(0.7, None, "measured"))
    old = MotorCore(profile)
    new = MotorCore(profile, replace(Tunables(), exercise_load_scale=0.5, train_friction_gain_resist=1, train_friction_gain_down=1))
    for velocity in [-100, 0, 100]:
        state = ObservedState(500, velocity, 0, 0)
        assert new._law("weightless", "left", state, state, 0) == old._law("weightless", "left", state, state, 0)
    assert new.profile == old.profile
    assert per_side_n(20) == pytest.approx(10 * G)


def test_load_scale_is_persisted_and_validated():
    bundle = apply_changes(ProfileBundle(), [{"scope": "tunables", "key": "exercise_load_scale", "value": 0.5}])
    assert ProfileBundle.from_dict(bundle.to_dict()).tunables.exercise_load_scale == 0.5
    assert ProfileBundle.from_dict({}).tunables.exercise_load_scale == 1
    for invalid in [0, -0.5, float("nan"), float("inf"), 3]:
        with pytest.raises(ValueError):
            apply_changes(bundle, [{"scope": "tunables", "key": "exercise_load_scale", "value": invalid}])