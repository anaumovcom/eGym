"""All catalog calibrations on the twin: each session recovers the known physics and reports it."""

from __future__ import annotations

import math
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
from app.motor.units import SIDES, kgf_to_n, passport_n_per_raw
from app.services.hardware_runtime import hardware_runtime


def _params(**side: Any) -> PlantParams:
    params = PlantParams()
    for name in SIDES:
        params = params.with_side(name, replace(params.side(name), **side))
    return params


def _bench(params: PlantParams, profile: MachineProfile) -> TwinBench:
    return TwinBench(params, {side: profile.side(side) for side in SIDES}, initial_raw=100)


def _run(bench: TwinBench, code: str, profile: MachineProfile, max_s: float = 1600.0, operator: Any = None, **options: Any) -> CalibrationSession:
    session = CalibrationSession(code, bench.drives, profile, options=options)
    session.begin()
    end = bench.t + max_s
    while session.running and bench.t < end:
        bench.advance(0.05)
        session.keepalive()
        if operator is not None:
            operator(session)
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
    assert set(ORDER) == set(BY_CODE) and [code for code in ORDER if code in WIZARD_STAGES] == list(WIZARD_STAGES)
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


# ---------------------------------------------------------------- extended set (B2 … L2)
# a bench like the A6 one (2026-10-09) with the effects the new calibrations measure
# (dwell stiction, screw ripple, a tight spot, load friction)
FEATURES: dict[str, Any] = {
    "weight_n": 150.0, "coulomb_up_n": 40.0, "coulomb_down_n": 40.0, "viscous_n_per_mm_s": 0.3, "stop_adhesion_n": 20.0,
    "stiction_extra_n": 1.0, "dwell_stiction_n": 3.0, "dwell_tau_s": 6.0, "ripple_n": 3.0,
    "friction_load_up": 0.1, "friction_load_down": 0.05, "tight_spots": ((600.0, 15.0, 25.0),),
}


class _Operator:
    """A simulated person: types the tape reading, hangs/removes the weight, pushes the bar like a hand,
    holds the bar and does reps for G3 and rates the feel."""

    def __init__(self, bench: TwinBench, base: PlantParams, kg: float = 20.0) -> None:
        self.bench, self.base, self.kg = bench, base, kg
        self.force, self.until, self.text, self.x0 = 0.0, 0.0, "", 0.0
        self.mode, self.load, self.turns, self.direction = "push", 0.0, 0, 1
        bench.user = self._hand

    def _hand(self, t: float, bench: TwinBench) -> dict[str, float]:
        x, v = bench.true_state("left")
        if self.mode == "hold":
            return {side: self.load - 0.3 * v for side in SIDES}
        if self.mode == "reps":
            if (x > 330 and self.direction > 0) or (x < 200 and self.direction < 0):
                self.direction, self.turns = -self.direction, self.turns + 1
            if self.turns >= 4:
                self.mode = "lower"
            return {side: self.load + self.direction * 25.0 + 0.3 * (self.direction * 80 - v) for side in SIDES}
        if self.mode == "lower":
            if x < 12:
                self.mode = "push"
                return {}
            return {side: self.load - 15.0 + 0.3 * (-30 - v) for side in SIDES}
        if t >= self.until:
            return {}
        sign = 1.0 if self.force > 0 else -1.0
        # a person eases off once the bar moves (≈ 15 mm/s)
        return {side: max(-90.0, min(90.0, self.force + 3.0 * (sign * 15.0 - bench.plant.state[side].v_mm_s))) for side in SIDES}

    def _set(self, params: PlantParams) -> None:
        self.bench.params = self.bench.plant.params = params

    def __call__(self, session: CalibrationSession) -> None:
        prompt = session.prompt
        if prompt is None:
            if self.mode in ("reps", "lower"):
                self.mode = "push"  # the prompt is over: hands off
            return
        x = self.bench.plant.state["left"].x_mm
        if prompt.kind == "input" and prompt.label == "Оценка":
            session.reply(4)
        elif prompt.kind == "input":
            session.reply(round(x, 1))
        elif "Повесьте" in prompt.text:
            extra = replace(self.base.left, extra_mass_kg=self.kg / 2)
            self._set(self.base.with_side("left", extra).with_side("right", replace(self.base.right, extra_mass_kg=self.kg / 2)))
            session.reply(None)
        elif "Снимите" in prompt.text:
            self._set(self.base)
            session.reply(None)
        elif prompt.text.startswith("Нагрузка"):  # G3: take the bar
            kg = float(prompt.text.split()[1].replace(",", "."))
            self.mode, self.load = "hold", kgf_to_n(kg / 2)
            session.reply(None)
        elif prompt.kind == "action" and "повторений" in prompt.text:
            if self.mode == "hold":
                self.mode, self.turns, self.direction = "reps", 0, 1
        elif prompt.kind == "action" and self.until < self.bench.t:
            sign = -1.0 if ("вниз" in prompt.text or "опустите" in prompt.text.lower()) else 1.0
            if prompt.text != self.text:
                self.text, self.x0 = prompt.text, x
            if "10 см" not in prompt.text:
                self.force, self.until = sign * 50.0, self.bench.t + 0.6
            elif sign * (x - self.x0) < 90.0:
                self.force, self.until = sign * 50.0, self.bench.t + 0.3
        elif prompt.kind == "confirm":
            session.reply(None)


