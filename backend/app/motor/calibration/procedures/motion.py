"""Motion on top of a known static window (S3): governed travel, stop, landing on the stops.

Every move is built on the window ``[W − Fc⁻, W + Fc⁺]``: the force sits just
beyond the edge in the direction of travel and a slow integrator keeps the
speed inside a band. Above 2.2× the target speed the force jumps to the middle
of the window — dry friction stops the bar — and the move restarts. The
middle of the window holds the bar still; the stops end a descent.
"""

from __future__ import annotations

import bisect
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.profile import MachineProfile
from app.motor.units import SIDES, Side

Gen = Generator[Command, Frame, Any]
STILL_MM_S = 1.0
NO_MOTION_TIMEOUT_S = 20.0


@dataclass
class Balance:
    points: dict[Side, list[tuple[float, float]]]  # [(x, W)] sorted by x
    coulomb_up: dict[Side, float]
    coulomb_down: dict[Side, float]

    @classmethod
    def from_profile(cls, profile: MachineProfile) -> Balance:
        return cls(
            {side: sorted((float(x), float(w)) for x, w in profile.side(side).gravity_map.value) for side in SIDES},
            {side: float(profile.side(side).coulomb_up_n.value) for side in SIDES},
            {side: float(profile.side(side).coulomb_down_n.value) for side in SIDES},
        )

    def weight(self, side: Side, x_mm: float) -> float:
        points = self.points[side]
        if len(points) == 1:
            return points[0][1]
        xs = [p[0] for p in points]
        i = bisect.bisect_left(xs, x_mm)
        if i <= 0:
            return points[0][1]
        if i >= len(points):
            return points[-1][1]
        (x0, w0), (x1, w1) = points[i - 1], points[i]
        return w0 + (w1 - w0) * (x_mm - x0) / (x1 - x0)

    def friction(self, side: Side, direction: int) -> float:
        return self.coulomb_up[side] if direction > 0 else self.coulomb_down[side]

    def edge(self, side: Side, x_mm: float, direction: int) -> float:
        return self.weight(side, x_mm) + direction * self.friction(side, direction)

    def mid(self, frame: Frame) -> dict[Side, float]:
        return {side: self.weight(side, frame.x(side)) for side in SIDES}

    def set_point(self, side: Side, x_mm: float, weight_n: float, merge_mm: float = 20.0) -> None:
        kept = [p for p in self.points[side] if abs(p[0] - x_mm) > merge_mm]
        self.points[side] = sorted([*kept, (x_mm, weight_n)])


def _still(frame: Frame) -> bool:
    return all(abs(frame.v(side)) < STILL_MM_S for side in SIDES)


def hold_still(balance: Balance, frame: Frame, *, note: str = "остановка", progress: float | None = None, timeout_s: float = 4.0) -> Gen:
    """Middle of the window until both sides are still for 5 frames."""

    still = 0
    start = frame.t
    while still < 5:
        if frame.t - start > timeout_s:
            raise ProcedureError("гриф не останавливается серединой окна невесомости: повторите S3")
        frame = yield Command(balance.mid(frame), note=note, progress=progress)
        still = still + 1 if _still(frame) else 0
    return frame


def _governed(
    balance: Balance,
    frame: Frame,
    direction: int,
    speed_mm_s: float,
    done: Any,
    *,
    note: str,
    progress: Any,
) -> Gen:
    """Move in ``direction`` at about ``speed_mm_s`` until ``done(frame, extra)``; returns the last frame."""

    def reset() -> dict[Side, float]:
        return {side: -0.15 * balance.friction(side, direction) for side in SIDES}

    extra = reset()
    step = {side: max(0.2, 0.01 * balance.friction(side, direction)) for side in SIDES}
    cap = {side: max(0.6 * balance.friction(side, direction), 10.0) for side in SIDES}
    moving_at = frame.t
    while not done(frame, extra):
        v = direction * frame.v_mean
        if v > 2.2 * speed_mm_s:
            frame = yield from hold_still(balance, frame, note=f"{note}: торможение", progress=progress(frame))
            extra = reset()
            continue
        for side in SIDES:
            if v < 0.5 * speed_mm_s:
                extra[side] = min(extra[side] + step[side], cap[side])
            elif v > 1.5 * speed_mm_s:
                extra[side] -= step[side]
        if v > STILL_MM_S:
            moving_at = frame.t
        elif frame.t - moving_at > NO_MOTION_TIMEOUT_S:
            raise ProcedureError("гриф не трогается с места: проверьте упоры и окно невесомости (S3)")
        forces = {side: balance.edge(side, frame.x(side), direction) + direction * extra[side] for side in SIDES}
        frame = yield Command(forces, note=note, progress=progress(frame))
    return frame


def travel(
    balance: Balance,
    frame: Frame,
    target_mm: float,
    *,
    speed_mm_s: float = 15.0,
    note: str | None = None,
    progress_span: tuple[float, float] | float | None = None,
) -> Gen:
    """Governed move to ``target_mm`` (bar mean), then a stop in the middle of the window."""

    start = frame.x_mean
    direction = 1 if target_mm > start else -1
    label = note or f"{'подъём' if direction > 0 else 'опускание'} на {target_mm:.0f} мм"
    if isinstance(progress_span, tuple):
        p0, p1 = progress_span
        distance = abs(target_mm - start) or 1.0

        def progress(f: Frame) -> float | None:
            return p0 + (p1 - p0) * min(1.0, max(0.0, abs(f.x_mean - start) / distance))
    else:
        def progress(f: Frame) -> float | None:
            return progress_span  # type: ignore[return-value]

    if abs(target_mm - start) > 1.0:
        frame = yield from _governed(
            balance, frame, direction, speed_mm_s, lambda f, _extra: direction * (target_mm - f.x_mean) <= 0, note=label, progress=progress,
        )
    return (yield from hold_still(balance, frame, note=label, progress=progress(frame)))


def land(balance: Balance, frame: Frame, *, speed_mm_s: float = 15.0, progress: float | None = None) -> Gen:
    """Down to the stops: pushing ≥ 0.25·Fc⁻ below the window and still for 1 s = resting on the stops."""

    if frame.x_mean > 60.0:
        frame = yield from travel(balance, frame, 30.0, speed_mm_s=max(speed_mm_s, 20.0), progress_span=progress)
    rested = {"frames": 0}

    def done(f: Frame, extra: dict[Side, float]) -> bool:
        pressing = all(extra[side] >= 0.25 * balance.coulomb_down[side] for side in SIDES)
        rested["frames"] = rested["frames"] + 1 if pressing and _still(f) else 0
        return rested["frames"] >= 20

    frame = yield from _governed(balance, frame, -1, speed_mm_s, done, note="опускание на упоры", progress=lambda _f: progress)
    forces = {side: balance.weight(side, frame.x(side)) - 0.5 * balance.coulomb_down[side] for side in SIDES}
    return (yield Command(forces, note="гриф на упорах", progress=progress))
