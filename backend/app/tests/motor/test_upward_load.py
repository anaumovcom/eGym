"""Upward motor load: deterministic laws and an in-process twin, never hardware/API."""

from dataclasses import replace

import pytest

from app.motor.calibration.runner import Frame
from app.motor.core import FLOOR_K_N_PER_MM, FLOOR_MAX_N, RANGE_STOP_MM, UPWARD_TOP_EXTRA_MM, CoreOutput, MotorCore
from app.motor.drive.protocol import DriveSample
from app.motor.estimation.observer import ObservedState
from app.motor.estimation.user_force import UserForceEstimate
from app.motor.force.load_models import LoadSetpoint, load_force, phase_multiplier
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, Tunables
from app.motor.supervisor.modes import Mode
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import run_core
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES, force_to_raw
from app.motor.workout import SetPlan, WorkoutController, WorkoutError


def _states(x=500.0, v=0.0, a=0.0):
    return {side: ObservedState(x, v, a, 0.0) for side in SIDES}


def _core(load=100.0, **kwargs):
    core = MotorCore(MachineProfile())
    core.command("ready")
    core.command("hold")
    core.command("train")
    core.release_enabled = False
    core.set_load(LoadSetpoint(load_n=load, lower_mm=300, upper_mm=700, load_direction="up", **kwargs))
    core._dt = 0.02
    return core


def _frame(t=0.0, x=700.0):
    return Frame(t, {side: DriveSample(side, t, ok=True, position_mm=x) for side in SIDES})


def _workout():
    bench = TwinBench(PlantParams(), x0_mm=700)
    workout = WorkoutController(bench.drives, MachineProfile(), Tunables(), SafetyEnvelope())
    workout.frame = _frame()
    workout.start_set(SetPlan(300, 700, 100, start_point="upper", load_direction="up"))
    assert workout.core is not None
    return workout, bench


def _grip(workout, force=-80.0):
    estimate = UserForceEstimate(force / 2, force / 2, force / 2, "moving")
    workout.output = CoreOutput("force", {}, Mode.HOLD, _states(700), {side: estimate for side in SIDES})
    workout._watch_grip(_frame())
    workout._watch_grip(_frame(0.21))


def test_defaults_and_positional_callers_remain_down():
    assert SetPlan(300, 700, 100, "constant", "upper", 10, 1, None).load_direction == "down"
    assert LoadSetpoint("constant", 100, .7, 1.2, 300, 700, 1, 1, True).load_direction == "down"
    core = _core()
    core.set_load(LoadSetpoint(load_n=100))
    state = _states()["left"]
    assert core._law("train", "left", state, state, 0) == pytest.approx(core.profile.left.weight_n(500) - 100)
    core.set_load(LoadSetpoint(load_n=-50))  # legacy D5 reference mass, not an upward workout plan
    assert core.load.load_n == -50


@pytest.mark.parametrize("mode,effort,returning", [("constant", 1, 1), ("assist_up", .7, 1), ("eccentric", 1, 1.2)])
def test_phase_models_follow_effort_direction(mode, effort, returning):
    point = LoadSetpoint(mode=mode, load_n=100, load_direction="up")
    assert phase_multiplier(point, "down") == effort
    assert phase_multiplier(point, "up") == returning
    assert load_force(point, 500, 0) == pytest.approx(100 * returning)
    assert load_force(point, 500, 1) == pytest.approx(100 * effort)


def test_curve_stays_in_physical_position_coordinates():
    point = LoadSetpoint(mode="curve", load_n=100, lower_mm=300, upper_mm=700, curve_start=.5, curve_end=2, load_direction="up")
    assert load_force(point, 300, 0) == 50
    assert load_force(point, 700, 1) == 200


