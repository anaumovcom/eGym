"""Mid-return load continuity and runaway protection; pure core / twin, never hardware."""

from dataclasses import replace

import pytest

from app.motor.core import (
    FLOOR_K_N_PER_MM,
    FLOOR_MAX_N,
    LOAD_RELIEF_DROP_S,
    LOAD_RELIEF_RECOVER_S,
    RANGE_STOP_MM,
    MotorCore,
)
from app.motor.estimation.observer import ObservedState
from app.motor.force.load_models import LoadSetpoint
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, Tunables
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import run_core
from app.motor.twin.plant import PlantParams, SidePhysics
from app.motor.units import SIDES


def _core():
    # Rounded physical values and timing from the 22 kg pulldown incident, independent of the local database.
    side = replace(MachineProfile().left, gravity_map=Measured([(0, 165)]),
                   coulomb_up_n=Measured(58), coulomb_down_n=Measured(58),
                   viscous_n_per_mm_s=Measured(.21), moving_mass_kg=Measured(60))
    profile = replace(MachineProfile(), left=side, right=side,
                      loop_delay_s=Measured(.0735), torque_lag_s=Measured(.0479))
    core = MotorCore(profile, Tunables(), replace(SafetyEnvelope(), soft_max_mm=9000))
    core.command("ready")
    core.command("hold")
    core.command("train")
    core.release_enabled = False
    core.set_load(LoadSetpoint(load_n=22 * 9.80665 / 2, lower_mm=715.2, upper_mm=1097.4,
                              load_direction="up"))
    return core


def _update(core, v, a=0, dt=.02):
    core._dt = dt
    states = {side: ObservedState(900, v, a, 0) for side in SIDES}
    core._update_range(states)
    return core.load_relief["left"]


@pytest.mark.parametrize("v", [0, 200, 280, 350, 420])
def test_normal_upward_return_keeps_load_and_training_friction(v):
    core = _core()
    for _ in range(50):
        assert _update(core, v) == 1
    assert core._descent_gain("left", core.load.load_n) == core.tunables.train_friction_gain_down


@pytest.mark.parametrize("dt", [.01, .02, .067, .1])
def test_incident_acceleration_does_not_trigger_a_full_unload(dt):
    core = _core()
    # Log: v=364.5, a=563.5 -> predicted 432.9 mm/s, just above onset 420, well below limit 700.
    for _ in range(round(.6 / dt)):
        relief = _update(core, 364.5, 563.5, dt)
    assert .99 < relief < 1
    assert core.load_relief["left"] == core.load_relief["right"]


def test_recorded_mid_return_does_not_lose_and_reapply_the_whole_load():
    core = _core()
    core.set_load(replace(core.load, range_guard=True))
    # Rounded consecutive mid-rise frames, 00:29:43.710..00:29:44.157 in the incident log.
    frames = [(280, 507), (364.5, 563.5), (415.5, 565), (400, 445.5),
              (347.5, 260.5), (282, 101.5), (230.5, -29)]
    relief = [_update(core, v, a, dt=.075) for v, a in frames]
    assert min(relief) > .94  # previously 1 -> .46 -> 0, retained even after the bar slowed
    for _ in range(8):
        _update(core, 350, dt=.075)
    assert core.load_relief["left"] == 1


def test_normal_return_force_keeps_the_same_load_through_the_middle_of_the_range():
    core = _core()
    core.set_load(replace(core.load, range_guard=True))
    for x in (800, 850, 900):
        for v in (200, 280, 350, 420):
            states = {side: ObservedState(x, v, 0, 0) for side in SIDES}
            core._dt = .067
            core._update_range(states)
            state = states["left"]
            force = core._law("train", "left", state, state, 0)
            friction = core.friction["left"].force(v) * core.tunables.train_friction_gain_down
            assert force - core.profile.left.weight_n(x) - friction == pytest.approx(core.load.load_n)


@pytest.mark.parametrize("distance_to_top", [100, 40, 10, 1, .01, 0])
@pytest.mark.parametrize("v,a", [(100, 0), (350, 0), (400, 100), (600, 1000)])
def test_upper_range_guard_does_not_change_force_until_actual_crossing(distance_to_top, v, a):
    guarded, reference = _core(), _core()
    guarded.set_load(replace(guarded.load, range_guard=True))
    x = guarded.load.upper_mm - distance_to_top
    states = {side: ObservedState(x, v, a, 0) for side in SIDES}
    for _ in range(10):
        for core in (guarded, reference):
            core._dt = .067
            core._update_range(states)
        assert guarded.range_force_n == 0
        assert guarded.floor_cut == 0
        assert guarded.load_relief == reference.load_relief  # independent overspeed protection is retained
        for side in SIDES:
            assert guarded._law("train", side, states[side], states[side], 0) == pytest.approx(
                reference._law("train", side, states[side], states[side], 0))


@pytest.mark.parametrize("v", [100, 350, 400])
def test_upper_range_unloading_and_braking_start_only_after_crossing(v):
    core = _core()
    core.set_load(replace(core.load, range_guard=True))
    core._dt = .067
    for offset in (-40, -1, 0, .01):
        states = {side: ObservedState(core.load.upper_mm + offset, v, 0, 0) for side in SIDES}
        core._update_range(states)
        if offset <= 0:
            assert core.load_relief == {side: 1 for side in SIDES}
            assert core.floor_cut == 0
            assert core.range_force_n == 0
        else:
            assert 0 < core.load_relief["left"] < 1
            assert core.floor_cut > 0
            assert core.range_force_n < 0


