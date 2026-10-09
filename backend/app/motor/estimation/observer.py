"""State observer per side: α-β filter on position fused with PA_1C1 speed, real dt, delay compensation."""

from __future__ import annotations

from dataclasses import dataclass

from app.motor.profile import MachineProfile, Measured


@dataclass(frozen=True)
class ObservedState:
    x_mm: float
    v_mm_s: float
    a_mm_s2: float
    t: float
    stale: bool = False
    missed_frames: int = 0


class AlphaBetaObserver:
    def __init__(
        self,
        alpha: float = 0.6,
        beta: float = 0.15,
        speed_weight: float = 0.7,
        accel_smoothing: float = 0.3,
        *,
        speed_scale: float = 1.0,
        speed_lag_s: float = 0.0,
    ) -> None:
        self.alpha = alpha
        self.beta = beta
        self.speed_weight = speed_weight
        self.accel_smoothing = accel_smoothing
        self.speed_scale = speed_scale if speed_scale > 0 else 1.0
        self.speed_lag_s = max(speed_lag_s, 0.0)  # V1: PA_1C1 lags the encoder by this much
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
        speed = speed_mm_s / self.speed_scale + self.a * self.speed_lag_s  # the register's lag made up by a·τ
        v_new = self.speed_weight * speed + (1 - self.speed_weight) * v_ab
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

    @staticmethod
    def from_profile(profile: MachineProfile, accel_smoothing: float | None = None) -> AlphaBetaObserver:
        """Observer with the V1 speed register correction and the V2 acceleration filter (defaults until measured)."""

        def value(item: Measured, default: float) -> float:
            return float(item.value) if item.value is not None else default

        lag = value(profile.speed_lag_s, 0.0)
        period = value(profile.loop_period_s, 0.04)
        # a register lagging by more than half a frame is trusted less than the encoder
        speed_weight = 0.7 if lag <= 0.5 * period else max(0.3, 0.35 * period / lag)
        smoothing = accel_smoothing if accel_smoothing is not None else value(profile.accel_smoothing, 0.3)
        return AlphaBetaObserver(speed_weight=speed_weight, accel_smoothing=smoothing, speed_scale=value(profile.speed_scale, 1.0), speed_lag_s=lag)

    def state(self, stale: bool = False) -> ObservedState:
        return ObservedState(self.x, self.v, self.a, self.t or 0.0, stale, self.missed)
