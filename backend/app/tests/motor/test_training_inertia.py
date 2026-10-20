"""Explicit exercise inertia settings must override F1/F2, without changing calibration physics."""

from dataclasses import replace

import pytest

from app.motor.core import MotorCore
from app.motor.estimation.observer import ObservedState
from app.motor.force.load_models import LoadSetpoint
from app.motor.parameters import apply_changes
from app.motor.profile import MachineProfile, Measured, Tunables
from app.motor.store import ProfileBundle
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import run_core
from app.motor.twin.plant import PlantParams, SidePhysics
from app.motor.units import SIDES


def _core(gain=None, table=False, load=36.775):
    side = replace(MachineProfile().left, gravity_map=Measured([(0, 165)]),
                   moving_mass_kg=Measured(60), coulomb_up_n=Measured(58),
                   coulomb_down_n=Measured(58), viscous_n_per_mm_s=Measured(.21))
    profile = replace(MachineProfile(), left=side, right=side, inertia_ratio_max=Measured(.72),
                      inertia_table=Measured([(0, .8), (200, .8)] if table else None))
    core = MotorCore(profile, replace(Tunables(), train_inertia_gain=gain, inertia_gain=0,
                                     train_friction_gain_resist=1, train_friction_gain_down=1))
    core.set_load(LoadSetpoint(load_n=load, lower_mm=888.4, upper_mm=1403.4))
    core._bar_x_mm = 1100
    return core


def _force(core, v, a):
    state = ObservedState(1100, v, a, 0)
    core._bar_a_mm_s2 = a
    core._bar_v_mm_s = v
    return core._law("train", "left", state, state, 0)


@pytest.mark.parametrize("table", [False, True])
@pytest.mark.parametrize("v,a", [(397.5, 674.5), (522, 682), (-150, 500), (-200, -400)])
def test_explicit_zero_removes_acceleration_feedback_despite_calibration(table, v, a):
    old, new = _core(table=table), _core(gain=0, table=table)
    assert old.inertia_share("left") > .7  # inertia_gain=0 did not switch off F1/F2
    assert _force(new, v, a) == pytest.approx(_force(new, v, 0))
    mass = 60 - old.virtual_mass_kg
    assert _force(old, v, a) - _force(new, v, a) == pytest.approx(mass * a / 1000 * old.inertia_share("left"))
    assert old.profile == new.profile


def test_zero_disables_even_added_virtual_mass():
    core = _core(gain=0, load=650)
    assert core.virtual_mass_kg > 60
    assert _force(core, 100, 500) == _force(core, 100, 0)


def test_calibration_override_and_other_modes_remain_unchanged():
    old, new = _core(), _core(gain=0)
    for output in ("weightless", "idle", "hold", "calibrate"):
        state = ObservedState(1100, 100, 500, 0)
        assert old._law(output, "left", state, state, 0) == new._law(output, "left", state, state, 0)
    old.inertia_override = new.inertia_override = .4
    assert _force(old, 100, 500) == _force(new, 100, 500)


def test_setting_roundtrip_and_bounds():
    bundle = apply_changes(ProfileBundle(), [{"scope": "tunables", "key": "train_inertia_gain", "value": 0}])
    assert ProfileBundle.from_dict(bundle.to_dict()).tunables.train_inertia_gain == 0
    assert ProfileBundle.from_dict({}).tunables.train_inertia_gain is None
    for value in (-1, 2, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            apply_changes(bundle, [{"scope": "tunables", "key": "train_inertia_gain", "value": value}])


@pytest.mark.parametrize("delay", [1, 2])
@pytest.mark.parametrize("weight_kg", [8, 15])
def test_released_press_descends_without_self_lift_and_stays_bounded(delay, weight_kg):
    core = _core(gain=0, load=weight_kg * 9.80665 * .5 / 2)
    core.set_load(replace(core.load, range_guard=True))
    core.command("ready")
    core.command("hold")
    core.command("train")
    core.release_enabled = False
    physics = SidePhysics(weight_n=165, mass_kg=60, coulomb_up_n=58, coulomb_down_n=58,
                          viscous_n_per_mm_s=.21)
    bench = TwinBench(PlantParams(left=physics, right=physics, command_delay_ticks=delay,
                                 torque_lag_s=.0479),
                      profiles={side: core.profile.side(side) for side in SIDES},
                      x0_mm=1300, initial_raw=233)
    trace = run_core(core, bench, 12, dt=.067)
    assert set(trace.mode) == {"training"}
    for side in SIDES:
        assert max(trace.x[side]) < 1305  # no user push: the exercise must not lift the bar by itself
        assert min(trace.v[side]) > -core.envelope.max_descent_mm_s
        assert core.envelope.soft_min_mm < min(trace.x[side])
        assert trace.x[side][-1] < core.load.lower_mm + 40
        assert max(abs(v) for v in trace.v[side][-15:]) < 20