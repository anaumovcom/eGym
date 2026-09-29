import pytest

from app.core.config import get_settings
from app.api.routes import modbus_debug
from app.schemas.modbus import ModbusCommandRequestSchema, ModbusConnectionParamsSchema, ModbusReadRequestSchema, ModbusWriteRequestSchema, PositionExerciseSchema, PositionCalibrationCaptureSchema, WeightlessPositionSchema
from app.services.modbus_service import ModbusService
from app.services import hardware_service as hardware_service_module
from app.schemas.hardware import HardwareCommandRequestSchema
from app.services.hardware_runtime import HardwareRuntime
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


def test_motion_adapter_explains_blocked_safety_controller_not_drive_alarm():
    adapter = ModbusDriveAdapter()
    telemetry = adapter.step(DriveCommand(), 0.02)
    assert not telemetry.left.connected
    assert telemetry.left.error_code == "E-CTRL-UNAVAILABLE"
    assert "Контур движения Modbus не настроен" in telemetry.left.error_message
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
    assert (moved.left.position_mm, moved.right.position_mm, moved.skew_mm) == (32, 16, 16)
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
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    rebased = service.get_positions()
    assert rebased.zeroed  # reconnect is application startup: capture both counters again
    assert rebased.left.position_mm == rebased.right.position_mm == 0


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


def test_readiness_allows_zero_without_motion_safety_and_survives_fault():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    _write_pulses(service, 1, -1000)
    _write_pulses(service, 2, 2000)
    positions = service.capture_zero()
    assert positions.readiness.communication_ready
    assert positions.readiness.encoder_ready and positions.readiness.allow_zero_offset
    assert positions.readiness.degraded_manual_mode
    assert not positions.readiness.motion_safety_ready
    assert not positions.readiness.torque_control_ready
    assert not positions.readiness.allow_automatic_motion
    assert not positions.readiness.allow_homing
    assert positions.left.position_mm == positions.right.position_mm == positions.skew_mm == 0


def test_software_stop_both_sides_simulated_with_active_segment():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    for slave in (1, 2):
        assert service.write_register(ModbusWriteRequestSchema(address=0x093, value=3, slave_id=slave)).success
        assert service.write_register(ModbusWriteRequestSchema(address=0x12F, value=120, slave_id=slave)).success
        assert service.execute_command(ModbusCommandRequestSchema(command="servo_on", confirmed=True, slave_id=slave)).success
    result = service.software_stop()
    assert not result.success
    assert "Servo-OFF" in result.errors[0]
    for slave in (1, 2):
        assert service.read_registers(ModbusReadRequestSchema(address=0x12F, slave_id=slave)).registers[0].value == 120
        assert service.read_registers(ModbusReadRequestSchema(address=0x201, slave_id=slave)).registers[0].value & 1


def test_software_stop_does_not_claim_real_servo_off():
    service = ModbusService()
    service._connected = True
    service._params = ModbusConnectionParamsSchema(port="/dev/ttyUSB0")

    class FakeInstrument:
        address = 1

        def read_register(self, address, **kwargs):
            return 0

        def write_register(self, address, value, **kwargs):
            assert address == 0x12C and value == 0

    service._instr = FakeInstrument()
    result = service.software_stop()
    assert not result.success
    assert len(result.errors) == 1


def test_partial_encoder_failure_does_not_rebase_offsets_or_claim_readiness(monkeypatch):
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    service.capture_zero()
    monkeypatch.setattr(service, "_read_position", lambda slave: (0, None) if slave == 1 else (None, "timeout"))
    result = service.capture_zero()
    assert not result.readiness.encoder_ready
    assert not result.readiness.allow_zero_offset
    assert result.left_zero_pulses == result.right_zero_pulses == 0


def test_real_modbus_runtime_is_degraded_but_never_auto_homes(monkeypatch):
    monkeypatch.setenv("HARDWARE_ADAPTER", "modbus")
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    assert isinstance(runtime.adapter, ModbusDriveAdapter)
    assert runtime.controller.state.mode.value == "idle"
    runtime._tick_motion()
    assert runtime.controller.state.mode.value != "fault"
    assert runtime.state.machine_state.value == "warning"
    with pytest.raises(PermissionError, match="E-CTRL-UNAVAILABLE"):
        runtime.home()
    with pytest.raises(PermissionError, match="E-CTRL-UNAVAILABLE"):
        runtime.manual_move("up", 10, "service")


def _read_value(service: ModbusService, slave: int, address: int) -> int:
    return service.read_registers(ModbusReadRequestSchema(address=address, slave_id=slave)).registers[0].value