def test_upper_crossing_is_judged_on_bar_mean_not_a_single_side():
    core = _core()
    core.set_load(replace(core.load, range_guard=True))
    core._dt = .067
    top = core.load.upper_mm
    core._update_range({"left": ObservedState(top + 2, 200, 0, 0),
                        "right": ObservedState(top - 4, 200, 0, 0)})
    assert core.load_relief == {side: 1 for side in SIDES}
    assert core.floor_cut == 0
    assert core.range_force_n == 0


@pytest.mark.parametrize("v", [420, 450, 490, 560, 630, 700, 800])
def test_excess_speed_gets_bounded_proportional_relief_not_an_integrating_cut(v):
    core = _core()
    expected = 1 - min(1, max(0, (v - 420) / 280)) ** 2
    for _ in range(50):
        _update(core, v)
    assert core.load_relief["left"] == pytest.approx(expected)
    for _ in range(100):
        assert _update(core, v) == pytest.approx(expected)


@pytest.mark.parametrize("dt", [.01, .02, .067, .1])
def test_runaway_prediction_still_unloads_and_recovery_does_not_wait_for_210(dt):
    core = _core()
    previous = 1.0
    for _ in range(round(.6 / dt)):
        relief = _update(core, 600, 1000, dt)  # predicts beyond the unchanged 700 mm/s ceiling
        assert 0 <= previous - relief <= dt / LOAD_RELIEF_DROP_S + 1e-12
        previous = relief
    assert relief == 0
    for _ in range(round(.6 / dt)):
        relief = _update(core, 350, 0, dt)  # inside the normal return range, but above the old rearm threshold
        assert 0 <= relief - previous <= dt / LOAD_RELIEF_RECOVER_S + 1e-12
        previous = relief
    assert relief == 1


def test_downward_load_retains_original_fast_fall_protection():
    core = _core()
    core.set_load(replace(core.load, load_direction="down"))
    for _ in range(10):
        _update(core, -250)
    assert core.load_relief == {side: 0 for side in SIDES}
    assert _update(core, -150) == 0  # old descent hysteresis unchanged
    assert _update(core, -100) == pytest.approx(.04)


@pytest.mark.parametrize("delay_ticks", [1, 2])
@pytest.mark.parametrize("user_n", [0, -80])
def test_delayed_twin_upward_runaway_is_bounded_without_unload_reload_cycles(delay_ticks, user_n):
    core = _core()
    physics = SidePhysics(weight_n=165, mass_kg=60, coulomb_up_n=58, coulomb_down_n=58,
                          viscous_n_per_mm_s=.21)
    bench = TwinBench(PlantParams(left=physics, right=physics, travel_mm=10000,
                                 command_delay_ticks=delay_ticks, torque_lag_s=.0479),
                      profiles={side: core.profile.side(side) for side in SIDES}, x0_mm=200,
                      user=lambda _t, _bench: {side: user_n for side in SIDES})
    relief = []
    trace = run_core(core, bench, 5, dt=.067, on_tick=lambda _t, _out: relief.append(core.load_relief["left"]))
    assert set(trace.mode) == {"training"}
    for side in SIDES:
        assert max(trace.v[side]) < core.envelope.max_speed_mm_s
        assert max(trace.x[side]) < core.envelope.soft_max_mm
        assert max(trace.v[side][-15:]) - min(trace.v[side][-15:]) < 30
    assert max(relief[-15:]) - min(relief[-15:]) < .1
    assert min(relief) > .1  # no repeated full-weight -> zero-weight cuts


@pytest.mark.parametrize("delay_ticks", [1, 2])
@pytest.mark.parametrize("load_n", [25, 108, 160])
def test_delayed_twin_still_catches_a_released_bar_at_the_upper_point(delay_ticks, load_n):
    core = _core()
    core.set_load(replace(core.load, load_n=load_n, range_guard=True))
    physics = SidePhysics(weight_n=165, mass_kg=60, coulomb_up_n=58, coulomb_down_n=58,
                          viscous_n_per_mm_s=.21)
    bench = TwinBench(PlantParams(left=physics, right=physics, command_delay_ticks=delay_ticks,
                                 torque_lag_s=.0479),
                      profiles={side: core.profile.side(side) for side in SIDES}, x0_mm=800, initial_raw=235)
    trace = run_core(core, bench, 8, dt=.067)
    assert set(trace.mode) == {"training"}
    # Without pre-braking, reserve space AFTER the point for the command latency and return spring.
    # This is a twin regression budget, not a guaranteed stopping distance on the real machine.
    stopping_room = (core.envelope.max_speed_mm_s * (core._loop_delay() + .067)
                     + RANGE_STOP_MM + FLOOR_MAX_N / FLOOR_K_N_PER_MM)
    for side in SIDES:
        assert max(trace.v[side]) < core.envelope.max_speed_mm_s
        assert max(trace.x[side]) < core.load.upper_mm + stopping_room
        assert max(trace.x[side]) < SafetyEnvelope().soft_max_mm
        assert core.load.upper_mm - 15 < trace.x[side][-1] < core.load.upper_mm + 15
        assert max(trace.x[side][-10:]) - min(trace.x[side][-10:]) < 2