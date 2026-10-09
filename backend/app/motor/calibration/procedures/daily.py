"""Q1 daily check (plan 15 §2.9): configuration, zero on the stops, static window against the profile.

Writes nothing. The static window is compared as the sum of both sides: the
split of the weight between the sides is not observable statically (the bar
couples them), the sum is.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from app.motor.calibration.procedures.bus import config_check, fit_config
from app.motor.calibration.procedures.reference import loaded_window
from app.motor.calibration.procedures.statics import fit_balance
from app.motor.calibration.runner import Command, Frame
from app.motor.drive.protocol import TorqueDrive
from app.motor.profile import MachineProfile
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
WEIGHT_WARN, WEIGHT_FAIL = 0.07, 0.15
FRICTION_WARN = 0.25
ZERO_MM, SKEW_MM = 5.0, 3.0


def daily_check(drives: dict[Side, TorqueDrive], start_forces: dict[Side, float]) -> Procedure:
    config = yield from config_check(drives)
    frame = yield Command(None, note="положение на упорах", progress=0.15)
    rest = {side: frame.x(side) for side in SIDES}
    window = yield from loaded_window(start_forces, repeats=2)
    return {"config": config, "rest": rest, "window": window}


def _deviation(measured: float, expected: float) -> float:
    return (measured - expected) / expected if expected else 0.0


def fit_daily(data: dict[str, Any], profile: MachineProfile) -> dict[str, Any]:
    config = fit_config(data["config"])
    rest = data["rest"]
    skew = rest["left"] - rest["right"]
    estimate = fit_balance(data["window"])
    h = estimate.height_mm
    weight = sum(estimate.weight_n[side].mean for side in SIDES)
    up = sum(estimate.coulomb_up_n[side].mean for side in SIDES)
    down = sum(estimate.coulomb_down_n[side].mean for side in SIDES)
    extra = {side: float(profile.side(side).stribeck_extra_n.value or 0.0) for side in SIDES}
    weight_p = sum(profile.side(side).weight_n(h) for side in SIDES)
    up_p = sum(float(profile.side(side).coulomb_up_n.value) + extra[side] for side in SIDES)
    down_p = sum(float(profile.side(side).coulomb_down_n.value) + extra[side] for side in SIDES)
    d_weight, d_up, d_down = _deviation(weight, weight_p), _deviation(up, up_p), _deviation(down, down_p)
    zero_ok = all(abs(x) < ZERO_MM for x in rest.values()) and abs(skew) < SKEW_MM
    failures = [
        *([f"настройки приводов: {'; '.join(config['mismatches'])}"] if not config["ok"] else []),
        *([f"положение на упорах {rest['left']:.1f} / {rest['right']:.1f} мм — ноль энкодера потерян?"] if not zero_ok else []),
        *([f"вес отличается от профиля на {100 * d_weight:+.0f} %"] if abs(d_weight) > WEIGHT_FAIL else []),
    ]
    warnings = [
        *([f"вес отличается от профиля на {100 * d_weight:+.0f} %"] if WEIGHT_WARN < abs(d_weight) <= WEIGHT_FAIL else []),
        *([f"трение вверх отличается на {100 * d_up:+.0f} %"] if abs(d_up) > FRICTION_WARN else []),
        *([f"трение вниз отличается на {100 * d_down:+.0f} %"] if abs(d_down) > FRICTION_WARN else []),
    ]
    return {
        "config": config,
        "rest_mm": rest,
        "skew_mm": skew,
        "zero_ok": zero_ok,
        "height_mm": h,
        "weight_n": weight,
        "weight_profile_n": weight_p,
        "up_n": up,
        "up_profile_n": up_p,
        "down_n": down,
        "down_profile_n": down_p,
        "deviation": {"weight": d_weight, "up": d_up, "down": d_down},
        "failures": failures,
        "warnings": warnings,
        "ok": not failures,
    }
