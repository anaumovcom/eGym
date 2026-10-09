"""X2 side coupling through the bar (plan 15 §2.4).

One side is pulled up by a slow force ramp while the other is held in the
middle of its window by dry friction. Once the pulled side creeps, its force
balances friction plus the bar spring: ``F − W − Fc = k·skew``, so the slope
of force over skew is the coupling stiffness ``k``. The ramp stops when the
held side starts to move (coupling > its friction), at the skew limit or at
the force limit; then the held side is pulled up to level the bar.
A stiff bar (skew below ``RESOLUTION_MM``) gives only a lower bound.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from app.motor.calibration.fit import linear_fit
from app.motor.calibration.procedures.motion import Balance, hold_still, land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
RESOLUTION_MM = 0.05
LEVEL_MM = 0.1


def _other(side: Side) -> Side:
    return "right" if side == "left" else "left"


def side_coupling(
    balance: Balance,
    *,
    height_mm: float = 40.0,
    ramp_n_s: float = 3.0,
    max_extra: float = 0.8,
    max_skew_mm: float = 1.5,
) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, height_mm, progress_span=(0.0, 0.1))
    runs: dict[str, dict[str, Any]] = {}
    for index, side in enumerate(SIDES):
        other = _other(side)
        label = "левая" if side == "left" else "правая"
        span = (0.1 + 0.4 * index, 0.1 + 0.4 * (index + 1))
        frame = yield from hold_still(balance, frame, progress=span[0])
        skew0, other0 = frame.x(side) - frame.x(other), frame.x(other)
        start = balance.edge(side, frame.x(side), +1) - 0.2 * balance.coulomb_up[side]
        limit = balance.edge(side, frame.x(side), +1) + max_extra * balance.coulomb_up[side]
        hold_other = balance.weight(other, frame.x(other))
        rows: list[tuple[float, float]] = []
        t0, reason = frame.t, "предел силы"
        at_limit_since: float | None = None
        while True:
            force = min(limit, start + ramp_n_s * (frame.t - t0))
            frame = yield Command({side: force, other: hold_other}, note=f"{label} сторона: сила {force - balance.weight(side, frame.x(side)):+.0f} Н к весу", progress=span[0] + 0.3 * (span[1] - span[0]) * min(1.0, (force - start) / max(limit - start, 1.0)))
            skew = frame.x(side) - frame.x(other) - skew0
            rows.append((force - balance.weight(side, frame.x(side)), skew))
            if abs(frame.x(other) - other0) > 0.3 or abs(frame.v(other)) > 1.0:
                reason = "сдвинулась вторая сторона"
                break
            if skew > max_skew_mm:
                reason = "предел перекоса"
                break
            if force >= limit:
                at_limit_since = at_limit_since if at_limit_since is not None else frame.t
                if frame.t - at_limit_since > 1.0:
                    break
        # level the bar: the pulled side rests in its window, the held side follows up
        t1 = frame.t
        pulled_mid = balance.weight(side, frame.x(side))
        while frame.x(side) - frame.x(other) - skew0 > LEVEL_MM and frame.t - t1 < 15.0:
            catch_up = min(balance.edge(other, frame.x(other), +1) + 0.3 * balance.coulomb_up[other], hold_other + 6.0 * (frame.t - t1))
            frame = yield Command({side: pulled_mid, other: catch_up}, note="выравнивание сторон", progress=span[0] + 0.8 * (span[1] - span[0]))
        frame = yield from hold_still(balance, frame, note="выравнивание сторон", progress=span[1])
        runs[side] = {"rows": rows, "reason": reason}
        if frame.x_mean > height_mm + 30:
            frame = yield from travel(balance, frame, height_mm, progress_span=span[1])
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_coupling(data: dict[str, Any]) -> dict[str, Any]:
    sides: dict[str, dict[str, Any]] = {}
    for side, run in data["runs"].items():
        rows = run["rows"]
        moving = [(f, s) for f, s in rows if s > 0.02]
        skew_range = max((s for _, s in rows), default=0.0)
        if len(moving) >= 5 and skew_range >= RESOLUTION_MM:
            line = linear_fit([s for _, s in moving], [f for f, _ in moving])
            if line.slope <= 0:
                raise ProcedureError(f"{side}: сила не растёт с перекосом — связь не определяется (подклинивание?)")
            sides[side] = {"k_n_per_mm": line.slope, "r2": line.r2, "skew_max_mm": skew_range, "lower_bound": False, "reason": run["reason"], "points": len(moving)}
        else:
            force_range = max((f for f, _ in rows), default=0.0) - min((f for f, _ in rows), default=0.0)
            sides[side] = {"k_n_per_mm": force_range / RESOLUTION_MM, "r2": None, "skew_max_mm": skew_range, "lower_bound": True, "reason": run["reason"], "points": len(moving)}
    values = [item["k_n_per_mm"] for item in sides.values()]
    k = sum(values) / len(values)
    return {
        "k_n_per_mm": k,
        "ci95": abs(values[0] - values[-1]) / 2 if len(values) > 1 else None,
        "lower_bound": any(item["lower_bound"] for item in sides.values()),
        "sides": sides,
    }
