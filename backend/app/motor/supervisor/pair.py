"""Compare encoder positions at a common acquisition time on the sequential drive bus."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from app.motor.drive.protocol import DriveSample
from app.motor.units import SIDES, Side


class Timestamped(Protocol):
    @property
    def t(self) -> float: ...


Sample = TypeVar("Sample", bound=Timestamped)


def aligned_difference(samples: dict[Side, Sample], previous: dict[Side, Sample], stale_s: float,
                       value: Callable[[Sample], float]) -> float | None:
    """Left minus right at the earlier timestamp, interpolating only between observed frames."""
    left, right = samples["left"], samples["right"]
    if left.t == right.t:
        return value(left) - value(right)
    later: Side = "right" if left.t < right.t else "left"
    earlier = left if later == "right" else right
    end, start = samples[later], previous.get(later)
    if start is None or not start.t <= earlier.t < end.t or end.t - start.t > stale_s:
        return None
    fraction = (earlier.t - start.t) / (end.t - start.t)
    interpolated = value(start) + fraction * (value(end) - value(start))
    return value(earlier) - interpolated if later == "right" else interpolated - value(earlier)


@dataclass(frozen=True)
class MotionFault:
    code: str
    message: str


class PairMonitor:
    def __init__(self) -> None:
        self.previous: dict[Side, DriveSample] = {}
        self.delta_mm: float | None = None
        self._critical_sign = 0
        self._unaligned_since: float | None = None

    def check(self, samples: dict[Side, DriveSample], now: float, stale_s: float, critical_mm: float | None) -> MotionFault | None:
        self.delta_mm = None
        for side in SIDES:
            s = samples.get(side)
            label = "Левая каретка" if side == "left" else "Правая каретка"
            if s is None or not s.ok or s.alarm:
                cause = s.error if s else None
                if not cause and s and s.alarm:
                    cause = f"авария привода {s.alarm}"
                return MotionFault("drive", f"{label} · {cause or 'нет данных привода'}")
            if not all(math.isfinite(v) for v in (s.t, s.position_mm, s.speed_mm_s, s.motor_force_n)):
                return MotionFault("telemetry", f"{label} · некорректное значение телеметрии")
            if not 0 <= now - s.t <= stale_s or (side in self.previous and s.t <= self.previous[side].t):
                return MotionFault("telemetry", f"{label} · нет свежего кадра энкодера")

        # Interpolate the later-read side between two actual encoder samples. Comparing raw
        # heights from different instants can look like a tilt even on a perfectly level fast bar.
        self.delta_mm = aligned_difference(samples, self.previous, stale_s, lambda s: s.position_mm)
        self.previous = samples.copy()
        if self.delta_mm is not None:
            self._unaligned_since = None
        elif critical_mm is not None:
            if self._unaligned_since is None:
                self._unaligned_since = now
            elif now - self._unaligned_since >= stale_s:
                return MotionFault("telemetry", "Невозможно совместить кадры энкодеров по времени. Проверьте цикл шины B1.")
        if self.delta_mm is None or critical_mm is None or abs(self.delta_mm) < critical_mm:
            self._critical_sign = 0
            return None
        sign = 1 if self.delta_mm > 0 else -1
        confirmed = sign == self._critical_sign or abs(self.delta_mm) >= 2 * critical_mm
        self._critical_sign = sign
        if confirmed:
            higher = "левая выше правой" if sign > 0 else "правая выше левой"
            return MotionFault("skew", f"Перекос · {higher} на {abs(self.delta_mm):.1f} мм при пороге {critical_mm:g} мм. Проверьте ноль B7 и направляющие.")
        return None
