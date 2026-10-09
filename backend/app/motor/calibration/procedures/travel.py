"""B8 working travel: governed rise to the upper stop (plan 14 §13.1, CZ).

The bar rises at a governed speed. At the upper stop the speed integrator
saturates while the bar stays still. A tight spot or a side stuck after a
stop (A6 bench: breakaway at height needs up to +2·Fc over the normal cap)
looks the same, so the stop is confirmed only after the governor has spent
every cap escalation (0.6 → 2.6·Fc⁺ beyond the window edge, see
``DRIVE_LIMIT_ESCALATE_S``) and the bar stays still for ``press_frames``. The rise is drive-limited
(PA_056 = target speed): a tight spot that gives way does not throw the bar, so the force keeps
its margin and the bar does not stall again right after it.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from app.motor.calibration.procedures.motion import TRANSIT_UP_MM_S, Balance, Motion, _governed, _still, land
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
MIN_TRAVEL_MM = 300.0


def travel_range(balance: Balance, *, expected_mm: float = 1400.0, speed_mm_s: float = TRANSIT_UP_MM_S, press_frames: int = 10) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    start = frame.x_mean
    pressed: dict[str, Any] = {"frames": 0, "extra": {}}
    state = Motion()

    def at_top(f: Frame, extra: dict[Side, float]) -> bool:
        pressed["frames"] = pressed["frames"] + 1 if state.at_full_cap and _still(f) and f.x_mean > start + 50 else 0
        pressed["extra"] = dict(extra)
        return pressed["frames"] >= press_frames

    def progress(f: Frame) -> float:
        return 0.05 + 0.5 * min(1.0, max(0.0, f.x_mean / max(expected_mm, 1.0)))

    frame = yield from _governed(balance, frame, +1, speed_mm_s, at_top, note="подъём до верхнего упора", progress=progress, state=state, drive_limit=True)
    top = {side: frame.x(side) for side in SIDES}
    force = {side: balance.edge(side, top[side], +1) + pressed["extra"].get(side, 0.0) for side in SIDES}
    yield from land(balance, frame, progress=0.8)
    return {"top": top, "force_n": force}


def fit_travel(data: dict[str, Any]) -> dict[str, Any]:
    top = data["top"]
    travel = min(top.values())
    if travel < MIN_TRAVEL_MM:
        force = data.get("force_n") or {}
        pushed = f" при силе подъёма {force['left']:.0f} / {force['right']:.0f} Н (Л / П)" if force else ""
        raise ProcedureError(
            f"гриф остановился на {travel:.0f} мм{pushed} — тугое место, перекос кареток или не хватает предела момента привода (PA_05E), а не верхний упор"
        )
    return {"travel_mm": travel, "top": top, "skew_mm": top["left"] - top["right"]}
