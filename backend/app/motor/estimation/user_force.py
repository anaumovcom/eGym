"""User force estimate without a load cell (plan 14 §4.5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.motor.estimation.friction import FrictionModel

Confidence = Literal["moving", "static_interval"]


@dataclass(frozen=True)
class UserForceEstimate:
    value_n: float
    low_n: float
    high_n: float
    confidence: Confidence


def estimate_user_force(
    *,
    motor_force_n: float,
    weight_n: float,
    v_mm_s: float,
    a_mm_s2: float,
    mass_kg: float,
    friction: FrictionModel,
    moving_threshold_mm_s: float = 3.0,
) -> UserForceEstimate:
    """F_user = m·a + W + F_f(v) − F_motor while moving; an interval while static."""

    if abs(v_mm_s) >= moving_threshold_mm_s:
        value = mass_kg * a_mm_s2 / 1000 + weight_n + friction.force(v_mm_s) - motor_force_n
        return UserForceEstimate(value, value, value, "moving")
    base = weight_n - motor_force_n
    low = base - friction.coulomb_down_n - friction.stribeck_extra_n
    high = base + friction.coulomb_up_n + friction.stribeck_extra_n
    return UserForceEstimate(0.0 if low <= 0 <= high else (low if low > 0 else high), low, high, "static_interval")
