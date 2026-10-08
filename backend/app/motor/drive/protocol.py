"""Drive contract: only Torque Mode, one force command per side (plan 14 §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.motor.units import Side


@dataclass(frozen=True)
class DriveSample:
    side: Side
    t: float  # monotonic time of the reply
    ok: bool
    position_mm: float = 0.0
    speed_mm_s: float = 0.0  # from PA_1C1, not differentiated
    motor_force_n: float = 0.0  # from PA_1C4
    command_raw: int | None = None  # last written PA_12C
    alarm: int = 0
    error: str | None = None

    def age(self, now: float) -> float:
        return now - self.t


class TorqueDrive(Protocol):
    side: Side

    def read(self) -> DriveSample: ...

    def write_force(self, force_n: float) -> str | None: ...

    def write_raw(self, raw: int) -> str | None: ...

    def support(self) -> str | None: ...

    def zero(self) -> str | None: ...
