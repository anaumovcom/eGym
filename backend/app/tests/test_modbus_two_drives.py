import pytest

from app.api.routes import modbus_debug
from app.schemas.modbus import (
    ModbusCommandRequestSchema,
    ModbusConnectionParamsSchema,
    ModbusReadRequestSchema,
    ModbusWriteRequestSchema,
)
from app.services.modbus_service import ModbusService
from app.services.motion.adapter import DriveCommand
from app.services.motion.modbus_adapter import ModbusDriveAdapter


def test_simulated_drives_have_independent_feedback_and_diagnostics():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    for slave_id, low, high in [(1, 42, 0), (2, 0xFFFE, 0xFFFF)]:
        assert service.write_register(ModbusWriteRequestSchema(address=0x1BC, value=low, slave_id=slave_id)).success
        assert service.write_register(ModbusWriteRequestSchema(address=0x1BD, value=high, slave_id=slave_id)).success
        result = service.read_registers(ModbusReadRequestSchema(address=0x1BC, count=2, slave_id=slave_id))
        assert result.success
        assert [r.value for r in result.registers] == [low, high]
        assert service.get_diagnostics(slave_id).slave_id == slave_id
    first = service.read_registers(ModbusReadRequestSchema(address=0x1BC, count=2, slave_id=1))
    assert [r.value for r in first.registers] == [42, 0]


def test_real_port_never_falls_back_to_simulation(monkeypatch):
    service = ModbusService()
    monkeypatch.setattr(service, "_real_serial_available", lambda: False)
    status = service.connect(ModbusConnectionParamsSchema(port="/dev/no-such-modbus-port", baud_rate=19200))
    assert not status.connected
    assert not status.simulation_mode
    assert service.get_status().error_message


def test_unverified_real_motor_commands_are_rejected():
    service = ModbusService()
    service._connected = True
    service._params = ModbusConnectionParamsSchema(port="/dev/ttyUSB0")

    class FakeInstrument:
        address = 1

    service._instr = FakeInstrument()
    for slave_id in (1, 2):
        result = service.execute_command(ModbusCommandRequestSchema(command="servo_on", confirmed=True, slave_id=slave_id))
        assert not result.success
        assert "не реализована" in result.error


def test_motion_adapter_reports_offline_modbus_not_drive_alarm():
    adapter = ModbusDriveAdapter(service=ModbusService())
    telemetry = adapter.step(DriveCommand(), 0.02)
    assert not telemetry.left.connected
    assert telemetry.left.error_code == "E-MODBUS-OFFLINE"
    assert not adapter.self_test()[0].passed


def _write_pulses(service: ModbusService, slave_id: int, pulses: int) -> None:
    raw = pulses & 0xFFFFFFFF
    for address, value in ((0x1BC, raw & 0xFFFF), (0x1BD, raw >> 16)):
        assert service.write_register(ModbusWriteRequestSchema(address=address, value=value, slave_id=slave_id)).success


def test_software_zero_captures_both_signed_encoders_and_computes_relative_skew():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    _write_pulses(service, 1, 100_000)
    _write_pulses(service, 2, -20_000)
    zero = service.capture_zero()
    assert zero.zeroed
    assert (zero.left.zero_pulses, zero.right.zero_pulses) == (100_000, -20_000)
    assert (zero.left.position_mm, zero.right.position_mm, zero.skew_mm) == (0, 0, 0)

    _write_pulses(service, 1, 110_000)
    _write_pulses(service, 2, -15_000)
    moved = service.get_positions()
    assert (moved.left.position_mm, moved.right.position_mm) == (
        pytest.approx(10000 * 1703 / 6_980_387),
        pytest.approx(5000 * 1703 / 6_980_387),
    )
    assert moved.skew_mm == pytest.approx(5000 * 1703 / 6_980_387)
    assert (moved.left.zero_pulses, moved.right.zero_pulses) == (100_000, -20_000)

    zero_again = service.capture_zero()
    assert zero_again.skew_mm == 0
    assert zero_again.left.position_mm == zero_again.right.position_mm == 0


def test_failed_second_read_keeps_both_old_offsets_and_reconnect_invalidates_them(monkeypatch):
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    _write_pulses(service, 1, 100)
    _write_pulses(service, 2, 200)
    service.capture_zero()
    original_read = service._read_position
    monkeypatch.setattr(service, "_read_position", lambda slave_id: (None, "timeout") if slave_id == 2 else original_read(slave_id))
    failed = service.capture_zero()
    assert failed.error and "Правый: timeout" in failed.error
    assert (failed.left.zero_pulses, failed.right.zero_pulses) == (100, 200)
    monkeypatch.undo()
    service.disconnect()
    monkeypatch.setattr(service, "initialize_torque_mode", lambda **_kwargs: ["read failed"])
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    unzeroed = service.get_positions()
    assert not unzeroed.zeroed
    assert unzeroed.left.position_mm is None
    assert unzeroed.right.position_mm is None


def test_modbus_connect_route_captures_both_zeros_and_zero_route_rebases(monkeypatch):
    service = ModbusService()
    monkeypatch.setattr(modbus_debug, "modbus_service", service)
    assert modbus_debug.connect(ModbusConnectionParamsSchema(port="SIM://")).connected
    assert modbus_debug.get_positions().zeroed
    _write_pulses(service, 1, 1234)
    _write_pulses(service, 2, -4321)
    result = modbus_debug.zero_positions()
    assert (result.left_zero_pulses, result.right_zero_pulses) == (1234, -4321)
    assert result.left_position_mm == result.right_position_mm == result.skew_mm == 0


def test_stale_reply_from_other_slave_is_drained_and_write_retried():
    service = ModbusService()
    service._connected = True
    service._params = ModbusConnectionParamsSchema(port="/dev/ttyUSB0")

    class FakeSerial:
        flushed = 0

        def reset_input_buffer(self):
            self.flushed += 1

    class FakeInstrument:
        address = 1
        serial = FakeSerial()
        calls: list[tuple[int, int, int]] = []

        def write_register(self, address, value, signed=False):
            self.calls.append((self.address, address, value))
            if len(self.calls) == 1:
                raise OSError("Wrong return slave address: 1 instead of 2")

    service._instr = FakeInstrument()
    service._torque_ready = {2: True}
    assert service.set_torque_command(2, 100, log=False) is None
    assert FakeInstrument.calls == [(2, 0x12C, 100), (2, 0x12C, 100)]
    assert FakeInstrument.serial.flushed == 1


def test_real_port_locked_by_another_backend_is_not_used(monkeypatch):
    import minimalmodbus

    closed = []

    class LockedSerial:
        def close(self):
            closed.append(True)

        @property
        def exclusive(self):
            return None

        @exclusive.setter
        def exclusive(self, value):
            raise OSError("Could not exclusively lock port /dev/ttyFAKE")

    class FakeInstrument:
        def __init__(self, port, slave_id):
            self.serial = LockedSerial()

        def read_register(self, *args, **kwargs):
            raise AssertionError("must not touch the bus")

    service = ModbusService()
    monkeypatch.setattr(service, "_real_serial_available", lambda: True)
    monkeypatch.setattr(minimalmodbus, "Instrument", FakeInstrument)
    status = service.connect(ModbusConnectionParamsSchema(port="/dev/ttyFAKE"))
    assert not status.connected
    assert "exclusively lock" in status.error_message
    assert closed == [True]
