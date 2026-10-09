"""Friction along the travel and in time (S5, S6, S8).

* S5 dwell: the breakaway grows with the time the bar stands still (grease
  squeezed out). At 30 mm: rest 0.5 / 3 / 10 / 25 s → slow ramp up to the
  breakaway; ``e(t) = e₀ + A·(1 − exp(−t/τ))`` → ``A`` and ``τ`` per side.
  The first repetition after a pause feels heavier by ``A``.
* S6 screw ripple: slow governed rise over 4 revolutions of the screw; the
  force beyond the window vs height is fitted with a sine of the 32 mm lead.
* S8 tight spots: governed rise over the whole working travel; 10 mm bins
  where the force beyond the window exceeds the median by > max(5 N, 15 % Fc).
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from app.motor.calibration.fit import BreakawayDetector, least_squares
from app.motor.calibration.procedures.common import Context, Outcome, Procedure, line, mean, recenter
from app.motor.calibration.procedures.motion import Balance, Motion, hold_still, land, travel
from app.motor.calibration.runner import Command, ProcedureEnvelope, ProcedureError
from app.motor.units import SCREW_LEAD_MM, SIDES, Side

SIDE_LABEL = {"left": "Л", "right": "П"}
TAU_GRID_S = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0)


# ---------------------------------------------------------------- S5
def dwell_test(balance: Balance, *, dwells: tuple[float, ...] = (0.5, 3.0, 10.0, 25.0), height_mm: float = 30.0, rate_n_s: float = 6.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, height_mm, progress_span=(0.0, 0.05))
    runs: list[dict[str, Any]] = []
    for index, dwell in enumerate(dwells):
        progress = 0.05 + 0.9 * index / len(dwells)
        frame = yield from recenter(balance, frame, height_mm, progress)
        rest_from = frame.t
        end = frame.t + dwell
        while frame.t < end:
            frame = yield Command(balance.mid(frame), note=f"стоянка {dwell:.0f} с", progress=progress)
        edge = {side: balance.edge(side, frame.x(side), +1) for side in SIDES}
        forces = {side: edge[side] - 0.1 * balance.coulomb_up[side] for side in SIDES}
        detectors = {side: BreakawayDetector(frame.x(side), +1, dx_mm=0.3, v_mm_s=1.0, frames=2) for side in SIDES}
        found: dict[Side, float] = {}
        first_at: float | None = None
        t_prev = frame.t
        while len(found) < len(SIDES):
            dt = min(max(frame.t - t_prev, 0.0), 0.25)
            t_prev = frame.t
            for side in SIDES:
                if side not in found:
                    forces[side] += rate_n_s * dt
                    if forces[side] - edge[side] > 2.0 * balance.coulomb_up[side]:
                        raise ProcedureError("трогание после стоянки не найдено в пределах +2·трение")
            frame = yield Command(dict(forces), note=f"трогание после стоянки {dwell:.0f} с", progress=progress)
            for side in SIDES:
                if side not in found and detectors[side].update(frame.x(side), frame.v(side)):
                    found[side] = forces[side] - rate_n_s * 0.05
                    first_at = first_at if first_at is not None else frame.t
            if first_at is not None and frame.t - first_at > 1.0:
                for side in SIDES:
                    found.setdefault(side, forces[side])
        runs.append({"dwell_s": frame.t - rest_from, "extra": {side: found[side] - edge[side] for side in SIDES}})
        frame = yield from hold_still(balance, frame, progress=progress)
    yield from land(balance, frame, progress=0.97)
    return {"runs": runs}


def fit_dwell(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = sorted(data["runs"], key=lambda run: run["dwell_s"])
    if len(runs) < 3:
        raise ProcedureError("мало стоянок для оценки")
    sides: dict[Side, dict[str, tuple[Any, float | None]]] = {}
    report = []
    for side in SIDES:
        ts = [run["dwell_s"] for run in runs]
        es = [run["extra"][side] for run in runs]
        best: tuple[float, float, float, float] | None = None  # rmse, tau, e0, amplitude
        for tau in TAU_GRID_S:
            fit = least_squares([[1.0, 1 - math.exp(-t / tau)] for t in ts], es)
            if best is None or fit.rmse < best[0]:
                best = (fit.rmse, tau, fit.coef[0], fit.coef[1])
        assert best is not None
        _rmse, tau, e0, amplitude = best
        amplitude = max(0.0, amplitude)
        sides[side] = {"dwell_extra_n": (round(amplitude, 1), None), "dwell_tau_s": (tau, None)}
        points = ", ".join(f"{t:.0f} с → {e:+.1f}" for t, e in zip(ts, es, strict=True))
        report.append(line(f"{SIDE_LABEL[side]}: рост трогания со стоянкой", f"+{amplitude:.1f} Н, τ ≈ {tau:.0f} с"))
        report.append(line(f"{SIDE_LABEL[side]}: сила сверх окна по стоянкам", f"{points} Н"))
    return Outcome(report=report, sides=sides, data={"runs": runs})


# ---------------------------------------------------------------- S6
def ripple_scan(balance: Balance, *, start_mm: float = 40.0, revolutions: int = 4, speed_mm_s: float = 6.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, start_mm, progress_span=(0.0, 0.1))
    state = Motion(trace=[])
    end = start_mm + revolutions * SCREW_LEAD_MM
    frame = yield from travel(balance, frame, end, speed_mm_s=speed_mm_s, state=state, note=f"медленный подъём {speed_mm_s:.0f} мм/с, {revolutions} оборота винта", progress_span=(0.1, 0.85))
    yield from land(balance, frame, progress=0.95)
    return {"trace": [(t, x, v, extra) for t, x, v, extra in state.trace or []], "speed_mm_s": speed_mm_s}


def fit_ripple(data: dict[str, Any], ctx: Context) -> Outcome:
    target = data["speed_mm_s"]
    rows = [(x, extra) for _t, x, v, extra in data["trace"][10:] if abs(v - target) <= 0.6 * target]
    if len(rows) < 30:
        raise ProcedureError("скорость не держалась — повторите M2")
    sides: dict[Side, dict[str, tuple[Any, float | None]]] = {}
    report = []
    w = 2 * math.pi / SCREW_LEAD_MM
    for side in SIDES:
        fit = least_squares([[1.0, x, math.sin(w * x), math.cos(w * x)] for x, _ in rows], [extra[side] for _, extra in rows])
        c, d = fit.coef[2], fit.coef[3]
        amplitude, phase = math.hypot(c, d), math.atan2(d, c)
        friction = ctx.balance.coulomb_up[side]
        significant = amplitude > 0.1 * friction
        sides[side] = {"screw_ripple_n": (round(amplitude, 2), None), "screw_ripple_phase_rad": (round(phase, 3), None)}
        report.append(line(
            f"{SIDE_LABEL[side]}: неравномерность за оборот винта",
            f"±{amplitude:.1f} Н ({100 * amplitude / friction:.0f} % трения){' — заметна, стоит компенсировать' if significant else ''}",
            not significant,
        ))
    report.append(line("Точек на установившейся скорости", str(len(rows))))
    return Outcome(report=report, sides=sides, data={"points": len(rows)})


# ---------------------------------------------------------------- S8
def tight_spot_scan(balance: Balance, *, start_mm: float = 30.0, top_mm: float = 1200.0, speed_mm_s: float = 20.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, start_mm, progress_span=(0.0, 0.03))
    state = Motion(trace=[])
    frame = yield from travel(balance, frame, top_mm, speed_mm_s=speed_mm_s, state=state, note=f"подъём по всему ходу до {top_mm:.0f} мм", progress_span=(0.03, 0.6))
    yield from land(balance, frame, speed_mm_s=20.0, progress=0.8)
    return {"trace": state.trace or [], "speed_mm_s": speed_mm_s, "top_mm": top_mm}


def fit_tight_spots(data: dict[str, Any], ctx: Context) -> Outcome:
    target = data["speed_mm_s"]
    trace = [(x, v, extra) for t, x, v, extra in data["trace"] if v > 0.2 * target and t - data["trace"][0][0] > 1.0]
    if len(trace) < 30:
        raise ProcedureError("гриф не прошёл ход на установившейся скорости")
    bins: dict[int, list[float]] = {}
    for x, _v, extra in trace:
        bins.setdefault(int(x // 10), []).append(mean([extra[side] for side in SIDES]))
    levels = {key: mean(values) for key, values in bins.items() if len(values) >= 2}
    if len(levels) < 5:
        raise ProcedureError("мало участков хода для оценки")
    base = statistics.median(levels.values())
    friction = mean([ctx.balance.coulomb_up[side] for side in SIDES])
    threshold = max(5.0, 0.15 * friction)
    spots: list[list[float]] = []  # [x_from, x_to, peak]
    for key in sorted(levels):
        excess = levels[key] - base
        if excess <= threshold:
            continue
        x = key * 10 + 5
        if spots and x - spots[-1][1] <= 15:
            spots[-1][1] = x
            spots[-1][2] = max(spots[-1][2], excess)
        else:
            spots.append([x, x, excess])
    result = [((a + b) / 2, round(peak, 1)) for a, b, peak in spots]
    report = [
        line("Пройденный ход", f"{min(x for x, _v, _e in trace):.0f}…{max(x for x, _v, _e in trace):.0f} мм"),
        line("Обычная сила сверх окна", f"{base:+.1f} Н, порог тугого места +{threshold:.0f} Н"),
        line("Тугие места", ", ".join(f"{x:.0f} мм (+{peak:.0f} Н)" for x, peak in result) if result else "нет", not result),
    ]
    return Outcome(report=report, machine={"tight_spots": ([(round(x), peak) for x, peak in result], None)}, data={"spots": result, "base_n": base})


SPECS = {
    "S5": (lambda ctx: (dwell_test(ctx.balance), ProcedureEnvelope(max_x_mm=80.0)), fit_dwell),
    "S6": (lambda ctx: (ripple_scan(ctx.balance), ProcedureEnvelope(max_x_mm=220.0)), fit_ripple),
    "S8": (lambda ctx: (tight_spot_scan(ctx.balance, top_mm=ctx.top_mm), ProcedureEnvelope(max_x_mm=ctx.top_mm + 60.0)), fit_tight_spots),
}
