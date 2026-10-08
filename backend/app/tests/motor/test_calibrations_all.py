"""All catalog calibrations on the twin: each session recovers the known physics and reports it."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.motor.calibration.graph import BY_CODE, CATALOG, status
from app.motor.calibration.runner import Frame
from app.motor.calibration.session import CalibrationSession
from app.motor.profile import MachineProfile, Measured
from app.motor.twin.bench import TwinBench
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES, passport_n_per_raw
from app.services.hardware_runtime import hardware_runtime


def _params(**side: Any) -> PlantParams:
    params = PlantParams()
    for name in SIDES:
        params = params.with_side(name, replace(params.side(name), **side))
    return params


def _bench(params: PlantParams, profile: MachineProfile) -> TwinBench:
    return TwinBench(params, {side: profile.side(side) for side in SIDES}, initial_raw=100)


def _run(bench: TwinBench, code: str, profile: MachineProfile, max_s: float = 1600.0, **options: Any) -> CalibrationSession:
    session = CalibrationSession(code, bench.drives, profile, options=options)
    session.begin()
    end = bench.t + max_s
    while session.running and bench.t < end:
        bench.advance(0.05)
        session.keepalive()
        session.step(Frame(bench.t, {side: bench.drives[side].read() for side in SIDES}))
    assert not session.running, f"{code} did not finish"
    return session


def _calibrated(bench: TwinBench, profile: MachineProfile | None = None) -> MachineProfile:
    session = _run(bench, "S3", profile or MachineProfile())
    assert session.status == "done", session.reason
    for drive in bench.drives.values():
        drive.write_raw(0)  # the bar settles on the stops (the start precondition)
    for _ in range(200):
        bench.advance(0.05)
    assert all(bench.plant.state[side].x_mm < 1 for side in SIDES)
    for drive in bench.drives.values():
        drive.support()
    return session.profile


def _done(session: CalibrationSession) -> dict[str, Any]:
    payload = session.to_payload()
    assert payload["status"] == "done", payload["reason"]
    result = payload["stages"][-1]["result"]
    assert result["report"] and all(set(line) == {"label", "value", "ok"} for line in result["report"])
    return payload


def test_catalog_is_fully_implemented() -> None:
    assert all(spec.implemented and spec.description and spec.steps and spec.duration_s for spec in CATALOG)
    assert BY_CODE["S9"].inputs == ("referenceKg",) and BY_CODE["G1"].inputs == ("referenceKg",)


def test_b0_config_check_and_b1_bus_timing() -> None:
    bench = _bench(PlantParams(), MachineProfile())
    payload = _done(_run(bench, "B0", MachineProfile()))
    assert not payload["hasChanges"] and payload["stages"][0]["result"]["ok"]

    session = _run(bench, "B1", MachineProfile())
    payload = _done(session)
    result = payload["stages"][0]["result"]
    assert result["loop_period_s"] == pytest.approx(0.05, abs=1e-6) and result["ok"]
    assert session.profile.loop_period_s.provenance == "measured" and payload["hasChanges"]
    assert bench.drives["left"].last_raw == 100  # support during the measurement


def test_b7_absolute_zero() -> None:
    params = replace(PlantParams(), encoder_zero_counts=123_456)
    bench = _bench(params, MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "B7", profile)
    _done(session)
    for side in SIDES:
        assert session.profile.side(side).zero_counts.value == pytest.approx(123_456, abs=2)
        assert session.profile.side(side).zero_counts.provenance == "measured"


def test_s7_height_map_recovers_slope() -> None:
    slope = 0.02  # N/mm
    bench = _bench(_params(weight_slope_n_per_mm=slope), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "S7", profile)
    payload = _done(session)
    assert status(profile, BY_CODE["S7"]) == "missing"
    assert status(session.profile, BY_CODE["S7"]) == "actual"
    for side in SIDES:
        points = session.profile.side(side).gravity_map.value
        assert len(points) == 5 and points[-1][0] > 1000
        assert payload["stages"][0]["result"]["sides"][side]["slope_n_per_m"] == pytest.approx(slope * 1000, abs=5)
        assert session.profile.side(side).weight_n(points[-1][0]) - session.profile.side(side).weight_n(points[0][0]) == pytest.approx(
            slope * (points[-1][0] - points[0][0]), abs=4
        )
    assert {"coulomb_up_n", "gravity_map"} <= {item["key"] for item in payload["changes"]}


def test_s9_scale_and_g1_accuracy() -> None:
    true_k = 0.8
    params = _params(n_per_raw=true_k)
    bench = _bench(params, MachineProfile())
    profile = _calibrated(bench)  # believes the passport 0.71
    bench.params = bench.plant.params = _params(n_per_raw=true_k, extra_mass_kg=5.0)

    with pytest.raises(ValueError, match="эталонного"):
        CalibrationSession("S9", bench.drives, profile)
    session = _run(bench, "S9", profile, referenceKg=10.0)
    payload = _done(session)
    for side in SIDES:
        assert session.profile.side(side).n_per_raw_value == pytest.approx(true_k, rel=0.04)
        ratio = true_k / passport_n_per_raw()
        assert session.profile.side(side).weight_n(10) == pytest.approx(profile.side(side).weight_n(10) * ratio, rel=0.04)
    assert {"n_per_raw", "gravity_map", "hold_ultimate_k_n_per_mm"} <= {item["key"] for item in payload["changes"]}

    scaled = session.profile
    for drive in bench.drives.values():
        drive.profile = scaled.side(drive.side)  # type: ignore[attr-defined]
    check = _run(bench, "G1", scaled, referenceKg=10.0)
    payload = _done(check)
    assert payload["stages"][0]["result"]["ok"] and not payload["hasChanges"]

    wrong = _run(bench, "G1", scaled, referenceKg=20.0)
    assert wrong.status == "failed" and "допуск" in (wrong.reason or "")
    assert wrong.stages[0].result["report"] and not wrong.stages[0].result["ok"]


@pytest.mark.parametrize("viscous", [0.05, 0.2])
def test_d2_viscous_friction(viscous: float) -> None:
    bench = _bench(_params(viscous_n_per_mm_s=viscous), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "D2", profile)
    _done(session)
    for side in SIDES:
        assert session.profile.side(side).viscous_n_per_mm_s.value == pytest.approx(viscous, abs=0.05)


def test_d4_moving_mass() -> None:
    bench = _bench(_params(viscous_n_per_mm_s=0.1), MachineProfile())
    profile = _calibrated(bench)
    for side in SIDES:
        profile = profile.with_side(side, replace(profile.side(side), viscous_n_per_mm_s=Measured(0.1, None, "measured")))
    session = _run(bench, "D4", profile)
    _done(session)
    for side in SIDES:
        assert session.profile.side(side).moving_mass_kg.value == pytest.approx(60.0, rel=0.2)


def test_c3_support_lowers_the_bar_slowly() -> None:
    bench = _bench(PlantParams(), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "C3", profile)
    payload = _done(session)
    result = payload["stages"][0]["result"]
    assert 5.0 <= result["speed_mm_s"] <= 25.0
    raw = {side: session.profile.side(side).support_raw.value for side in SIDES}
    assert all(isinstance(value, int) and 0 < value < 100 for value in raw.values())
    assert all(abs(bench.plant.state[side].x_mm) < 15 for side in SIDES)  # landed


def test_api_reference_weight_and_verification_status(client) -> None:
    hardware_runtime.set_service_mode(True)
    hardware_runtime.set_servo(True)
    try:
        for _ in range(3):
            hardware_runtime.tick()
        catalog = {item["code"]: item for item in client.get("/api/motor/calibrations").json()}
        assert catalog["B0"]["status"] == "missing" and catalog["S9"]["inputs"] == ["referenceKg"]
        assert client.post("/api/motor/calibration/start", json={"code": "S9", "referenceKg": 100}).status_code == 422

        assert client.post("/api/motor/calibration/start", json={"code": "B0"}).status_code == 200
        session = hardware_runtime.calibration
        assert session is not None
        for _ in range(200):
            if not session.running:
                break
            session.keepalive()
            hardware_runtime.tick()
        assert session.status == "done", session.reason
        catalog = {item["code"]: item for item in client.get("/api/motor/calibrations").json()}
        assert catalog["B0"]["status"] == "actual" and catalog["B0"]["measuredAt"]
        assert client.post("/api/motor/calibration/discard").json() == {"ok": True}
        catalog = {item["code"]: item for item in client.get("/api/motor/calibrations").json()}
        assert catalog["B0"]["status"] == "actual"  # a passed check stays passed after closing
    finally:
        hardware_runtime.abort_calibration()
        hardware_runtime.set_service_mode(False)
