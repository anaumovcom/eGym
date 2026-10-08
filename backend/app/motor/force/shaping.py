"""Virtual spring (HOLD/FIXED/ISOMETRIC), descent/overspeed governor, side sync, output shaping."""

from __future__ import annotations

from app.motor.units import clamp


def virtual_spring(x_mm: float, v_mm_s: float, target_mm: float, k_n_per_mm: float, c_n_per_mm_s: float, limit_n: float) -> float:
    return clamp(k_n_per_mm * (target_mm - x_mm) - c_n_per_mm_s * v_mm_s, -limit_n, limit_n)


def governor(v_mm_s: float, max_speed_mm_s: float, max_descent_mm_s: float, gain_n_per_mm_s: float = 0.5, onset: float = 0.7) -> float:
    """"Viscous wall" above ``onset``·limit in both directions: resists, never pushes.

    The gain is small on purpose: with 60 kg reflected mass and 1–3 ticks of bus
    delay a stiff velocity loop oscillates. Descent is mainly bounded by load relief
    (``MotorCore``), which does not depend on loop gain.
    """

    if v_mm_s > onset * max_speed_mm_s:
        return -gain_n_per_mm_s * (v_mm_s - onset * max_speed_mm_s)
    if v_mm_s < -onset * max_descent_mm_s:
        return gain_n_per_mm_s * (-v_mm_s - onset * max_descent_mm_s)
    return 0.0


def side_sync(x_side_mm: float, x_other_mm: float, k_n_per_mm: float, max_n: float) -> float:
    """Pull this side towards the mean of both sides."""

    return clamp(-k_n_per_mm * (x_side_mm - x_other_mm) / 2, -max_n, max_n)


def rate_limit(previous_n: float, target_n: float, max_rate_n_per_s: float, dt: float) -> float:
    step = max_rate_n_per_s * dt
    return previous_n + clamp(target_n - previous_n, -step, step)
