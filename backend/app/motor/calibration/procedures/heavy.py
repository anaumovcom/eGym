"""Loads heavier than the bar: the motor pulls the bar down (N1, N2).

With the law F = W + friction + inertia − L, any load L above the bar weight W makes the motor force
negative: the motor no longer carries the bar, it pulls it down, and everything the calibrations measured
with an upward force has to hold for a downward one too:

* N1 — the drive's downward torque per raw relative to the upward one (``pull_scale``): the torque loop and the
  separate torque limits are not guaranteed symmetric. A pull cannot be measured by motion here (with the bar
  weight it is a free fall), so it is measured on the stops: pushes below the bar weight and pulls onto the stops,
  the drive reports its torque (PA_1C4). The screw efficiency (motor driving vs back-driven) is L1/L2.
* N2 — reps and a pause with a load ~10 kgf per side heavier than the bar: the motor pulls through the whole
  set, the load stays inside what the drives can pull (``MotorCore.load_limit_n``), turns stay clean.
"""

from __future__ import annotations

from typing import Any

from app.motor.calibration.procedures.common import Context, Outcome, Procedure, line, mean, recenter
from app.motor.calibration.procedures.feel import FEEL_SPEED_MM_S, TURN_STICK_S, _end, _reps, _turns
from app.motor.calibration.procedures.motion import land
from app.motor.calibration.procedures.trainer import Row, Trainer, drive
from app.motor.calibration.runner import Command, ProcedureEnvelope, ProcedureError
from app.motor.force.load_models import LoadSetpoint
from app.motor.units import SIDES, kgf_to_n, n_to_kgf

SIDE_LABEL = {"left": "Л", "right": "П"}


# ---------------------------------------------------------------- N1
N1_SHARES = (0.2, 0.6)  # of the bar weight: up stays on the stops (F < W), down pulls the bar onto them
N1_STEP_S = 0.6


def pull_scale(ctx: Context) -> Procedure:
    """On the stops: the drive's torque (PA_1C4) for two pushes and two pulls; the slopes cancel the dead zone."""

    weight = {side: min(w for _x, w in ctx.profile.side(side).gravity_map.value) for side in SIDES}
    frame = yield Command(None, note="старт", progress=0.0)
    if any(frame.x(side) > 15.0 for side in SIDES):
        raise ProcedureError("гриф должен лежать на упорах")
    rows = []
    levels = [sign * share for sign in (1, -1) for share in N1_SHARES]
    for index, level in enumerate(levels):
        forces = {side: level * weight[side] for side in SIDES}
        samples: dict[str, list[float]] = {side: [] for side in SIDES}
        end = frame.t + N1_STEP_S
        while frame.t < end:
            word = "толчок вверх" if level > 0 else "тяга вниз"
            frame = yield Command(forces, note=f"{word} {abs(level):.0%} веса грифа (гриф на упорах)", progress=0.05 + 0.9 * index / len(levels))
            if any(frame.x(side) > 15.0 for side in SIDES):
                raise ProcedureError("гриф оторвался от упоров: вес грифа (S3) завышен")
            if end - frame.t < N1_STEP_S / 2:
                for side in SIDES:
                    samples[side].append(frame.samples[side].motor_force_n)
        rows.append({"level": level, "command": forces, "torque": {side: mean(samples[side]) for side in SIDES}})
    yield Command(None, note="поддержка", progress=1.0)
    return {"rows": rows, "believed": {side: ctx.profile.side(side).pull_scale_value for side in SIDES}}


def fit_pull_scale(data: dict[str, Any], _ctx: Context) -> Outcome:
    report = []
    sides = {}
    for side in SIDES:
        def gain(sign: int, side: str = side) -> float | None:
            rows = sorted((r for r in data["rows"] if r["level"] * sign > 0), key=lambda r: abs(r["level"]))
            if len(rows) < 2:
                return None
            d_cmd = rows[-1]["command"][side] - rows[0]["command"][side]
            return (rows[-1]["torque"][side] - rows[0]["torque"][side]) / d_cmd if d_cmd else None

        push, pull = gain(1), gain(-1)
        if not push or not pull or push <= 0 or pull <= 0:
            raise ProcedureError(f"{side}: момент привода не следует команде — проверьте B5 и D1")
        # pulls were already sent through the believed scale: the new one corrects it
        scale = data["believed"][side] * pull / push
        report.append(line(f"{SIDE_LABEL[side]}: момент / команда", f"толчок {push:.2f}, тяга {pull:.2f}: масштаб тяги {scale:.0%}", 0.9 <= scale <= 1.1 or None))
        if not 0.6 <= scale <= 1.5:
            return Outcome(report=report, error=f"{SIDE_LABEL[side]}: тяга вниз {scale:.0%} от толчка — проверьте пределы момента PA_05E/PA_05F")
        sides[side] = {"pull_scale": (round(scale, 3), None)}
    return Outcome(report=report, sides=sides, data={"rows": data["rows"]})


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
    "N1": (lambda ctx: (pull_scale(ctx), ProcedureEnvelope(max_speed_mm_s=30.0, max_x_mm=30.0)), fit_pull_scale),
    "N2": (lambda ctx: (heavy_check(ctx), ProcedureEnvelope(max_speed_mm_s=FEEL_SPEED_MM_S, max_x_mm=340.0)), fit_heavy_check),
}

__all__ = ["SPECS"]
