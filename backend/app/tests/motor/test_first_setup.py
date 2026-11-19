from dataclasses import replace

import pytest

from app.motor.calibration.graph import (
    AUTO_STAGES,
    BY_CODE,
    PRIORITY_ORDER,
    RUN_SPECS,
    RUNNABLE,
    CheckResult,
    graph,
    status,
)
from app.motor.calibration.procedures.common import Context, Operator
from app.motor.calibration.procedures.estimation import fit_friction_track
from app.motor.calibration.procedures.feel import fit_release
from app.motor.calibration.procedures.motion import Balance
from app.motor.calibration.runner import Frame
from app.motor.calibration.session import CalibrationSession
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.twin.bench import TwinBench
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES
from app.tests.motor.test_calibrations_all import FEATURES, _params, _TrackingOperator


def test_catalog_explains_each_priority_and_series_inherit_the_highest_stage() -> None:
    profile = MachineProfile()
    catalog = {item["code"]: item for item in graph(profile)}
    assert catalog.keys() == RUN_SPECS.keys()
    for code, spec in RUN_SPECS.items():
        assert catalog[code]["priority"] == spec.priority and spec.priority in PRIORITY_ORDER
        assert catalog[code]["priorityReason"] == spec.priority_reason and spec.priority_reason.strip()
        stages = RUNNABLE[code]
        if len(stages) > 1:
            assert spec.priority == max((BY_CODE[stage].priority for stage in stages), key=PRIORITY_ORDER.index)
    assert all(catalog[code]["priority"] == "critical" for code in ("M5", "E1", "F11"))
    assert catalog["S10"]["priority"] == "important"
    assert catalog["F9"]["priority"] == "refinement"
    for ok, expected in ((True, "actual"), (False, "failed")):
        checked = next(item for item in graph(profile, {"B0": CheckResult("2026-01-12T10:00:00Z", ok)}) if item["code"] == "B0")
        assert checked["status"] == expected
        assert checked["priority"] == catalog["B0"]["priority"] == "critical"


def test_track_refuses_to_fill_a_gap_on_one_rail() -> None:
    profile = MachineProfile()
    ctx = Context(profile, Balance.from_profile(profile), SafetyEnvelope(), {}, Operator(), {})
    data = {"low_mm": 0.0, "high_mm": 600.0, "speed_mm_s": 30, "up": {}, "down": {}}
    for leg in ("up", "down"):
        for side in SIDES:
            data[leg][side] = [(1.0, x + offset, 30.0, 12 if x == 350 else 1) for x in range(10, 600, 20) for offset in (-1, 0, 1)]
    data["down"]["right"] = [row for row in data["down"]["right"] if not 215 < row[1] < 305]
    outcome = fit_friction_track(data, ctx)
    track = outcome.data["track"]
    assert outcome.error and not outcome.sides
    assert track["sides"]["right"].count(None) == 4 and None not in track["sides"]["left"]
    assert track["sides"]["left"][track["heightsMm"].index(350)] == 11
    gap = track["heightsMm"].index(250)
    assert track["directionalN"]["right"]["up"][gap] is not None
    assert track["directionalN"]["right"]["down"][gap] is None


