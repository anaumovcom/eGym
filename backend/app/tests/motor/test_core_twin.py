from __future__ import annotations

from dataclasses import replace

import pytest

from app.motor.core import MotorCore
from app.motor.force.load_models import LoadSetpoint
from app.motor.profile import MachineProfile, SafetyEnvelope
from app.motor.supervisor.modes import Mode
from app.motor.tuning import metrics
from app.motor.twin import users
from app.motor.twin.bench import TwinBench
from app.motor.twin.loop import Trace, run_core
from app.motor.twin.plant import PlantParams
from app.motor.units import kgf_to_n

X0 = 400.0


def _setup(user=None, params: PlantParams | None = None) -> tuple[MotorCore, TwinBench]:
    bench = TwinBench(params or PlantParams(), seed=1, x0_mm=X0, user=user, initial_raw=100)
    core = MotorCore(MachineProfile())
    run_core(core, bench, 0.2)
    core.command("ready")
    return core, bench


def test_weightless_stops_after_push_without_drift() -> None:
    core, bench = _setup(users.push(kgf_to_n(6), at_s=0.5, duration_s=0.4))
    core.command("weightless")
    run_core(core, bench, 1.5)
    assert bench.true_state("left")[0] > X0 + 3  # the push moved the bar
    trace = run_core(core, bench, 4.0)
    assert metrics.drift_mm_s(trace, start_s=1.0) < 2.0
    assert metrics.sync_rms_mm(trace) < 1.0


def test_hold_is_stable_after_disturbance() -> None:
    core, bench = _setup(users.push(kgf_to_n(8), at_s=1.0, duration_s=0.3))
    core.command("hold")
    trace = run_core(core, bench, 6.0)
    center = trace.x["left"][-1]
    assert metrics.hold_osc_mm(trace, start_s=3.0) < 2.0
    assert metrics.limit_cycle(trace, center, start_s=3.0) == 0


def test_training_balance_and_lift() -> None:
    load = kgf_to_n(20)
    core, bench = _setup(users.constant(load, start_s=0.7))
    core.command("hold")
    run_core(core, bench, 0.5)
    assert core.supervisor.mode == Mode.HOLD
    core.command("train")
    core.set_load(LoadSetpoint(load_n=load))
    trace = run_core(core, bench, 3.0)
    # user force == load: the bar must not run away
    assert metrics.drift_mm_s(trace, start_s=1.0) < 5.0

    bench.user = users.constant(load + kgf_to_n(8))
    run_core(core, bench, 1.0)
    assert bench.true_state("left")[1] > 20.0  # extra force lifts the bar


def test_governor_bounds_descent_when_user_lets_go() -> None:
    load = kgf_to_n(20)
    bench = TwinBench(replace(PlantParams(), travel_mm=2000.0), x0_mm=1300.0, initial_raw=100)
    core = MotorCore(MachineProfile())
    run_core(core, bench, 0.2)
    core.command("ready")
    core.command("hold")
    run_core(core, bench, 0.5)
    core.command("train")
    core.set_load(LoadSetpoint(load_n=load))
    trace = run_core(core, bench, 4.0)
    envelope = SafetyEnvelope()
    assert min(trace.v["left"]) > -envelope.max_descent_mm_s
    assert metrics.overspeed_events(trace, envelope.max_descent_mm_s) == 0


def test_lost_frames_fault_to_support() -> None:
    core, bench = _setup()
    core.command("weightless")
    bench.params = replace(bench.params, drop_probability=1.0)
    trace = Trace()
    run_core(core, bench, 0.2, trace=trace)
    assert core.supervisor.mode == Mode.FAULT
    assert trace.kind[-1] == "support"
    assert "fault" not in trace.mode[:1]


@pytest.mark.parametrize("seed", range(5))
def test_estop_always_support(seed: int) -> None:
    core, bench = _setup(users.steady(10, 300, 700))
    core.command("weightless")
    run_core(core, bench, 0.5 + seed * 0.1)
    core.command("estop")
    trace = run_core(core, bench, 0.1)
    assert set(trace.kind) == {"support"}
