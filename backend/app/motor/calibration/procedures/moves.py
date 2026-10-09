"""Motion calibrations (group M): what the governed moves need beyond the static window.

* M1 lift-off: force beyond the up edge of the window needed to leave the
  bottom stops after a rest (adhesion, grease squeezed out, a dwell-dependent
  stiction). The static window (S3) is measured in the air and misses it: on
  the A6 bench a move limited to edge + 0.6·Fc never left the stops.
* M2 governed travel: force beyond the edge that keeps the reference speed
  up and down — the start point of the speed integrator, so moves reach their
  speed at once instead of creeping and overshooting.
* M3 braking: distance the bar runs after the force switches to the middle of
  the window, ``d = v·τ + v²/(2a)`` per direction — moves command the stop
  that much before the target.
* M4 check: travel to several heights at the reference speed; stop error,
  overshoot and skew of the sides against the tolerance. Writes nothing.
"""

from __future__ import annotations

import math
from collections.abc import Generator, Sequence
from typing import Any

from app.motor.calibration.fit import BreakawayDetector, least_squares, stat
from app.motor.calibration.procedures.motion import (
    FEED_SPEED_MM_S,
    STOPS_MM,
    Balance,
    Motion,
    _governed,
    hold_still,
    land,
    speed,
    travel,
)
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
LIFTOFF_LIMIT_FC = 3.0  # no lift-off within edge + 3·Fc: something holds the bar
STOP_TOLERANCE_MM = 5.0
SKEW_TOLERANCE_MM = 5.0


def _on_stops(frame: Frame) -> bool:
    return all(frame.x(side) < STOPS_MM for side in SIDES)


def _rest(balance: Balance, frame: Frame, seconds: float, note: str, progress: float) -> Generator[Command, Frame, Frame]:
    forces = {side: balance.weight(side, frame.x(side)) - 0.5 * balance.coulomb_down[side] for side in SIDES}
    end = frame.t + seconds
    while frame.t < end:
        frame = yield Command(dict(forces), note=note, progress=progress)
    return frame


# ---------------------------------------------------------------- M1
def liftoff_test(balance: Balance, *, repeats: int = 3, dwell_s: float = 3.0, rate_n_s: float = 6.0) -> Procedure:
    """``repeats`` × (rest on the stops → slow ramp up from below the edge → breakaway per side → stop → land)."""

    frame = yield Command(None, note="старт", progress=0.0)
    extras: dict[Side, list[float]] = {side: [] for side in SIDES}
    dwell: list[float] = []
    for index in range(repeats):
        span = 0.9 / repeats
        progress = 0.05 + span * index
        if index > 0 or not _on_stops(frame):
            frame = yield from land(balance, frame, progress=progress)  # the catch leaves the bar a few mm up
        frame = yield from _rest(balance, frame, dwell_s, f"стоянка на упорах {index + 1}/{repeats}", progress)
        dwell.append(dwell_s)
        x0 = {side: frame.x(side) for side in SIDES}
        edge = {side: balance.edge(side, x0[side], +1) for side in SIDES}
        forces = {side: edge[side] - 0.2 * balance.coulomb_up[side] for side in SIDES}
        detectors = {side: BreakawayDetector(x0[side], +1, dx_mm=0.3, v_mm_s=1.0, frames=2) for side in SIDES}
        found: dict[Side, float] = {}
        first_at: float | None = None
        t_prev, previous = frame.t, None
        while len(found) < len(SIDES):
            dt = min(max(frame.t - t_prev, 0.0), 0.25)
            t_prev = frame.t
            for side in SIDES:
                if side not in found:
                    forces[side] += rate_n_s * dt
                    if forces[side] - edge[side] > LIFTOFF_LIMIT_FC * balance.coulomb_up[side]:
                        raise ProcedureError(
                            f"{side}: гриф не отрывается от упоров при силе на {LIFTOFF_LIMIT_FC:.0f}·трение выше окна — проверьте, не заблокирован ли гриф"
                        )
            frame = yield Command(dict(forces), note=f"отрыв от упоров {index + 1}/{repeats}: {max(forces[s] - edge[s] for s in SIDES):+.0f} Н к окну", progress=progress + 0.5 * span, liftoff=True)
            v_bar = speed(frame, previous)
            previous = frame
            for side in SIDES:
                quick = frame.x(side) - x0[side] > 0.1 and v_bar > 5.0
                if side not in found and (detectors[side].update(frame.x(side), frame.v(side)) or quick):
                    found[side] = forces[side] - rate_n_s * 0.05  # one frame of lag
                    first_at = first_at if first_at is not None else frame.t
            if first_at is not None and frame.t - first_at > 1.0:
                for side in SIDES:
                    found.setdefault(side, forces[side])  # dragged by the bar
        for side in SIDES:
            extras[side].append(found[side] - edge[side])
        frame = yield from hold_still(balance, frame, note=f"остановка после отрыва {index + 1}/{repeats}", progress=progress + 0.8 * span, liftoff=True)
    yield from land(balance, frame, progress=0.95)
    return {"extra": extras, "dwell_s": dwell}


