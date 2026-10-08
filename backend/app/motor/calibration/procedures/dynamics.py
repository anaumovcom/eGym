"""D2 friction in upward motion and D4 reflected mass (plan 15 §2.3).

Both record (x, v, commanded force) per frame and fit the motion equation of
each side by least squares on the moving frames:

    F − W(x) = Fc_kin·sign(v) + c·v + m·a,     a = Δv/Δt between frames.

The command acts with an unknown bus lag (0–2 frames); the lag with the
smallest residual wins. Frames around a command step or a velocity sign change
are skipped (torque rise, stiction).

* D2: steps of constant force ``W + Fc⁺ + Δᵢ`` upward, each for ≤ 60 mm or
  until 50 mm/s → ``c`` (and kinetic ``Fc⁺``, ``m`` as a by-product);
* D4: a force meander around the window (two amplitudes so that ``a`` varies
  at a constant friction sign), switching on speed ±40 mm/s or ±25 mm of
  travel → ``m`` with ``c`` from D2 and kinetic ``Fc⁺``/``Fc⁻`` fitted.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import Any

from app.motor.calibration.fit import LeastSquares, least_squares
from app.motor.calibration.procedures.motion import Balance, hold_still, land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
MIN_SPEED_MM_S = 3.0
LAGS = (0, 1, 2)


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
    levels: Sequence[float] = (0.03, 0.06, 0.1, 0.15, 0.25, 0.4),
    start_mm: float = 20.0,
    segment_mm: float = 60.0,
    top_mm: float = 400.0,
    v_cap_mm_s: float = 50.0,
    level_s: float = 6.0,
) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, start_mm, progress_span=(0.0, 0.05))
    segments = []
    count = len(levels)
    for index, level in enumerate(levels):
        delta = {side: max(1.0, level * balance.coulomb_up[side]) for side in SIDES}
        note = f"подъём силой «трогание + {delta['left']:.1f} Н» {index + 1}/{count}"
        progress = 0.05 + 0.85 * index / count
        segment = _new_segment()
        x0, t0 = frame.x_mean, frame.t
        while True:
            forces = {side: balance.edge(side, frame.x(side), +1) + delta[side] for side in SIDES}
            _record(segment, frame, forces)
            frame = yield Command(forces, note=note, progress=progress)
            if frame.v_mean > v_cap_mm_s or frame.x_mean - x0 > segment_mm or frame.x_mean > top_mm or frame.t - t0 > level_s:
                break
        _record(segment, frame, balance.mid(frame))
        segments.append(segment)
        frame = yield from hold_still(balance, frame, progress=progress)
        if frame.x_mean > top_mm - 10:
            break
    yield from land(balance, frame, progress=0.95)
    return {"segments": segments}


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
    while frame.t - t0 < seconds:
        x, v = frame.x_mean, frame.v_mean
        if (phase > 0 and (v > v_peak_mm_s or x > center_mm + amplitude_mm)) or (phase < 0 and (v < -v_peak_mm_s or x < center_mm - amplitude_mm)):
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


def fit_friction_up(data: dict[str, Any], balance: Balance) -> dict[Side, dict[str, float]]:
    """F − W = Fc⁺ + c·v + m·a over upward motion."""

    def build(rows: list[tuple[float, float, float]]) -> tuple[list[list[float]], list[float]]:
        ups = [row for row in rows if row[0] > 0]
        return [[1.0, v, a / 1000] for v, a, _ in ups], [y for _, _, y in ups]

    result: dict[Side, dict[str, float]] = {}
    for side in SIDES:
        fit, lag, rows = _best(data["segments"], side, balance, build)
        coulomb, viscous, mass = fit.coef
        result[side] = {
            "viscous_n_per_mm_s": max(viscous, 0.0),
            "viscous_raw": viscous,
            "ci95": fit.ci95[1],
            "coulomb_kin_n": coulomb,
            "mass_kg": mass,
            "rmse_n": fit.rmse,
            "lag_frames": lag,
            "rows": rows,
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
