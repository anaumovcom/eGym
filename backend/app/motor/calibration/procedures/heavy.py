"""Loads heavier than the bar: the motor pulls the bar down (N1, N2).

With the law F = W + friction + inertia − L, any load L above the bar weight W makes the motor force
negative: the motor no longer carries the bar, it pulls it down, and everything the calibrations measured
with an upward force has to hold for a downward one too:

* N1 — the drive's downward force per raw relative to the upward one (``pull_scale``). The torque constant is
  nominally symmetric, but the drive's torque loop, the PA_05E/PA_05F limits and the screw efficiency are not
  guaranteed to be. Two force steps of the same size up and down (both down steps pull, F < 0): the bar mass and
  the friction cancel in the difference of the accelerations, so the ratio needs no other calibration.
* N2 — reps and a pause with a load ~10 kgf per side heavier than the bar: the motor pulls through the whole
  set, the load stays inside what the drives can pull (``MotorCore.load_limit_n``), turns stay clean.
"""

from __future__ import annotations

from typing import Any

from app.motor.calibration.procedures.common import Context, Gen, Outcome, Procedure, line, mean, recenter
from app.motor.calibration.procedures.feel import FEEL_SPEED_MM_S, TURN_STICK_S, _end, _reps, _turns
from app.motor.calibration.procedures.motion import hold_still, land
from app.motor.calibration.procedures.trainer import Row, Trainer, drive, slope
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError
from app.motor.force.load_models import LoadSetpoint
from app.motor.units import SIDES, kgf_to_n, n_to_kgf

# ---------------------------------------------------------------- N1
N1_PULLS_N = (3.0, 13.0)  # motor pulling down (F = −P), the bar going down
N1_STEP_N = 10.0
N1_PUSH_BELOW_EDGE_N = 8.0  # the push pair straddles the lower window edge: the bar keeps going down
N1_STEP_S = 0.2
N1_START_MM = 330.0
N1_START_S = 0.12  # a light pull breaks the bar away; the measurement starts in motion (stiction gone)
N1_REPEATS = 2  # push and pull runs, alternated


def _steps(ctx: Context, frame: Frame, levels: list[dict[str, float]], note: str, progress: float) -> Gen:
    """A light pull to start, then each level for ``N1_STEP_S`` in one descent: the acceleration of each."""

    t0 = frame.t
    while frame.t - t0 < N1_START_S:
        frame = yield Command({side: -N1_PULLS_N[0] for side in SIDES}, note=f"{note}: трогание", progress=progress)
    accels = []
    for index, forces in enumerate(levels):
        points: list[tuple[float, float]] = []
        t0 = frame.t
        while frame.t - t0 < N1_STEP_S:
            frame = yield Command(dict(forces), note=f"{note}: уровень {index + 1}", progress=progress)
            points.append((frame.t, frame.v_mean))
        accels.append(slope(points[1:]))  # first frame: the bus delay, still the previous level
    frame = yield from hold_still(ctx.balance, frame, progress=progress)
    return frame, accels


def pull_scale(ctx: Context) -> Procedure:
    balance = ctx.balance
    frame = yield Command(None, note="старт", progress=0.0)
    runs: list[dict[str, Any]] = []
    for repeat in range(N1_REPEATS):
        for kind in ("push", "pull"):
            progress = 0.05 + 0.85 * (2 * repeat + (0 if kind == "push" else 1)) / (2 * N1_REPEATS)
            frame = yield from recenter(balance, frame, N1_START_MM, progress)
            frame = yield from hold_still(balance, frame, progress=progress)
            if kind == "pull":
                levels = [{side: -pull for side in SIDES} for pull in N1_PULLS_N]
                note = "тяга вниз"
            else:
                # both pushes up (F > 0) around the lower window edge: the bar keeps going down slowly
                low = {side: max(1.0, balance.edge(side, frame.x(side), -1) - N1_PUSH_BELOW_EDGE_N) for side in SIDES}
                levels = [low, {side: low[side] + N1_STEP_N for side in SIDES}]
                note = "толчок вверх при опускании"
            frame, accels = yield from _steps(ctx, frame, levels, note, progress)
            if any(a is None for a in accels):
                raise ProcedureError(f"{note}: мало кадров — проверьте B1")
            runs.append({"kind": kind, "accels": [round(a, 1) for a in accels], "delta": round(accels[1] - accels[0], 1)})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "step_n": N1_STEP_N}


