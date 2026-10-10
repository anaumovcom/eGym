"""High-speed motion (M5, M6): braking from fast-transit speeds and a check of fast moves.

* M5: for 150 / 250 / 350 mm/s up and 150 / 250 mm/s down the bar runs a fast move and, at a steady
  speed, either brakes at once with the active brake force (lag and deceleration of the brake) or first
  coasts ``COAST_S`` on support — what an abort does — and then brakes (the coast deceleration). The
  coast sets how early fast moves slow down near the end stops; the brake, how hard they slow to a target.
* M6: fast moves between points over the whole travel: time, peak speed, stop error, fallbacks.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.motor.calibration.fit import least_squares
from app.motor.calibration.procedures.common import Context, Outcome, Procedure, line, mean
from app.motor.calibration.procedures.motion import (
    FAST_BRAKE_MM_S2,
    FAST_DOWN_MM_S,
    FAST_DRIVE_LIMIT_MM_S,
    FAST_ENVELOPE_MARGIN_MM_S,
    FAST_TOLERANCE_MM,
    FAST_UP_MM_S,
    Balance,
    _end_bound,
    _fast,
    fast_decel,
    hold_still,
    land,
    travel,
)
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError
from app.motor.units import SIDES

SPEEDS = {+1: (150.0, 250.0, 350.0), -1: (150.0, 250.0)}
COAST_S = 0.3  # support this long, then the active brake: enough to see the slope, short enough for the room
BRAKE_STOP_MM_S = 20.0
BRAKE_MAX_S = 3.0
LOW_MM = 100.0
STOP_ROOM_DECEL_MM_S2 = 600.0  # a pessimistic brake for planning the room after the cut


def _approach(v: float) -> float:
    """Distance for the reference to reach ``v`` and settle (ramp + smoothing + the governed start)."""

    return v * v / 1000.0 + 1.0 * v + 60.0


def _after(balance: Balance, v: float, direction: int) -> float:
    """Room after the cut: the reference still at speed there, and the coast + brake fit before the target."""

    runout = v * v / (2 * fast_decel(balance, direction)) + 0.3 * v + 30.0
    stop = v * COAST_S + 0.2 * v + v * v / (2 * STOP_ROOM_DECEL_MM_S2) + 30.0
    return max(runout, stop)


def plan(balance: Balance, low_mm: float, high_mm: float) -> list[tuple[int, float, float, float, float]]:
    """(direction, speed, start, cut, target) of the runs that fit into the travel and under the end-stop bound."""

    runs = []
    for direction, speeds in SPEEDS.items():
        for v in speeds:
            start = low_mm if direction > 0 else high_mm
            cut = start + direction * _approach(v)
            target = cut + direction * _after(balance, v, direction)
            if not low_mm <= target <= high_mm or _end_bound(balance, cut, direction) < v:
                continue
            runs.append((direction, v, start, cut, target))
    return runs


def _brake_forces(balance: Balance, frame: Frame, direction: int) -> dict:
    return {
        side: balance.weight(side, frame.x(side)) + direction * (balance.friction(side, direction) - balance.mass_kg[side] * FAST_BRAKE_MM_S2 / 1000.0)
        for side in SIDES
    }


def fast_braking(balance: Balance, *, low_mm: float, high_mm: float) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    runs_plan = plan(balance, low_mm, high_mm)
    if not runs_plan:
        raise ProcedureError("ход слишком мал для разгона до 150 мм/с и торможения: проверьте B8 и программный предел")
    runs: list[dict[str, Any]] = []
    total = 2 * len(runs_plan)
    index = 0
    for direction, v, start, cut, target in runs_plan:
        top = FAST_UP_MM_S if direction > 0 else FAST_DOWN_MM_S
        allowance = max(top, v) + FAST_ENVELOPE_MARGIN_MM_S
        limits = {side: min(FAST_DRIVE_LIMIT_MM_S, v + 20.0) if direction > 0 else FAST_DRIVE_LIMIT_MM_S for side in SIDES}
        arrow = "↑" if direction > 0 else "↓"
        for mode in ("brake", "coast"):
            progress = 0.03 + 0.9 * index / total
            index += 1
            label = f"{arrow} {v:.0f} мм/с → {'торможение' if mode == 'brake' else 'поддержка, затем торможение'}"
            if abs(frame.x_mean - start) > 10.0:
                frame = yield from travel(balance, frame, start, progress_span=progress)
            stats: dict[str, Any] = {}
            frame = yield from _fast(balance, frame, target, note=label, progress=lambda _f, p=progress: p, top_mm_s=v, cut_mm=cut, stats=stats)
            run: dict[str, Any] = {"direction": direction, "target_mm_s": v, "mode": mode}
            if stats["failed"] or direction * (frame.x_mean - cut) < 0:
                runs.append({**run, "ok": False})  # the fast move fell back: it has already braked and stopped
                continue
            t0, v0, x0 = frame.t, direction * frame.v_mean, frame.x_mean
            if mode == "coast":
                while frame.t - t0 < COAST_S and direction * frame.v_mean > 0.3 * v0:
                    frame = yield Command(None, note=label, progress=progress, max_speed_mm_s=allowance)
            t_brake, x_brake, v_brake = frame.t, frame.x_mean, direction * frame.v_mean
            while direction * frame.v_mean > BRAKE_STOP_MM_S and frame.t - t_brake < BRAKE_MAX_S:
                frame = yield Command(_brake_forces(balance, frame, direction), note=label, progress=progress, speed_limit_mm_s=limits, max_speed_mm_s=allowance)
            if direction * frame.v_mean > BRAKE_STOP_MM_S:
                raise ProcedureError(f"{arrow} {v:.0f} мм/с: гриф не тормозится за {BRAKE_MAX_S:.0f} с — проверьте массу (D4) и предел момента")
            coast_mm = direction * (x_brake - x0)
            runs.append({
                **run,
                "ok": True,
                "v_mm_s": v0,
                # (v0² − v1²)/(2·d): includes the bus delay, i.e. what an abort really gives
                "coast_mm_s2": (v0 * v0 - v_brake * v_brake) / (2 * coast_mm) if mode == "coast" and coast_mm > 1.0 else None,
                "coast_mm": coast_mm,
                "brake_v_mm_s": v_brake,
                "brake_mm": direction * (frame.x_mean - x_brake),
                "brake_s": frame.t - t_brake,
            })
            frame = yield from hold_still(balance, frame, note=label, progress=progress)
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_fast_braking(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    brakes = [run for run in runs if run["ok"] and run["mode"] == "brake" and run["brake_v_mm_s"] > 50.0]
    coasts = [run for run in runs if run["ok"] and run["mode"] == "coast" and run["coast_mm_s2"] is not None]
    failed = [run for run in runs if not run["ok"]]
    up = [run for run in brakes if run["direction"] > 0]
    down = [run for run in brakes if run["direction"] < 0]
    if not up or not down:
        return Outcome(report=[line("Торможение", "нет удачных прогонов в одну из сторон", False)], data=data, error="быстрый переезд не удался: повторите M2/M3 и D4")
    rows = [[run["brake_v_mm_s"], run["brake_v_mm_s"] ** 2 / 2 if run["direction"] > 0 else 0.0, run["brake_v_mm_s"] ** 2 / 2 if run["direction"] < 0 else 0.0] for run in brakes]
    distances = [max(0.0, run["brake_mm"]) for run in brakes]
    lag, decel = 0.0, {1: None, -1: None}
    try:
        lag, inv_up, inv_down = least_squares(rows, distances).coef
        decel = {1: 1 / inv_up if inv_up > 1e-6 else None, -1: 1 / inv_down if inv_down > 1e-6 else None}
    except ValueError:
        pass
    lag = max(0.0, lag)
    for direction, items in ((1, up), (-1, down)):
        if decel[direction] is None:  # one speed or a degenerate fit: per-run v²/(2·(d − v·τ))
            values = [run["brake_v_mm_s"] ** 2 / (2 * max(1.0, run["brake_mm"] - run["brake_v_mm_s"] * lag)) for run in items]
            decel[direction] = mean(values)
    coast = {d: mean([run["coast_mm_s2"] for run in coasts if run["direction"] == d]) for d in (1, -1) if any(run["direction"] == d for run in coasts)}

    def arrow(run: dict[str, Any]) -> str:
        return "↑" if run["direction"] > 0 else "↓"

    report = []
    for run in runs:
        name = f"{arrow(run)} {run['target_mm_s']:.0f} мм/с, {'торможение' if run['mode'] == 'brake' else 'выбег'}"
        if not run["ok"]:
            report.append(line(name, "быстрый переезд перешёл в медленный режим", False))
        elif run["mode"] == "brake":
            report.append(line(name, f"с {run['brake_v_mm_s']:.0f} мм/с: путь {run['brake_mm']:.0f} мм за {run['brake_s']:.2f} с"))
        else:
            value = f"{run['coast_mm_s2']:.0f} мм/с²" if run["coast_mm_s2"] is not None else "—"
            report.append(line(name, f"с {run['v_mm_s']:.0f} мм/с на поддержке: замедление {value}, путь {run['coast_mm']:.0f} мм за {COAST_S:.1f} с"))
    report += [
        line("Задержка быстрого торможения", f"{lag * 1000:.0f} мс", lag < 0.3),
        line("Активное торможение вверх / вниз", f"{decel[1]:.0f} / {decel[-1]:.0f} мм/с²", min(decel.values()) >= 300.0),
        line("Выбег на поддержке вверх / вниз", " / ".join(f"{coast[d]:.0f} мм/с²" if d in coast else "—" for d in (1, -1))),
    ]
    probe = replace(_ctx.balance, fast_coast=coast)
    for x in (100.0, 300.0):
        report.append(line(f"Быстрый спуск на высоте {x:.0f} мм — не быстрее", f"{_end_bound(probe, x, -1):.0f} мм/с"))
    machine: dict[str, tuple[Any, float | None]] = {
        "fast_brake_lag_s": (round(lag, 3), None),
        "fast_brake_up_mm_s2": (round(decel[1], 0), None),
        "fast_brake_down_mm_s2": (round(decel[-1], 0), None),
    }
    for d, key in ((1, "fast_coast_up_mm_s2"), (-1, "fast_coast_down_mm_s2")):
        if d in coast:
            machine[key] = (round(max(0.0, coast[d]), 0), None)
    if failed:
        report.append(line("Прогоны в медленном режиме", f"{len(failed)} из {len(runs)}", False))
    return Outcome(report=report, machine=machine, data={"runs": runs, "lag_s": lag, "decel": {str(k): v for k, v in decel.items()}, "coast": {str(k): v for k, v in coast.items()}})


# ---------------------------------------------------------------- M6
def fast_check(balance: Balance, *, low_mm: float, high_mm: float) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    span = high_mm - low_mm
    if span < 300.0:
        raise ProcedureError("ход слишком мал для проверки быстрых переездов")
    targets = (low_mm + 0.8 * span, low_mm, low_mm + 0.5 * span, high_mm, low_mm + 0.15 * span)
    moves = []
    for index, target in enumerate(targets):
        progress = (0.05 + 0.85 * index / len(targets), 0.05 + 0.85 * (index + 1) / len(targets))
        start, t0 = frame.x_mean, frame.t
        stats: dict[str, Any] = {}
        frame = yield from travel(balance, frame, target, note=f"переезд на {target:.0f} мм ({index + 1}/{len(targets)})", progress_span=progress, fast_stats=stats)
        moves.append({
            "from_mm": start,
            "target_mm": target,
            "error_mm": frame.x_mean - target,
            "time_s": frame.t - t0,
            "vmax_mm_s": stats.get("vmax", 0.0),
            "fast": bool(stats),
            "fallback": bool(stats.get("failed")),
            "reason": stats.get("reason"),
        })
    yield from land(balance, frame, progress=0.95)
    return {"moves": moves}


def fit_fast_check(data: dict[str, Any], _ctx: Context) -> Outcome:
    moves = data["moves"]

    def ok(move: dict[str, Any]) -> bool:
        return abs(move["error_mm"]) <= FAST_TOLERANCE_MM and not move["fallback"]

    report = [
        line(
            f"{move['from_mm']:.0f} → {move['target_mm']:.0f} мм",
            f"{move['time_s']:.1f} с, до {move['vmax_mm_s']:.0f} мм/с, ошибка {move['error_mm']:+.1f} мм" + (f", медленный режим: {move['reason']}" if move["fallback"] else ""),
            ok(move),
        )
        for move in moves
    ]
    distance = sum(abs(move["target_mm"] - move["from_mm"]) for move in moves)
    seconds = sum(move["time_s"] for move in moves)
    report.append(line("Средняя скорость переездов", f"{distance / seconds:.0f} мм/с" if seconds > 0 else "—"))
    bad = [move for move in moves if not ok(move)]
    return Outcome(
        report=report,
        data={"moves": moves},
        error=f"{len(bad)} переезд(а) с ошибкой > {FAST_TOLERANCE_MM:.0f} мм или в медленном режиме: повторите M5 (и D4)" if bad else None,
    )


def _range(ctx: Context) -> tuple[float, float]:
    return LOW_MM, ctx.top_mm


SPECS = {
    "M5": (lambda ctx: (fast_braking(ctx.balance, low_mm=_range(ctx)[0], high_mm=_range(ctx)[1]), ProcedureEnvelope(max_x_mm=ctx.top_mm + 80.0)), fit_fast_braking),
    "M6": (lambda ctx: (fast_check(ctx.balance, low_mm=_range(ctx)[0], high_mm=_range(ctx)[1]), ProcedureEnvelope(max_x_mm=ctx.top_mm + 80.0)), fit_fast_check),
}