def test_upward_force_is_gravity_plus_load_and_twin_rises():
    core = _core()
    state = _states()["left"]
    assert core._law("train", "left", state, state, 0) == pytest.approx(core.profile.left.weight_n(500) + 100)
    bench = TwinBench(PlantParams(), x0_mm=500, initial_raw=100)
    trace = run_core(core, bench, .7)
    assert all(trace.x[side][-1] > 520 and max(trace.v[side]) > 20 for side in SIDES)
    assert set(trace.mode) == {"training"}


@pytest.mark.parametrize("load", [25.0, 100.0])
def test_released_upward_load_settles_at_upper_bound_on_twin(load):
    core = _core(load=load, range_guard=True)
    bench = TwinBench(PlantParams(), x0_mm=500, initial_raw=100)
    trace = run_core(core, bench, 8)
    # Stopping now starts AFTER the crossing, not in a predicted landing zone before the exercise point.
    # Account for a delayed command and the bounded return spring's travel, not the old anticipatory 60 mm.
    stopping_room = (core.envelope.max_speed_mm_s * (core._loop_delay() + .02)
                     + RANGE_STOP_MM + FLOOR_MAX_N / FLOOR_K_N_PER_MM)
    for side in SIDES:
        assert max(trace.x[side]) < core.load.upper_mm + UPWARD_TOP_EXTRA_MM + stopping_room
        assert max(trace.x[side]) < core.envelope.soft_max_mm
        assert 685 < trace.x[side][-1] < 725
        assert max(abs(x - trace.x[side][-1]) for x in trace.x[side][-10:]) < 2
    assert set(trace.mode) == {"training"}


@pytest.mark.parametrize("x,v,sign", [(720, 80, -1), (280, -80, 1)])
def test_range_guard_brakes_both_bounds(x, v, sign):
    core = _core(range_guard=True)
    core._update_range(_states(x, v))
    assert sign * core.range_force_n > 0
    assert core.floor_cut > 0 if x > 700 else core.floor_cut == 0
    assert core.load_relief["left"] == core.load_relief["right"]


def test_upper_range_cut_ramps_and_rearms_only_inside_hysteresis():
    core = _core(range_guard=True)
    core._update_range(_states(710))
    core._update_range(_states(710))
    cut = core.floor_cut
    core._update_range(_states(695))
    assert core.floor_cut == cut
    core._update_range(_states(680, -20))
    assert core.floor_cut < cut
    assert core.range_force_n == 0  # pulling back down must not trigger an upward return damper


@pytest.mark.parametrize("x", [680, 695, 700, 705, 720])
@pytest.mark.parametrize("v", [-10, -30, -80, -200])
def test_upper_range_guard_does_not_kick_up_when_pulled_back_down(x, v):
    core = _core(range_guard=True)
    for _ in range(20):
        core._update_range(_states(720))  # unload above the upper point
    assert core.floor_cut > 0
    core._update_range(_states(x, v))
    assert core.range_force_n <= 0  # brake / return spring may push down, never kick up


def test_downward_load_keeps_lower_range_return_damper():
    core = _core(range_guard=True)
    core.set_load(replace(core.load, load_direction="down"))
    for _ in range(20):
        core._update_range(_states(280))
    core._update_range(_states(320, 80))
    assert core.floor_cut > 0
    assert core.range_force_n < 0  # the normal load still brakes an unloaded bar coasting up


def test_upward_relief_uses_asymmetric_max_speed_and_predicted_acceleration():
    core = _core()
    core.envelope = replace(core.envelope, max_speed_mm_s=600, max_descent_mm_s=100)
    core._update_range(_states(v=100))
    assert core.load_relief["left"] == 1  # not the downward threshold (60)
    for _ in range(8):
        core._update_range(_states(v=350, a=1000))  # ahead > 360
    target = 1 - ((350 + 1000 * core._loop_delay() - 360) / 240) ** 2
    assert core.load_relief == {side: pytest.approx(target) for side in SIDES}
    for _ in range(8):
        core._update_range(_states(v=600))
    assert core.load_relief == {side: 0 for side in SIDES}
    core._update_range(_states(v=0))
    assert core.load_relief["left"] == pytest.approx(.04)


