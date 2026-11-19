"""Geometry and complete digital-twin runs for calibrated mid-travel measurements."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from app.motor.calibration.middle_zone import D4_HIGH_MM, middle_window
from app.motor.calibration.procedures.smith import fit_repeatability
from app.motor.calibration.runner import Frame
from app.motor.calibration.session import CalibrationSession
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.twin.bench import TwinBench
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES


def _measured_profile(
    travel: float = 1300.0, *, soft_min: float = 20.0, soft_max: float = 1270.0
) -> tuple[MachineProfile, SafetyEnvelope]:
    """Профиль с измеренными B7 (обе стороны), B8 и C3 и корректной огибающей."""
    profile = replace(MachineProfile(), travel_mm=Measured(travel, None, "measured"))
    for side in SIDES:
        profile = profile.with_side(side, replace(
            profile.side(side),
            zero_counts=Measured(123_456, None, "measured"),
            support_raw=Measured(50, None, "measured"),
        ))
    return profile, SafetyEnvelope(soft_min_mm=soft_min, soft_max_mm=soft_max)


def _run(
    bench: TwinBench, code: str, profile: MachineProfile, *, safety: SafetyEnvelope | None = None, **options
) -> CalibrationSession:
    session = CalibrationSession(code, bench.drives, profile, options=options, safety=safety)
    session.begin()
    end = bench.t + 2000.0
    while session.running and bench.t < end:
        bench.advance(0.05)
        session.keepalive()
        session.step(Frame(bench.t, {side: bench.drives[side].read() for side in SIDES}))
    assert not session.running, f"{code} не завершилась"
    return session


# -------------------------------------------------------------------- геометрия

def test_d2_middle_zone_is_centered_400mm() -> None:
    profile, safety = _measured_profile(travel=1300.0, soft_max=1270.0)
    low, high = middle_window("D2", profile, safety)
    assert (low, high) == (450.0, 850.0)
    assert high - low == 400.0
    assert (low + high) / 2 == 650.0  # середина подтверждённого хода


def test_d4_middle_zone_top_is_capped_at_700() -> None:
    profile, safety = _measured_profile(travel=1300.0, soft_max=1270.0)
    low, high = middle_window("D4", profile, safety)
    assert high <= D4_HIGH_MM
    assert (low, high) == (300.0, 700.0)
    assert high - low == 400.0


def test_short_travel_fills_the_available_band() -> None:
    profile, safety = _measured_profile(travel=500.0, soft_max=470.0)
    low, high = middle_window("D2", profile, safety)
    assert (low, high) == (20.0, 390.0)
    assert high - low == pytest.approx(370.0)


def test_minimum_stroke_is_used_when_boundaries_are_tight() -> None:
    profile, safety = _measured_profile(travel=430.0, soft_max=400.0)
    low, high = middle_window("D2", profile, safety)
    assert (low, high) == (20.0, 320.0)
    assert high - low == pytest.approx(300.0)


# --------------------------------------------------------------------- отказы

def test_rejects_procedures_with_fixed_working_heights() -> None:
    profile, safety = _measured_profile()
    with pytest.raises(ValueError, match="собственный участок"):
        middle_window("S3", profile, safety)
    with pytest.raises(ValueError, match="собственный участок"):
        middle_window("WIZARD", profile, safety)


def test_rejects_missing_b7_b8_c3() -> None:
    profile, safety = _measured_profile()
    with pytest.raises(ValueError, match="B7"):
        middle_window("D2", replace(profile, left=replace(profile.left, zero_counts=Measured(None))), safety)
    with pytest.raises(ValueError, match="B8"):
        middle_window("D2", replace(profile, travel_mm=Measured(1300.0)), safety)
    with pytest.raises(ValueError, match="C3"):
        middle_window("D2", replace(profile, right=replace(profile.right, support_raw=Measured(None))), safety)


def test_rejects_bad_soft_limits_and_travel() -> None:
    profile, _ = _measured_profile()
    with pytest.raises(ValueError, match="должен быть ниже"):
        middle_window("D2", profile, SafetyEnvelope(soft_min_mm=20.0, soft_max_mm=1380.0))
    with pytest.raises(ValueError, match="выше нижнего"):
        middle_window("D2", profile, SafetyEnvelope(soft_min_mm=100.0, soft_max_mm=100.0))
    with pytest.raises(ValueError, match="отрицательным"):
        middle_window("D2", profile, SafetyEnvelope(soft_min_mm=-5.0, soft_max_mm=1000.0))
    with pytest.raises(ValueError, match="конечными"):
        middle_window("D2", profile, SafetyEnvelope(soft_min_mm=20.0, soft_max_mm=math.nan))


def test_rejects_when_300mm_do_not_fit() -> None:
    profile, safety = _measured_profile(travel=420.0, soft_max=390.0)
    with pytest.raises(ValueError, match="доступно"):
        middle_window("D2", profile, safety)


# ------------------------------------------------------------ полные прогоны

def test_d2_middle_zone_full_run() -> None:
    profile, safety = _measured_profile(travel=1300.0, soft_max=1270.0)
    bench = TwinBench(PlantParams(travel_mm=1300.0), {side: profile.side(side) for side in SIDES}, initial_raw=100)
    session = _run(bench, "D2", profile, safety=safety, workingZone="middle")
    assert session.status == "done", session.reason
    result = session.to_payload()["stages"][0]["result"]
    assert result["working_zone"] == {"low_mm": 450.0, "high_mm": 850.0}
    assert any("Рабочая зона" in line["label"] and "450…850" in line["value"] for line in result["report"])
    for side in SIDES:
        assert session.profile.side(side).viscous_n_per_mm_s.value == pytest.approx(0.05, abs=0.05)


def test_d4_middle_zone_full_run_after_d2() -> None:
    profile, safety = _measured_profile(travel=1300.0, soft_max=1270.0)
    bench = TwinBench(PlantParams(travel_mm=1300.0), {side: profile.side(side) for side in SIDES}, initial_raw=100)
    d2 = _run(bench, "D2", profile, safety=safety, workingZone="middle")
    assert d2.status == "done", d2.reason
    d4 = _run(bench, "D4", d2.profile, safety=safety, workingZone="middle")
    assert d4.status == "done", d4.reason
    result = d4.to_payload()["stages"][0]["result"]
    assert result["working_zone"] == {"low_mm": 300.0, "high_mm": 700.0}
    assert any("Рабочая зона" in line["label"] and "300…700" in line["value"] for line in result["report"])
    for side in SIDES:
        assert d4.profile.side(side).moving_mass_kg.value == pytest.approx(60.0, rel=0.25)


@pytest.mark.parametrize("code", ["F3", "G4", "V1", "V2", "V3"])
def test_smith_measurements_use_the_displayed_window_and_land(code: str) -> None:
    profile, safety = _measured_profile()
    bench = TwinBench(PlantParams(travel_mm=1300.0), {side: profile.side(side) for side in SIDES}, initial_raw=100)
    session = _run(bench, code, profile, safety=safety, workingZone="middle")
    assert session.status == "done", session.reason
    low, high = middle_window(code, profile, safety)
    assert session.working_zone == {"lowMm": low, "highMm": high}
    trace = session.log_payload()
    assert high - 10 <= max(trace["xL"]) <= high + 20
    assert high - 10 <= max(trace["xR"]) <= high + 20
    assert all(bench.plant.state[side].x_mm < 15.0 for side in SIDES)
    if code == "G4":
        result = session.stages[0].result
        assert len(result["passes"]) == 6
        assert all(450 < height < 850 for height in result["heightsMm"])
        assert all(line["ok"] is not False for line in result["report"])
        assert not session.changes()
        result["passes"][0]["left"][1] = None
        missing = fit_repeatability(result, session._context)
        assert missing.error and any(line["ok"] is False for line in missing.report)
        result["passes"][0]["left"][1] = result["passes"][2]["left"][1] + 60
        uneven = fit_repeatability(result, session._context)
        assert uneven.error and "трение" in uneven.error


def test_hand_trial_hands_over_the_bar_in_the_selected_window() -> None:
    profile, safety = _measured_profile()
    bench = TwinBench(PlantParams(travel_mm=1300.0), {side: profile.side(side) for side in SIDES}, initial_raw=100)
    session = CalibrationSession("G3", bench.drives, profile, options={"workingZone": "middle"}, safety=safety)
    session.begin()
    while session.running and session.prompt is None and bench.t < 180:
        bench.advance(0.05)
        session.keepalive()
        session.step(Frame(bench.t, {side: bench.drives[side].read() for side in SIDES}))
    low, high = middle_window("G3", profile, safety)
    assert session.prompt and "6 кг" in session.prompt.text
    assert low < bench.true_state("left")[0] < high - 200
    session.cancel("проверка стартовой точки завершена")


def test_h3_runs_the_fixed_law_at_common_height_and_archives_only_engaged_frames() -> None:
    from app.motor.calibration.procedures.fixed import fit_fixed

    profile, safety = _measured_profile()
    profile = replace(profile, hold_k_n_per_mm=Measured(1.8, provenance="measured"), hold_c_n_per_mm_s=Measured(.3, provenance="measured"))
    bench = TwinBench(PlantParams(travel_mm=1300), {side: profile.side(side) for side in SIDES}, initial_raw=100)
    session = _run(bench, "H3", profile, safety=safety)
    result = session.stages[0].result
    assert session.status == "done", (session.reason, result)
    assert result["targetMm"] == 650 and [r["direction"] for r in result["runs"]] == [-1, 1]
    assert min(r["appliedN"] for r in result["runs"]) >= 28.5
    assert all(abs(bench.true_state(s)[0]) < 5 for s in SIDES)
    log = session.log_payload()
    assert log["holdTargetMm"][0] is None and log["holdTargetMm"][-1] is None
    assert {v for v in log["holdTargetMm"] if v is not None} == {650}
    assert len(log["skewMm"]) == len(log["holdTargetMm"]) == len(log["t"])
    assert not session.changes()
    masked = {**result["runs"][0], "excursion": dict.fromkeys(SIDES, 0.2), "breakawayN": dict.fromkeys(SIDES, 80)}
    assert "Трение покоя" in fit_fixed({**result, "runs": [masked]}, session._context).error
    result["runs"][0]["tail"]["right"] = 6.1
    assert fit_fixed(result, session._context).error
    result["runs"][0]["tail"]["right"] = 0
    result["runs"][0]["appliedN"] = 0
    assert fit_fixed(result, session._context).error
