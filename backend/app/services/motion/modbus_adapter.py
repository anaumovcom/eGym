"""Real-hardware adapter: two Lichuan A6 drives in Torque Mode over Modbus RTU.

Runtime control is one signed register per drive, PA_12C (0.1 % of rated
torque).  ``TorqueController`` turns the motion controller's per-side commands
(kg-equivalent force, bar weight share, exercise load) into PA_12C values;
this adapter only does I/O, telemetry mapping and fail-safe behaviour:

* PA_000 / PA_002 / PA_090 are never written, no EEPROM saves at runtime.
* Stop means PA_12C = 0 (the servo stays enabled, no Servo OFF).
* Monitoring: PA_1BC/1BD position, PA_1C1 speed, PA_1C3 command torque,
  PA_1C4 feedback torque, PA_1C9 alarm (PA_1DB/1DE in the debug telemetry).
* Overspeed: the warning level reduces the exercise torque working along the
  movement, the alarm level writes PA_12C = 0 and reports a drive fault.
"""

from __future__ import annotations

import time
from typing import Any

from app.services.modbus_service import ModbusService, modbus_service
from app.services.motion.adapter import (
    SIDES,
    AdapterTelemetry,
    DriveCommand,
    SelfTestResult,
    Side,
    SideTelemetry,
)
from app.services.motion.parameters import MotionParameters
from app.services.motion.torque import SideInput, TorqueController, TorqueOutput, TorqueSettings

_WRITE_DEADBAND_RAW = 3  # do not rewrite PA_12C for changes below 0.3 %
_WRITE_REFRESH_S = 0.25  # but refresh the reference at least this often
_VELOCITY_FILTER = 0.5
_COMM_RETRY_S = 0.5  # after a bus failure do not hammer the lock/bus every control tick