@pytest.mark.parametrize("mode,factor", [("constant", 1), ("eccentric", 1.2), ("curve", 2)])
def test_upward_cap_reserves_worst_gravity_friction_and_model_peak(mode, factor):
    profile = MachineProfile()
    side = replace(profile.left, gravity_map=Measured([(0, 70), (1000, 150)]), n_per_raw=Measured(1), coulomb_up_n=Measured(50), viscous_n_per_mm_s=Measured(0), pull_scale=Measured(.1))
    core = MotorCore(replace(profile, left=side, right=side), Tunables(train_friction_gain_down=1), envelope=replace(SafetyEnvelope(), max_force_n_per_side=500, max_raw=400))
    assert core.load_limit_n("up") == 160  # 400 - 150 - 50 - 40; N1 pull scale is irrelevant
    core.set_load(LoadSetpoint(mode=mode, load_n=1000, curve_end=2, load_direction="up"))
    assert core.load_capped
    assert core.load.load_n == pytest.approx(160 / factor)
    assert max(load_force(core.load, x, blend) for x in (0, 1000) for blend in (0, 1)) <= 160


def test_no_upward_headroom_means_zero_load():
    core = MotorCore(MachineProfile(), envelope=replace(SafetyEnvelope(), max_force_n_per_side=20))
    core.set_load(LoadSetpoint(load_n=100, load_direction="up"))
    assert core.load_capped and core.load.load_n == 0


def test_upward_cap_reserves_calibrated_table_before_raw_saturation():
    profile = MachineProfile()
    side = replace(profile.left, gravity_map=Measured([(0, 150)]), n_per_raw=Measured(1),
                   coulomb_up_n=Measured(50), viscous_n_per_mm_s=Measured(0),
                   friction_table_up=Measured([(100, 160)]))
    core = MotorCore(replace(profile, left=side, right=side),
                     envelope=replace(SafetyEnvelope(), max_force_n_per_side=500, max_raw=400))
    core.set_load(LoadSetpoint(load_n=1000, load_direction="up"))
    state = _states(v=100)["left"]
    target = core._law("train", "left", state, state, 0)
    assert 0 < target <= 360  # positive force before the final safety/raw clamp, with 10% headroom
    assert core.load.load_n == pytest.approx(58)  # 400 - 150 - .95 * 160 - 40
    assert force_to_raw(target, 1, 1) <= core.envelope.max_raw


@pytest.mark.parametrize("mode", ["constant", "assist_up", "eccentric", "curve"])
@pytest.mark.parametrize("track", [True, False])
def test_upward_cap_bounds_full_law_at_profile_and_phase_peaks(mode, track):
    profile = MachineProfile()
    side = replace(profile.left, gravity_map=Measured([(0, 70), (700, 100), (1380, 150)]),
                   n_per_raw=Measured(1), coulomb_up_n=Measured(30),
                   friction_table_up=Measured([(20, 35), (100, 120), (160, 40)]),
                   viscous_n_per_mm_s=Measured(.02), friction_load_up=Measured(.12),
                   friction_load_down=Measured(.2), screw_ripple_n=Measured(8),
                   screw_ripple_phase_rad=Measured(.37),
                   friction_map=Measured([(20, 2), (517, 18), (1380, 4)] if track else None))
    machine = replace(profile, left=side, right=replace(side, n_per_raw=Measured(1.1)),
                      track_comp_gain=Measured(.8), friction_load_gain=Measured(.7),
                      tight_spots=Measured([(509, 10), (525, 15)]))
    core = MotorCore(machine, Tunables(friction_gain_up=.65, train_friction_gain_down=.95),
                     replace(SafetyEnvelope(), max_force_n_per_side=500, max_raw=400))
    core.set_load(LoadSetpoint(mode=mode, load_n=1000, alpha=1.4, beta=1.8,
                              lower_mm=20, upper_mm=1380, curve_start=2, curve_end=.5,
                              load_direction="up"))
    assert core.load_capped and core.load.load_n > 0
    for motor_side in SIDES:
        for previous in (0, 400, -400):
            core.previous[motor_side] = previous
            for x in (20, 494, 510, 517, 524, 540, 700, 1380):
                for v in (0, .5, 20, 100, 160, 280, 420, 700):
                    core._bar_v_mm_s = v
                    state = _states(x, v)[motor_side]
                    for blend in (0, .5, 1):
                        target = core._law("train", motor_side, state, state, blend)
                        assert 0 < target <= 400, (motor_side, previous, x, v, blend, target)
                        assert abs(force_to_raw(target, machine.side(motor_side).n_per_raw_value, 1)) <= 400