def test_screw_track_separates_directional_load_from_local_resistance_and_noise() -> None:
    profile = MachineProfile()
    ctx = Context(profile, Balance.from_profile(profile), SafetyEnvelope(), {}, Operator(), {})
    data = {"low_mm": 0.0, "high_mm": 600.0, "speed_mm_s": 30, "up": {}, "down": {}}
    for leg, direction in (("up", 1), ("down", -1)):
        for side in SIDES:
            trace = []
            for x in range(10, 600, 20):
                # An unmodelled vertical load reverses sign in the directional residual.
                weight = 18 if x == 190 else 0
                extra = 22 if side == "left" and x == 350 else 0
                noise = (0, 3, -3)[(x // 20) % 3] if side == "right" else 0
                trace.extend([(1, x, 30, 5 + extra + direction * weight + noise)] * 3)
                trace.extend([(1, x, 30, float("nan")), (1, x, 90, 900), (0.1, x, 30, 900)])
            data[leg][side] = trace
    track = fit_friction_track(data, ctx).data["track"]
    weight_idx = track["heightsMm"].index(190)
    assert track["sides"]["left"][weight_idx] == 0
    assert track["directionalN"]["left"]["up"][weight_idx] == round(ctx.balance.coulomb_up["left"] + 23, 1)
    assert track["directionalN"]["left"]["down"][weight_idx] == round(ctx.balance.coulomb_down["left"] - 13, 1)
    assert track["summary"]["left"]["peakN"] == 22 and track["summary"]["left"]["weightWithinTolerance"] is False
    assert track["summary"]["right"]["peakN"] is None
    assert track["summary"]["right"]["thresholdN"] > track["summary"]["left"]["thresholdN"]
    assert track["summary"]["left"]["typicalN"] == round(5 + (ctx.balance.coulomb_up["left"] + ctx.balance.coulomb_down["left"]) / 2, 1)


def test_refining_speed_tables_does_not_date_the_inertia_or_claim_a_weight_test() -> None:
    profile = MachineProfile()
    first = Measured(1.0, None, "measured", "AUTO_MOTION-abc", "2026-01-01T12:00:00Z")
    for side in SIDES:
        profile = profile.with_side(side, replace(profile.side(side), **{
            path.split(".")[1]: first for code in ("D2", "D4") for path in BY_CODE[code].produces if path.startswith(side)
        }))
    assert status(profile, BY_CODE["F3"]) == status(profile, BY_CODE["D5"]) == "missing"
    finer = replace(first, value=[(40, 20), (80, 22)], run_id="AUTO_FEEL-def", measured_at="2026-01-02T12:00:00Z")
    for side in SIDES:
        profile = profile.with_side(side, replace(profile.side(side), friction_table_up=finer, friction_table_down=finer))
    assert status(profile, BY_CODE["F3"]) == status(profile, BY_CODE["D4"]) == "actual"


def test_short_overlapping_release_estimates_cannot_set_a_grip_threshold() -> None:
    frames = [(i * 0.05, 55.0) for i in range(40)]
    trial = {"load_n": 60.0, "held": frames, "moving": frames, "released": [(i * 0.05, v) for i, v in enumerate([55, 15, 12, 10])]}
    outcome = fit_release({"trials": [trial, trial], "period_s": 0.05}, None)
    assert outcome.error and not outcome.machine
    assert any(row["ok"] is False for row in outcome.report)


def test_all_series_validate_external_inputs_before_motion() -> None:
    bench = TwinBench(PlantParams())
    for code in AUTO_STAGES:
        with pytest.raises(ValueError, match="B7|массу эталонного"):
            CalibrationSession(code, bench.drives, MachineProfile())


@pytest.mark.parametrize("uneven", (False, True), ids=("standard", "short-uneven-guides"))
def test_complete_first_setup_from_a_factory_profile(uneven: bool) -> None:
    params = PlantParams()
    if uneven:
        params = _params(**FEATURES)
        params = replace(params, right=replace(params.right, tight_spots=((680.0, 18.0, 32.0),)), travel_mm=1270.0)
    profile, safety, checks = MachineProfile(), SafetyEnvelope(), {}
    bench = TwinBench(params, initial_raw=100)
    route = ("WIZARD", "B8", "B6", *AUTO_STAGES, "F11", "G4", "G2", "G3")
    for code in route:
        for prerequisite in RUN_SPECS[code].requires:
            allowed = ("actual",) if code == "G3" else ("actual", "stale")
            assert status(profile, BY_CODE[prerequisite], checks) in allowed, (code, prerequisite)
        bench.user = None
        for side in SIDES:
            bench.drives[side].profile = profile.side(side)
            bench.drives[side].write_raw(0)
        for _ in range(200):
            bench.advance(0.05)
        options = {}
        loaded = params
        if code == "AUTO_WEIGHT":
            options["referenceKg"] = 20
            loaded = replace(params, **{s: replace(params.side(s), extra_mass_kg=10) for s in SIDES})
        elif code in ("G4", "G3"):
            options["workingZone"] = "middle"
        bench.params = bench.plant.params = loaded
        run = CalibrationSession(code, bench.drives, profile, safety=safety, options=options)
        operator = _TrackingOperator(bench, params) if code in ("B6", "G3") else None
        run.begin()
        first_direction = last_coverage = None
        for tick in range(30000):
            if not run.running:
                break
            bench.advance(0.05)
            run.keepalive()
            if operator:
                operator(run)
            run.step(Frame(bench.t, {s: bench.drives[s].read() for s in SIDES}))
            if code == "AUTO_GUIDES" and run.running and run.current_stage.code == "S10" and tick % 20 == 0:
                last_coverage = run.to_payload()["frictionCoverage"]
                if first_direction is None and 1 in last_coverage["sides"]["left"]:
                    first_direction = last_coverage
        assert run.status == "done", (code, run.reason, run.current_stage.result)
        for stage in run.stages:
            if not BY_CODE[stage.code].produces:
                checks[stage.code] = CheckResult(run.finished_at.isoformat(), True)
        profile = run.profile
        if code == "B8" and run.stages[0].result["suggestedSoftMaxMm"] is not None:
            safety = replace(safety, soft_max_mm=run.stages[0].result["suggestedSoftMaxMm"])
        if code == "AUTO_GUIDES":
            track = run.stages[-1].result["track"]
            assert first_direction and last_coverage and last_coverage["heightsMm"] == track["heightsMm"]
            assert run.to_payload()["frictionCoverage"] is None
            for side, expected in (("left", 600), ("right", 680)):
                assert 3 not in first_direction["sides"][side]
                assert [flag == 3 for flag in last_coverage["sides"][side]] == [v is not None for v in track["sides"][side]]
                peak = track["summary"][side]["peakMm"]
                if uneven:
                    assert peak == pytest.approx(expected, abs=30)
                else:
                    assert peak is None
            assert all(0 < len(run.log_payload(stage, 240)["t"]) <= 241 for stage in run.stages)
        if code == "AUTO_MOTION":
            assert all(stage.zone and stage.zone[0] > 100 for stage in run.stages[:2])
        if code == "G3":
            assert [item["reps"] for item in run.current_stage.result["items"]] == [3, 3]
    catalog = {item["code"]: item["status"] for item in graph(profile, checks)}
    assert all(catalog[code] == "actual" for code in route)