def fit_pull_scale(data: dict[str, Any], _ctx: Context) -> Outcome:
    up = [r["delta"] for r in data["runs"] if r["kind"] == "push"]
    down = [-r["delta"] for r in data["runs"] if r["kind"] == "pull"]
    if not up or not down or mean(up) <= 0:
        raise ProcedureError("нет разгонов для сравнения")
    scale = mean(down) / mean(up)
    report = [
        line("Опускание: +10 Н толкающей силы тормозит на", ", ".join(f"{a:.0f}" for a in up) + " мм/с²"),
        line("Опускание: +10 Н тяги разгоняет на", ", ".join(f"{a:.0f}" for a in down) + " мм/с²"),
        line("Тяга вниз относительно толчка вверх", f"{scale:.0%}", 0.8 <= scale <= 1.2),
    ]
    if not 0.6 <= scale <= 1.5:
        return Outcome(report=report, error=f"тяга вниз {scale:.0%} от толчка: проверьте PA_05E/PA_05F и направление (B5)")
    return Outcome(report=report, sides={side: {"pull_scale": (round(scale, 3), None)} for side in SIDES}, data={"runs": data["runs"]})


# ---------------------------------------------------------------- N2
N2_OVER_KGF = 10.0  # per side above the bar weight
N2_PAUSE_S = 1.5


def heavy_check(ctx: Context) -> Procedure:
    balance = ctx.balance
    weight = min(balance.weight(side, 200.0) for side in SIDES)
    probe = Trainer(ctx)
    limit = probe.core.load_limit_n()
    load = min(weight + kgf_to_n(N2_OVER_KGF), limit)
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from recenter(balance, frame, 160.0, 0.05)
    trainer = Trainer(ctx, load=LoadSetpoint(load_n=load), inertia=0.0)
    rows: list[Row] = []
    frame, why = yield from _reps(ctx, frame, trainer, load, low=150.0, high=260.0, speed_mm_s=60.0, seconds=8.0, note=f"повторения {n_to_kgf(2 * load):.0f} кг (мотор тянет вниз)", progress=0.3, rows=rows)
    paused: list[Row] = []
    if why == "time":
        frame, why = yield from drive(trainer, frame, lambda _f: load, seconds=N2_PAUSE_S, note="пауза: пользователь держит вес", progress=0.7, rows=paused,
                                      x_range=(80.0, 330.0), speed_cap=FEEL_SPEED_MM_S - 10)
    frame = yield from _end(balance, frame, 0.85)
    yield from land(balance, frame, progress=0.95)
    return {
        "load_n": load, "weight_n": weight, "limit_n": limit, "why": why, "turns": _turns(rows),
        "min_force_n": round(min((r.force for r in rows), default=0.0), 1), "max_abs_force_n": round(max((abs(r.force) for r in rows + paused), default=0.0), 1),
        "pause_drift_mm": round(max((r.x for r in paused), default=0.0) - min((r.x for r in paused), default=0.0), 1),
        "max_force_n": ctx.safety.max_force_n_per_side,
    }


def fit_heavy_check(data: dict[str, Any], _ctx: Context) -> Outcome:
    turns = data["turns"]
    pulls = data["min_force_n"] < 0
    reps_ok = data["why"] == "time"
    turn_ok = turns["chatter"] == 0 and (turns["stick_s"] or 0.0) <= TURN_STICK_S
    margin_ok = data["max_abs_force_n"] < 0.95 * data["max_force_n"]
    report = [
        line("Нагрузка", f"{n_to_kgf(data['load_n']):.1f} кгс на сторону при весе грифа {n_to_kgf(data['weight_n']):.1f} (предел приводов {n_to_kgf(data['limit_n']):.0f})"),
        line("Мотор тянет вниз", f"наименьшая сила {data['min_force_n']:+.0f} Н", pulls),
        line("Повторения", "без прерываний" if reps_ok else f"прервались ({data['why']})", reps_ok),
        line("Разворот", f"залипание {1000 * (turns['stick_s'] or 0):.0f} мс, дрожание {turns['chatter']}", turn_ok),
        line("Запас силы", f"до {data['max_abs_force_n']:.0f} Н из {data['max_force_n']:.0f}", margin_ok),
        line("Пауза с весом", f"смещение {data['pause_drift_mm']:.0f} мм", None),
    ]
    failed = not (pulls and reps_ok and turn_ok and margin_ok)
    return Outcome(report=report, data=data, error="тяжёлая нагрузка ведёт себя не как свободный вес: повторите N1, L1/L2, F4" if failed else None)


SPECS = {
    "N1": (lambda ctx: (pull_scale(ctx), ProcedureEnvelope(max_speed_mm_s=300.0, max_x_mm=N1_START_MM + 30.0)), fit_pull_scale),
    "N2": (lambda ctx: (heavy_check(ctx), ProcedureEnvelope(max_speed_mm_s=FEEL_SPEED_MM_S, max_x_mm=340.0)), fit_heavy_check),
}

__all__ = ["SPECS"]
