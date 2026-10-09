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
from typing import Any

from app.motor.calibration.fit import LeastSquares, least_squares
from app.motor.calibration.procedures.motion import Balance, Motion, hold_still, land, travel
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


# ---------------------------------------------------------------- D4
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


def _best(segments: Sequence[dict[str, Any]], side: Side, balance: Balance, build: Any) -> tuple[LeastSquares, int, int]:
    best: tuple[LeastSquares, int, int] | None = None
    for lag in LAGS:
        rows = [row for segment in segments for row in _rows(segment, side, lag, balance)]
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
    for side in SIDES:
        c = viscous[side]

        def build(rows: list[tuple[float, float, float]], c: float = c) -> tuple[list[list[float]], list[float]]:
            return [[a / 1000, 1.0 if v > 0 else 0.0, -1.0 if v < 0 else 0.0] for v, a, _ in rows], [y - c * v for v, _, y in rows]

        fit, lag, rows = _best(data["segments"], side, balance, build)
        mass, up, down = fit.coef
        result[side] = {"mass_kg": mass, "ci95": fit.ci95[0], "coulomb_up_kin_n": up, "coulomb_down_kin_n": down, "rmse_n": fit.rmse, "lag_frames": lag, "rows": rows}
    return result