@pytest.fixture(scope="module")
def commissioned() -> tuple[PlantParams, MachineProfile]:
    """The commissioning chain the extended calibrations need: S3, M1, M2, M3, C3, C1, X2."""

    params = _params(**FEATURES)
    bench = _bench(params, MachineProfile())
    profile = _calibrated(bench)
    for code in ("M1", "M2", "M3", "C3", "C1", "X2"):
        session = _run(bench, code, profile)
        assert session.status == "done", (code, session.reason)
        profile = session.profile
    return params, profile


def _chain(params: PlantParams, profile: MachineProfile, codes: tuple[str, ...], **options: Any) -> tuple[MachineProfile, dict[str, CalibrationSession]]:
    bench = _bench(params, profile)
    operator = _Operator(bench, params)
    sessions = {}
    for code in codes:
        session = _run(bench, code, profile, operator=operator, **options)
        _done(session)
        sessions[code] = session
        profile = session.profile
        assert all(bench.plant.state[side].x_mm < 15 for side in SIDES), f"{code}: the bar is not back on the stops"
    return profile, sessions


def test_drive_response_b2_d1_b6(commissioned: tuple[PlantParams, MachineProfile]) -> None:
    params, profile = commissioned
    profile, _ = _chain(replace(params, deadband_raw=6), profile, ("B2", "D1", "B6"))
    assert 0.0 < profile.torque_lag_s.value < 0.1
    for side in SIDES:
        assert profile.side(side).deadband_raw.value == pytest.approx(6, abs=2)


def test_friction_map_s5_s6_s8(commissioned: tuple[PlantParams, MachineProfile]) -> None:
    params, profile = commissioned
    profile, _ = _chain(params, profile, ("S5", "S6", "S8"))
    for side in SIDES:
        item = profile.side(side)
        assert item.dwell_extra_n.value == pytest.approx(3.0 + 1.0, abs=2.5)  # dwell + Stribeck
        assert item.screw_ripple_n.value == pytest.approx(3.0, abs=1.0)
    spots = profile.tight_spots.value
    assert len(spots) == 1 and spots[0][0] == pytest.approx(600.0, abs=40.0)


def test_positioning_p1_p2_a1_a2_a3_r1_e1(commissioned: tuple[PlantParams, MachineProfile]) -> None:
    params, profile = commissioned
    profile, sessions = _chain(params, profile, ("P1", "P2", "A1", "A2", "A3", "R1", "E1"))
    assert profile.position_speed_up_mm_s.value >= 20 and profile.position_speed_down_mm_s.value >= 20
    assert profile.left.travel_table_up.provenance == "measured"
    assert profile.accel_mm_s2.value >= 60 and profile.decel_mm_s2.value >= 60
    assert 5 <= profile.landing_speed_mm_s.value <= 25
    assert 0.0 <= profile.reversal_stick_s.value < 0.5
    assert 0.0 <= profile.stop_overshoot_mm.value < 10.0


