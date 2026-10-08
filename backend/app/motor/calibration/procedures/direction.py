"""B5: motor direction and encoder direction per side, from the bottom stops.

Ramps raw PA_12C with one sign on both drives until a side lifts by
``lift_mm``, drops it back to 0 (the bar settles on the stops), then tries the
other sign for sides that did not move. The sign that lifts a side is its
``direction_sign``; the encoder must move the same way, otherwise the wiring
or a parameter is wrong.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side


def direction_test(believed_sign: dict[Side, int], *, rate_raw_s: float = 40.0, max_raw: int = 600, lift_mm: float = 0.5) -> Generator[Command, Frame, dict[str, Any]]:
    raw = {side: 0 for side in SIDES}
    frame = yield Command(raw=dict(raw), note="старт")
    result: dict[Side, dict[str, Any]] = {}
    for sign in (1, -1):
        pending = [side for side in SIDES if side not in result]
        if not pending:
            break
        start = {side: frame.x(side) for side in SIDES}
        level = 0.0
        t_prev = frame.t
        while pending and level < max_raw:
            level += rate_raw_s * (frame.t - t_prev)
            t_prev = frame.t
            for side in pending:
                raw[side] = int(sign * level)
            frame = yield Command(raw=dict(raw))
            for side in list(pending):
                moved = frame.x(side) - start[side]
                if abs(moved) > lift_mm:
                    register_delta = moved * believed_sign[side]
                    result[side] = {"direction_sign": sign, "encoder_sign": 1 if register_delta > 0 else -1, "lift_raw": raw[side]}
                    raw[side] = 0
                    pending.remove(side)
        raw = {side: 0 for side in SIDES}
        end = frame.t + 1.0
        while frame.t < end:  # back onto the stops
            frame = yield Command(raw=dict(raw))
    missing = [side for side in SIDES if side not in result]
    if missing:
        raise ProcedureError(f"Сторона не поднимается ни в одном направлении: {', '.join(missing)}")
    for side, item in result.items():
        if item["encoder_sign"] != item["direction_sign"]:
            raise ProcedureError(f"{side}: энкодер и момент направлены в разные стороны — проверьте параметры привода")
    return {"sides": result}
