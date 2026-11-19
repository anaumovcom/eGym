"""Рабочая зона в середине подтверждённого хода (``options.workingZone='middle'``).

Измерительный участок отделён от подъезда с упоров и посадки. Выбранные
процедуры используют одни границы для предварительной проверки и движения.
"""

from __future__ import annotations

import math

from app.motor.profile import MachineProfile, SafetyEnvelope
from app.motor.units import SIDES

# TRAVEL_MARGIN_MM и TOP_GUARD_MM повторяют parameters.TRAVEL_MARGIN_MM и запас
# CalibrationSession._top_mm(), чтобы средняя зона не выходила за штатную огибающую.
TRAVEL_MARGIN_MM = 20.0
TOP_GUARD_MM = 80.0
STROKE_MIN_MM = 300.0
STROKE_MAX_MM = 400.0
D4_HIGH_MM = 700.0

OBSERVER_STROKES_MM = {"V1": 200.0, "V2": 200.0, "V3": 170.0}
REQUIRED_MIDDLE = ("G4", "H3")
MIDDLE_CODES = ("D2", "D4", "F3", "G3", "P1", "P2", "X3", *REQUIRED_MIDDLE, *OBSERVER_STROKES_MM)


def confirmed_bounds(profile: MachineProfile, safety: SafetyEnvelope) -> tuple[float, float, float]:
    """Measured travel and usable measurement bounds after the end-stop margins."""
    for side in SIDES:
        zero = profile.side(side).zero_counts
        if zero.provenance != "measured" or zero.value is None:
            raise ValueError(f"Средняя зона: абсолютный ноль стороны {side} не измерен — запустите B7")

    travel_item = profile.travel_mm
    if travel_item.provenance != "measured" or travel_item.value is None:
        raise ValueError("Средняя зона: рабочий ход не измерен — запустите B8")
    travel = float(travel_item.value)

    for side in SIDES:
        support = profile.side(side).support_raw
        if support.provenance != "measured" or support.value is None:
            raise ValueError(f"Средняя зона: поддержка стороны {side} не измерена — запустите C3")

    soft_min = float(safety.soft_min_mm)
    soft_max = float(safety.soft_max_mm)
    if not (math.isfinite(travel) and math.isfinite(soft_min) and math.isfinite(soft_max)):
        raise ValueError("Средняя зона: рабочий ход и программные пределы должны быть конечными")
    if soft_min < 0.0:
        raise ValueError("Средняя зона: нижний программный предел не может быть отрицательным")
    if soft_max <= soft_min:
        raise ValueError("Средняя зона: верхний программный предел должен быть выше нижнего")
    if soft_max > travel - TRAVEL_MARGIN_MM:
        raise ValueError(
            f"Средняя зона: верхний программный предел {soft_max:.0f} мм должен быть ниже рабочего хода "
            f"{travel:.0f} мм минимум на {TRAVEL_MARGIN_MM:.0f} мм"
        )

    return travel, soft_min, min(travel - TRAVEL_MARGIN_MM, soft_max) - TOP_GUARD_MM


def middle_window(code: str, profile: MachineProfile, safety: SafetyEnvelope) -> tuple[float, float]:
    if code not in MIDDLE_CODES:
        raise ValueError("Для этой процедуры предусмотрен собственный участок хода")
    travel, low_bound, high_bound = confirmed_bounds(profile, safety)
    if code == "D4":
        high_bound = min(high_bound, D4_HIGH_MM)

    available = high_bound - low_bound
    local_strokes = {**OBSERVER_STROKES_MM, "H3": 100.0, "X3": 120.0}
    required = local_strokes.get(code, STROKE_MIN_MM)
    if available < required:
        raise ValueError(
            f"Средняя зона: доступно {available:.0f} мм между пределами {low_bound:.0f}…{high_bound:.0f} мм, "
            f"нужно не менее {required:.0f} мм"
        )

    stroke = local_strokes.get(code, min(STROKE_MAX_MM, available))
    center = min(max(travel / 2.0, low_bound + stroke / 2.0), high_bound - stroke / 2.0)
    return center - stroke / 2.0, center + stroke / 2.0


__all__ = ["D4_HIGH_MM", "MIDDLE_CODES", "STROKE_MAX_MM", "STROKE_MIN_MM", "middle_window"]
