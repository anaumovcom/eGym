"""State observer per side: α-β filter on position fused with PA_1C1 speed, real dt, delay compensation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObservedState:
    x_mm: float
    v_mm_s: float
    a_mm_s2: float
    t: float
    stale: bool = False
    missed_frames: int = 0


class AlphaBetaObserver:
    def __init__(self, alpha: float = 0.6, beta: float = 0.15, speed_weight: float = 0.7, accel_smoothing: float = 0.3) -> None:
        self.alpha = alpha
        self.beta = beta
        self.speed_weight = speed_weight
        self.accel_smoothing = accel_smoothing
        self.x = 0.0
        self.v = 0.0
        self.a = 0.0
        self.t: float | None = None
        self.missed = 0

    def update(self, position_mm: float, speed_mm_s: float, t: float) -> ObservedState:
        if self.t is None:
            self.x, self.v, self.a, self.t = position_mm, speed_mm_s, 0.0, t
            self.missed = 0
            return self.state()
        dt = max(t - self.t, 1e-4)
        x_pred = self.x + self.v * dt
        v_pred = self.v
        residual = position_mm - x_pred
        x_new = x_pred + self.alpha * residual
        v_ab = v_pred + self.beta * residual / dt
        v_new = self.speed_weight * speed_mm_s + (1 - self.speed_weight) * v_ab
        a_raw = (v_new - self.v) / dt
        self.a += self.accel_smoothing * (a_raw - self.a)
        self.x, self.v, self.t = x_new, v_new, t
        self.missed = 0
        return self.state()

    def miss(self, t: float) -> ObservedState:
        """No frame: extrapolate the position, do not invent acceleration."""

        if self.t is not None:
            dt = max(t - self.t, 0.0)
            self.x += self.v * dt
            self.t = t
        self.missed += 1
        return self.state(stale=True)

    def predict(self, horizon_s: float) -> float:
        """Position ``horizon_s`` ahead: compensates the known bus delay."""

        return self.x + self.v * horizon_s + 0.5 * self.a * horizon_s * horizon_s

    def state(self, stale: bool = False) -> ObservedState:
        return ObservedState(self.x, self.v, self.a, self.t or 0.0, stale, self.missed)
