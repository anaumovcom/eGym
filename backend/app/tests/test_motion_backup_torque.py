"""Backup support is best effort, not a mechanical brake or a speed guarantee."""

import asyncio
from threading import Event

import pytest

from app.core.config import get_settings
from app.schemas.modbus import ModbusConnectionParamsSchema
from app.services.hardware_runtime import HardwareRuntime
from app.services.modbus_service import ModbusService
from app.services.motion.adapter import DriveCommand, SideCommand
from app.services.motion.controller import ControlMode
from app.services.motion.modbus_adapter import ModbusDriveAdapter
from app.services.motion.parameters import MotionParameters


def connected():
    service = ModbusService()
    assert service.connect(ModbusConnectionParamsSchema(port="SIM://")).connected
    return service


def references(service):
    return [service.read_torque_telemetry(side)["command_torque_raw"] for side in (1, 2)]


def loaded():
    return DriveCommand(
        left=SideCommand(mode="torque", force_kg=20, weight_comp_kg=13),
        right=SideCommand(mode="torque", force_kg=20, weight_comp_kg=13),
    )


def test_startup_never_writes_zero_reference(monkeypatch):
    service = ModbusService()
    writes = []
    original = service._write_register_locked

    def spy(address, value, slave_id, **kwargs):
        if address == 0x12C:
            writes.append((slave_id, value))
        return original(address, value, slave_id, **kwargs)

    monkeypatch.setattr(service, "_write_register_locked", spy)
    assert service.connect(
        ModbusConnectionParamsSchema(port="SIM://"), initial_commands={1: 100, 2: -100},
    ).connected
    assert writes == [(1, 100), (2, -100)]
    assert references(service) == [100, -100]


def test_software_fault_is_latched_and_direction_is_respected():
    service = connected()
    params = MotionParameters()
    params.set_many({"screw.rightDirectionInverted": True}, temporary=True)
    adapter = ModbusDriveAdapter(service=service, parameters=params)
    assert adapter.enter_safe_descent() == {}
    for _ in range(40):
        adapter.step(loaded(), 0.02)
    assert references(service) == [100, -100]
    assert adapter.safe_descent_active
    adapter.reset_errors()
    assert not adapter.safe_descent_active
    assert references(service) == [100, -100]
    for _ in range(40):
        adapter.step(loaded(), 0.02)
    assert references(service) == [400, -400]


def test_leaving_idle_does_not_ramp_from_zero():
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    adapter.step(DriveCommand(), 0.02)
    assert references(service) == [100, 100]
    adapter.step(loaded(), 0.02)
    assert references(service) == [125, 125]


@pytest.mark.parametrize("error_kind", ["comm", "alarm"])
def test_one_drive_failure_attempts_support_on_both_drives(monkeypatch, error_kind):
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    original = service.read_torque_telemetry

    def read(slave, **kwargs):
        data = original(slave, **kwargs)
        if slave == 1:
            if error_kind == "comm":
                data["error"] = "no response"
            else:
                data["alarm"] = 42
        return data

    monkeypatch.setattr(service, "read_torque_telemetry", read)
    telemetry = adapter.step(loaded(), 0.02)
    assert not telemetry.left.connected
    assert adapter.safe_descent_active
    assert [original(side)["command_torque_raw"] for side in (1, 2)] == [100, 100]


def test_failed_backup_write_does_not_skip_other_drive(monkeypatch):
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    original = service.set_torque_command

    def write(slave, value, **kwargs):
        if slave == 1:
            raise OSError("bus failure")
        return original(slave, value, **kwargs)

    monkeypatch.setattr(service, "set_torque_command", write)
    assert adapter.enter_safe_descent() == {1: "bus failure"}
    assert references(service)[1] == 100


def test_write_failure_replaces_previous_exercise_reference(monkeypatch):
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    original = service.set_torque_command
    writes = []

    def write(slave, value, **kwargs):
        writes.append((slave, value))
        if slave == 1 and value != 100:
            return "write failed"
        return original(slave, value, **kwargs)

    monkeypatch.setattr(service, "set_torque_command", write)
    adapter.step(loaded(), 0.02)
    assert adapter.safe_descent_active
    assert writes[-2:] == [(1, 100), (2, 100)]
    assert references(service) == [100, 100]


def test_overspeed_latch_is_not_overridden_by_idle_or_shutdown(monkeypatch):
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    original = service.read_torque_telemetry

    def fast(slave, **kwargs):
        data = original(slave, **kwargs)
        data["feedback_speed_rpm"] = 500
        return data

    monkeypatch.setattr(service, "read_torque_telemetry", fast)
    assert adapter.step(loaded(), 0.02).left.error_code == "E-OVERSPEED"
    monkeypatch.setattr(service, "read_torque_telemetry", original)
    adapter.step(DriveCommand(), 0.02)
    adapter.enter_safe_descent()
    assert references(service) == [0, 0]


def test_disconnect_can_preserve_delivered_support(monkeypatch):
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    adapter.enter_safe_descent()
    writes = []
    monkeypatch.setattr(service, "stop_all_torque", lambda: writes.append("zero"))
    assert not service.disconnect(preserve_torque=True).connected
    assert writes == []


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("HARDWARE_ADAPTER", "emulator")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "false")
    get_settings.cache_clear()
    instance = HardwareRuntime()
    instance.adapter = ModbusDriveAdapter(service=connected(), parameters=instance.parameters)
    yield instance
    get_settings.cache_clear()