def test_upward_cap_uses_max_push_feedback_not_requested_load_for_friction():
    profile = MachineProfile()
    side = replace(profile.left, gravity_map=Measured([(20, 70), (1380, 150)]), n_per_raw=Measured(1),
                   coulomb_up_n=Measured(30), viscous_n_per_mm_s=Measured(0),
                   friction_load_up=Measured(.5), friction_load_down=Measured(.1))
    core = MotorCore(replace(profile, left=side, right=side), Tunables(train_friction_gain_down=1),
                     replace(SafetyEnvelope(), max_raw=400))
    assert core.load_limit_n("up") == pytest.approx(15)  # 400 - 150 - (30 + .5 * (400 - 70)) - 40
    core.set_load(LoadSetpoint(load_n=1000, load_direction="up"))
    core.previous["left"] = 400
    state = _states(1380, 100)["left"]
    assert core._law("train", "left", state, state, 0) <= 400


@pytest.mark.parametrize("table", [None, [(100, 60), (200, 20), (10000, 10000)]])
def test_upward_cap_limits_reserve_to_supported_motion_domain(table):
    profile = MachineProfile()
    side = replace(profile.left, gravity_map=Measured([(0, 100), (20, 100), (1380, 100), (5000, 10000)]),
                   n_per_raw=Measured(1), coulomb_up_n=Measured(20), viscous_n_per_mm_s=Measured(.2),
                   friction_table_up=Measured(table), friction_map=Measured([(20, 0), (1380, 0), (5000, 10000)]))
    core = MotorCore(replace(profile, left=side, right=side, track_comp_gain=Measured(1)),
                     Tunables(friction_gain_up=1, train_friction_gain_down=1),
                     replace(SafetyEnvelope(), max_speed_mm_s=200, max_raw=400, overspeed_rpm_alarm=10000))
    assert core.load_limit_n("up") == pytest.approx(200)  # peak F=60 inside 20..1380 mm / 0..200 mm/s


def test_upward_cap_samples_stribeck_interior_and_soft_endpoint_peaks():
    profile = MachineProfile()
    side = replace(profile.left, gravity_map=Measured([(20, 100)]), n_per_raw=Measured(1),
                   coulomb_up_n=Measured(20), viscous_n_per_mm_s=Measured(0),
                   stribeck_extra_n=Measured(80), stribeck_v_mm_s=Measured(50),
                   friction_table_up=Measured([(200, 100)]),
                   friction_map=Measured([(0, 10), (2000, 50)]))
    core = MotorCore(replace(profile, left=side, right=side, track_comp_gain=Measured(1)),
                     Tunables(friction_gain_up=1, train_friction_gain_down=1, friction_blend_mm_s=0),
                     replace(SafetyEnvelope(), max_speed_mm_s=200, max_raw=400))
    core.set_load(LoadSetpoint(load_n=1000, load_direction="up"))
    state = _states(core.envelope.soft_max_mm, 6.35)["left"]
    target = core._law("train", "left", state, state, 0)
    assert 359 < target <= 360


