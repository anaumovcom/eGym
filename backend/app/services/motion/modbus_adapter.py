"""Real-hardware adapter skeleton on top of the Modbus RTU layer.

Time-critical loops (side synchronisation, descent speed limiting, spotter)
must eventually live in the drive controller firmware; this adapter only maps
controller targets/limits to registers and reads telemetry back.  Register
addresses below are placeholders for the Lichuan A6 map used by
``modbus_service`` and must be verified against the drive manual.
"""

from __future__ import annotations

import time

from app.services.motion.adapter import (
    SIDES,
    AdapterTelemetry,
    DriveCommand,
    SelfTestResult,
    SideTelemetry,
)


class ModbusDriveAdapter:
    name = "modbus-rtu"

    # TODO(hardware): confirm register map with the drive manual.
    REG_CONTROL_MODE = 0x002  # 0 position / 1 speed / 2 torque
    REG_TARGET_TORQUE = 0x120  # placeholder: torque reference, 0.1 %
    REG_TARGET_SPEED = 0x121  # placeholder: speed reference, rpm
    REG_TARGET_POSITION = 0x122  # placeholder: position reference, pulses
    REG_TORQUE_LIMIT = 0x123  # placeholder: torque limit, 0.1 %
    REG_BRAKE = 0x124  # placeholder: brake output
    REG_HEARTBEAT = 0x125  # placeholder: watchdog register the drive expects to see toggled
    REG_STATUS_POSITION = 0x300  # placeholder: actual position
    REG_STATUS_SPEED = 0x301
    REG_STATUS_CURRENT = 0x302
    REG_STATUS_TEMP = 0x303
    REG_ALARM = 0x200

    def __init__(self, left_address: int = 1, right_address: int = 2) -> None:
        self.addresses = {"left": left_address, "right": right_address}
        self._heartbeat_bit = 0
        self._last = AdapterTelemetry(
            timestamp=time.monotonic(),
            left=SideTelemetry("left", connected=False, homed=False, error_code="E-COMM-02", error_message="адаптер не подключён"),
            right=SideTelemetry("right", connected=False, homed=False, error_code="E-COMM-02", error_message="адаптер не подключён"),
            power_ok=False,
            heartbeat_ok=False,
        )

    def step(self, command: DriveCommand, dt: float) -> AdapterTelemetry:
        # TODO(hardware): write per-side mode/targets/limits, toggle heartbeat register,
        # then read back position/speed/current/temperature/alarms for both sides.
        # Until the register map is verified this adapter reports "not connected"
        # so the controller stays in a safe blocked state.
        del command, dt
        self._heartbeat_bit ^= 1
        self._last.timestamp = time.monotonic()
        return self._last

    def read(self) -> AdapterTelemetry:
        return self._last

    def emergency_stop(self) -> None:
        # TODO(hardware): issue servo-off + brake on both drives.
        return None

    def release_emergency_stop(self) -> None:
        # TODO(hardware): alarm reset + servo-on into position hold.
        return None

    def set_brake(self, engaged: bool) -> None:
        del engaged
        # TODO(hardware): write REG_BRAKE for both sides.
        return None

    def home(self) -> None:
        # TODO(hardware): run drive homing routine and zero position counters.
        return None

    def self_test(self) -> list[SelfTestResult]:
        return [
            SelfTestResult(f"comm-{side}", f"Связь: {side}", False, "Реальный драйвер не реализован", "critical")
            for side in SIDES
        ]

    def reset_errors(self) -> None:
        # TODO(hardware): alarm reset register.
        return None
