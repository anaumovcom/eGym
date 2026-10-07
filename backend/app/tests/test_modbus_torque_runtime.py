"""Torque Mode runtime: PA_12C is the only movement reference sent to the drives."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.schemas.modbus import ModbusConnectionParamsSchema, ModbusReadRequestSchema
from app.services.hardware_runtime import HardwareRuntime
from app.services.modbus_service import ModbusService
from app.services.motion.adapter import DriveCommand, SideCommand
from app.services.motion.modbus_adapter import ModbusDriveAdapter
from app.services.motion.parameters import MotionParameters, ParameterValidationError
from app.services.motion.torque import SideInput, TorqueController, TorqueSettings

PA_12C = 0x12C


def _reg(service: ModbusService, address: int, slave_id: int) -> int:
    result = service.read_registers(ModbusReadRequestSchema(address=address, slave_id=slave_id))
    assert result.success
    return result.registers[0].value


def _signed(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


def _connected_service() -> ModbusService:
    service = ModbusService()
    status = service.connect(ModbusConnectionParamsSchema(port="SIM://"))
    assert status.connected
    return service


def _torque_command(force_kg: float, weight_kg: float = 13.0) -> DriveCommand:
    side = SideCommand(mode="torque", force_kg=force_kg, weight_comp_kg=weight_kg)
    return DriveCommand(left=side, right=SideCommand(mode="torque", force_kg=force_kg, weight_comp_kg=weight_kg))


def _inputs(position: float = 500.0, speed_rpm: float = 0.0, velocity: float = 0.0) -> dict:
    return {"left": SideInput(position, velocity, speed_rpm), "right": SideInput(position, velocity, speed_rpm)}


def _settled(controller: TorqueController, command: DriveCommand, inputs: dict, cycles: int = 60):  # noqa: ANN202
    output = None
    for _ in range(cycles):
        output = controller.compute(command, inputs, 0.02)
    return output


# ---------------------------------------------------------------- service
def test_torque_init_sets_mode_without_touching_forbidden_registers() -> None:
    service = _connected_service()
    writes: list[tuple[int, int]] = []
    original = service._write_register_locked

    def spy(address, value, slave_id, **kwargs):  # noqa: ANN001, ANN003, ANN202
        writes.append((address, slave_id))
        return original(address, value, slave_id, **kwargs)

    service._write_register_locked = spy  # type: ignore[method-assign]
    assert service.initialize_torque_mode() == []
    assert service.torque_ready(1) and service.torque_ready(2)
    written = {address for address, _ in writes}
    assert not written & {0x000, 0x002, 0x090, 0x091, 0x094, 0x096, 0x168, 0x169, 0x190}
    assert PA_12C in written
    for slave_id in (1, 2):
        assert _reg(service, 0x002, slave_id) == 2
        assert _reg(service, 0x093, slave_id) == 0
        assert _signed(_reg(service, PA_12C, slave_id)) == 0


def test_torque_command_is_signed_and_clamped_to_limit() -> None:
    service = _connected_service()
    assert service.set_torque_command(1, 150) is None
    assert _signed(_reg(service, PA_12C, 1)) == 150
    assert service.set_torque_command(2, -150) is None
    assert _signed(_reg(service, PA_12C, 2)) == -150
    limit = service.read_torque_telemetry(1)["torque_limit_raw"]
    assert service.set_torque_command(1, 5000) is None
    assert _signed(_reg(service, PA_12C, 1)) == limit
    assert service.set_torque_command(1, -5000) is None
    assert _signed(_reg(service, PA_12C, 1)) == -limit
    service.stop_torque(1)
    assert _signed(_reg(service, PA_12C, 1)) == 0
    assert _signed(_reg(service, 0x002, 1)) == 2  # stop is PA_12C=0, not a mode change


def test_disconnect_zeroes_torque() -> None:
    service = _connected_service()
    service.set_torque_command(1, 100)
    service.set_torque_command(2, -100)
    service.disconnect()
    assert not service.torque_ready(1)


# ------------------------------------------------------ pure pipeline
def test_weight_plus_exercise_with_ramp_and_right_side_inversion() -> None:
    controller = TorqueController(TorqueSettings(per_kg_raw=20, ramp_step_raw=25, max_command_raw=400, right_inverted=True))
    command = _torque_command(force_kg=13 + 5)
    first = controller.compute(command, _inputs(), 0.02)
    assert first.sides["left"].command_raw == 25  # one ramp step only
    assert first.sides["right"].command_raw == -25  # right drive is mounted inverted
    settled = _settled(controller, command, _inputs())
    assert settled.sides["left"].weight_compensation_raw == pytest.approx(13 * 20)
    assert settled.sides["left"].exercise_raw == pytest.approx(5 * 20)
    assert settled.sides["left"].command_raw == 360
    assert settled.sides["right"].command_raw == -360


def test_command_is_clamped_to_max_command() -> None:
    controller = TorqueController(TorqueSettings(per_kg_raw=20, max_command_raw=300, ramp_step_raw=500, right_inverted=True))
    output = _settled(controller, _torque_command(force_kg=60), _inputs(), cycles=5)
    assert output.sides["left"].command_raw == 300
    assert output.sides["right"].command_raw == -300


def test_brake_and_disabled_modes_write_zero() -> None:
    controller = TorqueController(TorqueSettings())
    _settled(controller, _torque_command(20), _inputs(), cycles=40)
    output = controller.compute(DriveCommand(), _inputs(), 0.02)
    assert output.command("left") == 0 and output.command("right") == 0


def test_weight_calibration_scales_with_commanded_weight_share() -> None:
    controller = TorqueController(TorqueSettings(weight_comp_raw=200, nominal_weight_kg_per_side=10, ramp_step_raw=1000))
    output = _settled(controller, _torque_command(force_kg=10, weight_kg=10), _inputs(), cycles=2)
    assert output.sides["left"].command_raw == 200
    assert output.sides["left"].exercise_raw == pytest.approx(0)


def test_overspeed_warning_reduces_exercise_torque_and_alarm_cuts_pa12c() -> None:
    settings = TorqueSettings(per_kg_raw=20, ramp_step_raw=1000, max_command_raw=1000, speed_warn_rpm=100, speed_alarm_rpm=200)
    controller = TorqueController(settings)
    command = _torque_command(force_kg=13 + 10)
    normal = _settled(controller, command, _inputs(velocity=50), cycles=3)
    assert normal.sides["left"].command_raw == 13 * 20 + 200

    warned = controller.compute(command, _inputs(speed_rpm=150, velocity=50), 0.02)
    assert warned.warning
    assert warned.sides["left"].command_raw == pytest.approx(13 * 20 + 100, abs=1)  # exercise part halved, weight kept

    alarm = controller.compute(command, _inputs(speed_rpm=250, velocity=50), 0.02)
    assert alarm.alarm
    assert alarm.command("left") == 0 and alarm.command("right") == 0
    again = controller.compute(command, _inputs(), 0.02)
    assert again.alarm and again.command("left") == 0  # latched until reset
    controller.reset()
    assert controller.compute(command, _inputs(), 0.02).command("left") != 0


def test_soft_limits_do_not_push_beyond_travel() -> None:
    settings = TorqueSettings(per_kg_raw=20, ramp_step_raw=1000, soft_min_mm=50, soft_max_mm=1800)
    controller = TorqueController(settings)
    down = _settled(controller, _torque_command(force_kg=5), _inputs(position=40), cycles=3)  # force < weight: pushes down
    assert down.sides["left"].logical_raw == pytest.approx(13 * 20)  # never below the bar weight
    up = _settled(controller, _torque_command(force_kg=30), _inputs(position=1850), cycles=3)
    assert up.sides["left"].logical_raw == pytest.approx(13 * 20)  # no upward push at the top


def test_limits_are_ignored_until_zero_is_known() -> None:
    controller = TorqueController(TorqueSettings(ramp_step_raw=1000, soft_max_mm=1800))
    inputs = {"left": SideInput(1850, 0, 0, limits_known=False), "right": SideInput(1850, 0, 0, limits_known=False)}
    output = _settled(controller, _torque_command(force_kg=30), inputs, cycles=3)
    assert output.sides["left"].logical_raw == pytest.approx(30 * 20)


def test_torque_parameters_validate_and_never_expose_forbidden_registers() -> None:
    params = MotionParameters()
    settings = TorqueSettings.from_parameters(params)
    assert settings.max_command_raw == 400 and settings.per_kg_raw == 20
    with pytest.raises(ParameterValidationError):
        params.set_many({"torque.maxCommandRaw": 4000}, temporary=True)
    with pytest.raises(ParameterValidationError):
        params.set_many({"torque.speedWarnRpm": 500}, temporary=True)


# --------------------------------------------------------- adapter + sim
def test_adapter_requires_online_and_ready_modbus() -> None:
    adapter = ModbusDriveAdapter(service=ModbusService())
    assert adapter.step(_torque_command(20), 0.02).left.error_code == "E-MODBUS-OFFLINE"


def test_adapter_writes_pa12c_to_both_drives_in_sim() -> None:
    service = _connected_service()
    adapter = ModbusDriveAdapter(service=service, parameters=MotionParameters())
    adapter.home()
    telemetry = None
    for _ in range(40):
        telemetry = adapter.step(_torque_command(13 + 5), 0.02)
    assert telemetry is not None and telemetry.left.error_code is None
    assert _signed(_reg(service, PA_12C, 1)) == 360
    assert _signed(_reg(service, PA_12C, 2)) == 360  # right drive is not inverted (verified on hardware)
    adapter.step(DriveCommand(), 0.02)
    assert _signed(_reg(service, PA_12C, 1)) == 100
    assert _signed(_reg(service, PA_12C, 2)) == 100


def test_manual_torque_is_not_overwritten_by_adapter_loop() -> None:
    service = _connected_service()
    adapter = ModbusDriveAdapter(service=service, parameters=MotionParameters())
    adapter.home()
    service.begin_manual_torque()
    assert service.set_torque_command(1, 100) is None
    assert service.set_torque_command(2, -100) is None
    for _ in range(30):
        telemetry = adapter.step(DriveCommand(), 0.02)
    assert telemetry.left.error_code is None
    assert _signed(_reg(service, PA_12C, 1)) == 100
    assert _signed(_reg(service, PA_12C, 2)) == -100
    service.end_manual_torque()
    service.stop_all_torque()
    adapter.step(DriveCommand(), 0.02)
    assert _signed(_reg(service, PA_12C, 1)) == 100


def test_adapter_emergency_stop_latches_support_torque() -> None:
    service = _connected_service()
    adapter = ModbusDriveAdapter(service=service, parameters=MotionParameters())
    adapter.home()
    for _ in range(40):
        adapter.step(_torque_command(20), 0.02)
    adapter.emergency_stop()
    assert _signed(_reg(service, PA_12C, 1)) == 100
    adapter.step(_torque_command(20), 0.02)
    assert _signed(_reg(service, PA_12C, 1)) == 100
    adapter.release_emergency_stop()


def test_adapter_overspeed_alarm_writes_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _connected_service()
    adapter = ModbusDriveAdapter(service=service, parameters=MotionParameters())
    adapter.home()
    for _ in range(40):
        adapter.step(_torque_command(20), 0.02)
    assert _signed(_reg(service, PA_12C, 1)) != 0
    original = service.read_torque_telemetry

    def fast(slave, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        data = original(slave, *args, **kwargs)
        data["feedback_speed_rpm"] = 500
        return data

    monkeypatch.setattr(service, "read_torque_telemetry", fast)
    telemetry = adapter.step(_torque_command(20), 0.02)
    assert telemetry.left.error_code == "E-OVERSPEED"
    assert _signed(_reg(service, PA_12C, 1)) == 0
    assert _signed(_reg(service, PA_12C, 2)) == 0


# ----------------------------------------------------- levitation
@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch) -> HardwareRuntime:
    monkeypatch.setenv("HARDWARE_KEYBOARD_SIMULATION_ENABLED", "false")
    get_settings.cache_clear()
    instance = HardwareRuntime()
    for _ in range(25):
        instance._tick_motion()
    yield instance
    get_settings.cache_clear()


def test_controller_levitates_below_lower_bound_and_loads_above(runtime: HardwareRuntime) -> None:
    from app.services.motion.controller import ControlMode

    runtime.start_motion(
        calibration_id=None,
        lower_bound_mm=700,
        upper_bound_mm=1000,
        target_set=1,
        target_reps=50,
        motion_profile="training",
        load_kg=30,
        auto_user=True,
    )
    for _ in range(1500):
        runtime._tick_motion()
        if runtime.controller.state.mode == ControlMode.training:
            break
    controller = runtime.controller
    assert controller.state.mode == ControlMode.training

    runtime.emulator.reset(position_mm=500)
    for _ in range(3):
        runtime._tick_motion()
    command = runtime.last_command.left
    assert controller.state.levitating
    assert command.mode == "torque"
    assert command.force_kg == pytest.approx(command.weight_comp_kg, abs=0.5)  # only the bar weight

    for _ in range(40):
        runtime.emulator.reset(position_mm=900)
        runtime._tick_motion()
    command = runtime.last_command.left
    assert not controller.state.levitating
    assert command.force_kg < command.weight_comp_kg - 3  # exercise load (pulls the bar down) is back


def test_torque_debug_routes_in_sim(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import modbus_debug
    from app.schemas.modbus import ModbusTorqueCommandRequestSchema

    service = _connected_service()
    monkeypatch.setattr(modbus_debug, "modbus_service", service)
    assert modbus_debug.initialize_torque_mode().success
    assert modbus_debug.set_torque_command(ModbusTorqueCommandRequestSchema(slave_id=1, torque_raw=100)).success
    telemetry = modbus_debug.read_torque_telemetry(slave_id=1)
    assert telemetry.command_torque_raw == 100 and telemetry.torque_written_raw == 100
    assert modbus_debug.stop_torque().success
    assert _signed(_reg(service, PA_12C, 1)) == 0
