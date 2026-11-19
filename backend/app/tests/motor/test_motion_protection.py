from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.motor.calibration.fault_rehearsal import fault_rehearsal
from app.motor.calibration.procedures.fast import fit_fast_check
from app.motor.calibration.procedures.feel import fit_sync_train
from app.motor.calibration.procedures.holding import fit_sync
from app.motor.calibration.procedures.motion import Balance
from app.motor.calibration.procedures.positioning import fit_positioning
from app.motor.calibration.runner import CalibrationRunner, Command, Frame, ProcedureEnvelope
from app.motor.core import MotorCore
from app.motor.drive.protocol import DriveSample
from app.motor.estimation.observer import ObservedState
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.supervisor.pair import PairMonitor
from app.motor.twin.bench import TwinBench
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES


def samples(t, delta):
    return {s: DriveSample(s, t, True, 600.0 + (delta if s == "left" else 0)) for s in SIDES}


def test_rehearsal_uses_saved_thresholds_and_virtual_sequential_reads():
    result = fault_rehearsal(MachineProfile(), SafetyEnvelope(sync_warning_mm=3, sync_critical_mm=12))
    cases = {r["id"]: r for r in result["cases"]}
    assert len(cases) == 7 and all(r["matches"] for r in cases.values())
    assert cases["level"]["frames"][0]["deltaMm"] is None
    assert all(abs(f["rawMm"]) > 12 and f["deltaMm"] == 0 for f in cases["level"]["frames"][1:])
    assert cases["left"]["frames"][-1]["deltaMm"] < -12 and cases["right"]["frames"][-1]["deltaMm"] > 12
    assert cases["frozen"]["frames"][-1]["deltaMm"] is None
    assert cases["spike"]["frames"][-1]["state"] == "ok"


def test_skew_needs_consecutive_fresh_frames_of_one_sign_except_at_double_threshold():
    monitor = PairMonitor()
    for t, delta in enumerate((16, -16, 0, 16), start=1):
        assert monitor.check(samples(t, delta), t, .15, 15) is None
    assert monitor.check(samples(5, 16), 5, .15, 15).code == "skew"
    assert PairMonitor().check(samples(1, -30), 1, .15, 15).code == "skew"


def test_sync_feedback_does_not_steer_a_level_fast_bar_on_sequential_reads():
    core = MotorCore(MachineProfile())
    for mode in ("hold", "train"):
        core._sync_previous.clear()
        for i in range(1, 6):
            times = {"left": i * .04 - .012, "right": i * .04}
            states = {side: ObservedState(500 + 1500 * t, 1500, 0, t) for side, t in times.items()}
            core._update_sync(mode, states)
            assert core.sync_left_n == pytest.approx(0, abs=1e-9)
        tilted = {side: replace(s, t=s.t + .04, x_mm=s.x_mm + 60 + (6 if side == "left" else 0)) for side, s in states.items()}
        core._update_sync(mode, tilted)
        assert core.sync_left_n < 0


def test_training_sync_preserves_previous_gain_on_bias_missing_direction_or_oscillation():
    ctx = SimpleNamespace(safety=SafetyEnvelope())
    flat = {"k": 2, "why": "time", "rms_mm": .1, "max_mm": 6, "swings": 0, "upSamples": 20, "downSamples": 20}
    runs = [flat, dict(flat, max_mm=1, downSamples=0), dict(flat, max_mm=1, swings=6)]
    outcome = fit_sync_train({"runs": runs, "coupling": 40}, ctx)
    assert outcome.error and not outcome.machine
    assert all(not row["ok"] for row in outcome.report)


@pytest.mark.parametrize("bad,code", [("missing", "drive"), ("stale", "telemetry"), ("alarm", "drive"), ("nan", "telemetry"), ("skew", "skew")])
def test_runner_stops_both_outputs_before_generator_receives_fault(bad, code):
    bench = TwinBench(PlantParams())
    runner = CalibrationRunner(bench.drives, envelope=ProcedureEnvelope(critical_skew_mm=15))
    def move():
        while True:
            yield Command(dict.fromkeys(SIDES, 180.0))

    runner.begin(move())
    pair = samples(1, 32 if bad == "skew" else 0)
    if bad == "missing":
        del pair["right"]
    elif bad == "stale":
        pair["right"] = replace(pair["right"], t=.5)
    elif bad == "alarm":
        pair["right"] = replace(pair["right"], alarm=2)
    elif bad == "nan":
        pair["right"] = replace(pair["right"], position_mm=float("nan"))
    result = runner.feed(Frame(1, pair))
    assert result.status == "aborted" and result.abort_code == code
    assert all(d.last_raw == d.profile.support_raw.value * d.profile.sign for d in bench.drives.values())


def test_x3_rejects_every_unstable_candidate_and_keeps_a_measured_zero():
    ctx = SimpleNamespace(safety=SafetyEnvelope())
    assert Balance.from_profile(replace(MachineProfile(), sync_k_n_per_mm=Measured(0, provenance="measured"))).sync_k == 0
    run = {"k": 2, "up": {"peak": 1}, "down": {"peak": -5}, "rms_mm": 2, "max_mm": 5, "oscillation": 2}
    noisy = dict(run, k=0, max_mm=2, oscillation=8)
    result = fit_sync({"runs": [noisy, run], "coupling": 40}, ctx)
    assert result.error and not result.machine


def test_positioning_ranks_actual_time_and_m6_checks_each_end():
    ctx = SimpleNamespace(safety=SafetyEnvelope(), profile=MachineProfile())
    slow = {"speed_mm_s": 20, "extra": dict.fromkeys(SIDES, 3), "samples": 8, "error_mm": 0, "worst_error_mm": 0,
            "overshoot_mm": 0, "time_s": 4, "steady_speed": 20, "peak_skew_mm": 2}
    fast = {"speed_mm_s": 100, "vmax_mm_s": 100, "distance_mm": 400, "time_s": 4, "error_mm": 0, "worst_error_mm": 2,
            "fallback": False, "peak_skew_mm": 2, "overshoot_mm": 1}
    candidates = [fast, dict(fast, speed_mm_s=200, time_s=3), dict(fast, speed_mm_s=300, time_s=2.98),
                  dict(fast, speed_mm_s=400, time_s=2, worst_error_mm=15)]
    result = fit_positioning({"direction": 1, "runs": [slow, dict(slow, steady_speed=50, speed_mm_s=50)], "fast_runs": candidates}, ctx)
    assert result.machine["position_speed_up_mm_s"][0] == 200
    move = dict(fast, from_mm=100, target_mm=500, limit_mm_s=100, side_error_mm={"left": 9, "right": -9})
    assert fit_fast_check({"moves": [move]}, ctx).error
