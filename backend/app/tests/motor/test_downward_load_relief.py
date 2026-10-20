"""Light eccentric load continuity and runaway checks, entirely offline."""

from dataclasses import replace

import pytest

from app.motor.core import DESCENT_RELIEF_RECOVER_S, LOAD_RELIEF_DROP_S, MotorCore
from app.motor.estimation.observer import ObservedState
from app.motor.force.load_models import LoadSetpoint
from app.motor.profile import MachineProfile, Measured, Tunables
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import run_core
from app.motor.twin.plant import PlantParams, SidePhysics
from app.motor.units import SIDES


def _core(load=7.355, guard=False):
    side = replace(MachineProfile().left, gravity_map=Measured([(0, 165)]),
                   coulomb_up_n=Measured(58), coulomb_down_n=Measured(58),
                   viscous_n_per_mm_s=Measured(.21), moving_mass_kg=Measured(60))
    profile = replace(MachineProfile(), left=side, right=side,
                      loop_delay_s=Measured(.0735), torque_lag_s=Measured(.0479))
    core = MotorCore(profile, replace(Tunables(), train_friction_gain_down=1,
                                     train_friction_gain_resist=1, exercise_load_scale=.5))
    core.command("ready")
    core.command("hold")
    core.command("train")
    core.release_enabled = False
    core.set_load(LoadSetpoint(load_n=load, lower_mm=400, upper_mm=1200, range_guard=guard))
    return core


def _update(core, v, a=0, dt=.067, x=900):
    core._dt = dt
    states = {side: ObservedState(x, v, a, 0) for side in SIDES}
    core._update_range(states)
    return states


@pytest.mark.parametrize("v", [-40, -100, -160, -200, -240])
def test_light_load_is_not_eaten_by_friction_at_normal_descent(v):
    core = _core()
    state = _update(core, v)["left"]
    force = core._law("train", "left", state, state, 0)
    required_user = core.profile.left.weight_n(900) + core.friction["left"].force(v) - force
    assert required_user == pytest.approx(core.load.load_n, abs=.01)
    assert core.load_relief["left"] == 1


@pytest.mark.parametrize("dt", [.01, .02, .067, .1])
def test_fast_descent_unloads_then_recovers_without_waiting_for_120(dt):
    core = _core()
    previous = 1
    for _ in range(round(.6 / dt)):
        _update(core, -350, -1000, dt)
        relief = core.load_relief["left"]
        assert 0 <= previous - relief <= dt / LOAD_RELIEF_DROP_S + 1e-12
        previous = relief
    assert relief == 0
    for _ in range(round(.6 / dt)):
        _update(core, -180, 0, dt)
        relief = core.load_relief["left"]
        assert 0 <= relief - previous <= dt / DESCENT_RELIEF_RECOVER_S + 1e-12
        previous = relief
    assert relief == 1


def test_incident_slowdown_recovers_before_midrange_stop():
    core = _core()
    core.load_relief = dict.fromkeys(SIDES, 0)
    # 12:45:18.026 onward: previously relief stayed zero down to -123 mm/s.
    for v, a in [(-256, -297), (-218, -184), (-187, -104), (-155, -36), (-123, 28)]:
        _update(core, v, a, dt=.083)
    assert core.load_relief["left"] > .8
    assert core.floor_cut == 0 and core.range_force_n == 0


def test_five_kg_incident_recovers_before_slow_midrange_segment():
    core = _core(load=5 * 9.80665 * .5 / 2)
    core.load_relief = dict.fromkeys(SIDES, 0)
    # Latest set, 13:27:51.132..51.347: previously .13/.33/.46/.60 and only 1 at51.548.
    values = []
    for v, a, dt in [(-249, -216.5, .082), (-217.5, -126.5, .081),
                     (-199, -73, .067), (-184.5, -29.5, .067)]:
        _update(core, v, a, dt=dt)
        values.append(core.load_relief["left"])
    assert values[1] > .85
    assert values[2:] == [1, 1]
    assert core.floor_cut == 0 and core.range_force_n == 0


def test_heavy_load_keeps_conservative_recovery():
    core = _core(load=100)
    core.load_relief = dict.fromkeys(SIDES, 0)
    _update(core, -180, dt=.067)
    assert core.load_relief["left"] == pytest.approx(.067 / .5)


def test_zero_load_and_full_speed_relief_keep_residual_friction():
    core = _core(0)
    assert core._descent_gain("left", 0) == core.tunables.friction_gain_down
    core = _core()
    for _ in range(10):
        _update(core, -400)
    assert core.load_relief == dict.fromkeys(SIDES, 0)
    assert core._descent_gain("left", 0) == core.tunables.friction_gain_down


@pytest.mark.parametrize("delay", [1, 2])
@pytest.mark.parametrize("load", [7.355, 25, 100, 160])
def test_released_bar_continues_down_and_is_caught_at_lower_point(delay, load):
    core = _core(load, guard=True)
    physics = SidePhysics(weight_n=165, mass_kg=60, coulomb_up_n=58, coulomb_down_n=58,
                          viscous_n_per_mm_s=.21)
    bench = TwinBench(PlantParams(left=physics, right=physics, command_delay_ticks=delay,
                                 torque_lag_s=.0479),
                      profiles={side: core.profile.side(side) for side in SIDES},
                      x0_mm=1000, initial_raw=235)
    trace = run_core(core, bench, 12, dt=.067)
    assert set(trace.mode) == {"training"}
    for side in SIDES:
        assert min(trace.x[side]) > core.envelope.soft_min_mm
        # At 160 N the force slew + two delayed frames allow a transient above the soft 400 mm/s target.
        # Bound it below 450 (original binary-relief twin ~447), never by raising the configured limit.
        bound = core.envelope.max_descent_mm_s if load <= 100 else 450
        assert min(trace.v[side]) > -bound
        assert trace.x[side][-1] < core.load.lower_mm + 40
        assert max(abs(v) for v in trace.v[side][-15:]) < 20


def test_loaded_ascent_force_keeps_existing_gain():
    core = _core()
    state = _update(core, 100)["left"]
    force = core._law("train", "left", state, state, 0)
    gain = .6 + .4 * core.load.load_n / 58
    assert force == pytest.approx(165 + core.friction["left"].force(100) * gain - core.load.load_n)