"""Automatic positioning and smooth motion (P1, P2, A1, A2, A3, R1, E1).

* P1/P2: moves up / down at 10…50 mm/s to a set point. The steady force beyond
  the window at each speed becomes a table (the speed controller starts from it),
  the fastest speed that stops within ±2 mm without overshoot — the positioning speed.
* A1: ramp-up of the target speed 60…500 mm/s²: the steepest ramp without
  speed overshoot (> 20 %) — smooth start of automatic moves.
* A2: ramp-down to the stop point 60…500 mm/s²: the steepest ramp that stops
  within ±2 mm without overshoot — smooth stop.
* A3: landing on the stops at 5…25 mm/s: the fastest landing with a contact
  speed ≤ 12 mm/s.
* R1: up→down reversal without a stop: the time the bar sticks at the turn
  (dry friction changes sign) — the dead time of every repetition turn.
* E1: STOP while moving up: the force switches to support; overshoot up and
  the descent speed afterwards (margin for the upper soft limit).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.motor.calibration.procedures.common import (
    Context,
    Outcome,
    Procedure,
    line,
    mean,
    recenter,
    sign_changes,
    steady,
)
from app.motor.calibration.procedures.motion import Balance, Motion, _governed, hold_still, land, speed, travel
from app.motor.calibration.procedures.moves import _Steady
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError
from app.motor.units import SIDES, Side

SIDE_LABEL = {"left": "Л", "right": "П"}
STOP_TOLERANCE_MM = 2.0
OVERSHOOT_MM = 1.5


# ---------------------------------------------------------------- P1, P2
def positioning(balance: Balance, direction: int, *, speeds: tuple[float, ...] = (10.0, 20.0, 35.0, 50.0), low_mm: float = 40.0, high_mm: float = 180.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    start, end = (low_mm, high_mm) if direction > 0 else (high_mm, low_mm)
    runs = []
    for index, v in enumerate(speeds):
        progress = 0.05 + 0.85 * index / len(speeds)
        frame = yield from recenter(balance, frame, start, progress)
        state = Motion(trace=[])
        frame = yield from travel(balance, frame, end, speed_mm_s=v, state=state, note=f"{'подъём' if direction > 0 else 'опускание'} на {end:.0f} мм со скоростью {v:.0f} мм/с", progress_span=progress)
        peak = max((direction * (x - end) for _t, x, _v, _e in state.trace or []), default=0.0)
        error = frame.x_mean - end
        speeds_ok, extras = steady(state.trace or [], v)
        runs.append({
            "speed_mm_s": v,
            "steady_speed": mean(speeds_ok) if speeds_ok else None,
            "extra": {side: mean(values) for side, values in extras.items()} if speeds_ok else None,
            "samples": len(speeds_ok),
            "error_mm": error,
            "overshoot_mm": max(0.0, peak, direction * error),
            "time_s": (state.trace[-1][0] - state.trace[0][0]) if state.trace and len(state.trace) > 1 else 0.0,
        })
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "direction": direction}


def fit_positioning(data: dict[str, Any], _ctx: Context) -> Outcome:
    direction = data["direction"]
    runs = data["runs"]
    table = [run for run in runs if run["extra"] is not None and run["samples"] >= 4]
    if len(table) < 2:
        raise ProcedureError("скорость не установилась хотя бы на двух уровнях: повторите M2/M3")
    good = [run for run in runs if abs(run["error_mm"]) <= STOP_TOLERANCE_MM and run["overshoot_mm"] <= OVERSHOOT_MM]
    best = max(good, key=lambda run: run["speed_mm_s"]) if good else None
    key = "up" if direction > 0 else "down"
    report = [
        line(
            f"{run['speed_mm_s']:.0f} мм/с",
            f"ошибка {run['error_mm']:+.1f} мм, перелёт {run['overshoot_mm']:.1f} мм, {run['time_s']:.1f} с"
            + ("" if run["extra"] is None else f"; сила сверх окна Л {run['extra']['left']:+.1f} / П {run['extra']['right']:+.1f} Н"),
            abs(run["error_mm"]) <= STOP_TOLERANCE_MM and run["overshoot_mm"] <= OVERSHOOT_MM,
        )
        for run in runs
    ]
    report.append(line("Скорость позиционирования", f"{best['speed_mm_s']:.0f} мм/с" if best else "ни одна скорость не дала точной остановки", best is not None))
    sides = {side: {f"travel_table_{key}": ([(round(run["steady_speed"], 1), round(run["extra"][side], 2)) for run in table], None)} for side in SIDES}
    machine = {f"position_speed_{key}_mm_s": (best["speed_mm_s"], None)} if best else {}
    return Outcome(report=report, sides=sides, machine=machine, data={"runs": runs}, error=None if best else "точная остановка не получилась ни на одной скорости: повторите M3")


# ---------------------------------------------------------------- A1
def accel_test(balance: Balance, *, accels: tuple[float, ...] = (60.0, 120.0, 250.0, 500.0), speed_mm_s: float = 40.0, low_mm: float = 40.0, high_mm: float = 190.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, accel in enumerate(accels):
        progress = 0.05 + 0.85 * index / len(accels)
        frame = yield from recenter(balance, frame, low_mm, progress)
        state = Motion(profile_trace=[])
        tuned = replace(balance, accel_mm_s2=accel, decel_mm_s2=None)
        frame = yield from travel(tuned, frame, high_mm, speed_mm_s=speed_mm_s, state=state, note=f"разгон {accel:.0f} мм/с² до {speed_mm_s:.0f} мм/с", progress_span=progress)
        trace = state.profile_trace or []
        t0 = trace[0][0] if trace else frame.t
        errors = [v - target for t, target, v in trace if t - t0 > 0.3]
        reach = next((t - t0 for t, _target, v in trace if v >= 0.9 * speed_mm_s), None)
        runs.append({
            "accel": accel,
            "overshoot_mm_s": max((v - target for _t, target, v in trace), default=0.0),
            "rmse_mm_s": (sum(e * e for e in errors) / len(errors)) ** 0.5 if errors else None,
            "reach_s": reach,
        })
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "speed_mm_s": speed_mm_s}


def fit_accel(data: dict[str, Any], _ctx: Context) -> Outcome:
    v = data["speed_mm_s"]
    runs = data["runs"]

    def smooth(run: dict[str, Any]) -> bool:
        return run["overshoot_mm_s"] <= 0.2 * v and (run["rmse_mm_s"] is None or run["rmse_mm_s"] <= 0.25 * v)

    good = [run for run in runs if smooth(run)]
    best = max(good, key=lambda run: run["accel"]) if good else None
    report = [
        line(
            f"{run['accel']:.0f} мм/с²",
            f"выход на скорость {run['reach_s']:.2f} с, превышение {run['overshoot_mm_s']:.1f} мм/с" if run["reach_s"] is not None else f"скорость не набрана, превышение {run['overshoot_mm_s']:.1f} мм/с",
            smooth(run),
        )
        for run in runs
    ]
    report.append(line("Ускорение автоматических перемещений", f"{best['accel']:.0f} мм/с²" if best else "нет плавного варианта", best is not None))
    return Outcome(report=report, machine={"accel_mm_s2": (best["accel"], None)} if best else {}, data={"runs": runs}, error=None if best else "разгон без превышения скорости не получился: повторите M2/P1")


# ---------------------------------------------------------------- A2
def decel_test(balance: Balance, *, decels: tuple[float, ...] = (60.0, 120.0, 250.0, 500.0), speed_mm_s: float = 40.0, low_mm: float = 40.0, high_mm: float = 190.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, decel in enumerate(decels):
        progress = 0.05 + 0.85 * index / len(decels)
        frame = yield from recenter(balance, frame, low_mm, progress)
        state = Motion(trace=[])
        tuned = replace(balance, decel_mm_s2=decel)
        frame = yield from travel(tuned, frame, high_mm, speed_mm_s=speed_mm_s, state=state, note=f"остановка с замедлением {decel:.0f} мм/с²", progress_span=progress)
        trace = state.trace or []
        peak = max((x - high_mm for _t, x, _v, _e in trace), default=0.0)
        runs.append({
            "decel": decel,
            "error_mm": frame.x_mean - high_mm,
            "overshoot_mm": max(0.0, peak, frame.x_mean - high_mm),
            "time_s": (trace[-1][0] - trace[0][0]) if len(trace) > 1 else 0.0,
        })
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_decel(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]

    def precise(run: dict[str, Any]) -> bool:
        return abs(run["error_mm"]) <= STOP_TOLERANCE_MM and run["overshoot_mm"] <= OVERSHOOT_MM

    good = [run for run in runs if precise(run)]
    best = max(good, key=lambda run: run["decel"]) if good else None
    report = [line(f"{run['decel']:.0f} мм/с²", f"ошибка {run['error_mm']:+.1f} мм, перелёт {run['overshoot_mm']:.1f} мм, {run['time_s']:.1f} с", precise(run)) for run in runs]
    report.append(line("Замедление автоматических перемещений", f"{best['decel']:.0f} мм/с²" if best else "нет точного варианта", best is not None))
    return Outcome(report=report, machine={"decel_mm_s2": (best["decel"], None)} if best else {}, data={"runs": runs}, error=None if best else "плавная точная остановка не получилась: повторите M3")


# ---------------------------------------------------------------- A3
def landing_test(balance: Balance, *, speeds: tuple[float, ...] = (5.0, 10.0, 15.0, 25.0), from_mm: float = 50.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, v in enumerate(speeds):
        progress = 0.05 + 0.9 * index / len(speeds)
        frame = yield from recenter(balance, frame, from_mm, progress)
        state = Motion(trace=[])
        t0 = frame.t
        frame = yield from land(balance, frame, speed_mm_s=v, progress=progress, state=state)
        trace = state.trace or []
        contact = next((i for i, (_t, x, _v, _e) in enumerate(trace) if x < 1.0), None)
        approach = [abs(vv) for _t, _x, vv, _e in trace[max(0, (contact or 0) - 2):contact]] if contact else []
        runs.append({"speed_mm_s": v, "contact_mm_s": max(approach) if approach else None, "time_s": frame.t - t0})
    return {"runs": runs}


def fit_landing(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    soft = [run for run in runs if run["contact_mm_s"] is not None and run["contact_mm_s"] <= 12.0]
    best = max(soft, key=lambda run: run["speed_mm_s"]) if soft else None
    report = [
        line(f"посадка {run['speed_mm_s']:.0f} мм/с", f"касание {run['contact_mm_s']:.1f} мм/с, {run['time_s']:.1f} с" if run["contact_mm_s"] is not None else "касание не зафиксировано", run in soft)
        for run in runs
    ]
    report.append(line("Скорость мягкой посадки", f"{best['speed_mm_s']:.0f} мм/с" if best else "нет", best is not None))
    return Outcome(report=report, machine={"landing_speed_mm_s": (best["speed_mm_s"], None)} if best else {}, data={"runs": runs}, error=None if best else "мягкая посадка не получилась")


# ---------------------------------------------------------------- R1
class _Travelled:
    def __init__(self, x0: float, direction: int, distance: float) -> None:
        self.x0, self.direction, self.distance = x0, direction, distance

    def __call__(self, frame: Frame, _extra: dict[Side, float]) -> bool:
        return self.direction * (frame.x_mean - self.x0) >= self.distance


def reversal_test(balance: Balance, *, cycles: int = 4, stroke_mm: float = 35.0, speed_mm_s: float = 25.0, base_mm: float = 50.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from recenter(balance, frame, base_mm, 0.05)
    turns: list[dict[str, float]] = []
    previous: Frame | None = None
    for index in range(2 * cycles):
        direction = 1 if index % 2 == 0 else -1
        t_switch = frame.t
        state = Motion()
        moved_at: list[float] = []

        def watch(f: Frame, extra: dict[Side, float], direction: int = direction, moved_at: list[float] = moved_at, done: _Travelled = _Travelled(frame.x_mean, direction, stroke_mm)) -> bool:
            if not moved_at and direction * f.v_mean > 3.0:
                moved_at.append(f.t)
            return done(f, extra)

        frame = yield from _governed(balance, frame, direction, speed_mm_s, watch, note=f"разворот {index // 2 + 1}/{cycles}: {'вверх' if direction > 0 else 'вниз'}", progress=lambda _f, i=index: 0.1 + 0.8 * i / (2 * cycles), state=state)
        if index > 0 and moved_at:
            turns.append({"direction": direction, "stick_s": moved_at[0] - t_switch})
        previous = frame
    del previous
    frame = yield from hold_still(balance, frame, progress=0.92)
    yield from land(balance, frame, progress=0.95)
    return {"turns": turns}


def fit_reversal(data: dict[str, Any], _ctx: Context) -> Outcome:
    turns = data["turns"]
    if len(turns) < 3:
        raise ProcedureError("мало разворотов для оценки")
    up = [turn["stick_s"] for turn in turns if turn["direction"] > 0]
    down = [turn["stick_s"] for turn in turns if turn["direction"] < 0]
    stick = mean([turn["stick_s"] for turn in turns])
    return Outcome(
        report=[
            line("Залипание на развороте вниз → вверх", f"{mean(up) * 1000:.0f} мс" if up else "—"),
            line("Залипание на развороте вверх → вниз", f"{mean(down) * 1000:.0f} мс" if down else "—"),
            line("Среднее", f"{stick * 1000:.0f} мс", stick < 0.5),
        ],
        machine={"reversal_stick_s": (round(stick, 3), None)},
        data={"turns": turns},
    )


# ---------------------------------------------------------------- E1
def stop_reaction(balance: Balance, *, speeds: tuple[float, ...] = (20.0, 40.0), low_mm: float = 40.0, stroke_mm: float = 120.0) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, v in enumerate(speeds):
        progress = 0.05 + 0.85 * index / len(speeds)
        frame = yield from recenter(balance, frame, low_mm, progress)
        state = Motion()
        frame = yield from _governed(balance, frame, +1, v, _Steady(frame.x_mean, v, +1, stroke_mm, state), note=f"подъём {v:.0f} мм/с → СТОП", progress=lambda _f, p=progress: p, state=state)
        x_stop, t_stop, v_stop = frame.x_mean, frame.t, state.v
        peak, descent, previous = x_stop, [], None
        while frame.t - t_stop < 25.0 and frame.x_mean > 3.0:
            frame = yield Command(None, note=f"СТОП с {v:.0f} мм/с: поддержка", progress=progress)
            peak = max(peak, frame.x_mean)
            bar_v = speed(frame, previous)
            previous = frame
            if frame.t - t_stop > 2.0:
                descent.append(-bar_v)
        on_stops = frame.x_mean <= 3.0
        if not on_stops:
            frame = yield from land(balance, frame, progress=progress)
        runs.append({"speed_mm_s": v_stop, "overshoot_mm": peak - x_stop, "descent_mm_s": mean(descent) if descent else None, "on_stops": on_stops})
    return {"runs": runs}


def fit_stop(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    overshoot = max(run["overshoot_mm"] for run in runs)
    report = [
        line(
            f"СТОП на {run['speed_mm_s']:.0f} мм/с",
            f"доезд вверх {run['overshoot_mm']:.1f} мм, затем опускание {run['descent_mm_s']:.0f} мм/с" if run["descent_mm_s"] is not None else f"доезд вверх {run['overshoot_mm']:.1f} мм",
            run["on_stops"] and (run["descent_mm_s"] is None or 3.0 <= run["descent_mm_s"] <= 40.0),
        )
        for run in runs
    ]
    report.append(line("Запас до верхнего предела", f"не менее {overshoot + 5:.0f} мм"))
    hanging = [run for run in runs if not run["on_stops"]]
    return Outcome(
        report=report,
        machine={"stop_overshoot_mm": (round(overshoot, 1), None)},
        data={"runs": runs},
        error="после СТОП гриф не опустился на упоры за 25 с: повторите C3" if hanging else None,
    )


def _envelope(top: float) -> ProcedureEnvelope:
    return ProcedureEnvelope(max_x_mm=top)


SPECS = {
    "P1": (lambda ctx: (positioning(ctx.balance, +1), _envelope(240.0)), fit_positioning),
    "P2": (lambda ctx: (positioning(ctx.balance, -1), _envelope(240.0)), fit_positioning),
    "A1": (lambda ctx: (accel_test(ctx.balance), _envelope(250.0)), fit_accel),
    "A2": (lambda ctx: (decel_test(ctx.balance), _envelope(250.0)), fit_decel),
    "A3": (lambda ctx: (landing_test(ctx.balance), _envelope(120.0)), fit_landing),
    "R1": (lambda ctx: (reversal_test(ctx.balance), _envelope(150.0)), fit_reversal),
    "E1": (lambda ctx: (stop_reaction(ctx.balance), _envelope(260.0)), fit_stop),
}

__all__ = ["SPECS", "sign_changes"]
