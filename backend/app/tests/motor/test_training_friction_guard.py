"""Workout-only friction guard: independent compensation and bounded, dissipative braking."""

from dataclasses import replace

import pytest

from app.motor.estimation.friction import FrictionModel
from app.motor.estimation.observer import ObservedState
from app.motor.parameters import apply_changes
from app.motor.profile import Measured
from app.motor.store import ProfileBundle
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import run_core
from app.motor.twin.plant import PlantParams, SidePhysics
from app.motor.units import SIDES
from app.tests.motor.test_downward_load_relief import _core, _update


def _guarded(load=7.355, guard=False):
    core = _core(load, guard)
    core.tunables = replace(core.tunables, train_descent_brake_load_ratio=1,
                            train_ascent_friction_extrapolation=0, train_inertia_gain=0)
    return core


@pytest.mark.parametrize("v", [-40, -100, -200, -240])
def test_normal_descent_keeps_nominal_load(v):
    core = _guarded()
    state = _update(core, v)["left"]
    force = core._law("train", "left", state, state, 0)
    assert force == pytest.approx(165 + core.friction["left"].force(v, 8) - core.load.load_n)


@pytest.mark.parametrize("load", [7.355, 36.775, 100, 160])
@pytest.mark.parametrize("relief", [0, .25, .5, 1])
def test_separate_brake_is_dissipative_and_capped_by_nominal_load(load, relief):
    core = _guarded(load)
    state = _update(core, -300)["left"]
    core.load_relief = dict.fromkeys(SIDES, relief)
    force = core._law("train", "left", state, state, 0)
    # governor at -300 adds 10 N. The rest is nominal friction, relieved load and the explicit brake.
    full = 165 + core.friction["left"].force(-300, 8) - load * relief + 10
    brake = force - full
    # The governor's 10 N belongs to the same budget, not an additional upward force.
    assert -1e-9 <= brake + 10 <= load * relief * .5 + 1e-9
    assert (brake + 10) * state.v_mm_s <= 1e-8
    legacy = _core(load)
    legacy.load_relief = dict.fromkeys(SIDES, relief)
    assert force <= legacy._law("train", "left", state, state, 0) + 1e-8


@pytest.mark.parametrize("v,relief", [(-280, 0), (-300, .2), (-310, .35), (-315, .49), (-320, .4)])
def test_recorded_press_descent_never_requires_downward_user_force(v, relief):
    core = _guarded(36.775)
    state = _update(core, v, x=950)["left"]
    core.load_relief = dict.fromkeys(SIDES, relief)
    force = core._law("train", "left", state, state, 0)
    required_user = 165 + core.friction["left"].force(v, 8) - force
    assert required_user >= core.load.load_n * relief * .5 - 1e-8


def test_full_speed_and_lower_range_keep_emergency_braking():
    core = _guarded(36.775, True)
    state = _update(core, -400)["left"]
    core.load_relief = dict.fromkeys(SIDES, 0)
    force = core._law("train", "left", state, state, 0)
    neutral = 165 + core.friction["left"].force(-400, 8)
    assert force > neutral  # emergency may override exercise feel
    state = _update(core, -200, x=380)["left"]
    force = core._law("train", "left", state, state, 0)
    assert core.range_force_n > 0
    core.range_force_n = 0
    assert force > core._law("train", "left", state, state, 0)


def test_ascent_cap_does_not_extrapolate_unmeasured_f3_assistance():
    core = _guarded(36.775)
    side = replace(core.profile.left, friction_table_up=Measured([(40, 66), (130, 82)]))
    core.profile = replace(core.profile, left=side)
    core.friction["left"] = FrictionModel.from_profile(side, core.profile)
    slow = ObservedState(900, 130, 0, 0)
    fast = ObservedState(900, 480, 0, 0)  # below upward governor onset
    assert core._law("train", "left", fast, fast, 0) == core._law("train", "left", slow, slow, 0)
    before = core._law("weightless", "left", fast, fast, 0)
    core.tunables = replace(core.tunables, train_ascent_friction_extrapolation=1)
    assert core._law("train", "left", fast, fast, 0) > core._law("train", "left", slow, slow, 0)
    assert core._law("weightless", "left", fast, fast, 0) == before