def test_upward_cap_leaves_downward_limit_unchanged():
    profile = MachineProfile()
    side = replace(profile.left, gravity_map=Measured([(0, 70), (1000, 150)]), n_per_raw=Measured(1),
                   coulomb_down_n=Measured(40), pull_scale=Measured(.8),
                   friction_table_up=Measured([(100, 900)]), friction_load_up=Measured(.5))
    core = MotorCore(replace(profile, left=side, right=side), envelope=replace(SafetyEnvelope(), max_raw=400))
    assert core.load_limit_n() == pytest.approx(318)  # 70 + 320 - 40 - 32
    core.load_limit_n("up")
    assert core.load_limit_n("down") == pytest.approx(318)


def test_breakaway_and_friction_are_mirrored_without_changing_effort_gain():
    core = _core(load=10, range_guard=True)
    core._still_s = {side: 1 for side in SIDES}
    core._update_range(_states())
    assert core._fall_assist("left", _states()["left"], 10) > 0
    assert core._descent_gain("left", 100) > core.tunables.friction_gain_up
    core._update_range(_states(710))
    assert core._fall_assist("left", _states(710)["left"], 10) == 0
    for _ in range(8):
        core._update_range(_states(500, core.envelope.max_speed_mm_s))
    assert core._descent_gain("left", 100) == core.tunables.friction_gain_up


def test_top_cushion_cancels_actual_phase_load():
    core = _core(mode="eccentric")
    core.profile = replace(core.profile, cushion_top_mm=Measured(120))
    state = _states(core.envelope.soft_max_mm - 5, 100)["left"]
    brake_loaded = core._cushion("left", state)
    core.set_load(replace(core.load, load_n=0))
    assert core._cushion("left", state) - brake_loaded == pytest.approx(120)


@pytest.mark.parametrize("confidence", ["moving", "static_interval"])
def test_release_uses_downward_user_force(confidence):
    core = _core()
    core.release_enabled = True
    pushing = UserForceEstimate(-100, -120, -80, confidence)
    core._released({side: pushing for side in SIDES}, 4)
    assert core.supervisor.mode == Mode.TRAINING
    released = UserForceEstimate(0, -10, 10, confidence)
    core._released({side: released for side in SIDES}, 4)
    assert core.supervisor.mode == Mode.HOLD


def test_grip_handover_ramp_pause_and_no_direction_flip():
    workout, _bench = _workout()
    _grip(workout, force=80)
    assert workout.mode == "start_hold"  # pushing with the upward load is not a grip
    _grip(workout)
    assert workout.mode == "training" and workout.load_n == 40
    assert workout.core.load.load_direction == "up"
    workout._ramp_load(.05)
    assert workout.load_n == 60
    old_plan = workout.plan
    with pytest.raises(WorkoutError, match="на паузу"):
        workout.start_set(SetPlan(300, 700, 100))
    assert workout.plan is old_plan and workout.core.load.load_direction == "up"
    workout.pause()
    assert workout.mode == "training"
    workout._ramp_load(.05)
    assert workout.load_n == 40
    workout._ramp_load(.1)
    assert workout.mode == "paused" and workout.load_n == 0


@pytest.mark.parametrize("change", [{"load_direction": "sideways"}, {"load_n": float("nan")}, {"upper_mm": float("inf")}, {"load_n": -1}, {"lower_mm": 800}])
def test_invalid_plan_rejected_before_mutation(change):
    workout, _bench = _workout()
    plan = workout.plan
    with pytest.raises(WorkoutError):
        workout.start_set(replace(plan, **change))
    assert workout.plan is plan


def test_stop_support_and_workout_abort_on_twin():
    workout, bench = _workout()
    _grip(workout)
    core = workout.core
    core.command("estop")
    output = core.step(_frame(.3).samples, .3)
    assert output.kind == "support" and output.mode == Mode.ESTOP
    assert workout._write(output) is None
    assert all(bench.drives[side].last_raw == int(core.profile.side(side).support_raw.value) * core.profile.side(side).sign for side in SIDES)
    workout.abort("STOP")
    assert workout.mode == "idle" and workout.core is None and workout.load_n == 0