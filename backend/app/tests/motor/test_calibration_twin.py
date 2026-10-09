"""T2/T3 on the twin: procedures recover known random physics; the wizard yields a working machine.

CI runs ``MOTOR_SEEDS`` (default 12) random machines; nightly sets it to hundreds.
Failures print the seed: ``random_machine(seed)`` reproduces the machine.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from app.motor.calibration.fit import BreakawayDetector, limit_cycle, linear_fit, stat
from app.motor.calibration.procedures.direction import direction_test
from app.motor.calibration.procedures.statics import balance_and_friction, fit_balance
from app.motor.calibration.runner import CalibrationRunner, Command, ProcedureEnvelope
from app.motor.calibration.wizard import commission
from app.motor.core import MotorCore
from app.motor.profile import MachineProfile, Measured, SideProfile
from app.motor.tuning import metrics
from app.motor.twin import users
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import run_core
from app.motor.twin.randomize import random_machine
from app.motor.units import SIDES, kgf_to_n

SEEDS = range(int(os.environ.get("MOTOR_SEEDS", "12")))


def _bench(seed: int, *, exact_profile: bool) -> TwinBench:
    params = random_machine(seed)
    profiles = None
    if exact_profile:
        profiles = {side: SideProfile(n_per_raw=Measured(params.side(side).n_per_raw), direction_sign=Measured(params.side(side).direction_sign)) for side in SIDES}
    return TwinBench(params, profiles, seed=seed, x0_mm=0.0, initial_raw=0)


def _tick(bench: TwinBench):
    def tick() -> float:
        bench.advance(0.02)
        return bench.t

    return tick


def test_fit_helpers() -> None:
    assert stat([1.0, 2.0, 3.0]).mean == 2.0
    fit = linear_fit([0, 1, 2, 3], [1, 3, 5, 7])
    assert (fit.slope, fit.intercept, fit.r2) == pytest.approx((2.0, 1.0, 1.0))
    detector = BreakawayDetector(0.0, +1)
    assert [detector.update(x, 2.0) for x in (0.1, 0.4, 0.5, 0.6)] == [False, False, False, True]
    ts = [i * 0.01 for i in range(400)]
    xs = [1.0 if (i // 25) % 2 else -1.0 for i in range(400)]
    cycle = limit_cycle(ts, xs, 0.0)
    assert cycle.regular and cycle.period_s == pytest.approx(0.5, abs=0.02) and cycle.amplitude_mm == pytest.approx(1.0)


@pytest.mark.parametrize("seed", SEEDS)
def test_direction_is_identified_from_wrong_belief(seed: int) -> None:
    bench = _bench(seed, exact_profile=False)
    runner = CalibrationRunner(bench.drives, _tick(bench), ProcedureEnvelope(max_speed_mm_s=200, min_x_mm=-30, max_x_mm=30))
    result = runner.run(direction_test({side: 1 for side in SIDES}))
    assert result.status == "done", (seed, result.reason)
    for side in SIDES:
        assert result.data["sides"][side]["direction_sign"] == bench.params.side(side).direction_sign, seed


@pytest.mark.parametrize("seed", SEEDS)
def test_static_window_is_identified(seed: int) -> None:
    """S1–S3: the window edges [W − Fc⁻, W + Fc⁺] of the bar (sum of sides) within 3 % of W.

    The split of one offset between W and the friction asymmetry is not observable
    without a load cell; the edges are what the force law needs.
    """

    bench = _bench(seed, exact_profile=True)
    result = CalibrationRunner(bench.drives, _tick(bench)).run(balance_and_friction({side: 0.0 for side in SIDES}))
    assert result.status == "done", (seed, result.reason)
    estimate = fit_balance(result.data)
    height = estimate.height_mm
    weight_true = sum(bench.params.side(side).weight_at(height) for side in SIDES)
    up_true = sum(bench.params.side(s).weight_at(height) + bench.params.side(s).coulomb_up_n + bench.params.side(s).stiction_extra_n for s in SIDES)
    down_true = sum(bench.params.side(s).weight_at(height) - bench.params.side(s).coulomb_down_n - bench.params.side(s).stiction_extra_n for s in SIDES)
    up = sum(estimate.weight_n[s].mean + estimate.coulomb_up_n[s].mean for s in SIDES)
    down = sum(estimate.weight_n[s].mean - estimate.coulomb_down_n[s].mean for s in SIDES)
    assert abs(up - up_true) <= 0.03 * weight_true, seed
    assert abs(down - down_true) <= 0.03 * weight_true, seed
    assert all(estimate.weight_n[s].rel_spread < 0.05 for s in SIDES), seed  # repeatability


@pytest.mark.parametrize("seed", SEEDS)
def test_wizard_then_hold_and_weightless_on_random_machine(seed: int) -> None:
    bench = _bench(seed, exact_profile=False)  # wrong directions and passport k: the wizard must cope
    report = commission(bench.drives, _tick(bench), MachineProfile())
    assert report.ok, (seed, report.error, report.stages)
    assert report.profile.left.gravity_map.provenance == "measured"

    core = MotorCore(report.profile)
    run_core(core, bench, 0.1)
    core.command("ready")
    core.command("hold")
    bench.user = users.push(kgf_to_n(8), at_s=bench.t + 1.0, duration_s=0.3)
    trace = run_core(core, bench, 6.0)
    assert metrics.hold_osc_mm(trace, start_s=3.0) < 2.0, seed
    assert metrics.limit_cycle(trace, trace.x["left"][-1], start_s=3.0) == 0, seed

    core.command("weightless")
    bench.user = users.push(kgf_to_n(8), at_s=bench.t + 0.5, duration_s=0.3)
    trace = run_core(core, bench, 5.0)
    assert core.supervisor.mode.value == "weightless", seed
    assert metrics.drift_mm_s(trace, start_s=2.0) < 2.0, seed


@pytest.mark.parametrize("seed", SEEDS[:4])
def test_wizard_hold_survives_parameter_drift(seed: int) -> None:
    """T4: after commissioning the physics drifts (+20 % friction, +1 tick delay): hold stays stable."""

    bench = _bench(seed, exact_profile=False)
    report = commission(bench.drives, _tick(bench), MachineProfile())
    assert report.ok, (seed, report.error)
    drifted = bench.params
    drifted = replace(drifted, command_delay_ticks=drifted.command_delay_ticks + 1)
    for side in SIDES:
        physics = drifted.side(side)
        drifted = drifted.with_side(side, replace(physics, coulomb_up_n=physics.coulomb_up_n * 1.2, coulomb_down_n=physics.coulomb_down_n * 1.2))
    bench.params = drifted
    bench.plant.params = drifted
    core = MotorCore(report.profile)
    run_core(core, bench, 0.1)
    core.command("ready")
    core.command("hold")
    bench.user = users.push(kgf_to_n(8), at_s=bench.t + 1.0, duration_s=0.3)
    trace = run_core(core, bench, 6.0)
    assert metrics.limit_cycle(trace, trace.x["left"][-1], start_s=3.0) == 0, seed


def test_dead_man_release_aborts_to_support() -> None:
    bench = _bench(0, exact_profile=True)
    pressed = {"value": True}
    runner = CalibrationRunner(bench.drives, _tick(bench), dead_man=lambda: pressed["value"])

    def procedure():
        frame = yield Command({side: 0.0 for side in SIDES})
        while True:
            if frame.t > 1.0:
                pressed["value"] = False
            frame = yield Command({side: 10.0 for side in SIDES})

    result = runner.run(procedure())
    assert result.status == "aborted"
    assert "экраном" in (result.reason or "")
    assert all(drive.writes[-1] == 100 * drive.profile.sign for drive in bench.drives.values())


def test_envelope_violation_aborts() -> None:
    bench = _bench(1, exact_profile=True)
    runner = CalibrationRunner(bench.drives, _tick(bench), ProcedureEnvelope(max_speed_mm_s=30.0))

    def procedure():
        yield Command({side: 0.0 for side in SIDES})
        while True:
            yield Command({side: 500.0 for side in SIDES})  # far above the window: the bar shoots up

    result = runner.run(procedure())
    assert result.status == "aborted"
    assert "скорость" in (result.reason or "")
