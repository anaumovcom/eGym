"""TorqueDrive for Lichuan A6 on top of the existing RS-485 transport (``modbus_service``)."""

from __future__ import annotations

import time
from typing import Any

from app.motor.drive.protocol import DriveSample
from app.motor.drive.registers import PA_TORQUE_COMMAND, PA_VIRTUAL_DI, alarm_text, assert_writable
from app.motor.profile import SideProfile
from app.motor.units import Side, clamp, force_to_raw, raw_to_force, rpm_to_mm_s


class LichuanTorqueDrive:
    def __init__(self, side: Side, slave_id: int, profile: SideProfile, max_raw: int, service: Any) -> None:
        self.side = side
        self.slave_id = slave_id
        self.profile = profile
        self.max_raw = max_raw
        self.service = service
        self.last_raw: int | None = None

    def read(self) -> DriveSample:
        now = time.monotonic()
        data = self.service.read_torque_telemetry(self.slave_id, log=False)
        if data.get("error"):
            return DriveSample(self.side, now, ok=False, error=str(data["error"]))
        alarm = int(data.get("alarm") or 0)
        position = data.get("position_mm")
        counts = data.get("feedback_position")
        sign = self.profile.sign
        sample = DriveSample(
            self.side,
            now,
            ok=alarm == 0 and position is not None,
            position_mm=float(position or 0.0) * sign,
            speed_mm_s=rpm_to_mm_s(float(data.get("feedback_speed_rpm") or 0)) * sign,
            motor_force_n=raw_to_force(float(data.get("feedback_torque_raw") or 0), self.profile.n_per_raw_value, sign),
            command_raw=self.last_raw,
            alarm=alarm,
            error=alarm_text(alarm) if alarm else (None if position is not None else "Ноль энкодера не известен"),
            counts=int(counts) if counts is not None else None,
        )
        return sample

    def write_raw(self, raw: int) -> str | None:
        assert_writable(PA_TORQUE_COMMAND)
        value = int(clamp(raw, -self.max_raw, self.max_raw))
        try:
            error = self.service.set_torque_command(self.slave_id, value, log=False)
        except Exception as exc:  # noqa: BLE001 - a broken drive must not stop the caller
            error = str(exc)
        self.last_raw = None if error else value
        return error

    def write_force(self, force_n: float) -> str | None:
        return self.write_raw(force_to_raw(force_n, self.profile.n_per_raw_value, self.profile.sign))

    def support(self) -> str | None:
        """Upward support against gravity: ``support_raw`` in the motor direction."""

        return self.write_raw(int(self.profile.support_raw.value) * self.profile.sign)

    def zero(self) -> str | None:
        return self.write_raw(0)

    def set_servo(self, on: bool) -> str | None:
        """SRV-ON via virtual DI0 (PA_1A4 bit0)."""

        assert_writable(PA_VIRTUAL_DI)
        try:
            return self.service.set_servo(self.slave_id, on)
        except Exception as exc:  # noqa: BLE001
            return str(exc)

    def servo_state(self) -> bool | None:
        return self.service.servo_state(self.slave_id)

    def config_report(self) -> list[dict[str, Any]]:
        """B0: commissioning registers against the reference (read-only)."""

        return self.service.commissioning_report(self.slave_id)
