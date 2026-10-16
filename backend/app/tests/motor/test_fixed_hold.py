"""Fixed hold regression bench. Pure twin: no runtime, API, database or drives."""

import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from app.motor.core import MotorCore
from app.motor.drive.protocol import DriveSample
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import run_core
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES

ORIGINAL_COMMIT = "bca88b938c721501af9841a2f906faf790c47f4d"


@pytest.fixture(scope="module")
def original_core():
    """Execute TRUE pre-change HEAD, never an experimental observer baseline."""
    source = subprocess.check_output(
        ["git", "show", f"{ORIGINAL_COMMIT}:backend/app/motor/core.py"],
        cwd=Path(__file__).resolve().parents[4], text=True, encoding="utf-8",
    )
    name = "app.motor._original_hold_test_reference"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, f"<git {ORIGINAL_COMMIT}:core.py>", "exec"), module.__dict__)
        yield module.MotorCore
    finally:
        sys.modules.pop(name, None)


def delayed_profile():
    profile = MachineProfile(
        hold_ultimate_k_n_per_mm=Measured(1.2264),
        hold_ultimate_period_s=Measured(0.537),
        loop_period_s=Measured(0.075),
        loop_delay_s=Measured(0.0735),
        torque_lag_s=Measured(0.048),
    )
    return replace(profile, **{
        side: replace(profile.side(side), moving_mass_kg=Measured(60.0))
        for side in SIDES
    })


def hanging_run(core_type=MotorCore, *, seconds=25.0, release_s=9.0, loads=(300.0, 300.0), params=None, envelope=None):
    def hanging(t, _bench):
        return {side: -min(load, max(0.0, (t - 1.0) * 150.0)) if t < release_s else 0.0
                for side, load in zip(SIDES, loads, strict=True)}

    profile = delayed_profile()
    bench = TwinBench(
        params or replace(PlantParams(), command_delay_ticks=2, torque_lag_s=0.048, coupling_n_per_mm=4.5),
        profiles={side: profile.side(side) for side in SIDES},
        x0_mm=700.0, user=hanging, initial_raw=100,
    )
    core = core_type(profile, envelope=envelope)
    core.command("ready")
    core.command("hold")
    core.command("fixed")
    core.hold_at({side: 700.0 for side in SIDES})
    trace = run_core(core, bench, seconds, dt=0.075)
    return core, bench, trace


def hold_metrics(trace, release_s=9.0):
    return {
        "sag_mm": max(700.0 - min(trace.x[side]) for side in SIDES),
        "overshoot_mm": max(0.0, *(x - 700.0 for side in SIDES for t, x in zip(trace.t, trace.x[side], strict=False) if t >= release_s)),
        "release_speed_mm_s": max(abs(v) for side in SIDES for t, v in zip(trace.t, trace.v[side], strict=False) if t >= release_s),
        "tail_osc_mm": max(max(xs[-40:]) - min(xs[-40:]) for xs in trace.x.values()),
        "final_error_mm": max(abs(xs[-1] - 700.0) for xs in trace.x.values()),
    }


@pytest.mark.parametrize("read_delay", [0, 1])
@pytest.mark.parametrize("coupling", [4.5, 40.0])
@pytest.mark.parametrize("loads", [(300, 300), (300, 200), (200, 300)])
def test_observer_reacts_to_hanging_much_faster_than_original_pi(original_core, read_delay, coupling, loads):
    params = replace(PlantParams(), command_delay_ticks=2, torque_lag_s=0.048,
                     coupling_n_per_mm=coupling, read_delay_ticks=read_delay)
    _, _, reference = hanging_run(original_core, params=params, loads=loads)
    core, _, trace = hanging_run(params=params, loads=loads)
    old, new = hold_metrics(reference), hold_metrics(trace)
    assert core.hold_target == {side: 700.0 for side in SIDES}
    assert set(trace.mode) == {"fixed"}
    assert new["sag_mm"] < 140 and new["sag_mm"] < old["sag_mm"] / 3
    assert new["overshoot_mm"] < 260 and new["overshoot_mm"] < old["overshoot_mm"] / 2
    # The release impulse is physical (stored torque × delay), not a gain choice: only bounded.
    assert new["release_speed_mm_s"] < 1.25 * old["release_speed_mm_s"]
    assert new["tail_osc_mm"] < 10
    assert new["final_error_mm"] < 8


