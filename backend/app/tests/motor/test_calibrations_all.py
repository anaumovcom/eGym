"""All catalog calibrations on the twin: each session recovers the known physics and reports it."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.motor.calibration.graph import BY_CODE, CATALOG, ORDER, WIZARD_STAGES, CheckResult, graph, status
from app.motor.calibration.runner import Frame
from app.motor.calibration.session import CalibrationSession
from app.motor.parameters import PARAMS, apply_changes
from app.motor.profile import MachineProfile, Measured
from app.motor.store import ProfileBundle
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
    assert set(ORDER) == set(BY_CODE) and ORDER[:len(WIZARD_STAGES)] == WIZARD_STAGES
    produced = {path.split(".")[-1] for spec in CATALOG for path in spec.produces}
    for spec in PARAMS:
        if spec.scope in ("side", "machine") and spec.key != "mm_per_pulse":
            assert spec.produced_by, f"{spec.key}: no calibration measures it"
            assert all(code in BY_CODE for code in spec.produced_by), spec.key
    assert produced <= {spec.key for spec in PARAMS}


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
        assert catalog["B0"]["lastCheck"]["ok"] and catalog["WIZARD"]["order"] == 0 and catalog["Q1"]["order"] == len(ORDER)
    finally:
        hardware_runtime.abort_calibration()
        hardware_runtime.set_service_mode(False)


@pytest.mark.parametrize("delay_ticks", [1, 2])
def test_b3_control_delay(delay_ticks: int) -> None:
    bench = _bench(replace(PlantParams(), command_delay_ticks=delay_ticks), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "B3", profile)
    _done(session)
    assert session.profile.loop_delay_s.value == pytest.approx(0.05 * delay_ticks, abs=0.02)
    assert session.profile.loop_delay_s.provenance == "measured"


def test_b8_travel_to_the_upper_stop() -> None:
    bench = _bench(replace(PlantParams(), travel_mm=1200.0), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "B8", profile)
    payload = _done(session)
    assert session.profile.travel_mm.value == pytest.approx(1200.0, abs=5.0)
    soft_limit = next(line for line in payload["stages"][0]["result"]["report"] if "программный" in line["label"])
    assert soft_limit["ok"] is False  # 1380 mm default is above the measured travel
    assert all(bench.plant.state[side].x_mm < 15 for side in SIDES)  # back on the stops


@pytest.mark.parametrize(("coupling", "lower_bound"), [(40.0, False), (2000.0, True)])
def test_x2_side_coupling(coupling: float, lower_bound: bool) -> None:
    bench = _bench(replace(PlantParams(), coupling_n_per_mm=coupling), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "X2", profile)
    payload = _done(session)
    k = session.profile.side_coupling_n_per_mm.value
    result = payload["stages"][0]["result"]
    assert result["lower_bound"] is lower_bound
    if lower_bound:
        assert 500 < k <= coupling  # a stiff bar: an honest lower bound
    else:
        assert k == pytest.approx(coupling, rel=0.25)
    assert all(abs(bench.plant.state[side].x_mm) < 15 for side in SIDES)


def test_q1_daily_check_passes_and_detects_drift() -> None:
    bench = _bench(PlantParams(), MachineProfile())
    profile = _calibrated(bench)
    payload = _done(_run(bench, "Q1", profile))
    assert payload["stages"][0]["result"]["ok"] and not payload["hasChanges"]

    bench.params = bench.plant.params = _params(extra_mass_kg=3.0)  # +29 N per side: ≈ +43 % weight
    failed = _run(bench, "Q1", profile)
    assert failed.status == "failed" and "вес" in (failed.reason or "")
    assert failed.stages[0].result["report"]


def test_d2_splits_stiction_from_kinetic_friction() -> None:
    bench = _bench(_params(stiction_extra_n=15.0), MachineProfile())
    profile = _calibrated(bench)  # S3 sees the breakaway: Fc + stiction ≈ 64 N
    session = _run(bench, "D2", profile)
    _done(session)
    for side in SIDES:
        before, after = profile.side(side), session.profile.side(side)
        assert after.stribeck_extra_n.value == pytest.approx(15.0, abs=4.0)
        assert after.coulomb_up_n.value == pytest.approx(49.0, abs=4.0)
        # the window edges (breakaway) do not change; the S3 measurement keeps its provenance
        assert after.coulomb_up_n.value + after.stribeck_extra_n.value == pytest.approx(before.coulomb_up_n.value, abs=1e-6)
        assert after.coulomb_down_n.value + after.stribeck_extra_n.value == pytest.approx(before.coulomb_down_n.value, abs=1e-6)
        assert after.coulomb_up_n.measured_at == before.coulomb_up_n.measured_at
    assert status(session.profile, BY_CODE["D2"]) == "actual"

    rerun = _run(bench, "S3", session.profile)  # S3 again: the split is reset, D2 is out of date
    assert rerun.profile.left.stribeck_extra_n.value == 0.0
    assert status(rerun.profile, BY_CODE["D2"]) == "stale"
    entry = next(item for item in graph(rerun.profile) if item["code"] == "D2")
    assert "S3" in (entry["staleReason"] or "")


def test_graph_checks_and_staleness() -> None:
    profile = MachineProfile()
    checks = {"B0": CheckResult("2026-01-01T10:00:00+00:00", False), "G1": CheckResult("2026-01-01T10:00:00", True)}
    items = {item["code"]: item for item in graph(profile, checks)}
    assert items["B0"]["status"] == "failed" and items["B0"]["lastCheck"] == {"finishedAt": "2026-01-01T10:00:00+00:00", "ok": False}
    assert items["G1"]["status"] == "actual"
    measured = Measured(0.8, None, "measured", "S9-x", "2026-02-01T10:00:00+00:00")
    profile = profile.with_side("left", replace(profile.left, n_per_raw=measured)).with_side("right", replace(profile.right, n_per_raw=measured))
    assert status(profile, BY_CODE["G1"], checks) == "stale"  # the scale changed after the check
    assert items["Q1"]["status"] == "missing" and items["B8"]["requires"] == ["S3", "C3"]


def test_parameter_cross_checks() -> None:
    bundle = ProfileBundle(MachineProfile())
    with pytest.raises(ValueError, match="аварийная|Аварийная"):
        apply_changes(bundle, [{"scope": "envelope", "key": "overspeed_rpm_alarm", "value": 900}])
    with pytest.raises(ValueError, match="PA_056"):
        apply_changes(bundle, [{"scope": "envelope", "key": "max_speed_mm_s", "value": 600}])
    with pytest.raises(ValueError, match="рабочего хода"):
        apply_changes(bundle, [{"scope": "machine", "key": "travel_mm", "value": 1300}])
    updated = apply_changes(bundle, [{"scope": "machine", "key": "travel_mm", "value": 1300}, {"scope": "envelope", "key": "soft_max_mm", "value": 1270}])
    assert updated.envelope.soft_max_mm == 1270
    assert apply_changes(bundle, [{"scope": "tunables", "key": "hold_k_fraction", "value": 0.2}]).tunables.hold_k_fraction == 0.2


# ---------------------------------------------------------------- motion (M)
def _adhesive(adhesion_n: float) -> PlantParams:
    """The A6 bench failure: the bar sticks to the bottom stops beyond the window measured in the air."""

    return _params(stop_adhesion_n=adhesion_n)


def test_c3_leaves_sticky_stops_without_m1() -> None:
    """Before M1 a move escalates its force step by step instead of giving up at edge + 0.6·Fc."""

    bench = _bench(_adhesive(45.0), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "C3", profile)
    _done(session)


def test_m1_measures_liftoff_and_moves_start_at_once() -> None:
    bench = _bench(_adhesive(45.0), MachineProfile())
    profile = _calibrated(bench)
    session = _run(bench, "M1", profile)
    _done(session)
    for side in SIDES:
        assert session.profile.side(side).liftoff_extra_n.value == pytest.approx(45.0, abs=8.0)
    # with M1 the lift-off needs no escalation
    from app.motor.calibration.procedures.motion import Balance, Motion, travel
    from app.motor.calibration.runner import CalibrationRunner, Command

    state = Motion()

    def lift():
        frame = yield Command(None)
        yield from travel(Balance.from_profile(session.profile), frame, 60.0, state=state)
        return {}

    runner = CalibrationRunner(bench.drives, lambda: (bench.advance(0.05), bench.t)[1])
    assert runner.run(lift()).status == "done"
    assert state.escalations == 0


def test_m2_m3_m4_governed_motion() -> None:
    bench = _bench(_params(stiction_extra_n=8.0, viscous_n_per_mm_s=0.1), MachineProfile())
    profile = _calibrated(bench)
    profile = _run(bench, "M1", profile).profile

    m2 = _run(bench, "M2", profile)
    payload = _done(m2)
    result = payload["stages"][0]["result"]
    assert abs(result["up"]["speed_mean"] - 20.0) < 4.0 and abs(result["down"]["speed_mean"] - 20.0) < 4.0
    for side in SIDES:
        assert m2.profile.side(side).travel_extra_up_n.provenance == "measured"
        # 20 mm/s up: kinetic friction (−stiction) + viscous ≈ −8 + 2 N beyond the breakaway edge
        assert m2.profile.side(side).travel_extra_up_n.value == pytest.approx(-6.0, abs=6.0)

    m3 = _run(bench, "M3", m2.profile)
    _done(m3)
    assert 0.0 <= m3.profile.brake_lag_s.value < 0.3
    assert m3.profile.brake_decel_up_mm_s2.value is None or m3.profile.brake_decel_up_mm_s2.value > 50

    support = _run(bench, "C3", m3.profile)
    check = _run(bench, "M4", support.profile)
    payload = _done(check)
    result = payload["stages"][0]["result"]
    assert result["ok"] and result["max_error_mm"] <= 5.0 and not payload["hasChanges"]


def test_envelope_ignores_a_single_speed_spike() -> None:
    """A6 bench: PA_1C1 reported 91 mm/s for one frame on a resting bar — not an abort; two frames are."""

    from app.motor.calibration.runner import CalibrationRunner, Command, ProcedureEnvelope
    from app.motor.drive.protocol import DriveSample

    bench = _bench(PlantParams(), MachineProfile())
    frames = {"n": 0}

    class Spiky:
        def __init__(self, drive, spikes):
            self.drive, self.spikes = drive, spikes

        def __getattr__(self, name):
            return getattr(self.drive, name)

        def read(self) -> DriveSample:
            sample = self.drive.read()
            return replace(sample, speed_mm_s=91.0) if frames["n"] in self.spikes else sample

    def tick() -> float:
        frames["n"] += 1
        bench.advance(0.05)
        return bench.t

    def rest():
        for _ in range(20):
            yield Command(None)
        return {}

    for spikes, expected in (({5}, "done"), ({5, 6}, "done"), ({5, 6, 7}, "aborted")):
        frames["n"] = 0
        drives = {side: Spiky(bench.drives[side], spikes) for side in SIDES}
        runner = CalibrationRunner(drives, tick, ProcedureEnvelope())
        assert runner.run(rest()).status == expected
