"""Exercises on the twin through the runtime: setup, start point, grip, load, reps, pause, park, STOP."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.config import get_settings
from app.motor import workout as workout_module
from app.motor.twin import users
from app.motor.workout import WorkoutError
from app.services.hardware_runtime import ABORT_SUPPORT_RAW, HardwareRuntime

FIXED_PLAN = {"setup_type": "fixed_position", "lower_point_mm": None, "upper_point_mm": None, "fixed_position_mm": 500.0}
RANGE_PLAN = {"setup_type": "bar_range", "lower_point_mm": 300.0, "upper_point_mm": 700.0, "fixed_position_mm": None}


@pytest.fixture(scope="module")
def calibrated_profile():
    """WIZARD (S3, M1, M3, C3 …) on the twin once; every test starts a fresh runtime with this profile."""

    mp = pytest.MonkeyPatch()
    mp.setenv("HARDWARE_ADAPTER", "twin")
    mp.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    runtime.set_service_mode(True)
    runtime.set_servo(True)
    for _ in range(3):
        runtime.tick()
    session = runtime.start_calibration("WIZARD")
    for _ in range(40000):
        if not session.running:
            break
        session.keepalive()
        runtime.tick()
    assert session.status == "done", session.reason
    profile = replace(session.profile, version=2)
    mp.undo()
    get_settings.cache_clear()
    return profile


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch, calibrated_profile) -> HardwareRuntime:
    monkeypatch.setenv("HARDWARE_ADAPTER", "twin")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    rt = HardwareRuntime()
    rt.reset(profile=calibrated_profile)
    rt.set_service_mode(True)
    rt.set_servo(True)
    rt.set_service_mode(False)
    for _ in range(10):
        rt.tick()
    return rt


def _ticks(rt: HardwareRuntime, seconds: float, until=None) -> bool:
    for _ in range(int(seconds / rt.tick_seconds)):
        rt.tick()
        if until is not None and until():
            return True
    return until is None


def _x(rt: HardwareRuntime) -> float:
    return rt.state.motion.bar_position_mm


def lifter(load_kg: float, lower_mm: float, upper_mm: float, *, speed_mm_s: float = 150.0, start_s: float = 0.0):
    """A person doing reps: works against the felt load, force builds up over ~0.3 s and stays within ±150 N of it."""

    state = {"dir": 1, "f": 0.0, "t": None}

    def user(t: float, bench) -> dict:
        x, v = bench.true_state("left")
        if x >= upper_mm:
            state["dir"] = -1
        elif x <= lower_mm:
            state["dir"] = 1
        base = load_kg * 9.81 / 2
        target = base + max(-150.0, min(150.0, 3.0 * (state["dir"] * speed_mm_s - v)))
        dt = 0.0 if state["t"] is None else t - state["t"]
        state["t"] = t
        ramp = min(1.0, max(0.0, (t - start_s) / 0.3))
        state["f"] += max(-1500 * dt, min(1500 * dt, ramp * target - state["f"]))
        return {"left": state["f"], "right": state["f"]}

    return user


def test_uncalibrated_profile_blocks_exercises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARDWARE_ADAPTER", "twin")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    rt = HardwareRuntime()
    rt.set_service_mode(True)
    rt.set_servo(True)
    rt.tick()
    with pytest.raises(WorkoutError, match="S3"):
        rt.workout_command("enter_weightless", {})
    assert rt.snapshot_payload()["control"]["motorControl"] == "disabled"


def test_ready_snapshot(runtime: HardwareRuntime) -> None:
    control = runtime.snapshot_payload()["control"]
    assert control["motorControl"] == "enabled", control["motorControlMessage"]
    assert control["mode"] == "idle" and runtime.mode == "support"


@pytest.mark.parametrize("target_mm, expected_limit", [(40.0, 240.0), (300.0, 140.0)])
@pytest.mark.parametrize("fixed", [False, True])
def test_start_move_has_extra_speed_headroom(runtime: HardwareRuntime, target_mm: float, expected_limit: float, fixed: bool) -> None:
    plan = FIXED_PLAN | {"fixed_position_mm": target_mm} if fixed else RANGE_PLAN | {"lower_point_mm": target_mm}
    runtime.workout_command("start_motion", {"weight_kg": 10}, plan)
    runner = runtime.workout.runner
    assert runner is not None
    assert runner.envelope.max_speed_mm_s == expected_limit


def test_start_move_headroom_respects_machine_speed_envelope(runtime: HardwareRuntime) -> None:
    runtime.workout.envelope = replace(runtime.workout.envelope, max_speed_mm_s=130.0)
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)
    runner = runtime.workout.runner
    assert runner is not None
    assert runner.envelope.max_speed_mm_s == 130.0


def test_set_moves_to_start_waits_for_grip_and_counts_reps(runtime: HardwareRuntime) -> None:
    bench = runtime.bench
    assert bench is not None
    bench.params = replace(bench.params, speed_limit_rpm=300.0)  # PA_056 a drive returns to after a move (old connect value)
    runtime.workout_command("start_motion", {"weight_kg": 20, "target_reps": 5}, RANGE_PLAN)
    assert runtime.control_mode == "moving"
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold"), runtime.workout.message()
    assert abs(_x(runtime) - 300) < 15
    # the move to the start restored PA_056: a fast rep must not hit the drive limit
    assert bench.plant.speed_limit_rpm == {"left": runtime.envelope.speed_limit_rpm, "right": runtime.envelope.speed_limit_rpm}
    _ticks(runtime, 2)
    assert runtime.control_mode == "start_hold" and abs(_x(runtime) - 300) < 15  # held without the user

    bench.user = lifter(20.0, 330, 670, start_s=bench.t)
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training"), runtime.workout.message()
    assert _ticks(runtime, 30, lambda: runtime.state.motion.repetition_count >= 3), (runtime.state.motion.repetition_count, _x(runtime))
    motion = runtime.state.motion
    assert motion.load_target_kg == pytest.approx(20, abs=0.2) and motion.load_effective_kg == pytest.approx(20, abs=0.5)
    assert runtime.snapshot_payload()["control"]["mode"] == "training"

    runtime.workout_command("complete_set", {})
    bench.user = users.nobody()
    # the rest: weightless where the set ended, not on the stops
    assert _ticks(runtime, 5, lambda: runtime.control_mode == "weightless"), runtime.workout.message()
    x = _x(runtime)
    _ticks(runtime, 3)
    assert x > 100 and abs(_x(runtime) - x) < 15 and runtime.latch is None, (x, _x(runtime))
    runtime.workout_command("park", {})
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "parked"), runtime.workout.message()
    assert _x(runtime) < 20 and runtime.latch is None
    assert runtime.mode == "support"


@pytest.mark.parametrize("from_top", [False, True])
def test_user_pushing_the_bar_at_the_start_point_starts_the_set(runtime: HardwareRuntime, from_top: bool) -> None:
    """Bench press: the bar arrives at the chest and the user presses it off before the move has settled.

    The move envelope (120 mm/s) must not latch a fault here: the hold catches the bar and the set starts.
    """

    bench = runtime.bench
    assert bench is not None
    if from_top:
        runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN | {"lower_point_mm": 650.0, "upper_point_mm": 900.0})
        assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
        runtime.workout_command("complete_set", {})
        _ticks(runtime, 1)
    runtime.workout_command("start_motion", {"weight_kg": 10, "target_reps": 5}, RANGE_PLAN)
    assert runtime.control_mode == "moving"
    assert _ticks(runtime, 40, lambda: abs(_x(runtime) - 300) < 40), _x(runtime)
    bench.user = lifter(10.0, 330, 670, speed_mm_s=250, start_s=bench.t)
    assert _ticks(runtime, 5, lambda: runtime.control_mode == "training"), (runtime.workout.message(), runtime.latch)
    assert runtime.latch is None
    assert _ticks(runtime, 30, lambda: runtime.state.motion.repetition_count >= 2), (runtime.state.motion.repetition_count, _x(runtime))


def test_bar_pushed_far_from_the_start_point_still_aborts_the_move(runtime: HardwareRuntime) -> None:
    bench = runtime.bench
    assert bench is not None
    runtime.workout_command("start_motion", {"weight_kg": 10, "target_reps": 5}, RANGE_PLAN | {"lower_point_mm": 900.0, "upper_point_mm": 1200.0})
    assert _ticks(runtime, 40, lambda: _x(runtime) > 100), _x(runtime)
    bench.user = users.constant(400.0, start_s=bench.t, stop_s=bench.t + 3)
    assert _ticks(runtime, 3, lambda: runtime.latch is not None), _x(runtime)
    assert runtime.latch == "fault" and "Перемещение грифа прервано" in (runtime.workout.message() or "")


def test_rest_left_alone_parks_the_bar(runtime: HardwareRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workout_module, "REST_PARK_S", 3.0)
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
    runtime.workout_command("complete_set", {})
    assert runtime.control_mode == "weightless"
    _ticks(runtime, 2)
    assert runtime.control_mode == "weightless"
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "parked"), runtime.workout.message()
    assert _x(runtime) < 20 and runtime.latch is None


def test_next_set_starts_from_the_weightless_rest(runtime: HardwareRuntime) -> None:
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
    runtime.workout_command("complete_set", {})
    _ticks(runtime, 2)
    assert runtime.control_mode == "weightless"
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN | {"lower_point_mm": 400.0})
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold"), runtime.workout.message()
    assert abs(_x(runtime) - 400) < 15 and runtime.latch is None


def test_next_set_starts_from_a_rest_above_the_soft_limit(runtime: HardwareRuntime, calibrated_profile) -> None:
    """The set ended with the bar pushed above the soft limit; the weightless rest left it there.

    The move to the next start begins outside soft_max + margin: it must go down, not latch a fault.
    """

    runtime.reset(profile=calibrated_profile, envelope=replace(runtime.envelope, soft_max_mm=800.0))
    runtime.set_service_mode(True)
    runtime.set_servo(True)
    runtime.set_service_mode(False)
    _ticks(runtime, 0.5)
    bench = runtime.bench
    assert bench is not None
    runtime.workout_command("enter_weightless", {})
    bench.user = users.constant(60.0, start_s=bench.t)
    assert _ticks(runtime, 40, lambda: _x(runtime) > 800 + workout_module.MOVE_MARGIN_MM + 40), _x(runtime)
    bench.user = users.nobody()
    _ticks(runtime, 2)
    assert runtime.control_mode == "weightless" and runtime.latch is None
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold"), (runtime.workout.message(), runtime.latch)
    assert abs(_x(runtime) - 300) < 15 and runtime.latch is None


def test_released_light_bar_goes_down(runtime: HardwareRuntime) -> None:
    """5 kg is below the screw's static friction: a released bar must still sink like a free weight."""

    runtime.workout_command("start_motion", {"weight_kg": 5, "target_reps": 5}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
    bench = runtime.bench
    assert bench is not None
    bench.user = lifter(5.0, 330, 670, start_s=bench.t)
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training")
    assert _ticks(runtime, 10, lambda: _x(runtime) > 600)
    bench.user = users.nobody()
    _ticks(runtime, 1.5)
    x = _x(runtime)
    _ticks(runtime, 4)
    assert _x(runtime) < x - 100, (x, _x(runtime))
    assert runtime.control_mode == "training" and runtime.latch is None
    # the user lifts again: the downward push is gone, the load is honest
    bench.user = lifter(5.0, 330, 670, start_s=bench.t)
    assert _ticks(runtime, 10, lambda: runtime.state.motion.repetition_count >= 1), (runtime.state.motion.repetition_count, _x(runtime))
    assert runtime.workout.core is not None and max(runtime.workout.core.fall_assist.values()) == 0.0


@pytest.mark.parametrize("weight_kg", [5.0, 60.0])
def test_dropped_bar_stops_at_the_lower_point(runtime: HardwareRuntime, weight_kg: float) -> None:
    """Released at the top, the bar sinks to the set's lower point (300) and stays there, not on the stops."""

    runtime.workout_command("start_motion", {"weight_kg": weight_kg, "target_reps": 50}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
    bench = runtime.bench
    assert bench is not None
    bench.user = lifter(weight_kg, 330, 670, start_s=bench.t)
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training")
    assert _ticks(runtime, 10, lambda: _x(runtime) > 650)
    bench.user = users.nobody()
    xs = []
    for _ in range(int(6 / runtime.tick_seconds)):
        runtime.tick()
        xs.append(_x(runtime))
    assert min(xs) > 260 and 280 < xs[-1] < 315, (min(xs), xs[-1])
    assert max(abs(x - xs[-1]) for x in xs[-10:]) < 2  # settled, no ringing on the point
    assert runtime.latch is None
    assert runtime.control_mode == "training"  # no automatic pause in a set
    # the user lifts again: the load comes back in the range
    bench.user = lifter(weight_kg, 330, 670, start_s=bench.t)
    assert _ticks(runtime, 15, lambda: runtime.control_mode == "training" and runtime.state.motion.load_effective_kg > weight_kg - 0.5), runtime.workout.message()


def test_set_from_the_upper_point_counts_reps_on_the_way_back_up(runtime: HardwareRuntime) -> None:
    """Squat: the bar waits at the upper point (saved with the bar setup); a rep is down and back up."""

    runtime.workout_command("start_motion", {"weight_kg": 20, "target_reps": 5}, RANGE_PLAN | {"start_point": "upper"})
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold"), runtime.workout.message()
    assert abs(_x(runtime) - 700) < 15 and runtime.state.motion.start_point == "upper"
    bench = runtime.bench
    assert bench is not None
    bench.user = lifter(20.0, 330, 670, start_s=bench.t)
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training"), runtime.workout.message()
    assert _ticks(runtime, 30, lambda: runtime.state.motion.repetition_count >= 2), (runtime.state.motion.repetition_count, _x(runtime))
    assert _x(runtime) > 500  # counted near the top, where a rep from the top ends


def test_bar_waits_at_the_upper_point_until_it_is_taken_down(runtime: HardwareRuntime) -> None:
    runtime.workout_command("start_motion", {"weight_kg": 20, "target_reps": 5}, RANGE_PLAN | {"start_point": "upper"})
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold"), runtime.workout.message()
    bench = runtime.bench
    assert bench is not None
    bench.user = users.constant(60.0, start_s=bench.t)  # hands on the bar, pushing up
    _ticks(runtime, 2)
    assert runtime.control_mode == "start_hold" and abs(_x(runtime) - 700) < 30, _x(runtime)
    bench.user = users.nobody()
    _ticks(runtime, 1)
    assert runtime.control_mode == "start_hold" and abs(_x(runtime) - 700) < 15, _x(runtime)
    bench.user = users.constant(-60.0, start_s=bench.t)  # takes it down
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training"), (runtime.workout.message(), _x(runtime))


def test_bar_lifted_above_the_upper_point_starts_the_set_when_pulled_down(runtime: HardwareRuntime) -> None:
    runtime.workout_command("start_motion", {"weight_kg": 20, "target_reps": 5}, RANGE_PLAN | {"start_point": "upper"})
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold"), runtime.workout.message()
    bench = runtime.bench
    assert bench is not None
    bench.user = users.constant(60.0, start_s=bench.t)
    _ticks(runtime, 1)
    bench.user = users.constant(-80.0, start_s=bench.t)  # straight down, no stop at the point
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training"), (runtime.workout.message(), _x(runtime))


def test_bar_thrown_above_the_upper_point_is_braked(runtime: HardwareRuntime) -> None:
    """Pushed fast past the upper point (700) and let go: the bar's momentum is braked there, then it goes down."""

    runtime.workout_command("start_motion", {"weight_kg": 5, "target_reps": 50}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
    bench = runtime.bench
    assert bench is not None
    bench.user = lifter(5.0, 330, 2000, speed_mm_s=350, start_s=bench.t)
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training")
    assert _ticks(runtime, 10, lambda: _x(runtime) > 680)
    assert bench.true_state("left")[1] > 250
    bench.user = users.nobody()
    xs = []
    for _ in range(int(2 / runtime.tick_seconds)):
        runtime.tick()
        xs.append(_x(runtime))
    assert max(xs) < 735 and xs[-1] < 650, (max(xs), xs[-1])  # without the brake: ~765 and back slowly
    assert runtime.latch is None


def test_pause_holds_then_resume_waits_for_grip(runtime: HardwareRuntime) -> None:
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
    bench = runtime.bench
    assert bench is not None
    bench.user = lifter(10.0, 330, 670, start_s=bench.t)
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "training")
    _ticks(runtime, 2)
    runtime.workout_command("pause", {})
    assert _ticks(runtime, 3, lambda: runtime.control_mode == "paused")  # load ramped out first
    bench.user = users.nobody()
    _ticks(runtime, 1)
    x = _x(runtime)
    _ticks(runtime, 2)
    assert abs(_x(runtime) - x) < 15  # held where it was paused
    runtime.workout_command("resume", {"weight_kg": 12})
    assert runtime.control_mode == "start_hold" and runtime.state.motion.load_target_kg == pytest.approx(12, abs=0.2)


def test_setup_weightless_capture_and_jog(runtime: HardwareRuntime) -> None:
    runtime.workout_command("enter_weightless", {})
    assert runtime.control_mode == "weightless"
    _ticks(runtime, 2)
    record = runtime.workout_command("capture_point", {"which": "lower"})
    assert record.payload["capturedPositionMm"] == pytest.approx(_x(runtime), abs=2)

    start = _x(runtime)
    runtime.workout_command("jog_start", {"jog_id": "a", "direction": "up"})
    for _ in range(40):  # 2 s with keepalives every 0.2 s
        runtime.tick()
        if _ % 4 == 0:
            runtime.workout_command("jog_keepalive", {"jog_id": "a"})
    assert _x(runtime) > start + 30
    runtime.workout_command("jog_stop", {"jog_id": "a"})
    assert _ticks(runtime, 6, lambda: runtime.control_mode == "weightless"), runtime.control_mode


def test_jog_stops_without_keepalive(runtime: HardwareRuntime) -> None:
    runtime.workout_command("hold", {})
    runtime.workout_command("jog_start", {"jog_id": "b", "direction": "up"})
    assert _ticks(runtime, 6, lambda: runtime.control_mode == "paused")
    x = _x(runtime)
    _ticks(runtime, 1)
    assert abs(_x(runtime) - x) < 10


def test_fixed_position_holds_stiff(runtime: HardwareRuntime) -> None:
    runtime.workout_command("start_fixed_position", {"weight_kg": 20}, FIXED_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "fixed_hold"), runtime.workout.message()
    bench = runtime.bench
    assert bench is not None
    x = _x(runtime)
    bench.user = users.constant(150.0, start_s=bench.t, stop_s=bench.t + 1.5)
    _ticks(runtime, 1.4)
    assert abs(_x(runtime) - x) < 60  # the user pushes 2×150 N, the bar yields only the spring travel
    _ticks(runtime, 2.5)
    settled = []
    for _ in range(20):
        runtime.tick()
        settled.append(_x(runtime))
    assert max(settled) - min(settled) < 5 and abs(settled[-1] - x) < 40  # no ringing on the stiff spring
    assert runtime.state.motion.repetition_count == 0  # force/position changes never count fixed-hold reps


def test_estop_aborts_the_set_with_slow_lowering(runtime: HardwareRuntime) -> None:
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)
    assert _ticks(runtime, 40, lambda: runtime.control_mode == "start_hold")
    runtime.trigger_emergency_stop()
    assert not runtime.workout.active and runtime.mode == "estop"
    assert all(drive.last_raw == ABORT_SUPPORT_RAW * drive.profile.sign for drive in runtime.drives.values())  # type: ignore[attr-defined]
    with pytest.raises(WorkoutError):
        runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)


def test_profile_cannot_change_during_a_set(runtime: HardwareRuntime) -> None:
    runtime.workout_command("start_motion", {"weight_kg": 10}, RANGE_PLAN)
    with pytest.raises(PermissionError, match="упражнение"):
        runtime.apply_profile(runtime.profile)
    runtime.set_service_mode(True)
    with pytest.raises(PermissionError, match="Упражнение"):
        runtime.start_calibration("B5")
