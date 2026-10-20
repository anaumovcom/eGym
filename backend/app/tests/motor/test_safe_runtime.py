from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.motor.profile import MachineProfile, Measured
from app.motor.units import passport_mm_per_pulse
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


@pytest.mark.parametrize("calibration_running,workout_active,expected", [
    (None, False, None),
    (False, False, None),
    (True, False, "Калибровка тренажёра"),
    (None, True, "Настройка или выполнение упражнения"),
    (False, True, "Настройка или выполнение упражнения"),
    (True, True, "Калибровка тренажёра"),
])
def test_scale_monitoring_guard_is_read_only(modbus_runtime, calibration_running, workout_active, expected) -> None:
    runtime, service = modbus_runtime
    runtime.calibration = None if calibration_running is None else SimpleNamespace(running=calibration_running)
    runtime.workout = SimpleNamespace(active=workout_active)
    writes = list(service.writes)
    events = list(runtime.events)

    assert runtime.scale_monitoring_block_reason() == expected
    assert service.writes == writes
    assert list(runtime.events) == events


def _profile_with_zero(left: int, right: int) -> MachineProfile:
    profile = MachineProfile()
    for side, value in (("left", left), ("right", right)):
        profile = profile.with_side(side, replace(profile.side(side), zero_counts=Measured(value, None, "measured", "reset_zero_position", None)))
    return profile


def test_restart_keeps_absolute_position_of_a_raised_bar(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    per_mm = 1 / passport_mm_per_pulse()
    # restart with the bar 600 mm up: the drive init captures the current counts as zero
    service.left_zero_pulses, service.right_zero_pulses = 7_634_010 + round(600 * per_mm), 49_321_568 + round(600 * per_mm)
    runtime.apply_profile(_profile_with_zero(7_634_010, 49_321_568))
    runtime.tick()
    assert (service.left_zero_pulses, service.right_zero_pulses) == (7_634_010, 49_321_568)


def test_operator_zero_survives_restart(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    runtime.set_service_mode(True)
    service.counts = {1: 7_634_010, 2: 49_321_568}
    command = runtime.reset_zero()
    assert (command.payload["leftZeroPulses"], command.payload["rightZeroPulses"]) == (7_634_010, 49_321_568)
    runtime.apply_profile(_profile_with_zero(7_634_010, 49_321_568))  # hardware_service saves it to the profile
    runtime.tick()
    assert (service.left_zero_pulses, service.right_zero_pulses) == (7_634_010, 49_321_568)
    # restart with the bar 300 mm up: init captures the current counts, the profile zero replaces them
    per_mm = 1 / passport_mm_per_pulse()
    service.left_zero_pulses, service.right_zero_pulses = 7_634_010 + round(300 * per_mm), 49_321_568 + round(300 * per_mm)
    runtime.reset(profile=_profile_with_zero(7_634_010, 49_321_568))
    assert (service.left_zero_pulses, service.right_zero_pulses) == (7_634_010, 49_321_568)


def test_lost_absolute_position_keeps_init_zero(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    service.left_zero_pulses, service.right_zero_pulses = 0, 0  # encoder reset: far outside the travel
    runtime.apply_profile(_profile_with_zero(7_634_010, 49_321_568))
    runtime.tick()
    assert (service.left_zero_pulses, service.right_zero_pulses) == (0, 0)
    assert any(event.get("kind") == "zero" and "вне хода" in str(event.get("message")) for event in runtime.events)


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
    service.speed_rpm = {1: 2300}
    service.writes.clear()
    runtime.tick()
    assert runtime.latch == "overspeed"
    assert service.writes[-2:] == [(1, 100), (2, 100)]  # not 0: without a brake the bar would fall freely
    service.speed_rpm = {}
    runtime.trigger_emergency_stop()
    runtime.apply_shutdown_support()
    assert runtime.latch == "overspeed"
    assert service.writes[-2:] == [(1, 100), (2, 100)]  # neither E-stop nor shutdown override it


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


def test_control_loop_ticks_while_event_loop_is_blocked(modbus_runtime) -> None:
    runtime, _service = modbus_runtime

    async def lifecycle() -> tuple[float, float]:
        await runtime.start()
        await asyncio.sleep(0.1)
        before = runtime._tick_started
        time.sleep(0.5)  # a handler waiting on a locked SQLite file blocks the event loop
        after = runtime._tick_started
        await runtime.stop()
        assert before is not None and after is not None
        return before, after

    before, after = asyncio.run(lifecycle())
    assert after - before >= 0.3


def test_motion_is_rejected_while_servo_off(modbus_runtime) -> None:
    runtime, _service = modbus_runtime
    with pytest.raises(PermissionError, match="Servo OFF"):
        runtime.workout_command("enter_weightless", {})
    assert runtime.snapshot_payload()["control"]["motorControl"] == "disabled"


def test_servo_requires_service_mode(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    with pytest.raises(PermissionError, match="сервисном"):
        runtime.set_servo(True)
    with pytest.raises(PermissionError, match="сервисном"):
        runtime.set_servo(False)
    assert service.servo_calls == []
    assert runtime.snapshot_payload()["control"]["servo"] == {"left": False, "right": False}


def test_servo_on_writes_support_first_and_switches_both(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    runtime.set_service_mode(True)
    service.writes.clear()
    runtime.set_servo(True)
    assert service.writes[:2] == [(1, 100), (2, 100)]
    assert all(on and before >= 2 for _slave, on, before in service.servo_calls)
    assert runtime.snapshot_payload()["control"]["servo"] == {"left": True, "right": True}
    runtime.set_servo(False)
    assert service.servo == {1: False, 2: False}


def test_servo_on_failure_rolls_back_both_sides(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    runtime.set_service_mode(True)
    service.servo_fail_slaves = {2}
    with pytest.raises(PermissionError, match="right"):
        runtime.set_servo(True)
    assert service.servo == {1: False, 2: False}


def test_servo_on_rejected_while_latched(modbus_runtime) -> None:
    runtime, service = modbus_runtime
    runtime.set_service_mode(True)
    runtime.trigger_emergency_stop()
    with pytest.raises(PermissionError, match="СТОП"):
        runtime.set_servo(True)
    assert service.servo_calls == []


def test_twin_starts_servo_off_and_toggles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    assert runtime.servo_states() == {"left": False, "right": False}
    runtime.set_service_mode(True)
    runtime.set_servo(True)
    assert runtime.servo_states() == {"left": True, "right": True}
