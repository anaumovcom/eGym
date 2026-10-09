"""Calibration sessions inside the runtime tick (twin) and the calibration/parameters API."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.hardware_runtime import HardwareRuntime, hardware_runtime


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


def _run(runtime: HardwareRuntime, max_ticks: int = 20000) -> None:
    session = runtime.calibration
    assert session is not None
    for _ in range(max_ticks):
        if not session.running:
            return
        session.keepalive()
        runtime.tick()
    raise AssertionError("calibration did not finish")


def _support_written(runtime: HardwareRuntime) -> bool:
    return all(drive.last_raw == int(drive.profile.support_raw.value) * drive.profile.sign for drive in runtime.drives.values())  # type: ignore[attr-defined]


def test_wizard_session_runs_stages_and_proposes_changes(twin_runtime: HardwareRuntime) -> None:
    session = twin_runtime.start_calibration("WIZARD")
    assert twin_runtime.mode == "calibration"
    _run(twin_runtime)
    payload = session.to_payload()
    assert payload["status"] == "done", payload["reason"]
    assert [stage["code"] for stage in payload["stages"]] == ["B0", "B1", "B5", "S3", "M1", "M2", "M3", "C3", "B7", "C1"]
    assert all(stage["status"] == "done" and stage["result"]["report"] for stage in payload["stages"])
    assert payload["progress"] == 1.0 and payload["hasChanges"]
    keys = {(item["side"], item["key"]) for item in payload["changes"]}
    assert {("left", "direction_sign"), ("right", "coulomb_up_n"), ("left", "support_raw"), ("right", "zero_counts"), (None, "loop_period_s"), (None, "hold_ultimate_k_n_per_mm")} <= keys
    assert payload["log"]["t"] and len(payload["log"]["t"]) <= 601
    assert twin_runtime.mode == "support" and _support_written(twin_runtime)
    assert twin_runtime.profile.left.gravity_map.provenance == "default"  # candidate not active until saved


def test_preconditions_block_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARDWARE_ADAPTER", "twin")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    with pytest.raises(PermissionError, match="Сервисный режим"):
        runtime.start_calibration("B5")
    runtime.set_service_mode(True)
    with pytest.raises(PermissionError, match="Servo ON"):
        runtime.start_calibration("B5")
    runtime.set_servo(True)
    with pytest.raises(PermissionError, match="S3"):
        runtime.start_calibration("C1")  # requires S3
    with pytest.raises(PermissionError, match="D2"):
        runtime.start_calibration("D4")  # requires D2
    with pytest.raises(ValueError):
        runtime.start_calibration("X9")


def test_dead_man_release_aborts_to_support(twin_runtime: HardwareRuntime) -> None:
    session = twin_runtime.start_calibration("WIZARD")
    for _ in range(40):
        session.keepalive()
        twin_runtime.tick()
    session.dead_man_timeout_s = -1.0
    twin_runtime.tick()
    assert session.status == "aborted" and "удержания" in (session.reason or "")
    assert session.current_stage.status == "aborted"
    assert _support_written(twin_runtime)


def test_estop_and_operator_abort(twin_runtime: HardwareRuntime) -> None:
    session = twin_runtime.start_calibration("B5")
    session.keepalive()
    twin_runtime.tick()
    twin_runtime.trigger_emergency_stop()
    assert session.status == "aborted" and twin_runtime.mode == "estop"
    assert _support_written(twin_runtime)

    twin_runtime.clear_emergency_stop()
    twin_runtime.discard_calibration()
    session = twin_runtime.start_calibration("B5")
    assert twin_runtime.abort_calibration()
    assert session.status == "aborted" and session.reason == "прервано оператором"
    assert _support_written(twin_runtime)


def test_calibration_api_accept_saves_and_applies(client) -> None:
    hardware_runtime.set_service_mode(True)
    hardware_runtime.set_servo(True)
    try:
        session = client.get("/api/motor/calibration/session", params={"code": "B5"}).json()
        assert session["session"] is None
        assert all(item["ok"] for item in session["preconditions"]), session["preconditions"]
        started = client.post("/api/motor/calibration/start", json={"code": "B5"})
        assert started.status_code == 200, started.text
        assert client.post("/api/motor/calibration/start", json={"code": "B5"}).status_code == 409
        assert client.post("/api/motor/calibration/keepalive").json() == {"running": True}
        _run(hardware_runtime)
        result = client.get("/api/motor/calibration/session", params={"code": "B5"}).json()["session"]
        assert result["status"] == "done" and result["hasChanges"]

        accepted = client.post("/api/motor/calibration/accept")
        assert accepted.status_code == 200, accepted.text
        version = accepted.json()["version"]
        assert hardware_runtime.profile.version == version
        assert hardware_runtime.profile.left.direction_sign.provenance == "measured"
        assert client.post("/api/motor/calibration/accept").status_code == 409
        catalog = {item["code"]: item for item in client.get("/api/motor/calibrations").json()}
        assert catalog["B5"]["status"] == "actual" and catalog["B5"]["description"] and catalog["WIZARD"]["runnable"]

        runs = client.get("/api/motor/calibration/runs").json()
        assert runs[0]["status"] == "saved" and runs[0]["savedVersion"] == version
        assert client.post("/api/motor/calibration/discard").json() == {"ok": True}
        assert client.get("/api/motor/calibration/session").json()["session"] is None
    finally:
        hardware_runtime.abort_calibration()
        hardware_runtime.set_service_mode(False)


def test_parameters_api_describes_and_validates(client) -> None:
    data = client.get("/api/motor/parameters").json()
    groups = {group["id"]: group for group in data["groups"]}
    assert set(groups) == {"drive", "statics", "dynamics", "motion", "behaviour", "safety"}
    items = {item["key"]: item for group in data["groups"] for item in group["items"]}
    assert items["coulomb_up_n"]["values"]["left"]["value"] > 0 and items["coulomb_up_n"]["description"]
    assert items["direction_sign"]["editable"] is False

    change = {"changes": [{"scope": "tunables", "key": "hold_k_fraction", "value": 0.2}]}
    assert client.put("/api/motor/parameters", json=change).status_code == 409  # not in service mode
    hardware_runtime.set_service_mode(True)
    try:
        assert client.put("/api/motor/parameters", json={"changes": [{"scope": "tunables", "key": "hold_k_fraction", "value": 5}]}).status_code == 422
        assert client.put("/api/motor/parameters", json={"changes": [{"scope": "side", "key": "direction_sign", "side": "left", "value": -1}]}).status_code == 422
        updated = client.put("/api/motor/parameters", json={"changes": [
            {"scope": "tunables", "key": "hold_k_fraction", "value": 0.2},
            {"scope": "side", "key": "support_raw", "side": "left", "value": 120},
        ]})
        assert updated.status_code == 200, updated.text
        items = {item["key"]: item for group in updated.json()["groups"] for item in group["items"]}
        assert items["hold_k_fraction"]["value"] == {**items["hold_k_fraction"]["value"], "value": 0.2, "provenance": "manual"}
        assert items["support_raw"]["values"]["left"]["value"] == 120
        assert hardware_runtime.drives["left"].profile.support_raw.value == 120  # type: ignore[attr-defined]
    finally:
        hardware_runtime.set_service_mode(False)
