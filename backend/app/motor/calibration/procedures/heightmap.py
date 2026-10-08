"""S7: balance and dry friction at several heights → W(x) map (plan 15 §2.2)."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import Any

from app.motor.calibration.fit import Stat, linear_fit, stat
from app.motor.calibration.procedures.motion import Balance, land, travel
from app.motor.calibration.procedures.statics import fit_balance, measure_window
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]


def map_heights(bottom_mm: float, top_mm: float, count: int = 5) -> list[float]:
    if top_mm <= bottom_mm + 50:
        raise ValueError("ход слишком мал для карты по высоте")
    return [round(bottom_mm + (top_mm - bottom_mm) * i / (count - 1), 1) for i in range(count)]


def height_map(balance: Balance, heights: Sequence[float], *, repeats: int = 2, slow_rate_n_s: float = 6.0, speed_mm_s: float = 30.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    points: list[dict[str, Any]] = []
    span = 1.0 / (len(heights) + 1)
    for index, height in enumerate(heights):
        p0 = index * span
        frame = yield from travel(balance, frame, height, speed_mm_s=speed_mm_s, progress_span=(p0, p0 + 0.3 * span))
        forces = balance.mid(frame)
        frame, data = yield from measure_window(
            forces, frame, repeats=repeats, slow_rate_n_s=slow_rate_n_s, progress_span=(p0 + 0.3 * span, p0 + span), label=f"{height:.0f} мм: ",
        )
        estimate = fit_balance(data)
        for side in SIDES:
            balance.set_point(side, estimate.height_mm, estimate.weight_n[side].mean)  # the next move starts from a better window
        points.append(data)
    frame = yield from land(balance, frame, speed_mm_s=speed_mm_s, progress=1.0 - 0.5 * span)
    return {"points": points}


def fit_height_map(data: dict[str, Any]) -> dict[str, Any]:
    estimates = [fit_balance(point) for point in data["points"]]
    if len(estimates) < 2:
        raise ProcedureError("нужно минимум две высоты")
    result: dict[str, Any] = {"heights_mm": [e.height_mm for e in estimates]}
    for side in SIDES:
        weights = [e.weight_n[side] for e in estimates]
        ups = [value for point in data["points"] for value in _edges(point, side, +1)]
        downs = [value for point in data["points"] for value in _edges(point, side, -1)]
        line = linear_fit([e.height_mm for e in estimates], [w.mean for w in weights])
        result[side] = {
            "map": [(e.height_mm, w.mean) for e, w in zip(estimates, weights, strict=True)],
            "ci95": max(_finite(w) for w in weights),
            "coulomb_up": stat(ups),
            "coulomb_down": stat(downs),
            "slope_n_per_m": line.slope * 1000,
            "max_deviation_n": max(abs(w.mean - (line.slope * e.height_mm + line.intercept)) for e, w in zip(estimates, weights, strict=True)),
        }
    return result


def _edges(point: dict[str, Any], side: Side, direction: int) -> list[float]:
    pairs = list(zip(point["up"][side], point["down"][side], strict=True))
    weight = sum(u + d for u, d in pairs) / (2 * len(pairs))
    return [u - weight for u, _ in pairs] if direction > 0 else [weight - d for _, d in pairs]


def _finite(value: Stat) -> float:
    return value.ci95 if value.ci95 != float("inf") else 0.0