def fit_liftoff(data: dict[str, Any]) -> dict[str, Any]:
    sides: dict[str, Any] = {}
    for side, values in data["extra"].items():
        s = stat(values)
        sides[side] = {
            "extra_n": max(0.0, s.mean),
            "ci95": s.ci95 if math.isfinite(s.ci95) else None,
            "first_n": values[0],
            "values": values,
        }
    return {"sides": sides}


# ---------------------------------------------------------------- M2
def travel_feed(balance: Balance, *, low_mm: float = 40.0, high_mm: float = 160.0, speed_mm_s: float = FEED_SPEED_MM_S, repeats: int = 2) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, low_mm, progress_span=(0.0, 0.1))
    runs: dict[str, list[list[tuple[float, float, float, dict[Side, float]]]]] = {"up": [], "down": []}
    for index in range(repeats):
        base = 0.1 + 0.8 * index / repeats
        step = 0.8 / repeats / 2
        for key, target in (("up", high_mm), ("down", low_mm)):
            state = Motion(trace=[])
            frame = yield from travel(
                balance, frame, target, speed_mm_s=speed_mm_s, state=state,
                note=f"{'подъём' if key == 'up' else 'опускание'} {speed_mm_s:.0f} мм/с, {index + 1}/{repeats}", progress_span=(base, base + step),
            )
            runs[key].append(state.trace or [])
            base += step
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "speed_mm_s": speed_mm_s}


def fit_travel_feed(data: dict[str, Any]) -> dict[str, Any]:
    """Mean integrator output while the speed is in ±30 % of the reference (after 0.5 s in band)."""

    target = data["speed_mm_s"]
    result: dict[str, Any] = {"speed_mm_s": target}
    for key, runs in data["runs"].items():
        per_side: dict[Side, list[float]] = {side: [] for side in SIDES}
        speeds: list[float] = []
        moving: list[float] = []
        for trace in runs:
            since: float | None = None
            for t, _x, v, extra in trace:
                if v > 0.3 * target:
                    moving.append(v)
                in_band = abs(v - target) <= 0.3 * target
                since = (since if since is not None else t) if in_band else None
                if since is not None and t - since >= 0.5:
                    speeds.append(v)
                    for side in SIDES:
                        per_side[side].append(extra[side])
        if len(speeds) < 6:
            raise ProcedureError(f"{'подъём' if key == 'up' else 'опускание'}: скорость не держится около {target:.0f} мм/с — повторите S3 и M1")
        result[key] = {
            "sides": {side: {"extra_n": stat(values).mean, "ci95": stat(values).ci95, "std_n": stat(values).std} for side, values in per_side.items()},
            "speed_mean": sum(speeds) / len(speeds),
            "speed_rms_err": math.sqrt(sum((v - target) ** 2 for v in moving) / len(moving)) if moving else None,
            "samples": len(speeds),
        }
    return result


# ---------------------------------------------------------------- M3
class _Steady:
    """``done`` for a braking run: travelled > 25 mm with the speed in ±25 % for 0.4 s, or the stroke is used up."""

    def __init__(self, x_start: float, v_target: float, direction: int, stroke_mm: float, state: Motion) -> None:
        self.x_start, self.v_target, self.direction, self.stroke, self.state = x_start, v_target, direction, stroke_mm, state
        self.since: float | None = None

    def __call__(self, frame: Frame, _extra: dict[Side, float]) -> bool:
        travelled = self.direction * (frame.x_mean - self.x_start)
        if abs(self.state.v - self.v_target) <= 0.25 * self.v_target:
            self.since = self.since if self.since is not None else frame.t
        else:
            self.since = None
        in_band = self.since is not None and frame.t - self.since >= 0.4
        return (travelled > 25 and in_band) or travelled > self.stroke


