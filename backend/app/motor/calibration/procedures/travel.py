"""B8 working travel: governed rise to the upper stop (plan 14 §13.1, CZ).

The bar rises at a governed speed. At the upper stop the speed integrator
saturates while the bar stays still: pressing ≥ 0.5·Fc⁺ beyond the window
edge and still for ``press_frames`` = the stop. The extra force is capped by
the governor (≤ 0.6·Fc⁺), so the bar meets the stop gently.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from app.motor.calibration.procedures.motion import Balance, _governed, _still, land
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
MIN_TRAVEL_MM = 300.0


def travel_range(balance: Balance, *, expected_mm: float = 1400.0, speed_mm_s: float = 30.0, press_frames: int = 10) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    start = frame.x_mean
    pressed = {"frames": 0}

    def at_top(f: Frame, extra: dict[Side, float]) -> bool:
        pressing = all(extra[side] >= 0.5 * balance.coulomb_up[side] for side in SIDES)
        pressed["frames"] = pressed["frames"] + 1 if pressing and _still(f) and f.x_mean > start + 50 else 0
        return pressed["frames"] >= press_frames

    def progress(f: Frame) -> float:
        return 0.05 + 0.5 * min(1.0, max(0.0, f.x_mean / max(expected_mm, 1.0)))

    frame = yield from _governed(balance, frame, +1, speed_mm_s, at_top, note="подъём до верхнего упора", progress=progress)
    top = {side: frame.x(side) for side in SIDES}
    yield from land(balance, frame, speed_mm_s=speed_mm_s, progress=0.8)
    return {"top": top}


def fit_travel(data: dict[str, Any]) -> dict[str, Any]:
    top = data["top"]
    travel = min(top.values())
    if travel < MIN_TRAVEL_MM:
        raise ProcedureError(f"гриф остановился на {travel:.0f} мм — препятствие или тугое место, а не верхний упор")
    return {"travel_mm": travel, "top": top, "skew_mm": top["left"] - top["right"]}
