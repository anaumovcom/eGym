from __future__ import annotations

import asyncio

import pytest

from app.core.config import get_settings
from app.services import hardware_runtime as runtime_module
from app.services.hardware_runtime import HardwareRuntime
from app.tests.motor.fakes import FakeModbusService


@pytest.fixture()
def modbus_runtime(monkeypatch: pytest.MonkeyPatch) -> tuple[HardwareRuntime, FakeModbusService]:
    service = FakeModbusService()
    monkeypatch.setattr(runtime_module, "modbus_service", service)
    monkeypatch.setenv("HARDWARE_ADAPTER", "modbus")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    return runtime, service


def test_startup_writes_support_first(modbus_runtime) -> None:
    _runtime, service = modbus_runtime
    assert service.writes[:2] == [(1, 100), (2, 100)]
    assert all(raw != 0 for _slave, raw in service.writes)


def test_twin_startup_writes_support_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    assert runtime.bench is not None
    assert all(drive.writes and drive.writes[0] == 100 for drive in runtime.bench.drives.values())


def test_support_attempts_both_sides(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    service.fail_slaves = {1}
    service.writes.clear()
    runtime._force_write = True
    runtime.tick()
    assert (2, 100) in service.writes
    assert runtime.latch == "fault"
    assert "left" in runtime.write_errors


def test_read_failure_latches_fault_and_keeps_support(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    service.read_fail_slaves = {2}
    service.writes.clear()
    runtime.tick()
    assert runtime.latch == "fault"
    assert {(1, 100), (2, 100)} <= set(service.writes)
    service.read_fail_slaves = set()
    runtime.tick()
    assert runtime.latch == "fault"  # latched until reset
    runtime.reset_fault()
    assert runtime.latch is None


def test_tick_exception_latches_fault_with_support(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    service.writes.clear()
    runtime._handle_failure(RuntimeError("boom"))
    assert runtime.latch == "fault"
    assert {(1, 100), (2, 100)} <= set(service.writes)


def test_overspeed_zero_latch(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    service.speed_rpm = {1: 1200}
    service.writes.clear()
    runtime.tick()
    assert runtime.latch == "overspeed"
    assert service.writes[-2:] == [(1, 0), (2, 0)]
    service.speed_rpm = {}
    runtime.trigger_emergency_stop()
    runtime.apply_shutdown_support()
    assert runtime.latch == "overspeed"
    assert service.writes[-2:] == [(1, 0), (2, 0)]  # neither E-stop nor shutdown override it


def test_estop_support_and_release(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    service.manual = True
    service.writes.clear()
    runtime.trigger_emergency_stop()
    assert service.manual is False  # E-stop ends manual torque
    assert service.writes == [(1, 100), (2, 100)]
    runtime.clear_emergency_stop()
    assert runtime.latch is None
    assert runtime.mode == "support"


def test_manual_torque_not_overwritten(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    service.manual = True
    service.writes.clear()
    for _ in range(10):
        runtime._last_write = 0.0
        runtime.tick()
    assert service.writes == []


def test_shutdown_writes_support(modbus_runtime) -> None:
    runtime, service = modbus_runtime

    async def lifecycle() -> None:
        await runtime.start()
        await asyncio.sleep(0.12)
        service.writes.clear()
        await runtime.stop()

    asyncio.run(lifecycle())
    assert service.writes[-2:] == [(1, 100), (2, 100)]


def test_motion_is_rejected(modbus_runtime) -> None:
    runtime, _service = modbus_runtime
    with pytest.raises(PermissionError, match="v2"):
        runtime.reject_motion("start_motion")