def test_holding_h1_h2_w1_w2_x3(commissioned: tuple[PlantParams, MachineProfile]) -> None:
    params, profile = commissioned
    profile, _ = _chain(params, profile, ("H1", "H2", "W1", "W2", "X3"))
    k_u = profile.hold_ultimate_k_n_per_mm.value
    assert 0.1 * k_u <= profile.hold_k_n_per_mm.value <= 0.5 * k_u
    assert 0.3 <= profile.weightless_gain_up.value <= 1.0 and 0.3 <= profile.weightless_gain_down.value <= 1.0
    assert 0.0 <= profile.sync_k_n_per_mm.value <= 0.2 * profile.side_coupling_n_per_mm.value
    # the trainer core uses the measured values
    from app.motor.profile import Tunables, calibrated_tunables

    tuned = calibrated_tunables(profile, Tunables())
    assert tuned.friction_gain_up == profile.weightless_gain_up.value and tuned.sync_k_n_per_mm == profile.sync_k_n_per_mm.value


def test_loaded_friction_l1_l2(commissioned: tuple[PlantParams, MachineProfile]) -> None:
    params, profile = commissioned
    profile, _ = _chain(params, profile, ("L1", "L2"), referenceKg=20.0)
    for side in SIDES:
        assert profile.side(side).friction_load_up.value == pytest.approx(0.1, abs=0.04)
        assert profile.side(side).friction_load_down.value == pytest.approx(0.05, abs=0.04)


def test_operator_reply_validation(client) -> None:
    assert client.post("/api/motor/calibration/reply", json={"value": 1.0}).status_code == 422  # nothing is running
    bench = _bench(PlantParams(), MachineProfile())
    profile = _calibrated(bench)
    session = CalibrationSession("B6", bench.drives, profile)
    session.begin()
    while session.running and session.prompt is None:
        bench.advance(0.05)
        session.keepalive()
        session.step(Frame(bench.t, {side: bench.drives[side].read() for side in SIDES}))
    prompt = session.to_payload()["prompt"]
    assert prompt["kind"] == "input" and prompt["unit"] == "мм"
    with pytest.raises(ValueError, match="Введите число"):
        session.reply(None)
    with pytest.raises(ValueError, match="допустимо"):
        session.reply(prompt["max"] + 1)
    session.cancel("тест")
    assert session.prompt is None


# ---------------------------------------------------------------- free-weight feel (V, F, S10, X4, L3, D5, G2, G3)
def test_motion_estimate_v1_v2_v3(feel_base: tuple[PlantParams, MachineProfile]) -> None:
    from app.motor.calibration.procedures.estimation import SMOOTHINGS

    params, profile = feel_base
    tau = 0.1  # PA_1C1 filter of the twin, applied once per 50-ms frame: the lag of a ramp is dt·e^(−dt/τ)/(1 − e^(−dt/τ))
    profile, _ = _chain(replace(params, speed_lag_s=tau), profile, ("V1", "V2", "V3"))
    share = 1 - math.exp(-0.05 / tau)
    assert profile.speed_lag_s.value == pytest.approx(0.05 * (1 - share) / share, abs=0.025)
    assert profile.speed_scale.value == pytest.approx(1.0, abs=0.03)
    assert profile.accel_smoothing.value in SMOOTHINGS
    delay = float(profile.loop_delay_s.value) + float(profile.torque_lag_s.value or 0.0)
    assert 0.0 <= profile.predict_horizon_s.value <= 1.5 * delay + 1e-6


def test_friction_track_and_speed_tables_s10_f3(feel_base: tuple[PlantParams, MachineProfile]) -> None:
    params, profile = feel_base
    profile, _ = _chain(params, profile, ("S10", "F3"))
    for side in SIDES:
        bump = max(profile.side(side).friction_map.value, key=lambda point: point[1])
        assert bump[0] == pytest.approx(600.0, abs=30.0) and bump[1] == pytest.approx(25.0, abs=10.0)
        up, down = profile.side(side).friction_table_up.value, profile.side(side).friction_table_down.value
        assert len(up) >= 2 and len(down) >= 2
        slope = (up[-1][1] - up[0][1]) / (up[-1][0] - up[0][0])
        assert slope == pytest.approx(0.3, abs=0.12)  # the twin's viscous friction