def _position_request(**overrides) -> PositionExerciseSchema:
    return PositionExerciseSchema(**{
        "target_type": "lower_boundary", "lower_boundary_mm": 400,
        "torque_limit": 300, "speed_rpm": 30, **overrides,
    })


def test_position_exercise_uses_independent_zeros_directions_and_segment_zero():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://", left_direction=1, right_direction=-1))
    _write_pulses(service, 1, -100_000)
    _write_pulses(service, 2, 800_000)
    assert service.capture_zero().skew_mm == 0

    result = service.start_position_exercise(_position_request())
    assert result.state == "exercise" and result.target_mm == 400
    for sid, target in ((1, 25_000), (2, 675_000)):
        assert _read_value(service, sid, 0x002) == 0
        assert _read_value(service, sid, 0x090) == 1
        assert _read_value(service, sid, 0x091) == 0
        assert _read_value(service, sid, 0x05E) == _read_value(service, sid, 0x05F) == 300
        assert _read_value(service, sid, 0x190) == 30
        raw = target & 0xFFFFFFFF
        assert _read_value(service, sid, 0x168) & 0xFFFF == raw & 0xFFFF
        assert _read_value(service, sid, 0x169) & 0xFFFF == raw >> 16
        assert _read_value(service, sid, 0x201) & 1
        assert not _read_value(service, sid, 0x201) & (1 << 5)
        assert _read_value(service, sid, 0x20A) == 0  # no torque command

    loads_before = sum(e.action == "CMD:pos_load" for e in service.get_log(limit=500).entries)
    service.start_position_exercise(_position_request(torque_limit=200))
    service.start_position_exercise(_position_request(torque_limit=200))
    assert sum(e.action == "CMD:pos_load" for e in service.get_log(limit=500).entries) == loads_before
    assert all(_read_value(service, sid, 0x05F) == 200 for sid in (1, 2))


def test_fixed_position_stop_raise_and_skew_fault_do_not_servo_off():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    result = service.start_position_exercise(PositionExerciseSchema(target_type="fixed_position", fixed_position_mm=1200,
                                                                     torque_limit=100, speed_rpm=20))
    assert result.target_type == "fixed_position" and result.target_mm == 1200
    raised = service.stop_raise()
    assert raised.state == "raising" and raised.target_mm == 2000
    assert raised.torque_limit == 300 and raised.speed_rpm == 30
    _write_pulses(service, 1, 1250)
    _write_pulses(service, 2, 0)
    fault = service.position_motion_status()
    assert fault.state == "fault" and "Перекос" in (fault.error or "")
    assert _read_value(service, 1, 0x201) & 1
    assert _read_value(service, 2, 0x201) & 1


def test_reversed_drive_goal_uses_twos_complement_words():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://", right_direction=-1))
    service.start_position_exercise(_position_request())
    raw = (-125_000) & 0xFFFFFFFF
    assert _read_value(service, 2, 0x168) == raw & 0xFFFF
    assert _read_value(service, 2, 0x169) == raw >> 16


def test_invalid_targets_and_active_zero_are_rejected_without_load():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    with pytest.raises(ValueError, match="не задана"):
        service.start_position_exercise(PositionExerciseSchema(target_type="fixed_position", torque_limit=300, speed_rpm=30))
    with pytest.raises(ValueError, match="вне программных"):
        service.start_position_exercise(_position_request(max_mm=300))
    assert not any(e.action == "CMD:pos_load" for e in service.get_log(limit=500).entries)
    service.start_position_exercise(_position_request())
    with pytest.raises(ValueError, match="программный ноль"):
        service.capture_zero()
    with pytest.raises(ValueError, match="Нельзя отключать"):
        service.disconnect()


def test_real_position_control_refuses_all_motion_before_writing():
    service = ModbusService()
    service._connected = True
    service._params = ModbusConnectionParamsSchema(port="/dev/ttyUSB0")

    class FakeInstrument:
        address = 1

        def write_register(self, *args, **kwargs):
            pytest.fail("Real drive write must not be attempted")

    service._instr = FakeInstrument()
    with pytest.raises(PermissionError, match="E-CTRL-UNAVAILABLE"):
        service.start_position_exercise(_position_request())
    with pytest.raises(PermissionError, match="E-CTRL-UNAVAILABLE"):
        service.stop_raise()


