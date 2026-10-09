"""Twin bench: plant + drive model (quantisation, PA_05E clamp, deadband, delay) + bus faults.

``TwinDrive`` implements the ``TorqueDrive`` contract with the *believed*
``SideProfile`` (like ``LichuanTorqueDrive``), while the plant uses the true
``PlantParams``: a wrong profile produces wrong forces, as on the real machine.
"""

from __future__ import annotations

import math
import random
from collections import deque
from collections.abc import Callable

from app.motor.drive.protocol import DriveSample
from app.motor.profile import SideProfile
from app.motor.twin.plant import Plant, PlantParams
from app.motor.units import SIDES, Side, clamp, force_to_raw, mm_s_to_rpm, passport_mm_per_pulse, rpm_to_mm_s

UserModel = Callable[[float, "TwinBench"], dict[Side, float]]


class TwinDrive:
    def __init__(self, bench: TwinBench, side: Side, profile: SideProfile) -> None:
        self.bench = bench
        self.side = side
        self.profile = profile
        self.last_raw: int | None = None
        self.fail_writes = False
        self.writes: list[int] = []
        self.servo_on = True

    def read(self) -> DriveSample:
        return self.bench.read(self.side, self.profile)

    def write_raw(self, raw: int) -> str | None:
        if self.fail_writes:
            self.last_raw = None
            return "twin: запись не прошла"
        value = int(clamp(int(raw), -self.bench.params.max_raw, self.bench.params.max_raw))
        self.writes.append(value)
        self.last_raw = value
        self.bench.queue_command(self.side, value)
        return None

    def write_force(self, force_n: float) -> str | None:
        return self.write_raw(force_to_raw(force_n, self.profile.n_per_raw_value, self.profile.sign))

    def support(self) -> str | None:
        return self.write_raw(int(self.profile.support_raw.value) * self.profile.sign)

    def zero(self) -> str | None:
        return self.write_raw(0)

    def set_servo(self, on: bool) -> str | None:
        if self.fail_writes:
            return "twin: запись не прошла"
        self.servo_on = on
        return None

    def servo_state(self) -> bool | None:
        return self.servo_on

    def config_report(self) -> list[dict[str, object]]:
        return [{"register": "twin", "label": "Двойник: регистры пусконаладки не проверяются", "value": None, "ok": True, "detail": None}]


class TwinBench:
    def __init__(
        self,
        params: PlantParams,
        profiles: dict[Side, SideProfile] | None = None,
        *,
        seed: int = 0,
        x0_mm: float = 0.0,
        user: UserModel | None = None,
        initial_raw: int = 0,
    ) -> None:
        self.params = params
        self.plant = Plant(params, x0_mm)
        self.rng = random.Random(seed)
        self.user = user
        self.t = 0.0
        self.alarm: dict[Side, int] = {side: 0 for side in SIDES}
        self._applied_raw: dict[Side, int] = {side: initial_raw for side in SIDES}
        self._pending: dict[Side, deque[tuple[int, int]]] = {side: deque() for side in SIDES}
        self._tick = 0
        self._history: deque[dict[Side, tuple[float, float, float]]] = deque(maxlen=8)
        self._speed_register: dict[Side, float] = {side: 0.0 for side in SIDES}
        default = SideProfile()
        self.drives: dict[Side, TwinDrive] = {side: TwinDrive(self, side, (profiles or {}).get(side, default)) for side in SIDES}

    # ----------------------------------------------------------- drive model
    def queue_command(self, side: Side, raw: int) -> None:
        self._pending[side].append((self._tick + self.params.command_delay_ticks, raw))

    def _true_force(self, side: Side, raw: int) -> float:
        if abs(raw) < self.params.deadband_raw:
            return 0.0
        physics = self.params.side(side)
        return raw * physics.direction_sign * physics.n_per_raw

    def applied_raw(self, side: Side) -> int:
        return self._applied_raw[side]

    def advance(self, dt: float) -> None:
        self._tick += 1
        for side in SIDES:
            queue = self._pending[side]
            while queue and queue[0][0] <= self._tick:
                self._applied_raw[side] = queue.popleft()[1]
        targets = {
            side: 0.0 if self.alarm[side] or not self.drives[side].servo_on else self._true_force(side, self._applied_raw[side])
            for side in SIDES
        }
        user = self.user(self.t, self) if self.user else {}
        self.plant.step(targets, user, dt)
        self.t += dt
        lag = self.params.speed_lag_s
        share = 1.0 if lag <= 0 else 1 - math.exp(-dt / lag)
        for side, s in self.plant.state.items():
            self._speed_register[side] += (s.v_mm_s - self._speed_register[side]) * share
        self._history.append({side: (s.x_mm, self._speed_register[side], s.motor_force_n) for side, s in self.plant.state.items()})

    # ------------------------------------------------------------- bus model
    def read(self, side: Side, profile: SideProfile) -> DriveSample:
        if self.params.drop_probability and self.rng.random() < self.params.drop_probability:
            return DriveSample(side, self.t, ok=False, error="twin: нет ответа")
        delay = min(self.params.read_delay_ticks, len(self._history) - 1)
        if self._history:
            x, v, force = self._history[-1 - delay][side]
        else:
            s = self.plant.state[side]
            x, v, force = s.x_mm, s.v_mm_s, s.motor_force_n
        physics = self.params.side(side)
        # registers as the drive reports them (motor direction), then the believed profile
        reg_position = x * physics.direction_sign + (self.rng.gauss(0, self.params.position_noise_mm) if self.params.position_noise_mm else 0.0)
        reg_rpm = round(mm_s_to_rpm(v * physics.direction_sign))
        reg_torque = round(force * physics.direction_sign / physics.n_per_raw)
        sign = profile.sign
        alarm = self.alarm[side]
        return DriveSample(
            side,
            self.t,
            ok=alarm == 0,
            position_mm=reg_position * sign,
            speed_mm_s=rpm_to_mm_s(reg_rpm) * sign,
            motor_force_n=reg_torque * sign * profile.n_per_raw_value,
            command_raw=self.drives[side].last_raw,
            alarm=alarm,
            error=f"twin alarm {alarm}" if alarm else None,
            counts=self.params.encoder_zero_counts + round(reg_position / passport_mm_per_pulse()),
        )

    def true_state(self, side: Side) -> tuple[float, float]:
        s = self.plant.state[side]
        return s.x_mm, s.v_mm_s