@pytest.fixture(scope="module")
def feel_base(commissioned: tuple[PlantParams, MachineProfile]) -> tuple[PlantParams, MachineProfile]:
    """What the feel calibrations stand on in the commissioning order: speed tables, ramps, landing, weightless gains."""

    params, profile = commissioned
    profile, _ = _chain(params, profile, ("P1", "P2", "A1", "A2", "A3", "W1"))
    return params, profile


@pytest.fixture(scope="module")
def feel_ready(feel_base: tuple[PlantParams, MachineProfile]) -> tuple[PlantParams, MachineProfile, dict[str, CalibrationSession]]:
    params, profile = feel_base
    profile, sessions = _chain(params, profile, ("D5", "F3", "F1", "F2", "F4"), referenceKg=20.0)
    return params, profile, sessions


def test_inertia_by_load_f1_f2_d5(feel_ready: tuple[PlantParams, MachineProfile, dict[str, CalibrationSession]]) -> None:
    _params_, profile, sessions = feel_ready
    for side in SIDES:  # D5: the swing measures the twin's 60 kg (friction cancels)
        assert profile.side(side).moving_mass_kg.value == pytest.approx(60.0, rel=0.2)
    ratio = profile.inertia_ratio_max.value
    assert 0.1 <= ratio <= 0.72
    table = profile.inertia_table.value
    assert len(table) == 4
    machine = float(profile.left.moving_mass_kg.value)
    for (load_n, share) in table:
        assert 0.0 <= share * max(machine - load_n / 9.80665, 0.0) <= ratio * machine + 1e-6  # within the F1 limit
    for item in sessions["F2"].stages[0].result["items"]:  # the compensation lowers the felt mass
        felt = [trial["mass_kg"] for trial in item["trials"] if trial["mass_kg"] is not None]
        assert len(felt) >= 2 and min(felt) < felt[0]


def test_feel_check_g2_and_core_uses_the_table(feel_ready: tuple[PlantParams, MachineProfile, dict[str, CalibrationSession]]) -> None:
    from app.motor.core import MotorCore
    from app.motor.force.load_models import LoadSetpoint

    params, profile, _sessions = feel_ready
    core = MotorCore(profile)
    core.set_load(LoadSetpoint(load_n=kgf_to_n(5.0)))
    assert core.inertia_share("left") == pytest.approx(dict(profile.inertia_table.value)[round(kgf_to_n(5.0), 1)], abs=1e-6)
    _done(_run(_bench(params, profile), "G2", profile, operator=None))


def test_turn_phase_breakaway_track_f4_f5_f6_f7(feel_ready: tuple[PlantParams, MachineProfile, dict[str, CalibrationSession]]) -> None:
    from app.motor.calibration.procedures.feel import F4_BLENDS, F5_HYSTERESES, F6_SOFTS
    from app.motor.profile import Tunables, calibrated_tunables

    params, profile, _sessions = feel_ready
    assert profile.feel_blend_mm_s.value in F4_BLENDS
    profile, sessions = _chain(params, profile, ("S6", "S8", "F5", "F6", "F7"))
    assert profile.feel_phase_hysteresis_mm_s.value in F5_HYSTERESES and 0.08 <= profile.feel_phase_blend_s.value <= 0.4
    assert profile.breakaway_soft_s.value in F6_SOFTS
    runs = sessions["F6"].stages[0].result["runs"]
    assert runs[-1]["peak_mm_s"] < runs[0]["peak_mm_s"]  # softening damps the jump after breakaway
    assert profile.track_comp_gain.value == 1.0  # the twin's ripple and tight spot are real: full compensation is best
    tuned = calibrated_tunables(profile, Tunables())
    assert tuned.friction_blend_mm_s == profile.feel_blend_mm_s.value and tuned.phase_blend_s == profile.feel_phase_blend_s.value


