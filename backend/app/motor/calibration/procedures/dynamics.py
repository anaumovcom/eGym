"""D2 friction in upward motion and D4 reflected mass (plan 15 §2.3).

Both record (x, v, commanded force) per frame and fit the motion equation of
each side by least squares on the moving frames:

    F − W(x) = Fc_kin·sign(v) + c·v + m·a,     a = Δv/Δt between frames.

The command acts with an unknown bus lag (0–2 frames); the lag with the
smallest residual wins. Frames around a command step or a velocity sign change
are skipped (torque rise, stiction).

* D2: governed rises at 12/20/30/40 mm/s (below ~10 mm/s the Stribeck dip makes stick-slip); the steady force beyond the
  breakaway edge vs speed → ``c`` (slope) and the stiction extra (intercept);
* D4: a force meander around the window (two amplitudes so that ``a`` varies
  at a constant friction sign), switching on speed ±40 mm/s or ±25 mm of
  travel → ``m`` with ``c`` from D2 and kinetic ``Fc⁺``/``Fc⁻`` fitted.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from dataclasses import replace
from statistics import fmean as mean
from typing import Any

from app.motor.calibration.fit import LeastSquares, least_squares
from app.motor.calibration.procedures.motion import FAST_VISCOUS_MAX, Balance, Motion, hold_still, land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
MIN_SPEED_MM_S = 3.0
LAGS = (0, 1, 2)
LOOKAHEAD_FRAMES = 2.5  # bus delay (1–2 frames) + one frame to react


def _new_segment() -> dict[str, Any]:
    return {"t": [], "x": {side: [] for side in SIDES}, "v": {side: [] for side in SIDES}, "f": {side: [] for side in SIDES}}


def _record(segment: dict[str, Any], frame: Frame, forces: dict[Side, float]) -> None:
    segment["t"].append(frame.t)
    for side in SIDES:
        segment["x"][side].append(frame.x(side))
        segment["v"][side].append(frame.v(side))
        segment["f"][side].append(forces[side])


# ---------------------------------------------------------------- D2
D2_SPEEDS = (40.0, 80.0, 150.0, 250.0)
STEADY_SHARE = 0.35  # the cruise speed (Δx/Δt) within 35 % of the target
STEADY_SKIP = 2  # frames after the reference reached the top (bus delay, the bar settles)
STEADY_MIN_FRAMES = 4
STEADY_MIN_S = 0.25


def friction_speeds(balance: Balance, *, low_mm: float, high_mm: float, speeds: Sequence[float] = D2_SPEEDS) -> Procedure:
    """Up and down at each speed between ``low_mm`` and ``high_mm`` by the fast-move tracker (no slow governor:
    it hunts at < 30 mm/s). The steady commanded force is the friction: F − W = ±(Fc + c·v) at a = 0.

    The feed-forward runs without the viscous term (an old D2 value would push the bar ahead); the PI finds the force.
    """

    from app.motor.calibration.procedures.motion import _fast
    probe = replace(balance, viscous={side: 0.0 for side in SIDES})
    seen: dict[Side, dict[int, list[tuple[float, float]]]] = {side: {1: [], -1: []} for side in SIDES}
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, low_mm, progress_span=(0.0, 0.05))
    runs = []
    total = 2 * len(speeds)
    for index, (speed_mm_s, direction) in enumerate((v, d) for v in speeds for d in (1, -1)):
        target = high_mm if direction > 0 else low_mm
        if abs(frame.x_mean - target) < 80.0:
            continue
        p = 0.05 + 0.9 * index / total
        trace: list[dict[str, Any]] = []
        stats: dict[str, Any] = {}
        note = f"{'подъём' if direction > 0 else 'опускание'} {speed_mm_s:.0f} мм/с"
        frame = yield from _fast(probe, frame, target, note=note, progress=lambda _f, p=p: p, top_mm_s=speed_mm_s, stats=stats, trace=trace)
        run = {"direction": direction, "speed_mm_s": speed_mm_s, "trace": trace, "fallback": bool(stats.get("failed")), "reason": stats.get("reason")}
        runs.append(run)
        # the next, faster run gets the viscous slope measured so far: else the PI integral carries c·v and the bar
        # overshoots the slowdown
        for side, item in _steady_points(run, balance).items():
            if item is not None:
                seen[side][direction].append((item[0], item[1]))
        probe = replace(probe, viscous={side: _viscous(seen[side]) for side in SIDES})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def _viscous(points: dict[int, list[tuple[float, float]]]) -> float:
    """c of F = Fc⁺·[up] + Fc⁻·[down] + c·v (up and down have different friction: a mixed slope is wrong)."""

    up, down = points[1], points[-1]
    if len(up) + len(down) < 3 or len({round(v) for v, _ in up}) + len({round(v) for v, _ in down}) < 3:
        return 0.0
    try:
        fit = least_squares([[1.0, 0.0, v] for v, _ in up] + [[0.0, 1.0, v] for v, _ in down], [f for _, f in up] + [f for _, f in down])
    except ValueError:
        return 0.0
    return max(0.0, min(fit.coef[2], FAST_VISCOUS_MAX))


def _steady_points(run: dict[str, Any], balance: Balance) -> dict[Side, tuple[float, float, int] | None]:
    """Per side (mean speed, mean friction, frames) over the cruise of one run (the reference at its top speed).

    The real bar does not hold the speed frame by frame (stick-slip at 40 mm/s, in-loop brakes at 250): the speed is
    Δx/Δt over the cruise and the friction the mean of ±(F − W) minus m·Δv/T — the energy balance of the window.
    """

    top, direction = run["speed_mm_s"], run["direction"]
    best: list[dict[str, Any]] = []
    window: list[dict[str, Any]] = []
    reached = 0
    for row in run["trace"]:
        reached = reached + 1 if abs(row["v_ref"] - top) < 0.02 * top else 0
        if reached > STEADY_SKIP:
            window.append(row)
        elif window:
            best, window = max(best, window, key=len), []
    best = max(best, window, key=len)
    if len(best) < STEADY_MIN_FRAMES or best[-1]["t"] - best[0]["t"] < STEADY_MIN_S:
        return {side: None for side in SIDES}
    span = best[-1]["t"] - best[0]["t"]
    result: dict[Side, tuple[float, float, int] | None] = {}
    for side in SIDES:
        speed = direction * (best[-1]["x"][side] - best[0]["x"][side]) / span
        if abs(speed - top) > STEADY_SHARE * top:
            result[side] = None
            continue
        accel = direction * (best[-1]["v"][side] - best[0]["v"][side]) / span
        force = mean([direction * (row["f"][side] - balance.weight(side, row["x"][side])) for row in best[:-1]])
        result[side] = (speed, force - balance.mass_kg[side] * accel / 1000.0, len(best))
    return result


def describe_runs(data: dict[str, Any], balance: Balance) -> str:
    parts = []
    for run in data["runs"]:
        cruise = sum(1 for row in run["trace"] if abs(row["v_ref"] - run["speed_mm_s"]) < 0.02 * run["speed_mm_s"])
        points = _steady_points(run, balance)
        seen = [f"{points[side][0]:.0f}" if points[side] else "—" for side in SIDES]
        tail = f", медленный режим: {run['reason']}" if run["fallback"] else ""
        parts.append(f"{'↑' if run['direction'] > 0 else '↓'}{run['speed_mm_s']:.0f}: {cruise} кадр. на скорости, Л/П {seen[0]}/{seen[1]} мм/с{tail}")
    return "; ".join(parts)


def fit_friction_speeds(data: dict[str, Any], balance: Balance) -> dict[Side, dict[str, Any]]:
    """Friction ±(F − W) = Fc⁺·[up] + Fc⁻·[down] + c·v over the steady points of all runs, per side."""

    points: dict[Side, dict[int, list[tuple[float, float]]]] = {side: {1: [], -1: []} for side in SIDES}
    for run in data["runs"]:
        for side, item in _steady_points(run, balance).items():
            if item is not None:
                points[side][run["direction"]].append((round(item[0], 1), round(item[1], 1)))
    result: dict[Side, dict[str, Any]] = {}
    for side in SIDES:
        up, down = sorted(points[side][1]), sorted(points[side][-1])
        if len(up) < 2 or len(down) < 2:
            raise ProcedureError("скорость не установилась хотя бы на двух уровнях в каждую сторону: " + describe_runs(data, balance))
        rows = [[1.0, 0.0, v] for v, _ in up] + [[0.0, 1.0, v] for v, _ in down]
        fit = least_squares(rows, [f for _, f in up] + [f for _, f in down])
        kin_up, kin_down, viscous = fit.coef
        result[side] = {
            "viscous_n_per_mm_s": max(viscous, 0.0),
            "viscous_raw": viscous,
            "ci95": fit.ci95[2],
            "coulomb_kin_up_n": kin_up,
            "coulomb_kin_down_n": kin_down,
            "coulomb_kin_ci95": max(fit.ci95[0], fit.ci95[1]),
            "rmse_n": fit.rmse,
            "table_up": up,
            "table_down": down,
        }
    return result


# ---------------------------------------------------------------- D2 (old: slow governed rises, kept for reference)
def friction_up(
    balance: Balance,
    *,
    speeds: Sequence[float] = (12.0, 20.0, 30.0, 40.0),
    start_mm: float = 20.0,
    segment_mm: float = 90.0,
    top_mm: float = 420.0,
) -> Procedure:
    """Governed rises at steady speeds: the force beyond the breakaway edge at each speed.

    A constant-force step (the textbook way) runs away after breakaway when the stiction drops and the
    bus delays the stop by 1–3 frames; a governed move holds the speed and its force is the friction.
    """

    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, start_mm, progress_span=(0.0, 0.05))
    runs = []
    count = len(speeds)
    for index, speed_mm_s in enumerate(speeds):
        target = min(frame.x_mean + segment_mm, top_mm)
        if target - frame.x_mean < 20:
            break
        state = Motion(trace=[])
        span = (0.05 + 0.85 * index / count, 0.05 + 0.85 * (index + 1) / count)
        frame = yield from travel(balance, frame, target, speed_mm_s=speed_mm_s, state=state, note=f"подъём {speed_mm_s:.0f} мм/с ({index + 1}/{count})", progress_span=span)
        runs.append({"speed_mm_s": speed_mm_s, "trace": state.trace or []})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def _steady(trace: Sequence[tuple[float, float, float, dict[Side, float]]], target: float) -> tuple[list[float], dict[Side, list[float]]]:
    from app.motor.calibration.procedures.common import steady

    return steady(trace, target)


# ---------------------------------------------------------------- D4 (fast moves)
D4_SPEED_MM_S = 250.0
D4_TRIPS = 3
D4_MIN_SPEED_MM_S = 20.0  # below: stiction, the friction sign is uncertain


def moving_mass_fast(balance: Balance, *, low_mm: float, high_mm: float, speed_mm_s: float = D4_SPEED_MM_S, trips: int = D4_TRIPS) -> Procedure:
    """Fast moves up and down between ``low_mm`` and ``high_mm``: the ramps (≈ 1000 mm/s²) give m·a ≈ 80 N, well above
    the friction noise. Each frame of the trace is a row of F − W = m·a + Fc⁺·[up] − Fc⁻·[down] + c·v."""

    from app.motor.calibration.procedures.motion import _fast

    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, low_mm, progress_span=(0.0, 0.05))
    segments = []
    for index in range(2 * trips):
        direction = 1 if index % 2 == 0 else -1
        p = 0.05 + 0.88 * index / (2 * trips)
        trace: list[dict[str, Any]] = []
        note = f"{'подъём' if direction > 0 else 'опускание'} {speed_mm_s:.0f} мм/с ({index // 2 + 1}/{trips})"
        frame = yield from _fast(balance, frame, high_mm if direction > 0 else low_mm, note=note, progress=lambda _f, p=p: p, top_mm_s=speed_mm_s, trace=trace)
        segment = _new_segment()
        for row in trace:
            segment["t"].append(row["t"])
            for side in SIDES:
                segment["x"][side].append(row["x"][side])
                segment["v"][side].append(row["v"][side])
                segment["f"][side].append(row["f"][side])
        segments.append(segment)
    yield from land(balance, frame, progress=0.95)
    return {"segments": segments, "fast": True}


def _rows_fast(segment: dict[str, Any], side: Side, lag: int, balance: Balance) -> list[tuple[float, float, float]]:
    """(v, a, F − W) per frame: central-difference acceleration, the command ``lag`` frames back (bus delay)."""

    t, x, v, f = segment["t"], segment["x"][side], segment["v"][side], segment["f"][side]
    rows = []
    for k in range(max(1, lag), len(t) - 1):
        dt = t[k + 1] - t[k - 1]
        if dt <= 0 or abs(v[k]) < D4_MIN_SPEED_MM_S or v[k - 1] * v[k + 1] <= 0:
            continue
        rows.append((v[k], (v[k + 1] - v[k - 1]) / dt, f[k - lag] - balance.weight(side, x[k])))
    return rows


# ---------------------------------------------------------------- D4 (old: force meander near the stops)
def moving_mass(
    balance: Balance,
    *,
    center_mm: float = 50.0,
    amplitude_mm: float = 25.0,
    v_peak_mm_s: float = 40.0,
    levels: Sequence[float] = (0.12, 0.25),
    seconds: float = 14.0,
) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, center_mm, progress_span=(0.0, 0.1))
    segment = _new_segment()
    phase, switches = +1, 0
    t0 = frame.t
    v_prev, t_prev = frame.v_mean, frame.t
    while frame.t - t0 < seconds:
        x, v = frame.x_mean, frame.v_mean
        dt = frame.t - t_prev
        accel = (v - v_prev) / dt if dt > 0 else 0.0
        v_prev, t_prev = v, frame.t
        ahead = v + accel * LOOKAHEAD_FRAMES * dt  # the switch acts after the bus delay
        if (phase > 0 and (ahead > v_peak_mm_s or x > center_mm + amplitude_mm)) or (phase < 0 and (ahead < -v_peak_mm_s or x < center_mm - amplitude_mm)):
            phase, switches = -phase, switches + 1
        level = levels[(switches // 2) % len(levels)]
        forces = {side: balance.edge(side, frame.x(side), phase) + phase * level * balance.friction(side, phase) for side in SIDES}
        _record(segment, frame, forces)
        frame = yield Command(forces, note=f"качание силой ±{level * balance.coulomb_up['left']:.0f} Н сверх окна", progress=0.1 + 0.8 * (frame.t - t0) / seconds)
    _record(segment, frame, balance.mid(frame))
    frame = yield from hold_still(balance, frame, progress=0.9)
    yield from land(balance, frame, progress=0.95)
    return {"segments": [segment]}


# ---------------------------------------------------------------- fit
def _rows(segment: dict[str, Any], side: Side, lag: int, balance: Balance) -> list[tuple[float, float, float]]:
    """(v_mid, a, F − W) for the usable frames of one segment."""

    t, x, v, f = segment["t"], segment["x"][side], segment["v"][side], segment["f"][side]
    rows = []
    for k in range(lag + 1, len(t) - 1):
        dt = t[k + 1] - t[k]
        if dt <= 0:
            continue
        if abs(f[k - lag] - f[k - lag - 1]) > 0.5 or v[k] * v[k + 1] <= 0:
            continue
        v_mid = (v[k] + v[k + 1]) / 2
        if abs(v_mid) < MIN_SPEED_MM_S:
            continue
        x_mid = (x[k] + x[k + 1]) / 2
        rows.append((v_mid, (v[k + 1] - v[k]) / dt, f[k - lag] - balance.weight(side, x_mid)))
    return rows


def _best(segments: Sequence[dict[str, Any]], side: Side, balance: Balance, build: Any, rows_of: Any = None) -> tuple[LeastSquares, int, int]:
    rows_of = rows_of or _rows
    best: tuple[LeastSquares, int, int] | None = None
    for lag in LAGS:
        rows = [row for segment in segments for row in rows_of(segment, side, lag, balance)]
        if len(rows) < 12:
            continue
        regressors, ys = build(rows)
        try:
            fit = least_squares(regressors, ys)
        except ValueError:
            continue
        if best is None or fit.rmse < best[0].rmse:
            best = (fit, lag, len(rows))
    if best is None:
        raise ProcedureError("недостаточно кадров движения для оценки")
    return best


def fit_friction_up(data: dict[str, Any], balance: Balance) -> dict[Side, dict[str, Any]]:
    """Force beyond the breakaway edge at steady speed: ``extra(v) = (Fc_kin − Fc_static) + c·v``.

    The slope is the viscous friction, a negative intercept is the stiction extra (static − kinetic).
    """

    points: dict[Side, list[tuple[float, float]]] = {side: [] for side in SIDES}
    for run in data["runs"]:
        speeds, extras = _steady(run["trace"], run["speed_mm_s"])
        if len(speeds) < 4:
            continue
        v = sum(speeds) / len(speeds)
        for side in SIDES:
            points[side].append((v, sum(extras[side]) / len(extras[side])))
    result: dict[Side, dict[str, Any]] = {}
    for side in SIDES:
        rows = points[side]
        if len(rows) < 3:
            raise ProcedureError("скорость не установилась хотя бы на трёх уровнях: повторите M2 и S3")
        fit = least_squares([[1.0, v] for v, _ in rows], [y for _, y in rows])
        intercept, viscous = fit.coef
        result[side] = {
            "viscous_n_per_mm_s": max(viscous, 0.0),
            "viscous_raw": viscous,
            "ci95": fit.ci95[1],
            "coulomb_kin_n": balance.coulomb_up[side] + intercept,
            "coulomb_kin_ci95": fit.ci95[0],
            "stribeck_v_mm_s": None,
            "rmse_n": fit.rmse,
            "points": [(round(v, 1), round(y, 2)) for v, y in rows],
            "rows": len(rows),
        }
    return result


def fit_moving_mass(data: dict[str, Any], balance: Balance, viscous: dict[Side, float]) -> dict[Side, dict[str, float]]:
    """F − W − c·v = m·a + Fc⁺·[v > 0] − Fc⁻·[v < 0]."""

    result: dict[Side, dict[str, float]] = {}
    fast = bool(data.get("fast"))
    for side in SIDES:
        c = viscous[side]

        def build(rows: list[tuple[float, float, float]], c: float = c) -> tuple[list[list[float]], list[float]]:
            if fast:  # c fitted too: the speeds span 20…250 mm/s
                return [[a / 1000, 1.0 if v > 0 else 0.0, -1.0 if v < 0 else 0.0, v] for v, a, _ in rows], [y for _, _, y in rows]
            return [[a / 1000, 1.0 if v > 0 else 0.0, -1.0 if v < 0 else 0.0] for v, a, _ in rows], [y - c * v for v, _, y in rows]

        fit, lag, rows = _best(data["segments"], side, balance, build, _rows_fast if fast else None)
        mass, up, down = fit.coef[:3]
        result[side] = {"mass_kg": mass, "ci95": fit.ci95[0], "coulomb_up_kin_n": up, "coulomb_down_kin_n": down, "rmse_n": fit.rmse, "lag_frames": lag, "rows": rows}
    return result