class ModbusDriveAdapter:
    name = "modbus-torque"

    def __init__(
        self,
        left_address: int = 1,
        right_address: int = 2,
        *,
        parameters: MotionParameters | None = None,
        service: ModbusService | None = None,
    ) -> None:
        self.addresses: dict[Side, int] = {"left": left_address, "right": right_address}
        self.parameters = parameters or MotionParameters()
        self.service = service or modbus_service
        self.torque = TorqueController(TorqueSettings.from_parameters(self.parameters))
        self.last_output = TorqueOutput()
        self.last_raw: dict[Side, dict[str, Any]] = {"left": {}, "right": {}}
        self._written: dict[Side, int | None] = {"left": None, "right": None}
        self._written_at: dict[Side, float] = {"left": 0.0, "right": 0.0}
        self._prev_position: dict[Side, float | None] = {"left": None, "right": None}
        self._prev_time: dict[Side, float] = {"left": 0.0, "right": 0.0}
        self._velocity: dict[Side, float] = {"left": 0.0, "right": 0.0}
        self._homed = False
        self._applied_limits: tuple[int, int] | None = None
        self._estop = False
        self._heartbeat = True
        self._comm_retry_at = 0.0
        self._last = self._unavailable("Modbus не подключён")

    # ------------------------------------------------------------ telemetry
    def _side_unavailable(self, side: Side, code: str, message: str) -> SideTelemetry:
        return SideTelemetry(side, connected=False, homed=False, error_code=code, error_message=message)

    def _unavailable(self, message: str, code: str = "E-MODBUS-OFFLINE") -> AdapterTelemetry:
        return AdapterTelemetry(
            timestamp=time.monotonic(),
            left=self._side_unavailable("left", code, message),
            right=self._side_unavailable("right", code, message),
            power_ok=False,
            heartbeat_ok=False,
        )

    def _inverted(self, side: Side) -> bool:
        return self.torque.settings.left_inverted if side == "left" else self.torque.settings.right_inverted

    def _velocity_from_position(self, side: Side, position_mm: float, now: float) -> float:
        previous = self._prev_position[side]
        elapsed = now - self._prev_time[side]
        if previous is not None and elapsed > 0.002:
            raw = (position_mm - previous) / elapsed
            self._velocity[side] += _VELOCITY_FILTER * (raw - self._velocity[side])
        self._prev_position[side] = position_mm
        self._prev_time[side] = now
        return self._velocity[side]

    def _read_side(self, side: Side, now: float) -> tuple[SideTelemetry, SideInput | None]:
        raw = self.service.read_torque_telemetry(self.addresses[side], log=False)
        self.last_raw[side] = raw
        if raw.get("error"):
            return self._side_unavailable(side, "E-MODBUS-COMM", str(raw["error"])), None
        alarm = int(raw["alarm"] or 0)  # type: ignore[arg-type]
        if alarm:
            return self._side_unavailable(side, f"E-DRIVE-{alarm:04X}", f"Авария привода PA_1C9={alarm}"), None
        position = raw.get("position_mm")
        position_mm = float(position) if position is not None else 0.0  # type: ignore[arg-type]
        velocity = self._velocity_from_position(side, position_mm, now)
        sign = -1.0 if self._inverted(side) else 1.0
        per_kg = max(self.torque.settings.per_kg_raw, 1e-6)
        force_kg = float(raw["feedback_torque_raw"] or 0) * sign / per_kg  # type: ignore[arg-type]
        telemetry = SideTelemetry(
            side,
            connected=True,
            homed=self._homed and position is not None,
            brake_engaged=False,
            position_mm=position_mm,
            velocity_mm_s=velocity,
            force_kg=force_kg,
            torque_limit_percent=int(min(100, max(0, round(float(raw.get("torque_limit_raw") or 0) / 10)))),  # type: ignore[arg-type]
            firmware_version="a6-torque",
        )
        return telemetry, SideInput(
            position_mm=position_mm,
            velocity_mm_s=velocity,
            speed_rpm=abs(float(raw["feedback_speed_rpm"] or 0)),  # type: ignore[arg-type]
            limits_known=self._homed and position is not None,
        )

    # ----------------------------------------------------------------- step
    def step(self, command: DriveCommand, dt: float) -> AdapterTelemetry:
        now = time.monotonic()
        self.torque.settings = TorqueSettings.from_parameters(self.parameters)
        if not self.service.get_status().connected:
            self._written = {"left": None, "right": None}
            self.torque.stop()
            self._last = self._unavailable("Modbus не подключён")
            return self._last
        not_ready = [side for side in SIDES if not self.service.torque_ready(self.addresses[side])]
        if not_ready:
            self.torque.stop()
            message = "Torque Mode не инициализирован (PA_002=2, PA_093=0, PA_12C=0 не подтверждены)"
            self._last = self._unavailable(message, "E-TORQUE-NOT-READY")
            return self._last
        if now < self._comm_retry_at:
            return self._last
        limit_error = self._apply_drive_limits()
        if limit_error:
            self.torque.stop()
            self._last = self._unavailable(limit_error, "E-MODBUS-WRITE")
            return self._last

        telemetry: dict[Side, SideTelemetry] = {}
        inputs: dict[Side, SideInput] = {}
        for side in SIDES:
            side_telemetry, side_input = self._read_side(side, now)
            telemetry[side] = side_telemetry
            if side_input is not None:
                inputs[side] = side_input

        if len(inputs) < len(SIDES):
            self.torque.stop()
            self._comm_retry_at = time.monotonic() + _COMM_RETRY_S
            if not self.service.manual_torque_active():
                self._write_zero_both()
            self._last = AdapterTelemetry(now, telemetry["left"], telemetry["right"], power_ok=False, heartbeat_ok=False)
            return self._last

        if self.service.manual_torque_active():
            # debug panel owns PA_12C: keep monitoring, write nothing, rewrite on resume
            self.torque.stop()
            self._written = {"left": None, "right": None}
            self._last = AdapterTelemetry(now, telemetry["left"], telemetry["right"], power_ok=True, heartbeat_ok=True)
            return self._last

        if self._estop:
            output = TorqueOutput()
            self.torque.stop()
        else:
            output = self.torque.compute(command, inputs, dt)
        self.last_output = output
        if output.alarm is not None:
            self._write_zero_both()
            for side in SIDES:
                telemetry[side] = self._side_unavailable(side, "E-OVERSPEED", f"Превышена скорость привода ({output.alarm}); PA_12C=0")
        else:
            for side in SIDES:
                error = self._write_torque(side, output.command(side), now)
                if error:
                    telemetry[side] = self._side_unavailable(side, "E-MODBUS-WRITE", error)
        self._heartbeat = not self._heartbeat
        healthy = all(item.connected for item in telemetry.values())
        self._last = AdapterTelemetry(now, telemetry["left"], telemetry["right"], power_ok=healthy, heartbeat_ok=healthy)
        return self._last

    def _apply_drive_limits(self) -> str | None:
        """PA_05E / PA_056 follow the parameters; written only when they change (runtime, no EEPROM)."""

        settings = self.torque.settings
        limits = (settings.max_command_raw, settings.speed_limit_rpm)
        if limits == self._applied_limits:
            return None
        for side in SIDES:
            address = self.addresses[side]
            error = self.service.set_torque_limit(address, limits[0]) or self.service.set_speed_limit_rpm(address, limits[1])
            if error:
                return error
        self._applied_limits = limits
        return None

    def _write_torque(self, side: Side, value: int, now: float) -> str | None:
        previous = self._written[side]
        if previous is not None and now - self._written_at[side] < _WRITE_REFRESH_S:
            if value == previous:
                return None
            if value != 0 and abs(value - previous) < _WRITE_DEADBAND_RAW:
                return None  # a stop (0) is always written immediately
        error = self.service.set_torque_command(self.addresses[side], value, log=False)
        if error:
            self._written[side] = None
            return error
        self._written[side] = value
        self._written_at[side] = now
        return None

    def _write_zero_both(self) -> None:
        for side in SIDES:
            if self.service.stop_torque(self.addresses[side]) is None:
                self._written[side] = 0
                self._written_at[side] = time.monotonic()

    def read(self) -> AdapterTelemetry:
        return self._last

    # ------------------------------------------------------------- commands
    def emergency_stop(self) -> None:
        """PA_12C = 0 on both drives and block further references until released."""

        self._estop = True
        self.service.end_manual_torque()
        self.torque.stop()
        self._write_zero_both()

    def release_emergency_stop(self) -> None:
        self._estop = False
        self.torque.stop()

    def set_brake(self, engaged: bool) -> None:
        # No separate brake line in Torque Mode: "engaged" means no torque reference.
        if engaged:
            self.torque.stop()
            self._write_zero_both()

    def home(self) -> None:
        """Establish the software zero of both encoders at the current bar position."""

        positions = self.service.capture_zero()
        if positions.left.current_pulses is None or positions.right.current_pulses is None or not positions.zeroed:
            raise RuntimeError(positions.error or "Не удалось зафиксировать нулевую позицию энкодеров")
        self._homed = True
        for side in SIDES:
            self._prev_position[side] = None
            self._velocity[side] = 0.0

    def self_test(self) -> list[SelfTestResult]:
        results: list[SelfTestResult] = []
        connected = self.service.get_status().connected
        for side in SIDES:
            address = self.addresses[side]
            if not connected:
                results.append(SelfTestResult(f"control-{side}", f"Управление моментом: {side}", False, "Modbus не подключён", "critical"))
                continue
            if not self.service.torque_ready(address):
                results.append(SelfTestResult(
                    f"control-{side}", f"Управление моментом: {side}", False,
                    "Torque Mode не инициализирован (проверьте PA_002=2, аварии и связь)", "critical",
                ))
                continue
            raw = self.service.read_torque_telemetry(address)
            if raw.get("error"):
                results.append(SelfTestResult(f"control-{side}", f"Управление моментом: {side}", False, str(raw["error"]), "critical"))
            elif raw.get("alarm"):
                results.append(SelfTestResult(f"control-{side}", f"Управление моментом: {side}", False, f"Авария привода PA_1C9={raw['alarm']}", "critical"))
            else:
                results.append(SelfTestResult(f"control-{side}", f"Управление моментом: {side}", True, "PA_002=2, PA_12C=0, мониторинг PA_1BC..PA_1C9 читается", "critical"))
        return results

    def reset_errors(self) -> None:
        """Clear the software overspeed latch and re-verify Torque Mode (PA_12C=0)."""

        self.torque.reset()
        self._estop = False
        self._written = {"left": None, "right": None}
        self._applied_limits = None
        if self.service.get_status().connected:
            settings = TorqueSettings.from_parameters(self.parameters)
            self.service.initialize_torque_mode(torque_limit=settings.max_command_raw, speed_limit_rpm=settings.speed_limit_rpm)
            self._applied_limits = (settings.max_command_raw, settings.speed_limit_rpm)
