"""Exercise load models: pure functions (phase, x) → L, N per side (plan 14 §4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.motor.units import clamp

LoadMode = Literal["constant", "assist_up", "eccentric", "curve", "bodyweight"]
Phase = Literal["up", "down", "still"]


@dataclass(frozen=True)
class LoadSetpoint:
    mode: LoadMode = "constant"
    load_n: float = 0.0  # per side
    alpha: float = 0.7  # assist_up: share on the way up
    beta: float = 1.2  # eccentric: share on the way down
    lower_mm: float = 0.0
    upper_mm: float = 1000.0
    curve_start: float = 1.0  # curve: multiplier at lower → upper (band/chain > 1 at top)
    curve_end: float = 1.0


def phase_multiplier(setpoint: LoadSetpoint, phase: Phase) -> float:
    if setpoint.mode == "assist_up":
        return setpoint.alpha if phase == "up" else 1.0
    if setpoint.mode == "eccentric":
        return setpoint.beta if phase == "down" else 1.0
    return 1.0


def position_multiplier(setpoint: LoadSetpoint, x_mm: float) -> float:
    if setpoint.mode != "curve" or setpoint.upper_mm <= setpoint.lower_mm:
        return 1.0
    u = clamp((x_mm - setpoint.lower_mm) / (setpoint.upper_mm - setpoint.lower_mm), 0.0, 1.0)
    return setpoint.curve_start + (setpoint.curve_end - setpoint.curve_start) * u


def load_force(setpoint: LoadSetpoint, x_mm: float, phase_blend: float) -> float:
    """``phase_blend`` ∈ [0, 1]: 0 = up multiplier, 1 = down multiplier (S-curve in time)."""

    up = phase_multiplier(setpoint, "up")
    down = phase_multiplier(setpoint, "down")
    return setpoint.load_n * (up + (down - up) * phase_blend) * position_multiplier(setpoint, x_mm)


class PhaseTracker:
    """Phase by velocity with hysteresis and a smooth (smoothstep in time) multiplier transition."""

    def __init__(self, hysteresis_mm_s: float, blend_s: float) -> None:
        self.hysteresis = hysteresis_mm_s
        self.blend_s = max(blend_s, 1e-6)
        self.phase: Phase = "still"
        self.blend = 0.0  # 0 = up, 1 = down
        self._target = 0.0

    def update(self, v_mm_s: float, dt: float) -> tuple[Phase, float]:
        if v_mm_s > self.hysteresis:
            self.phase, self._target = "up", 0.0
        elif v_mm_s < -self.hysteresis:
            self.phase, self._target = "down", 1.0
        step = dt / self.blend_s
        self.blend = clamp(self.blend + clamp(self._target - self.blend, -step, step), 0.0, 1.0)
        smooth = self.blend * self.blend * (3 - 2 * self.blend)
        return self.phase, smooth
