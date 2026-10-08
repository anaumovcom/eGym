"""S1–S3: breakaway up/down, balance W and dry friction at the current height (plan 15 §2.2).

Starts on the bottom stops: a fast ramp lifts the bar a few mm, a reverse
ramp stops it inside the static window. Then ``repeats`` × (slow ramp down to
breakaway → catch → slow ramp up to breakaway → catch). Directions alternate,
the bar never travels more than a few mm, both sides ramp together (the bar
couples them) and every side records its own breakaway force.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from app.motor.calibration.fit import BreakawayDetector, Stat, stat
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Gen = Generator[Command, Frame, Any]


@dataclass(frozen=True)
class StaticEstimate:
    weight_n: dict[Side, Stat]
    coulomb_up_n: dict[Side, Stat]
    coulomb_down_n: dict[Side, Stat]
    height_mm: float

    def to_dict(self) -> dict[str, Any]:
        def pack(values: dict[Side, Stat]) -> dict[str, dict[str, float]]:
            return {side: {"value": s.mean, "ci95": s.ci95, "std": s.std, "n": s.n} for side, s in values.items()}

        return {"weight_n": pack(self.weight_n), "coulomb_up_n": pack(self.coulomb_up_n), "coulomb_down_n": pack(self.coulomb_down_n), "height_mm": self.height_mm}


def _settle(forces: dict[Side, float], frame: Frame, seconds: float, note: str = "", progress: float | None = None) -> Gen:
    end = frame.t + seconds
    while frame.t < end:
        frame = yield Command(dict(forces), note=note, progress=progress)
    return frame


def _catch(forces: dict[Side, float], frame: Frame, direction: int, rate: float, max_force: float, note: str = "", progress: float | None = None) -> Gen:
    """Ramp against the motion (``direction`` while still) until both sides are still for 5 frames."""

    still = 0
    t_prev = frame.t
    while still < 5:
        dt = frame.t - t_prev
        t_prev = frame.t
        for side in SIDES:
            v = frame.v(side)
            step = -1 if v > 1.0 else (1 if v < -1.0 else 0)
            forces[side] += step * rate * dt
            if abs(forces[side]) > max_force:
                raise ProcedureError("не удалось остановить гриф в пределах силы процедуры")
        frame = yield Command(dict(forces), note=note, progress=progress)
        still = still + 1 if all(abs(frame.v(side)) < 1.0 for side in SIDES) else 0
    return frame


def _breakaway(
    forces: dict[Side, float], frame: Frame, direction: int, rate: float, lag_s: float, max_force: float, dx_mm: float = 0.3, note: str = "", progress: float | None = None
) -> Gen:
    detectors = {side: BreakawayDetector(frame.x(side), direction, dx_mm=dx_mm) for side in SIDES}
    found: dict[Side, float] = {}
    first_at: float | None = None
    t_prev = frame.t
    while len(found) < len(SIDES):
        dt = frame.t - t_prev
        t_prev = frame.t
        for side in SIDES:
            if side not in found:
                forces[side] += direction * rate * dt
                if abs(forces[side]) > max_force:
                    raise ProcedureError("трогание не обнаружено в пределах силы процедуры")
        frame = yield Command(dict(forces), note=note, progress=progress)
        for side in SIDES:
            if side not in found and detectors[side].update(frame.x(side), frame.v(side)):
                found[side] = forces[side] - direction * rate * lag_s
                first_at = first_at if first_at is not None else frame.t
        if first_at is not None and frame.t - first_at > 1.0:
            for side in SIDES:
                found.setdefault(side, forces[side])  # dragged by the bar
    return frame, found


def lift_off(
    forces: dict[Side, float],
    frame: Frame,
    *,
    fast_rate_n_s: float = 40.0,
    slow_rate_n_s: float = 3.0,
    max_force_n: float = 600.0,
    clearance_mm: float = 10.0,
    progress: float | None = None,
) -> Gen:
    """From the bottom stops to a standstill ``clearance_mm`` above them, inside the static window."""

    frame, _ = yield from _breakaway(forces, frame, +1, fast_rate_n_s / 2, 0.0, max_force_n, dx_mm=0.5, note="отрыв от упоров", progress=progress)
    for side in SIDES:
        forces[side] *= 0.97  # stiction released: kinetic friction is lower, keep climbing slowly
    while frame.x_mean < clearance_mm:
        if frame.v_mean < 0.5:
            for side in SIDES:
                forces[side] += slow_rate_n_s * 0.1
        elif frame.v_mean > 20.0:
            for side in SIDES:
                forces[side] -= slow_rate_n_s * 0.1
        frame = yield Command(dict(forces), note=f"подъём на {clearance_mm:.0f} мм", progress=progress)
    frame = yield from _catch(forces, frame, -1, fast_rate_n_s, max_force_n, note="остановка", progress=progress)
    return (yield from _settle(forces, frame, 0.3, note="остановка", progress=progress))


def balance_and_friction(
    start_forces: dict[Side, float],
    *,
    repeats: int = 3,
    fast_rate_n_s: float = 40.0,
    slow_rate_n_s: float = 3.0,
    lag_s: float = 0.04,
    max_force_n: float = 600.0,
    clearance_mm: float = 10.0,
) -> Generator[Command, Frame, dict[str, Any]]:
    forces = dict(start_forces)
    frame = yield Command(dict(forces), note="старт", progress=0.0)
    # lift off the stops and stop inside the static window, clear of the stops
    frame = yield from lift_off(forces, frame, fast_rate_n_s=fast_rate_n_s, slow_rate_n_s=slow_rate_n_s, max_force_n=max_force_n, clearance_mm=clearance_mm, progress=0.0)
    frame, data = yield from measure_window(forces, frame, repeats=repeats, fast_rate_n_s=fast_rate_n_s, slow_rate_n_s=slow_rate_n_s, lag_s=lag_s, max_force_n=max_force_n)
    return data


def measure_window(
    forces: dict[Side, float],
    frame: Frame,
    *,
    repeats: int = 3,
    fast_rate_n_s: float = 40.0,
    slow_rate_n_s: float = 3.0,
    lag_s: float = 0.04,
    max_force_n: float = 600.0,
    progress_span: tuple[float, float] = (0.0, 1.0),
    label: str = "",
) -> Gen:
    """From a standstill inside the window: ``repeats`` × (breakaway down → catch → breakaway up → catch)."""

    phases = 1 + 2 * repeats
    start, span = progress_span[0], progress_span[1] - progress_span[0]
    ups: dict[Side, list[float]] = {side: [] for side in SIDES}
    downs: dict[Side, list[float]] = {side: [] for side in SIDES}
    heights: list[float] = []
    for index in range(repeats):
        step = f"{label}{index + 1}/{repeats}"
        progress = start + span * (1 + 2 * index) / phases
        frame, found = yield from _breakaway(forces, frame, -1, slow_rate_n_s, lag_s, max_force_n, note=f"трогание вниз {step}", progress=progress)
        for side in SIDES:
            downs[side].append(found[side])
        frame = yield from _catch(forces, frame, +1, fast_rate_n_s, max_force_n, note=f"остановка {step}", progress=progress)
        frame = yield from _settle(forces, frame, 0.3, note=f"остановка {step}", progress=progress)
        heights.append(frame.x_mean)
        progress = start + span * (2 + 2 * index) / phases
        frame, found = yield from _breakaway(forces, frame, +1, slow_rate_n_s, lag_s, max_force_n, note=f"трогание вверх {step}", progress=progress)
        for side in SIDES:
            ups[side].append(found[side])
        frame = yield from _catch(forces, frame, -1, fast_rate_n_s, max_force_n, note=f"остановка {step}", progress=progress)
        frame = yield from _settle(forces, frame, 0.3, note=f"остановка {step}", progress=progress)
    return frame, {"up": ups, "down": downs, "height_mm": sum(heights) / len(heights), "final_forces": dict(forces)}


def fit_balance(data: dict[str, Any]) -> StaticEstimate:
    weight: dict[Side, Stat] = {}
    up: dict[Side, Stat] = {}
    down: dict[Side, Stat] = {}
    for side in SIDES:
        pairs = list(zip(data["up"][side], data["down"][side], strict=True))
        weight[side] = stat([(u + d) / 2 for u, d in pairs])
        up[side] = stat([u - weight[side].mean for u, _ in pairs])
        down[side] = stat([weight[side].mean - d for _, d in pairs])
    return StaticEstimate(weight, up, down, float(data["height_mm"]))