def test_calibration_uses_both_relative_encoders_and_expires_on_zero():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://", right_direction=-1))
    key = "alex:bench"
    request = _position_request(exercise_key=key, lower_boundary_mm=400)
    with pytest.raises(ValueError, match="Нет калибровки"):
        service.start_position_exercise(request)
    _write_pulses(service, 1, 125_000)
    _write_pulses(service, 2, -125_000)
    lower = service.capture_position_point(PositionCalibrationCaptureSchema(exercise_key=key, point="lower"))
    assert lower.lower_mm == 400 and lower.zero_generation == service.get_positions().zero_generation
    with pytest.raises(ValueError, match="верхнюю"):
        service.start_position_exercise(request)
    _write_pulses(service, 1, 375_000)
    _write_pulses(service, 2, -375_000)
    upper = service.capture_position_point(PositionCalibrationCaptureSchema(exercise_key=key, point="upper"))
    assert upper.upper_mm == 1200
    assert service.start_position_exercise(request).state == "exercise"
    with pytest.raises(ValueError, match="программный ноль"):
        service.capture_zero()
    service.stop_raise()
    service._motion_fault("test")
    service.capture_zero()
    assert service.get_position_calibration(key) is None
    with pytest.raises(ValueError, match="калибровки"):
        service.start_position_exercise(request)


def test_weightless_uses_2m_goal_below_explicit_threshold_and_can_hold():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    with pytest.raises(ValueError, match="ниже"):
        service.enter_weightless(WeightlessPositionSchema(torque_limit=100, no_motion_threshold=100))
    status = service.enter_weightless(WeightlessPositionSchema(torque_limit=20, no_motion_threshold=50))
    assert status.state == "weightless" and status.target_mm == 2000
    assert status.torque_limit == 20
    assert all(_read_value(service, sid, 0x05E) == _read_value(service, sid, 0x05F) == 20 for sid in (1, 2))
    assert all(_read_value(service, sid, 0x20A) == 0 for sid in (1, 2))
    with pytest.raises(ValueError, match="ниже измеренного порога"):
        service.update_position_limit(50)
    with pytest.raises(ValueError, match="Сначала удержите"):
        service.start_position_exercise(_position_request())
    _write_pulses(service, 1, 125_000)
    _write_pulses(service, 2, 125_000)
    assert service.position_motion_status().state == "weightless"  # large goal deviation is intentional
    assert service.capture_position_point(PositionCalibrationCaptureSchema(exercise_key="alex:fixed", point="fixed")).fixed_mm == 400
    held = service.hold_position()
    assert held.state == "holding" and held.target_mm == 400 and held.torque_limit == 300
    assert all(_read_value(service, sid, 0x201) & 1 for sid in (1, 2))
    with pytest.raises(ValueError, match="программный ноль"):
        service.capture_zero()


def test_weightless_checks_skew_and_refuses_real_port():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    _write_pulses(service, 1, 1250)
    with pytest.raises(ValueError, match="Перекос"):
        service.capture_position_point(PositionCalibrationCaptureSchema(exercise_key="alex:bench", point="lower"))
    service._params = ModbusConnectionParamsSchema(port="/dev/ttyUSB0")
    with pytest.raises(PermissionError, match="E-CTRL-UNAVAILABLE"):
        service.enter_weightless(WeightlessPositionSchema(torque_limit=1, no_motion_threshold=2))


def test_stop_raise_does_not_silently_extend_exercise_software_limits():
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    service.start_position_exercise(_position_request(max_mm=1500))
    with pytest.raises(ValueError, match="действующих программных границ"):
        service.stop_raise()
    assert service.position_motion_status().state == "exercise"


def test_debug_commands_cannot_override_active_weightless_controller(monkeypatch):
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    service.enter_weightless(WeightlessPositionSchema(torque_limit=1, no_motion_threshold=2))
    monkeypatch.setattr(modbus_debug, "modbus_service", service)
    result = modbus_debug.write_register(ModbusWriteRequestSchema(address=0x05E, value=2000, slave_id=1))
    assert not result.success and _read_value(service, 1, 0x05E) == 1
    command = modbus_debug.execute_command(ModbusCommandRequestSchema(command="servo_off", slave_id=1))
    assert not command.success and _read_value(service, 1, 0x201) & 1


def test_legacy_machine_calibration_and_motion_cannot_mix_modbus_feedback(monkeypatch):
    service = ModbusService()
    service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    monkeypatch.setattr(hardware_service_module, "modbus_service", service)
    for action in ("start_motion", "start_fixed_position", "enter_weightless", "capture_point", "manual_move"):
        with pytest.raises(PermissionError, match="отдельные координаты"):
            hardware_service_module.HardwareService().execute_command(None, HardwareCommandRequestSchema(action=action))
