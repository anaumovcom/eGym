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
SCREW_LENGTH_MM = 1800.0
SCREW_DIAMETER_MM = 32.0
STEEL_DENSITY_KG_M3 = 7850.0
ROTOR_INERTIA_KG_M2 = 2.6e-4  # 1 kW, 90 mm flange (catalogue class value)
BAR_AND_CARRIAGES_KG = 40.0  # the bar with both carriages, split between the sides


def passport_moving_mass_kg() -> float:
    """Reflected mass per side: screw (solid cylinder) + rotor through (2π/p)² + half the bar ≈ 86 kg."""

    radius = SCREW_DIAMETER_MM / 2000
    screw = 0.5 * STEEL_DENSITY_KG_M3 * math.pi * radius**2 * (SCREW_LENGTH_MM / 1000) * radius**2
    ratio = (2 * math.pi / (SCREW_LEAD_MM / 1000)) ** 2
    return (screw + ROTOR_INERTIA_KG_M2) * ratio + BAR_AND_CARRIAGES_KG / 2


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


def force_to_raw(force_n: float, n_per_raw: float, direction_sign: int, pull_scale: float = 1.0) -> int:
    """The single N → PA_12C conversion (rounded, sign = motor direction).

    ``pull_scale`` (N1): the drive's downward force per raw relative to the upward one; a pull is sent larger by 1/scale.
    """

    if force_n < 0 and pull_scale > 0:
        force_n /= pull_scale
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
