"""C3: support torque that lowers the bar slowly instead of dropping it (plan 15 §2.6).

From ``start_mm`` the drives get a constant raw command just below the lower
edge of the window, ``floor((W − Fc⁻)/k) − n`` raw, and the descent speed over
the last second of the run (≤ 6 s or down to ``bottom_mm``) is measured. ``n``
is searched by doubling, then bisection, until the speed is within the target
band or the 1-raw resolution is reached. A run faster than ``abort_mm_s`` is
stopped at once (middle of the window). The bar ends on the stops.
"""

from __future__ import annotations

import math
from collections.abc import Generator
from typing import Any

from app.motor.calibration.procedures.motion import Balance, hold_still, land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]


def support_descent(
    balance: Balance,
    n_per_raw: dict[Side, float],
    signs: dict[Side, int],
    *,
    start_mm: float = 120.0,
    bottom_mm: float = 30.0,
    target_mm_s: float = 15.0,
    tolerance_mm_s: float = 5.0,
    abort_mm_s: float = 40.0,
    run_s: float = 6.0,
    max_trials: int = 8,
) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    base = {side: (balance.weight(side, start_mm) - balance.coulomb_down[side]) / n_per_raw[side] for side in SIDES}
    trials: list[dict[str, Any]] = []
    offset, low, high = 0, None, None  # low: too slow, high: too fast
    for trial in range(max_trials):
        progress = 0.05 + 0.85 * trial / max_trials
        if frame.x_mean < start_mm - 15:
            frame = yield from travel(balance, frame, start_mm, speed_mm_s=20.0, progress_span=progress)
        raw = {side: max(0, math.floor(base[side]) - offset) for side in SIDES}
        note = f"опускание поддержкой {raw['left']}/{raw['right']} ед., попытка {trial + 1}"
        x0, t0 = frame.x_mean, frame.t
        track: list[tuple[float, float]] = []
        fast = False
        while True:
            frame = yield Command(raw={side: raw[side] * signs[side] for side in SIDES}, note=note, progress=progress)
            speed = -frame.v_mean
            track.append((frame.t, speed))
            if speed > abort_mm_s:
                fast = True
                break
            if frame.x_mean < bottom_mm or frame.t - t0 > run_s:
                break
        tail = [v for t, v in track if t >= track[-1][0] - 1.0]
        speed = abort_mm_s if fast else max(0.0, sum(tail) / len(tail))
        trials.append({"raw": raw, "offset": offset, "speed_mm_s": speed, "moved_mm": x0 - frame.x_mean, "fast": fast})
        frame = yield from hold_still(balance, frame, progress=progress)
        if abs(speed - target_mm_s) <= tolerance_mm_s:
            break
        if speed > target_mm_s:
            high = offset
        else:
            low = offset
        if low is not None and high is not None:
            if high - low <= 1:
                break
            offset = (low + high) // 2
        elif high is None:
            offset = offset + max(1, abs(offset)) if offset >= 0 else offset // 2
        else:
            offset = offset - max(1, abs(offset)) if offset <= 0 else offset // 2
        if min(math.floor(base[side]) - offset for side in SIDES) < 0:
            break
    yield from land(balance, frame, progress=0.95)
    return {"trials": trials, "base_raw": base, "target_mm_s": target_mm_s, "tolerance_mm_s": tolerance_mm_s}


def fit_support(data: dict[str, Any]) -> dict[str, Any]:
    moving = [trial for trial in data["trials"] if trial["speed_mm_s"] > 1.0 and not trial["fast"]]
    if not moving:
        fast = [trial["offset"] for trial in data["trials"] if trial["fast"]]
        still = [trial["offset"] for trial in data["trials"] if not trial["fast"] and trial["speed_mm_s"] <= 1.0]
        if fast and still and min(abs(a - b) for a in fast for b in still) <= 1:
            raise ProcedureError(
                "между «стоит» и «падает быстрее 40 мм/с» нет плавного режима: после трогания трение падает сильнее, "
                "чем растёт вязкое — постоянным моментом гриф плавно не опустить; поддержка оставлена прежней (выполните D2)"
            )
        raise ProcedureError("ни одна попытка не дала плавного опускания: гриф либо стоит, либо падает быстрее 40 мм/с")
    best = min(moving, key=lambda trial: abs(trial["speed_mm_s"] - data["target_mm_s"]))
    return {
        "support_raw": best["raw"],
        "speed_mm_s": best["speed_mm_s"],
        "in_band": abs(best["speed_mm_s"] - data["target_mm_s"]) <= data["tolerance_mm_s"],
        "trials": data["trials"],
    }