@pytest.mark.parametrize("delay", [1, 2])
@pytest.mark.parametrize("load", [7.355, 36.775, 100, 160])
def test_released_bar_remains_bounded_and_catches_lower_point(delay, load):
    core = _guarded(load, True)
    physics = SidePhysics(weight_n=165, mass_kg=60, coulomb_up_n=58, coulomb_down_n=58,
                          viscous_n_per_mm_s=.21)
    bench = TwinBench(PlantParams(left=physics, right=physics, command_delay_ticks=delay,
                                 torque_lag_s=.0479),
                      profiles={side: core.profile.side(side) for side in SIDES},
                      x0_mm=1000, initial_raw=235)
    trace = run_core(core, bench, 12, dt=.067)
    assert set(trace.mode) == {"training"}
    for side in SIDES:
        bound = core.envelope.max_descent_mm_s if load <= 100 else 450
        assert min(trace.v[side]) > -bound
        assert core.envelope.soft_min_mm < min(trace.x[side])
        assert max(trace.x[side]) < 1005  # no spontaneous upward launch
        assert trace.x[side][-1] < core.load.lower_mm + 40
        assert max(abs(v) for v in trace.v[side][-15:]) < 20


def test_settings_roundtrip_and_validation():
    changes = [{"scope": "tunables", "key": "train_descent_brake_load_ratio", "value": 1},
               {"scope": "tunables", "key": "train_ascent_friction_extrapolation", "value": 0}]
    bundle = apply_changes(ProfileBundle(), changes)
    restored = ProfileBundle.from_dict(bundle.to_dict())
    assert restored.tunables.train_descent_brake_load_ratio == 1
    assert restored.tunables.train_ascent_friction_extrapolation == 0
    assert ProfileBundle.from_dict({}).tunables.train_descent_brake_load_ratio is None
    assert ProfileBundle.from_dict({}).tunables.train_ascent_friction_extrapolation == 1
    for key, bad in [("train_descent_brake_load_ratio", 0), ("train_descent_brake_load_ratio", 4),
                     ("train_ascent_friction_extrapolation", -1), ("train_ascent_friction_extrapolation", 2)]:
        for value in [bad, float("nan"), float("inf")]:
            with pytest.raises(ValueError):
                apply_changes(bundle, [{"scope": "tunables", "key": key, "value": value}])


def test_light_set_preserves_more_load_at_constant_eccentric_speed():
    core = _guarded(36.775)
    for _ in range(20):
        _update(core, -344, a=0)
    legacy_target = 1 - (344 - 240) / 160
    assert core.load_relief["left"] > legacy_target + .1
    assert core.load_relief["left"] < 1  # speed protection remains active


def test_stale_acceleration_does_not_keep_slowing_light_bar_unloaded():
    core = _guarded(36.775)
    core.load_relief = dict.fromkeys(SIDES, 0)
    _update(core, -380, -900)
    values = []
    for v, a in [(-360, -700), (-345, -500), (-330, -350), (-315, -220)]:
        _update(core, v, a)
        values.append(core.load_relief["left"])
    assert values[1] > 0
    assert values[-1] > .5


def test_heavy_set_keeps_original_linear_prediction_and_reset_clears_history():
    core = _guarded(160)
    for _ in range(10):
        _update(core, -330, -100)
    prediction = core._loop_delay() + .067 + .15 / 2
    expected = 1 - (330 + 100 * prediction - 240) / 160
    assert core.load_relief["left"] == pytest.approx(expected)
    core.command("pause")
    assert core._descent_previous_v is None


def test_configured_descent_onset_and_limit():
    core = _guarded(36.775)
    core.tunables = replace(core.tunables, train_descent_relief_onset_mm_s=350)
    core.envelope = replace(core.envelope, max_descent_mm_s=600)
    for _ in range(20):
        _update(core, -350)
    assert core.load_relief["left"] == 1
    for _ in range(20):
        _update(core, -475)
    assert 0 < core.load_relief["left"] < 1
    for _ in range(20):
        _update(core, -600)
    assert core.load_relief["left"] == 0


