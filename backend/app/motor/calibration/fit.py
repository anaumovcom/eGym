"""Pure fitting helpers: statistics with ci95, least squares, breakaway detector, limit-cycle analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# two-sided 95 % Student t for n−1 degrees of freedom
_T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26, 10: 2.23}


@dataclass(frozen=True)
class Stat:
    mean: float
    ci95: float
    std: float
    n: int

    @property
    def rel_spread(self) -> float:
        return self.std / abs(self.mean) if self.mean else math.inf


def stat(values: Sequence[float]) -> Stat:
    n = len(values)
    if n == 0:
        raise ValueError("нет данных")
    mean = sum(values) / n
    if n == 1:
        return Stat(mean, math.inf, 0.0, 1)
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    return Stat(mean, _T95.get(n - 1, 1.96) * std / math.sqrt(n), std, n)


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    r2: float


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> LinearFit:
    n = len(xs)
    if n < 2:
        raise ValueError("нужно минимум две точки")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("вырожденные данные")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys, strict=True))
    return LinearFit(slope, intercept, 1 - ss_res / ss_tot if ss_tot else 1.0)


class BreakawayDetector:
    """Motion start: |x − x0| > ``dx_mm`` and v beyond ``v_mm_s`` in ``direction`` for ``frames`` frames."""

    def __init__(self, x0_mm: float, direction: int, dx_mm: float = 0.3, v_mm_s: float = 1.5, frames: int = 3) -> None:
        self.x0 = x0_mm
        self.direction = direction
        self.dx = dx_mm
        self.v = v_mm_s
        self.frames = frames
        self.count = 0

    def update(self, x_mm: float, v_mm_s: float) -> bool:
        moved = self.direction * (x_mm - self.x0) > self.dx and self.direction * v_mm_s > self.v
        self.count = self.count + 1 if moved else 0
        return self.count >= self.frames


@dataclass(frozen=True)
class LimitCycle:
    amplitude_mm: float
    period_s: float
    periods: list[float]
    sample_s: float = 0.0

    @property
    def regular(self) -> bool:
        if len(self.periods) < 4:
            return False
        last = self.periods[-6:]
        mean = sum(last) / len(last)
        # periods are quantised by the sample period and dry friction adds jitter
        return all(abs(p - mean) <= max(0.15 * mean, 2.5 * self.sample_s) for p in last)


def limit_cycle(ts: Sequence[float], xs: Sequence[float], center_mm: float) -> LimitCycle:
    crossings = [ts[i] for i in range(1, len(xs)) if xs[i - 1] < center_mm <= xs[i]]
    periods = [b - a for a, b in zip(crossings, crossings[1:], strict=False)]
    sample = (ts[-1] - ts[0]) / max(len(ts) - 1, 1) if len(ts) > 1 else 0.0
    if not periods:
        return LimitCycle(0.0, 0.0, [], sample)
    start = crossings[1] if len(crossings) > 1 else ts[0]
    window = [x for t, x in zip(ts, xs, strict=True) if t >= start]
    last = periods[-6:]
    return LimitCycle((max(window) - min(window)) / 2, sum(last) / len(last), periods, sample)