def braking_test(balance: Balance, *, speeds: Sequence[float] = (15.0, 25.0, 40.0), low_mm: float = 40.0, high_mm: float = 180.0) -> Procedure:
    """For each speed and direction: governed run, at a steady speed switch to the middle of the window, record the run-out."""

    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, low_mm, progress_span=(0.0, 0.05))
    runs: list[dict[str, Any]] = []
    total = 2 * len(speeds)
    for index, (v_target, direction) in enumerate((v, d) for v in speeds for d in (+1, -1)):
        progress = 0.05 + 0.85 * index / total
        start = low_mm if direction > 0 else high_mm
        if abs(frame.x_mean - start) > 10:
            frame = yield from travel(balance, frame, start, progress_span=progress)
        x_start = frame.x_mean
        state = Motion()
        steady = _Steady(x_start, v_target, direction, abs(high_mm - low_mm) - 50, state)

        label = f"{'вверх' if direction > 0 else 'вниз'} {v_target:.0f} мм/с → остановка"
        frame = yield from _governed(balance, frame, direction, v_target, steady, note=label, progress=lambda _f, p=progress: p, state=state)
        x_switch, t_switch, v_switch = frame.x_mean, frame.t, state.v
        previous: Frame | None = None
        still = 0
        while still < 3:
            frame = yield Command(balance.mid(frame), note=label, progress=progress)
            v = direction * speed(frame, previous)
            previous = frame
            still = still + 1 if abs(v) < 1.0 else 0
            if frame.t - t_switch > 4.0:
                raise ProcedureError("гриф не останавливается серединой окна невесомости: повторите S3")
        runs.append({
            "direction": direction,
            "target_mm_s": v_target,
            "v_mm_s": v_switch,
            "distance_mm": direction * (frame.x_mean - x_switch),
            "time_s": frame.t - t_switch,
            "escalations": state.escalations,
        })
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_braking(data: dict[str, Any]) -> dict[str, Any]:
    """``d = v·τ + v²/(2a)``: τ common to both directions (bus + drive), ``a`` per direction (friction ± gravity)."""

    runs = [run for run in data["runs"] if run["v_mm_s"] > 3.0]
    if len(runs) < 4:
        raise ProcedureError("мало прогонов с установившейся скоростью для оценки торможения")
    rows = [[run["v_mm_s"], run["v_mm_s"] ** 2 / 2 if run["direction"] > 0 else 0.0, run["v_mm_s"] ** 2 / 2 if run["direction"] < 0 else 0.0] for run in runs]
    distances = [max(0.0, run["distance_mm"]) for run in runs]
    try:
        fit = least_squares(rows, distances)
        lag, inv_up, inv_down = fit.coef
    except ValueError:
        lag, inv_up, inv_down = sum(distances) / sum(run["v_mm_s"] for run in runs), 0.0, 0.0
        fit = None
    lag = max(0.0, lag)
    return {
        "lag_s": lag,
        "decel_up_mm_s2": 1 / inv_up if inv_up > 1e-5 else None,
        "decel_down_mm_s2": 1 / inv_down if inv_down > 1e-5 else None,
        "rmse_mm": fit.rmse if fit else None,
        "runs": data["runs"],
    }


# ---------------------------------------------------------------- M4
def motion_check(balance: Balance, *, targets: Sequence[float] = (80.0, 150.0, 50.0, 120.0, 30.0), speed_mm_s: float = FEED_SPEED_MM_S) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    moves: list[dict[str, Any]] = []
    for index, target in enumerate(targets):
        progress = 0.05 + 0.85 * index / len(targets)
        start = frame.x_mean
        direction = 1 if target > start else -1
        state = Motion(trace=[])
        frame = yield from travel(balance, frame, target, speed_mm_s=speed_mm_s, state=state, note=f"перемещение на {target:.0f} мм ({index + 1}/{len(targets)})", progress_span=progress)
        trace = state.trace or []
        peak = max((direction * (x - target) for _t, x, _v, _e in trace), default=0.0)
        moves.append({
            "target_mm": target,
            "stop_mm": frame.x_mean,
            "error_mm": frame.x_mean - target,
            "overshoot_mm": max(0.0, peak),
            "skew_mm": max(abs(frame.x("left") - frame.x("right")), 0.0),
            "time_s": (trace[-1][0] - trace[0][0]) if len(trace) > 1 else 0.0,
            "speed_max_mm_s": max((v for _t, _x, v, _e in trace), default=0.0),
            "escalations": state.escalations,
        })
    yield from land(balance, frame, progress=0.95)
    return {"moves": moves, "speed_mm_s": speed_mm_s}


def fit_motion_check(data: dict[str, Any]) -> dict[str, Any]:
    moves = data["moves"]
    worst = max(abs(move["error_mm"]) for move in moves)
    skew = max(move["skew_mm"] for move in moves)
    return {
        "moves": moves,
        "max_error_mm": worst,
        "max_skew_mm": skew,
        "ok_stop": worst <= STOP_TOLERANCE_MM,
        "ok_skew": skew <= SKEW_TOLERANCE_MM,
        "ok": worst <= STOP_TOLERANCE_MM and skew <= SKEW_TOLERANCE_MM,
    }
