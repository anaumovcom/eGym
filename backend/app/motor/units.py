"""Units and passport constants. Internal units: N, mm, mm/s, s. kgf only at the API edge."""

from __future__ import annotations

import math
from typing import Literal

Side = Literal["left", "right"]
SIDES: tuple[Side, Side] = ("left", "right")

G = 9.80665  # m/s², N per kgf

# Passport (plan 14 §2.8): LCMT-10LR17NB-90M04025B, LCDA6-10B2R17, ball screw 3232
RATED_TORQUE_NM = 4.0
SCREW_LEAD_MM = 32.0
ENCODER_BITS = 17
SCREW_EFFICIENCY = 0.9
RAW_PER_RATED = 1000  # PA_12C unit = 0.1 % of rated torque
MAX_RAW_ABSOLUTE = 3000  # PA_05E upper bound (≈ 3·T_rated)


def kgf_to_n(kgf: float) -> float:
    return kgf * G


def n_to_kgf(newton: float) -> float:
    return newton / G


def passport_n_per_raw(efficiency: float = SCREW_EFFICIENCY, lead_mm: float = SCREW_LEAD_MM) -> float:
    """Linear force for one PA_12C unit: 0.001·T_rated·2π/p·η ≈ 0.71 N."""

    return RATED_TORQUE_NM / RAW_PER_RATED * 2 * math.pi / (lead_mm / 1000) * efficiency


def passport_mm_per_pulse(lead_mm: float = SCREW_LEAD_MM, bits: int = ENCODER_BITS) -> float:
    return lead_mm / (1 << bits)


def rpm_to_mm_s(rpm: float, lead_mm: float = SCREW_LEAD_MM) -> float:
    return rpm * lead_mm / 60.0


def mm_s_to_rpm(speed_mm_s: float, lead_mm: float = SCREW_LEAD_MM) -> float:
    return speed_mm_s * 60.0 / lead_mm


def force_to_raw(force_n: float, n_per_raw: float, direction_sign: int) -> int:
    """The single N → PA_12C conversion (rounded, sign = motor direction)."""

    return int(round(force_n / n_per_raw)) * direction_sign


def raw_to_force(raw: float, n_per_raw: float, direction_sign: int) -> float:
    return raw * direction_sign * n_per_raw


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def smooth_sign(value: float, width: float) -> float:
    """Continuous sign: tanh-like transition of half-width ``width``."""

    if width <= 0:
        return (value > 0) - (value < 0)
    return math.tanh(value / width)