@pytest.mark.parametrize("read_delay", [0, 1])
def test_continued_load_holds_without_drift_or_hunting(read_delay):
    params = replace(PlantParams(), command_delay_ticks=2, torque_lag_s=0.048,
                     coupling_n_per_mm=4.5, read_delay_ticks=read_delay)
    core, _, trace = hanging_run(params=params, seconds=120, release_s=999)
    assert core.hold_target == {side: 700.0 for side in SIDES}
    for xs in trace.x.values():
        settled = xs[len(xs) // 4:]
        assert max(settled) - min(settled) < 10
        assert abs(xs[-1] - 700.0) < 8


@pytest.mark.parametrize(("mass", "stiction", "cmd_ticks"), [(45.0, 0.0, 2), (80.0, 0.0, 2), (60.0, 30.0, 2), (60.0, 0.0, 3)])
def test_observer_robust_to_plant_mismatch(mass, stiction, cmd_ticks):
    params = replace(PlantParams(), command_delay_ticks=cmd_ticks, torque_lag_s=0.048, coupling_n_per_mm=4.5)
    side = replace(params.left, mass_kg=mass, stiction_extra_n=stiction)
    core, _, trace = hanging_run(params=replace(params, left=side, right=side))
    metrics = hold_metrics(trace)
    assert metrics["sag_mm"] < 140
    assert metrics["tail_osc_mm"] < 10
    assert metrics["final_error_mm"] < 8
    assert set(trace.mode) == {"fixed"}


def test_sustained_overload_is_bounded_not_claimed_holdable():
    envelope = replace(SafetyEnvelope(), max_force_n_per_side=250)
    core, _, trace = hanging_run(seconds=40, release_s=999, loads=(1000, 1000), envelope=envelope)
    for side in SIDES:
        assert max(abs(f) for f in trace.force[side]) <= 250
        assert abs(core.fixed_integral[side]) < 250
    # This original PI reaches the lower stop, not necessarily the overspeed latch.
    # Never label that outcome a successful hold or assume FAULT was triggered.
    assert all(min(xs) == 0 for xs in trace.x.values())


def prepared_core(*, envelope=None, profile=None, target=700.0):
    core = MotorCore(profile or delayed_profile(), envelope=envelope)
    core.command("ready")
    core.command("hold")
    core.command("fixed")
    core.hold_at({side: target for side in SIDES})
    core._t = 0.0
    return core


def samples_at(t, x=680.0):
    return {side: DriveSample(side, t, ok=True, position_mm=x) for side in SIDES}


@pytest.mark.parametrize("limit", ["force", "raw_push", "raw_pull", "slew", "soft_top", "soft_bottom", "shaping"])
def test_full_output_saturation_blocks_integral_growth(limit):
    profile, envelope = delayed_profile(), SafetyEnvelope()
    target, x, previous = 700.0, 680.0, 150.0
    if limit == "force":
        envelope = replace(envelope, max_force_n_per_side=150)
        x = 100.0
    elif limit in {"raw_push", "raw_pull"}:
        envelope = replace(envelope, max_raw=100)
        if limit == "raw_pull":
            profile = replace(profile, **{side: replace(profile.side(side), pull_scale=Measured(0.2)) for side in SIDES})
            target, x, previous = 100.0, 700.0, -100.0
    elif limit == "slew":
        envelope = replace(envelope, max_rate_n_per_s=1.0)
        previous = 0.0
    elif limit == "soft_top":
        x, target = envelope.soft_max_mm, envelope.soft_max_mm + 20
    elif limit == "soft_bottom":
        x, target, previous = envelope.soft_min_mm, envelope.soft_min_mm - 600, -100.0
    else:
        envelope = replace(envelope, max_force_n_per_side=160)
        x = 600.0
        profile = replace(profile, deadband_comp_gain=Measured(1.0), **{
            side: replace(profile.side(side), deadband_raw=Measured(100)) for side in SIDES
        })
    core = prepared_core(profile=profile, envelope=envelope, target=target)
    core.previous = {side: previous for side in SIDES}
    # The bias may unwind (the observer sees what the drive really delivers), never push deeper into the limit.
    deeper = -1.0 if limit in {"raw_pull", "soft_bottom"} else 1.0
    for tick in range(1, 31):
        core.step(samples_at(tick * 0.075, x), tick * 0.075)
        assert all(deeper * bias <= 1e-6 for bias in core.fixed_integral.values())


def test_saturation_allows_unwinding_and_fresh_frames_resume():
    core = prepared_core(envelope=replace(SafetyEnvelope(), max_force_n_per_side=150), target=600)
    core.fixed_integral = {side: 300.0 for side in SIDES}
    core.previous = {side: 150.0 for side in SIDES}
    core.step(samples_at(0.075, 610), 0.075)  # the first fresh frame only primes the observer
    core.step(samples_at(0.15, 610), 0.15)
    assert all(0 < bias < 300 for bias in core.fixed_integral.values())
    frozen = dict(core.fixed_integral)
    core.step(samples_at(0.15, 610), 0.225)
    assert core.fixed_integral == frozen
    core.step(samples_at(0.3, 610), 0.3)
    assert all(core.fixed_integral[side] < frozen[side] for side in SIDES)


@pytest.mark.parametrize("failure", ["missing", "old", "duplicate", "out_of_order"])
def test_stale_or_duplicate_frames_never_integrate(failure):
    core = MotorCore(delayed_profile())
    core.command("ready")
    core.command("hold")
    core.command("fixed")
    core.hold_at({side: 700.0 for side in SIDES})
    samples = {side: DriveSample(side, 1.0, ok=True, position_mm=680, motor_force_n=300) for side in SIDES}
    core.step(samples, 1.0)
    core.fixed_integral = {side: 100.0 for side in SIDES}
    if failure == "missing":
        samples = {}
    elif failure == "old":
        samples = {side: replace(sample, t=0.0) for side, sample in samples.items()}
    elif failure == "out_of_order":
        samples = {side: replace(sample, t=0.99) for side, sample in samples.items()}
    core.step(samples, 1.075)
    assert core.fixed_integral == {side: 100.0 for side in SIDES}


@pytest.mark.parametrize("event", ["estop", "pause", "fault"])
def test_leaving_fixed_clears_bias_and_estop_always_supports(event):
    core, bench, _ = hanging_run(seconds=5)
    assert any(abs(v) > 50 for v in core.fixed_integral.values())
    core.command(event)
    assert core.fixed_integral == {side: 0.0 for side in SIDES}
    trace = run_core(core, bench, 0.3, dt=0.075)
    if event != "pause":
        assert set(trace.kind) == {"support"}
        for side in SIDES:
            assert set(trace.force[side]) == {core._support_force(side)}


def test_fixed_integral_compatibility_and_soft_hold_isolation():
    core = MotorCore(delayed_profile())
    core.command("ready")
    core.command("hold")
    samples = {side: DriveSample(side, 1.0, ok=True, position_mm=700) for side in SIDES}
    core.fixed_integral = {side: 123.0 for side in SIDES}
    biased = core.step(samples, 1.0)
    reference = MotorCore(delayed_profile())
    reference.command("ready")
    reference.command("hold")
    clean = reference.step(samples, 1.0)
    assert biased.forces_n == clean.forces_n
    core.command("fixed")
    assert core.fixed_integral == {side: 0.0 for side in SIDES}
    core.command("pause")
    core.command("isometric")
    assert core.supervisor.output == "hold"