def test_descent_onset_setting_roundtrip_and_bounds():
    key = "train_descent_relief_onset_mm_s"
    bundle = apply_changes(ProfileBundle(), [{"scope": "tunables", "key": key, "value": 350}])
    assert ProfileBundle.from_dict(bundle.to_dict()).tunables.train_descent_relief_onset_mm_s == 350
    assert ProfileBundle.from_dict({}).tunables.train_descent_relief_onset_mm_s is None
    for value in [0, 1000, float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            apply_changes(bundle, [{"scope": "tunables", "key": key, "value": value}])


@pytest.mark.parametrize("delay", [1, 2, 3])
@pytest.mark.parametrize("load", [7.355, 36.775, 100, 160])
@pytest.mark.parametrize("onset,limit", [(350, 600), (450, 700)])
def test_configured_descent_released_bar(delay, load, onset, limit):
    core = _guarded(load, True)
    core.tunables = replace(core.tunables, train_descent_relief_onset_mm_s=onset)
    core.envelope = replace(core.envelope, max_descent_mm_s=limit)
    physics = SidePhysics(weight_n=165, mass_kg=60, coulomb_up_n=58, coulomb_down_n=58,
                          viscous_n_per_mm_s=.21)
    bench = TwinBench(PlantParams(left=physics, right=physics, command_delay_ticks=delay,
                                 torque_lag_s=.0479),
                      profiles={side: core.profile.side(side) for side in SIDES},
                      x0_mm=1000, initial_raw=235)
    trace = run_core(core, bench, 12, dt=.067)
    assert set(trace.mode) == {"training"}
    for side in SIDES:
        assert min(trace.v[side]) > -limit
        assert min(trace.x[side]) > core.envelope.soft_min_mm
        assert max(trace.x[side]) < 1005
        assert trace.x[side][-1] < core.load.lower_mm + 40
        assert max(abs(v) for v in trace.v[side][-15:]) < 20


def test_soft_landing_brake_is_local_capped_and_yields_to_hands():
    core = _guarded(36.775, True)
    core.tunables = replace(core.tunables, train_landing_brake_max_n=40)
    _update(core, -500, x=1100)
    assert core.range_force_n == 0
    _update(core, -500, x=480)
    brake = core.range_force_n
    assert 0 < brake <= 40
    _update(core, -500, a=2000, x=480)
    assert core.range_force_n < brake
    _update(core, 100, x=480)
    assert core.range_force_n == 0


def test_top_breakaway_wait_is_shorter_without_more_force_or_upward_help():
    core = _guarded(7.355, True)
    core.tunables = replace(core.tunables, train_fall_rest_s=.1)
    core._bar_x_mm = core.load.upper_mm
    core._dt = .067
    core._still_s = dict.fromkeys(SIDES, .11)
    state = ObservedState(core.load.upper_mm, 0, 0, 0)
    assert 0 < core._fall_assist("left", state, core.load.load_n) <= 120 * .067
    core.tunables = replace(core.tunables, train_fall_rest_s=.2)
    core.fall_assist = dict.fromkeys(SIDES, 0)
    assert core._fall_assist("left", state, core.load.load_n) == 0


@pytest.mark.parametrize("delay", [1, 2, 3])
@pytest.mark.parametrize("load", [7.355, 36.775, 100, 160])
def test_soft_landing_reduces_or_preserves_runout(delay, load):
    minima = []
    for brake in [0, 40]:
        core = _guarded(load, True)
        core.tunables = replace(core.tunables, train_landing_brake_max_n=brake,
                                train_fall_rest_s=.1, train_descent_relief_onset_mm_s=450)
        core.envelope = replace(core.envelope, max_descent_mm_s=700)
        physics = SidePhysics(weight_n=165, mass_kg=60, coulomb_up_n=58, coulomb_down_n=58,
                              viscous_n_per_mm_s=.21)
        bench = TwinBench(PlantParams(left=physics, right=physics, command_delay_ticks=delay,
                                     torque_lag_s=.0479),
                          profiles={side: core.profile.side(side) for side in SIDES},
                          x0_mm=1000, initial_raw=235)
        trace = run_core(core, bench, 12, dt=.067)
        minima.append(min(min(trace.x[side]) for side in SIDES))
        for side in SIDES:
            assert min(trace.v[side]) > -700
            assert min(trace.x[side]) > core.envelope.soft_min_mm
            assert max(trace.x[side]) < 1005
            assert abs(trace.x[side][-1] - core.load.lower_mm) < 40
            assert max(abs(v) for v in trace.v[side][-15:]) < 20
    assert minima[1] >= minima[0] - 1