def test_runtime_fault_requests_backup(runtime):
    runtime.controller._fault("test fault")
    runtime._tick_motion()
    assert runtime.adapter.safe_descent_active
    assert references(runtime.adapter.service) == [100, 100]


def test_runtime_physical_estop_applies_backup(runtime):
    runtime.controller.request_emergency_stop()
    runtime._tick_motion()
    assert references(runtime.adapter.service) == [100, 100]


@pytest.mark.asyncio
async def test_runtime_stop_leaves_backup_reference(runtime):
    await runtime.start()
    await runtime.stop()
    assert references(runtime.adapter.service) == [100, 100]
    assert runtime._task is None


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_tick_before_backup(runtime, monkeypatch):
    entered, release = Event(), Event()
    original = runtime._tick_motion

    def delayed():
        entered.set()
        assert release.wait(3)
        return original()

    monkeypatch.setattr(runtime, "_tick_motion", delayed)
    await runtime.start()
    assert await asyncio.to_thread(entered.wait, 3)
    stopping = asyncio.create_task(runtime.stop())
    try:
        await asyncio.sleep(0)
        assert not stopping.done()
    finally:
        release.set()
        await stopping
    assert references(runtime.adapter.service) == [100, 100]


@pytest.mark.asyncio
async def test_shutdown_support_after_task_failed(runtime):
    async def fail():
        raise RuntimeError("publisher failure")

    runtime._task = asyncio.create_task(fail())
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="publisher failure"):
        await runtime.stop()
    assert references(runtime.adapter.service) == [100, 100]
    assert runtime._task is None


@pytest.mark.asyncio
async def test_lifespan_restart_never_zeroes_reference(monkeypatch):
    from app import main
    from app.services.motion import modbus_adapter

    monkeypatch.setenv("HARDWARE_ADAPTER", "modbus")
    monkeypatch.setenv("MODBUS_PORT", "SIM://")
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    get_settings.cache_clear()
    service = ModbusService()
    monkeypatch.setattr(modbus_adapter, "modbus_service", service)
    instance = HardwareRuntime()
    monkeypatch.setattr(main, "hardware_runtime", instance)
    monkeypatch.setattr(main, "modbus_service", service)
    monkeypatch.setattr(main, "bootstrap_local_data", lambda: None)
    monkeypatch.setattr(main, "load_hardware_parameters", lambda: {"homing.limitSwitchesEnabled": False})
    writes = []
    original = service._write_register_locked

    def spy(address, value, slave_id, **kwargs):
        if address == 0x12C:
            writes.append(value)
        return original(address, value, slave_id, **kwargs)

    monkeypatch.setattr(service, "_write_register_locked", spy)
    try:
        for _ in range(2):
            async with main.lifespan(main.app):
                assert service.get_status().connected
            assert not service.get_status().connected
            assert writes[-2:] == [100, 100]
        assert writes and 0 not in writes
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_loop_exception_applies_backup_without_killing_loop(runtime, monkeypatch):
    failed = Event()

    def broken():
        raise RuntimeError("unexpected tick failure")

    original = runtime._handle_motion_failure

    def handled(error):
        original(error)
        failed.set()

    monkeypatch.setattr(runtime, "_tick_motion", broken)
    monkeypatch.setattr(runtime, "_handle_motion_failure", handled)
    await runtime.start()
    try:
        assert await asyncio.to_thread(failed.wait, 3)
        assert not runtime._task.done()
        assert runtime.controller.state.mode == ControlMode.fault
        assert references(runtime.adapter.service) == [100, 100]
    finally:
        await runtime.stop()


def test_estop_applies_and_keeps_backup_support():
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    adapter.emergency_stop()
    adapter.enter_safe_descent()
    adapter.step(DriveCommand(), 0.02)
    assert references(service) == [100, 100]


def test_brake_request_applies_support_without_latching():
    service = connected()
    adapter = ModbusDriveAdapter(service=service)
    adapter.set_brake(True)
    assert references(service) == [100, 100]
    assert not adapter.safe_descent_active


def test_estop_release_clears_estop_only_latch():
    adapter = ModbusDriveAdapter(service=connected())
    adapter.emergency_stop()
    assert adapter.safe_descent_active
    adapter.release_emergency_stop()
    assert not adapter.safe_descent_active


def test_runtime_backup_fault_names_the_drive_failure(runtime, monkeypatch):
    service = runtime.adapter.service
    original = service.read_torque_telemetry

    def read(slave, **kwargs):
        data = original(slave, **kwargs)
        if slave == 1:
            data["error"] = "no response"
        return data

    runtime.controller._enter(ControlMode.idle, "idle", "")
    monkeypatch.setattr(service, "read_torque_telemetry", read)
    runtime._tick_motion()
    fault = runtime.controller.state.fault_code or ""
    assert "Резервный момент 100" in fault
    assert "левый привод" in fault and "no response" in fault and "E-MODBUS-COMM" in fault