def test_deadband_dither_cushions_release_sync_f8_f9_f10_f11_x4(feel_ready: tuple[PlantParams, MachineProfile, dict[str, CalibrationSession]]) -> None:
    params, profile, _sessions = feel_ready
    params = replace(params, deadband_raw=8)
    profile, _ = _chain(params, profile, ("D1",))
    profile, sessions = _chain(params, profile, ("F8", "F9", "F10", "F11", "X4"))
    errors = sessions["F8"].stages[0].result["errors"]
    assert errors[str(profile.deadband_comp_gain.value)] == min(errors.values())  # D1 already shifts the threshold on the twin
    assert profile.dither_n.value > 0  # the twin's stiction and dwell narrow with dither
    assert profile.cushion_bottom_mm.value in (150.0, 100.0, 60.0) and profile.cushion_top_mm.value in (150.0, 100.0, 60.0)
    assert 10.0 <= profile.feel_release_force_n.value <= 60.0 and 0.2 <= profile.feel_release_timeout_s.value <= 1.0
    assert profile.sync_k_train_n_per_mm.value == 0.0  # symmetric twin: no skew to correct


def test_load_friction_and_hand_check_l3_g3(feel_ready: tuple[PlantParams, MachineProfile, dict[str, CalibrationSession]]) -> None:
    params, profile, _sessions = feel_ready
    profile, _ = _chain(params, profile, ("L1", "L2", "L3"), referenceKg=20.0)
    assert profile.friction_load_gain.value >= 0.5  # the twin's friction really grows with the load
    _profile, sessions = _chain(params, profile, ("F11", "G3"))
    items = sessions["G3"].stages[0].result["items"]
    assert [item["rating"] for item in items] == [4, 4] and all(item["frames"] > 20 for item in items)


def test_core_feel_terms() -> None:
    """Friction model extensions, cushion braking and release detection in the trainer core."""

    from app.motor.core import MotorCore
    from app.motor.estimation.friction import FrictionModel
    from app.motor.force.load_models import LoadSetpoint
    from app.motor.supervisor.modes import Mode
    from app.motor.twin.loop import run_core

    model = FrictionModel(40.0, 40.0, 0.3, table_up=((40.0, 52.0), (120.0, 76.0)), track=((590.0, 20.0), (610.0, 14.0)), track_gain=1.0, load_up=0.1, load_gain=1.0, ripple_n=3.0)
    assert model.force(80.0) == pytest.approx(64.0)  # the F3 table
    assert model.force(200.0) == pytest.approx(100.0)  # beyond: the slope of the last points
    assert model.force(80.0, x_mm=600.0) == pytest.approx(64.0 + 17.0)  # the S10 map
    assert model.force(80.0, axial_excess_n=100.0) == pytest.approx(64.0 + 10.0)  # L1 growth with the screw load
    assert model.ripple(8.0) == pytest.approx(3.0)  # a quarter of the 32-mm lead
    assert FrictionModel(40.0, 40.0, 0.3).force(80.0) == pytest.approx(40.0 + 24.0)  # unchanged without calibrations

    cushioned = replace(MachineProfile(), cushion_bottom_mm=Measured(150.0, None, "measured"), landing_speed_mm_s=Measured(15.0, None, "measured"))

    def drop(profile: MachineProfile) -> float:
        """A 16-kg bar let go at 400 mm in training: the fastest speed below 25 mm."""

        bench = TwinBench(replace(PlantParams(), travel_mm=2000.0), x0_mm=400.0, initial_raw=100)
        core = MotorCore(profile)
        run_core(core, bench, 0.2)
        core.command("ready")
        core.command("hold")
        run_core(core, bench, 0.5)
        core.command("train")
        core.set_load(LoadSetpoint(load_n=kgf_to_n(8.0)))
        core.release_enabled = False
        touch = [0.0]

        def low(_t: float, _out: object) -> None:
            x, v = bench.true_state("left")
            if x < 25.0:
                touch.append(-v)

        run_core(core, bench, 6.0, on_tick=low)
        return max(touch)

    assert drop(MachineProfile()) > 60.0
    assert drop(cushioned) < 45.0  # the user dropped the bar: the cushion lands it softly

    bench = TwinBench(PlantParams(), x0_mm=400.0, initial_raw=100)
    core = MotorCore(replace(MachineProfile(), feel_release_force_n=Measured(30.0, None, "measured"), feel_release_timeout_s=Measured(0.3, None, "measured")))
    run_core(core, bench, 0.2)
    core.command("ready")
    core.command("hold")
    core.command("train")
    core.set_load(LoadSetpoint(load_n=kgf_to_n(8.0)))
    run_core(core, bench, 2.0)  # nobody holds the 16-kg bar
    assert core.supervisor.mode == Mode.HOLD
