from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace


@dataclass
class FakeModbusService:
    """Stand-in for ``modbus_service``: records PA_12C writes, can fail per slave."""

    connected: bool = True
    manual: bool = False
    fail_slaves: set[int] = field(default_factory=set)
    read_fail_slaves: set[int] = field(default_factory=set)
    writes: list[tuple[int, int]] = field(default_factory=list)
    speed_rpm: dict[int, int] = field(default_factory=dict)
    alarm: dict[int, int] = field(default_factory=dict)
    servo: dict[int, bool] = field(default_factory=lambda: {1: False, 2: False})
    servo_fail_slaves: set[int] = field(default_factory=set)
    servo_calls: list[tuple[int, bool, int]] = field(default_factory=list)
    left_zero_pulses: int | None = None
    right_zero_pulses: int | None = None
    counts: dict[int, int] = field(default_factory=dict)  # raw absolute encoder counts per slave
    recovery_attempts: int = 0
    connection_requested: bool = True

    def request_connection(self, params) -> None:
        self.connection_requested = True

    def auto_servo_allowed(self) -> bool:
        return True

    def check_servo_pair(self) -> bool:
        return all(self.servo.values())

    def recover_pair(self, initial_commands: dict[int, int], torque_limit: int, speed_limit_rpm: int) -> list[str]:
        self.recovery_attempts += 1
        if not self.connection_requested:
            return ["Modbus отключён оператором"]
        self.connected = 1 not in self.read_fail_slaves
        errors = [f"ID{slave}: нет связи" for slave in sorted(self.read_fail_slaves)]
        errors += [f"ID{slave}: авария {code}" for slave, code in self.alarm.items() if code]
        return errors

    def get_status(self) -> SimpleNamespace:
        return SimpleNamespace(connected=self.connected)

    def set_session_zero(self, left_pulses: int, right_pulses: int) -> None:
        self.left_zero_pulses, self.right_zero_pulses = left_pulses, right_pulses

    def capture_zero(self) -> SimpleNamespace:
        self.left_zero_pulses, self.right_zero_pulses = self.counts.get(1, 0), self.counts.get(2, 0)
        return SimpleNamespace(error=None, left_zero_pulses=self.left_zero_pulses, right_zero_pulses=self.right_zero_pulses)

    def read_torque_telemetry(self, slave_id: int, *, extended: bool = False, log: bool = True) -> dict[str, object]:
        if not self.connected:
            return {"error": "Modbus не подключён"}
        if slave_id in self.read_fail_slaves:
            return {"error": "timeout"}
        return {
            "position_mm": 0.0,
            "feedback_speed_rpm": self.speed_rpm.get(slave_id, 0),
            "feedback_torque_raw": 100,
            "alarm": self.alarm.get(slave_id, 0),
            "error": None,
        }

    def set_torque_command(self, slave_id: int, torque_raw: int, *, log: bool = True) -> str | None:
        if slave_id in self.fail_slaves:
            return "write failed"
        self.writes.append((slave_id, torque_raw))
        return None

    def manual_torque_active(self) -> bool:
        return self.manual

    def end_manual_torque(self) -> None:
        self.manual = False

    def initialize_torque_mode(self, **_kwargs: object) -> list[str]:
        return []

    def servo_state(self, slave_id: int) -> bool | None:
        return self.servo.get(slave_id) if self.connected else None

    def set_servo(self, slave_id: int, on: bool) -> str | None:
        # (slave, on, PA_12C writes so far) – lets tests check support preceded SRV-ON
        self.servo_calls.append((slave_id, on, len(self.writes)))
        if on and slave_id in self.servo_fail_slaves:
            return "PA_1A4: timeout"
        self.servo[slave_id] = on
        return None
