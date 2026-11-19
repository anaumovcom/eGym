"""Guided calibration windows and session-scoped commands, using only twin/fake hardware."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.models.motor import CalibrationRun
from app.motor import store
from app.motor.calibration.graph import motion_check_settings
from app.motor.calibration.middle_zone import middle_window
from app.motor.calibration.runner import Frame, Prompt
from app.motor.calibration.session import CalibrationSession
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.twin.bench import TwinBench
from app.motor.units import SIDES
from app.services import hardware_runtime as runtime_module
from app.services.hardware_runtime import HardwareRuntime, hardware_runtime
from app.tests.motor.fakes import FakeModbusService


@pytest.fixture()
def twin_runtime(monkeypatch: pytest.MonkeyPatch) -> HardwareRuntime:
    monkeypatch.setenv("HARDWARE_ADAPTER", "twin")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    runtime.set_service_mode(True)
    runtime.set_servo(True)
    for _ in range(3):
        runtime.tick()
    return runtime


@pytest.fixture()
def modbus_runtime(monkeypatch: pytest.MonkeyPatch) -> tuple[HardwareRuntime, FakeModbusService]:
    service = FakeModbusService()
    monkeypatch.setattr(runtime_module, "modbus_service", service)
    monkeypatch.setenv("HARDWARE_ADAPTER", "modbus")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    runtime.set_service_mode(True)
    runtime.set_servo(True)
    return runtime, service


@pytest.fixture()
def guided_client(isolated_coach_lifespan, client):
    # No real lifespan: no hardware I/O and no bootstrap of the working DB.
    hardware_runtime.abort_calibration()
    hardware_runtime.reset()
    hardware_runtime.set_service_mode(True)
    hardware_runtime.set_servo(True)
    yield client
    hardware_runtime.abort_calibration()
    hardware_runtime.reset()


def _run_bench(bench: TwinBench, code: str, profile: MachineProfile, *, safety: SafetyEnvelope | None = None) -> CalibrationSession:
    """Run a calibration to completion on a standalone TwinBench (no hardware, no runtime thread)."""

    session = CalibrationSession(code, bench.drives, profile, safety=safety)
    session.begin()
    end = bench.t + 2000.0
    while session.running and bench.t < end:
        bench.advance(0.05)
        session.keepalive()
        session.step(Frame(bench.t, {side: bench.drives[side].read() for side in SIDES}))
    assert session.status == "done", f"{code}: {session.reason}"
    return session


def test_friction_archive_finds_s10_inside_series_and_pages_only_matching_sources(guided_client, db_session) -> None:
    stamp = datetime.now(UTC)
    track = {"heightsMm": [90, 110], "sides": {"left": [12, 0], "right": [None, 5]}}
    for i, (code, source, has_map) in enumerate((("S10", None, True), ("S10", "twin", True),
                                                  ("AUTO_GUIDES", "modbus", True), ("S10", "modbus-torque", True),
                                                  ("S10", "modbus", False), ("AUTO_GUIDES", "canopen", True))):
        db_session.add(CalibrationRun(id=f"screw-{i}", procedure=code, status="done", started_at=stamp + timedelta(minutes=i),
                                      metrics={"adapter": source, "stageLogs": {"S10": {"t": [1]}}},
                                      estimate={"S10": {"track": track}} if has_map else {"S8": {"report": []}}))
    db_session.commit()
    path = "/api/motor/calibration/friction-tracks"
    assert [r["id"] for r in guided_client.get(path).json()["items"]] == ["screw-1"]
    first = guided_client.get(path, params={"source": "modbus", "limit": 1}).json()
    assert first["hasMore"] and first["source"] == "modbus" and first["items"][0]["id"] == "screw-3"
    second = guided_client.get(path, params={"source": "modbus", "limit": 1, "offset": 1}).json()
    assert not second["hasMore"] and second["items"][0]["code"] == "AUTO_GUIDES" and second["items"][0]["track"] == track
    assert "stageLogs" not in second["items"][0]
    assert [r["id"] for r in guided_client.get(path, params={"source": "unknown"}).json()["items"]] == ["screw-0"]
    assert [r["id"] for r in guided_client.get(path, params={"source": "canopen"}).json()["items"]] == ["screw-5"]


def test_original_s10_profile_points_remain_visible_with_gaps_and_unknown_source(guided_client, db_session) -> None:
    run_id = "S10-original"
    stamp = datetime.now(UTC)
    bundle = store.load_active(db_session)
    machine = bundle.machine
    for side, source in (("left", run_id), ("right", "previous-run")):
        m = Measured([(90.0, 2.0), (150.0, 15.0)], None, "measured", source, stamp.isoformat())
        machine = machine.with_side(side, replace(machine.side(side), friction_map=m))
    version = store.save_version(db_session, replace(bundle, machine=machine), source_run_id=run_id)
    db_session.add(CalibrationRun(id=run_id, procedure="S10", status="saved", started_at=stamp, estimate={"S10": {"bins": 2}},
                                  metrics={"savedVersion": version}))
    db_session.commit()
    path = "/api/motor/calibration/friction-tracks"
    assert guided_client.get(path, params={"source": "modbus"}).json()["items"] == []
    track = guided_client.get(path, params={"source": "unknown"}).json()["items"][0]["track"]
    assert track["heightBasis"] == "bar" and track["heightsMm"] == [90, 110, 130, 150]
    assert track["sides"] == {"left": [2, None, None, 15], "right": [None] * 4}
    assert "directionalN" not in track


def test_measurement_archive_finds_partial_series_and_keeps_stage_source_and_limits(guided_client, db_session) -> None:
    stamp = datetime.now(UTC)
    stage = {"code": "D2", "status": "aborted", "reason": "Остановлено оператором", "workingZone": {"lowMm": 500, "highMm": 900}}
    point = {"table_up": [[72, 41]], "table_down": []}
    for i, (procedure, adapter, data) in enumerate((
        ("AUTO_MOTION", "modbus-torque", {"D2": {"sides": {"left": {**point, "ci95": 999}}, "partial": True}}),
        ("D2", "modbus", {"D2": {"sides": {"right": point}}}), ("D2", "modbus", {"D2": {"report": []}}),
        ("D2", "twin", {"D2": {"sides": {"left": point}}}),
    )):
        db_session.add(CalibrationRun(id=f"plot-{i}", procedure=procedure, status="aborted", started_at=stamp + timedelta(minutes=i),
                                      metrics={"adapter": adapter, "stages": [stage]}, estimate=data))
    # Older G4 stages saved thresholds in report rows. The middle-zone summary follows the skew row.
    report = [{"comparison": {"limit": 5}}, {}, {"comparison": {"limit": 7}}, {"comparison": {"limit": 8}},
              {"label": "Максимальный перекос"}, {"label": "Рабочая зона (середина хода)"}]
    db_session.add(CalibrationRun(id="old-G4", procedure="G4", status="failed", started_at=stamp,
                                  metrics={"adapter": "twin", "stages": [{"code": "G4", "status": "failed"}]},
                                  estimate={"G4": {"passes": [], "heightsMm": [700], "report": report}}))
    db_session.commit()
    path = "/api/motor/calibration/measurement-plots"
    assert guided_client.get(path, params={"stage": "D2"}).json()["items"][0]["id"] == "plot-3"
    page = guided_client.get(path, params={"stage": "D2", "source": "modbus", "limit": 1}).json()
    assert page["hasMore"] and [r["id"] for r in page["items"]] == ["plot-1"]
    assert page["priority"] == "important" and page["priorityReason"]
    page = guided_client.get(path, params={"stage": "D2", "source": "modbus", "limit": 1, "offset": 1}).json()
    row = page["items"][0]
    assert not page["hasMore"] and row["code"] == "AUTO_MOTION" and row["stageStatus"] == "aborted"
    assert row["workingZone"] == stage["workingZone"] and row["reason"] == stage["reason"]
    assert row["result"] == {"sides": {"left": point}, "partial": True}
    assert guided_client.get("/api/motor/calibration/runs/plot-0").json()["stages"][0]["result"] == row["result"]
    earlier = guided_client.get(path, params={"stage": "G4"}).json()["items"][0]["result"]
    assert earlier["spreadLimitsN"] == {"up": {"left": [5], "right": [None]}, "down": {"left": [7], "right": [8]}}
    assert guided_client.get(path, params={"stage": "B0"}).status_code == 422


def test_motion_checks_follow_source_settings_and_last_protection_trip(guided_client, db_session) -> None:
    bundle = store.load_active(db_session)
    timestamp = datetime.now(UTC)
    settings = motion_check_settings("M6", bundle.machine, bundle.envelope, bundle.tunables)

    def record(index, status, **metrics):
        stamp = timestamp + timedelta(seconds=index)
        db_session.add(CalibrationRun(id=f"M6-motion-{index}", procedure="M6", status=status,
                                      started_at=stamp, finished_at=stamp, metrics={"adapter": "twin", **metrics}))
        db_session.commit()

    def catalog_status():
        return next(item["status"] for item in guided_client.get("/api/motor/calibrations").json() if item["code"] == "M6")

    record(0, "done")
    assert catalog_status() == "stale"
    record(1, "done", checkSettings=settings)
    record(2, "failed", adapter="modbus")
    assert catalog_status() == "actual"
    response = guided_client.post("/api/motor/parameters/preview", json={"baseVersion": bundle.machine.version,
                                  "changes": [{"scope": "envelope", "key": "sync_warning_mm", "value": 4}]})
    assert response.status_code == 200, response.text
    assert any(item["code"] == "M6" and item["before"] == "actual" and item["after"] == "stale"
               for item in response.json()["statusChanges"])
    assert catalog_status() == "actual"
    record(3, "aborted", faultCode="skew")
    record(4, "aborted")  # operator cancellation leaves the last decisive result visible
    assert catalog_status() == "failed"
    before = hardware_runtime.profile.version
    result = guided_client.get("/api/motor/calibration/fault-rehearsal")
    assert result.status_code == 200 and len(result.json()["cases"]) == 7
    assert all(case["matches"] for case in result.json()["cases"])
    assert hardware_runtime.profile.version == before and catalog_status() == "failed"


def _settle(bench: TwinBench) -> None:
    """Lower the bar onto the stops and restore support, as the runtime would between calibrations."""

    for drive in bench.drives.values():
        drive.write_raw(0)
    for _ in range(200):
        bench.advance(0.05)
    assert all(bench.plant.state[side].x_mm < 1 for side in SIDES)
    for drive in bench.drives.values():
        drive.support()


def test_review_reports_source_and_calibration_impact_without_applying(guided_client, db_session) -> None:
    base = store.load_active(db_session)
    scale = Measured(1.25, 0.02, "measured", "S9-source", "2026-01-02T12:00:00Z")
    machine = replace(base.machine, weightless_gain_up=replace(scale, value=0.65, run_id="W1-source"))
    for side in SIDES:
        machine = machine.with_side(side, replace(machine.side(side), n_per_raw=scale))
    version = store.save_version(db_session, replace(base, machine=machine))
    previous_check = datetime(2026, 1, 3, 12, tzinfo=UTC)
    db_session.add(CalibrationRun(id="G1-scale-check", procedure="G1", status="done", started_at=previous_check, finished_at=previous_check))
    db_session.commit()
    runtime_version = hardware_runtime.profile.version
    payload = {"baseVersion": version, "changes": [
        {"scope": "side", "side": "right", "key": "n_per_raw", "value": 1.35},
        {"scope": "tunables", "key": "friction_gain_up", "value": 0.5},
    ]}
    response = guided_client.post("/api/motor/parameters/preview", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    right, gain = result["changes"]
    assert right["side"] == "right" and right["before"]["runId"] == "S9-source"
    assert right["after"]["provenance"] == "manual" and right["after"]["value"] == 1.35
    assert gain["effective"]["value"] == 0.65 and gain["effective"]["procedure"] == "W1" and gain["effective"]["key"] == "weightless_gain_up"
    assert any(c["code"] == "S9" and c["before"] == "actual" and c["after"] == "missing" for c in result["statusChanges"])
    assert any(c["code"] == "G1" and c["before"] == "actual" and c["after"] == "stale" for c in result["statusChanges"])
    assert [r["version"] for r in guided_client.get("/api/motor/profile/versions").json()] == [version]
    assert store.load_active(db_session).machine.right.n_per_raw.value == 1.25
    assert hardware_runtime.profile.version == runtime_version
    invalid = {"baseVersion": version, "changes": [{"scope": "envelope", "key": "soft_min_mm", "value": 500},
                                                  {"scope": "envelope", "key": "soft_max_mm", "value": 400}]}
    for path, send in (("/api/motor/parameters/preview", guided_client.post), ("/api/motor/parameters", guided_client.put)):
        error = send(path, json=invalid)
        assert error.status_code == 422 and "предел" in error.json()["detail"]
    accepted = guided_client.put("/api/motor/parameters", json=payload)
    assert accepted.status_code == 200 and accepted.json()["version"] == version + 1
    catalog = {row["code"]: row for row in guided_client.get("/api/motor/calibrations").json()}
    assert catalog["G1"]["status"] == "stale" and "вручную" in catalog["G1"]["staleReason"]
    for path, send in (("/api/motor/parameters/preview", guided_client.post), ("/api/motor/parameters", guided_client.put)):
        assert send(path, json=payload).status_code == 409
    assert len(guided_client.get("/api/motor/profile/versions").json()) == 2


def test_two_writers_from_factory_review_create_one_version(guided_client) -> None:
    def write(value: float) -> int:
        return guided_client.put("/api/motor/parameters", json={"baseVersion": 0, "changes": [
            {"scope": "tunables", "key": "hold_k_fraction", "value": value},
        ]}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, (0.2, 0.3))) == [200, 409]
    assert len(guided_client.get("/api/motor/profile/versions").json()) == 1


def _twin_measured_profile(bench: TwinBench) -> MachineProfile:
    """Real measured profile from the twin: S3 → C3 → B7 → B8, enough for a D2 middle-zone run."""

    s3 = _run_bench(bench, "S3", MachineProfile())
    _settle(bench)
    c3 = _run_bench(bench, "C3", s3.profile)
    _settle(bench)
    b7 = _run_bench(bench, "B7", c3.profile)
    _settle(bench)
    b8 = _run_bench(bench, "B8", b7.profile)
    _settle(bench)
    return b8.profile


def _apply_twin_profile(runtime: HardwareRuntime, profile: MachineProfile) -> SafetyEnvelope:
    """Apply a twin-measured profile with an envelope safely inside the measured travel (middle_window needs the margin)."""

    travel = float(profile.travel_mm.value)
    envelope = SafetyEnvelope(soft_min_mm=20.0, soft_max_mm=travel - 100.0)
    runtime.apply_profile(profile, envelope)
    return envelope


def _measured_profile(zero: tuple[int, int] = (101, 202), travel: float = 1400.0) -> tuple[MachineProfile, SafetyEnvelope]:
    """Deterministic profile with measured S3, C3, B7 and B8 for the Modbus zero check."""

    profile = replace(MachineProfile(), travel_mm=Measured(travel, None, "measured"))
    for side, value in zip(SIDES, zero, strict=True):
        profile = profile.with_side(side, replace(
            profile.side(side),
            zero_counts=Measured(value, None, "measured"),
            support_raw=Measured(50, None, "measured"),
            gravity_map=Measured([(0.0, 68.6)], None, "measured"),
            coulomb_up_n=Measured(49.0, None, "measured"),
            coulomb_down_n=Measured(49.0, None, "measured"),
        ))
    return profile, SafetyEnvelope(soft_min_mm=20.0, soft_max_mm=1380.0)


def _done_with_changes(runtime: HardwareRuntime) -> CalibrationSession:
    run = CalibrationSession("B5", runtime.drives, runtime.profile)
    run.status = "done"
    run.finished_at = datetime.now(UTC)
    run.stages[0].status = "done"
    left = run.profile.left
    run.profile = run.profile.with_side("left", replace(
        left,
        direction_sign=Measured(value=-left.sign, provenance="measured", run_id=run.id),
    ))
    return run


def test_d2_middle_api_exposes_real_window_and_start_forbids_extra(guided_client) -> None:
    bench = hardware_runtime.bench
    assert isinstance(bench, TwinBench)
    profile = _twin_measured_profile(bench)
    envelope = _apply_twin_profile(hardware_runtime, profile)
    for _ in range(3):
        hardware_runtime.tick()

    low, high = middle_window("D2", profile, envelope)
    response = guided_client.get("/api/motor/calibration/session", params={"code": "D2", "workingZone": "middle"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workingZone"] == {"lowMm": low, "highMm": high}
    middle = next(item for item in payload["preconditions"] if item["id"] == "middleZone")
    assert middle["ok"] is True and middle["detail"] is None

    started = guided_client.post("/api/motor/calibration/start", json={"code": "D2", "workingZone": "middle"})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["session"]["id"] == hardware_runtime.calibration.id
    assert body["workingZone"] == payload["workingZone"]
    # the session recomputes middle_window itself: boundaries are not duplicated into options
    assert hardware_runtime.calibration.options == {"workingZone": "middle"}

    assert guided_client.post("/api/motor/calibration/start", json={"code": "D2", "unexpected": True}).status_code == 422
    assert guided_client.post("/api/motor/calibration/start", json={"code": "D2", "workingZone": "full"}).status_code == 422
    assert guided_client.get("/api/motor/calibration/session", params={"workingZone": "full"}).status_code == 422


def test_d2_middle_full_run_and_accept_integration(guided_client) -> None:
    bench = hardware_runtime.bench
    assert isinstance(bench, TwinBench)
    _apply_twin_profile(hardware_runtime, _twin_measured_profile(bench))
    for _ in range(3):
        hardware_runtime.tick()

    started = guided_client.post("/api/motor/calibration/start", json={"code": "D2", "workingZone": "middle"})
    assert started.status_code == 200, started.text
    session = hardware_runtime.calibration
    assert session is not None
    end = bench.t + 2000.0
    while session.running and bench.t < end:
        hardware_runtime.calibration_keepalive()
        hardware_runtime.tick()
    assert session.status == "done", session.reason
    for side in SIDES:
        assert session.profile.side(side).viscous_n_per_mm_s.value == pytest.approx(0.05, abs=0.05)

    accepted = guided_client.post("/api/motor/calibration/accept", json={"sessionId": session.id})
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["version"] == 1
    assert body["session"]["savedVersion"] == 1
    assert hardware_runtime.profile.version == 1
    saved = guided_client.get("/api/motor/profile").json()
    assert saved["machine"]["version"] == 1


def test_b0_middle_zone_is_really_blocked(guided_client) -> None:
    bench = hardware_runtime.bench
    assert isinstance(bench, TwinBench)
    _apply_twin_profile(hardware_runtime, _twin_measured_profile(bench))
    for _ in range(3):
        hardware_runtime.tick()

    payload = guided_client.get("/api/motor/calibration/session", params={"code": "B0", "workingZone": "middle"}).json()
    middle = next(item for item in payload["preconditions"] if item["id"] == "middleZone")
    assert middle["ok"] is False
    assert "собственный участок" in (middle["detail"] or "")
    assert payload["workingZone"] is None

    started = guided_client.post("/api/motor/calibration/start", json={"code": "B0", "workingZone": "middle"})
    assert started.status_code == 409, started.text
    assert hardware_runtime.calibration is None


def test_short_travel_and_confirmed_limit_are_saved_together(guided_client) -> None:
    run = CalibrationSession("B8", hardware_runtime.drives, hardware_runtime.profile)
    stage = run.stages[0]
    run._fit_b8(stage, {"top": {"left": 1270.8, "right": 1271.2}})
    stage.status, stage.progress = "done", 1.0
    run._finish("done", None)
    hardware_runtime.calibration = run
    assert stage.result["suggestedSoftMaxMm"] == 1250
    response = guided_client.post("/api/motor/calibration/accept", json={"sessionId": run.id, "fitTravelLimit": True})
    assert response.status_code == 200, response.text
    assert hardware_runtime.profile.travel_mm.value == 1270.8
    assert hardware_runtime.envelope.soft_max_mm == 1250
    saved = guided_client.get(f"/api/motor/calibration/runs/{run.id}").json()["stages"][0]["result"]
    assert "1250 мм" in saved["report"][-1]["value"]
    assert guided_client.post("/api/motor/calibration/accept", json={"sessionId": run.id, "fitTravelLimit": True}).status_code == 409


def test_limit_adjustment_only_applies_to_a_matching_travel_measurement(guided_client) -> None:
    run = _done_with_changes(hardware_runtime)
    hardware_runtime.calibration = run
    initial = hardware_runtime.envelope
    response = guided_client.post("/api/motor/calibration/accept", json={"sessionId": run.id, "fitTravelLimit": True})
    assert response.status_code == 409 and run.saved_version is None
    assert hardware_runtime.envelope == initial


def test_hand_set_requires_the_automatic_load_check(guided_client) -> None:
    response = guided_client.get("/api/motor/calibration/session", params={"code": "G3"})
    check = next(item for item in response.json()["preconditions"] if item["id"] == "feelCheck")
    assert not check["ok"] and "G2" in check["detail"]
    response = guided_client.post("/api/motor/calibration/start", json={"code": "G3"})
    assert response.status_code == 409 and "G2" in response.text
    assert hardware_runtime.calibration is None


def test_weight_series_verification_follows_the_outcome_of_its_own_stage(guided_client, db_session) -> None:
    now = datetime.now(UTC)
    for i, (status, measure, check, expected) in enumerate((
        ("saved", "done", "done", "actual"), ("failed", "failed", "pending", "actual"), ("failed", "done", "failed", "failed"),
    )):
        stamp = now + timedelta(seconds=i)
        db_session.add(CalibrationRun(id=f"weight-{i}", procedure="AUTO_WEIGHT", status=status, started_at=stamp, finished_at=stamp,
                                      metrics={"stages": [{"code": "S9", "status": measure}, {"code": "G1", "status": check}]}))
        db_session.commit()
        catalog = guided_client.get("/api/motor/calibrations").json()
        assert next(item for item in catalog if item["code"] == "G1")["status"] == expected


def test_archived_record_retains_feedback_and_report_after_closing(guided_client) -> None:
    for _ in range(3):
        hardware_runtime.tick()
    started = guided_client.post("/api/motor/calibration/start", json={"code": "B0"}).json()["session"]
    for _ in range(4):
        hardware_runtime.tick()
    run = hardware_runtime.calibration
    assert run is not None and run.status == "done"
    log = run.log_payload()
    assert len(log["t"]) >= 2 and len(log["cycleMs"]) == len(log["t"])
    assert any(abs(f) > 0 for f in log["fL"])  # real feedback while the command was support
    assert guided_client.post("/api/motor/calibration/discard", json={"sessionId": started["id"]}).status_code == 200
    record = guided_client.get(f"/api/motor/calibration/runs/{started['id']}").json()
    assert record["log"] == log and record["stages"][0]["result"]["report"] and record["adapter"] == "twin"
    assert guided_client.get("/api/motor/calibration/runs?code=G4").json() == []
    assert guided_client.get("/api/motor/calibration/runs/missing").status_code == 404


def test_speed_study_is_read_only_with_an_uncommissioned_profile(guided_client) -> None:
    before = list(hardware_runtime.bench.drives["left"].writes)
    data = guided_client.get("/api/motor/calibration/speed-study?targetMmS=1500").json()
    assert data["targetRpm"] == 2812.5
    assert data["cycleMs"] is None and data["m5Source"] is None and data["adapter"] == "twin"
    replay = data["replay"]
    assert replay["cycleSource"] == "default" and replay["strokeMm"] == 400
    assert max(p[1] for p in replay["points"]) > 1450 and min(p[1] for p in replay["points"]) < -1450
    assert 0 < replay["rmsMmS"] < 150 and replay["turnDelayMs"] is not None
    for direction in data["directions"].values():
        assert direction["insideLimits"] is False and direction["brakingMm"] is None
        assert direction["availableMm"] is None
    assert guided_client.get("/api/motor/calibration/speed-study?targetMmS=1501").status_code == 422
    assert before == hardware_runtime.bench.drives["left"].writes and hardware_runtime.calibration is None


def test_speed_study_uses_same_run_braking_and_direction_specific_travel() -> None:
    from app.motor.calibration.speed_study import speed_study

    profile, safety = _measured_profile()
    profile = replace(profile, loop_period_s=Measured(0.05, None, "measured", "B1-1"), fast_brake_lag_s=Measured(0.1, None, "measured", "M5-1"),
                      fast_brake_up_mm_s2=Measured(1000, None, "measured", "M5-1"),
                      fast_brake_down_mm_s2=Measured(500, None, "measured", "M5-1"))
    rows = [{"direction": 1, "brake_v_mm_s": v, "mode": "brake", "ok": True} for v in (151, 348)]
    for v in (250, 1500):
        data = speed_study(profile, safety, v, rows)["directions"]
        assert data["up"]["brakingMm"] == pytest.approx(v * 0.1 + v**2 / 2000)
        assert data["down"]["brakingMm"] == pytest.approx(v * 0.1 + v**2 / 1000)
        assert data["up"]["availableMm"] == safety.soft_max_mm - 700
        assert data["down"]["availableMm"] == 700 - safety.soft_min_mm
        assert data["up"]["insideMeasuredRange"] is (v == 250)
        assert data["down"]["measuredMaxMmS"] is None
    manual = replace(profile, fast_brake_up_mm_s2=Measured(1500, None, "manual"))
    assert speed_study(manual, safety, 500, rows)["directions"]["up"]["brakingMm"] is None
    assert speed_study(profile, safety, 1500, rows)["travelPerCycleMm"] == 75
    replay = speed_study(profile, safety, 1500, rows)["replay"]
    assert replay["cycleSource"] == "measured" and replay["cycleMs"] == 50
    other = speed_study(profile, safety, 250, rows, braking_matches_source=False)["directions"]["up"]
    assert other["brakingMm"] is None and other["measuredMaxMmS"] is None


def test_saved_wizard_covers_configuration_until_a_newer_failed_check(guided_client, db_session) -> None:
    now = datetime.now(UTC)
    for i, (code, status, expected) in enumerate((("WIZARD", "saved", "actual"), ("B0", "failed", "failed"))):
        stamp = now + timedelta(seconds=i)
        db_session.add(CalibrationRun(id=f"test-{code}", procedure=code, status=status, started_at=stamp, finished_at=stamp))
        db_session.commit()
        catalog = guided_client.get("/api/motor/calibrations").json()
        assert next(spec for spec in catalog if spec["code"] == "B0")["status"] == expected


def test_modbus_d2_middle_refuses_unknown_or_rejected_zero(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    profile, envelope = _measured_profile(zero=(101, 202))
    runtime.apply_profile(profile, envelope)

    service.left_zero_pulses, service.right_zero_pulses = None, None
    with pytest.raises(PermissionError, match="фактический ноль неизвестен"):
        runtime.start_calibration("D2", {"workingZone": "middle"})
    payload = runtime.calibration_payload("D2", "middle")
    assert payload["workingZone"] is None
    middle = next(item for item in payload["preconditions"] if item["id"] == "middleZone")
    assert middle["ok"] is False and "фактический ноль неизвестен" in (middle["detail"] or "")
    assert runtime.calibration is None

    service.left_zero_pulses, service.right_zero_pulses = 999, 202
    with pytest.raises(PermissionError, match="ноль инициализации не совпадает"):
        runtime.start_calibration("D2", {"workingZone": "middle"})
    payload = runtime.calibration_payload("D2", "middle")
    middle = next(item for item in payload["preconditions"] if item["id"] == "middleZone")
    assert middle["ok"] is False and "ноль инициализации не совпадает" in (middle["detail"] or "")
    assert runtime.calibration is None


def test_modbus_d2_middle_requires_accepted_zero_and_uses_real_window(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    profile, envelope = _measured_profile(zero=(101, 202))
    runtime.apply_profile(profile, envelope)
    service.left_zero_pulses, service.right_zero_pulses = 101, 202

    started = runtime.start_calibration("D2", {"workingZone": "middle"})
    assert started.options == {"workingZone": "middle"}
    assert started._middle_zone == middle_window("D2", profile, envelope)


def test_static_pull_measurement_checks_encoder_zero_on_both_drives(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    profile, envelope = _measured_profile(zero=(101, 202))
    runtime.apply_profile(profile, envelope)
    service.left_zero_pulses, service.right_zero_pulses = 101, 999
    zero = next(p for p in runtime.calibration_preconditions("N1") if p["id"] == "zero")
    assert zero["ok"] is False and "правый" in zero["detail"]
    with pytest.raises(PermissionError, match="B7"):
        runtime.start_calibration("N1")
    service.right_zero_pulses = 202
    assert next(p for p in runtime.calibration_preconditions("N1") if p["id"] == "zero")["ok"]


def test_done_with_unsaved_changes_cannot_be_replaced(twin_runtime: HardwareRuntime) -> None:
    previous = _done_with_changes(twin_runtime)
    twin_runtime.calibration = previous

    with pytest.raises(PermissionError, match="сохраните или отклоните"):
        twin_runtime.start_calibration("B0")
    assert twin_runtime.calibration is previous
    assert previous.saved_version is None


def test_scoped_heartbeat_mismatch_is_lock_free_and_does_not_touch_next_run(twin_runtime: HardwareRuntime) -> None:
    old = twin_runtime.start_calibration("B5")
    twin_runtime.abort_calibration()
    twin_runtime.discard_calibration()
    current = twin_runtime.start_calibration("B5")
    before = current.keepalive_at
    result: list[bool] = []
    done = threading.Event()

    def heartbeat() -> None:
        result.append(twin_runtime.calibration_keepalive(session_id=old.id))
        done.set()

    with twin_runtime._lock:
        worker = threading.Thread(target=heartbeat)
        worker.start()
        assert done.wait(1.0), "heartbeat must not wait for the runtime lock"
    worker.join()
    assert result == [False]
    assert current.keepalive_at == before
    assert current.running


def test_scoped_abort_mismatch_is_noop(twin_runtime: HardwareRuntime) -> None:
    old = twin_runtime.start_calibration("B5")
    twin_runtime.abort_calibration()
    twin_runtime.discard_calibration()
    current = twin_runtime.start_calibration("B5")
    events = list(twin_runtime.events)

    assert twin_runtime.abort_calibration(session_id=old.id) is False
    assert twin_runtime.calibration is current
    assert current.running and current.reason is None
    assert list(twin_runtime.events) == events


def test_reply_checks_session_and_prompt_under_lock(twin_runtime: HardwareRuntime) -> None:
    current = CalibrationSession("B5", twin_runtime.drives, twin_runtime.profile)
    current.operator.prompt = Prompt("Введите массу", kind="input", min=2, max=60)
    twin_runtime.calibration = current

    with pytest.raises(PermissionError, match="другой сессии"):
        twin_runtime.calibration_reply(20, "B5-stale", current.operator.prompt.text)
    with pytest.raises(ValueError, match="другому вопросу"):
        twin_runtime.calibration_reply(20, current.id, "Устаревший вопрос")
    assert current.operator.reply is None

    twin_runtime.calibration_reply(20, current.id, "Введите массу")
    assert current.operator.reply == (20.0,)


def test_stale_accept_and_discard_cannot_affect_next_run(guided_client) -> None:
    old = _done_with_changes(hardware_runtime)
    current = _done_with_changes(hardware_runtime)
    hardware_runtime.calibration = current

    accepted = guided_client.post("/api/motor/calibration/accept", json={"sessionId": old.id})
    discarded = guided_client.post("/api/motor/calibration/discard", json={"sessionId": old.id})
    assert accepted.status_code == 409 and discarded.status_code == 409
    assert hardware_runtime.calibration is current
    assert current.saved_version is None

    accepted = guided_client.post("/api/motor/calibration/accept", json={"sessionId": current.id})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["session"]["id"] == current.id
    assert current.saved_version == accepted.json()["version"]
    assert guided_client.post("/api/motor/calibration/discard", json={"sessionId": current.id}).json() == {"ok": True}
    assert hardware_runtime.calibration is None
