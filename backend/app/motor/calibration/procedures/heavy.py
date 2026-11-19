"""Loads heavier than the bar: the motor pulls the bar down (N1, N2).

With the law F = W + friction + inertia − L, any load L above the bar weight W makes the motor force
negative: the motor no longer carries the bar, it pulls it down, and everything the calibrations measured
with an upward force has to hold for a downward one too:

* N1 — torque feedback per written drive unit in each direction, measured while the bar rests on its
  stops. Pushing below the bar weight and pulling onto the stops allows both sides to be measured
  independently. Loaded screw friction is measured separately by L1/L2.
* N2 — reps and a pause with a load ~10 kgf per side heavier than the bar: the motor pulls through the whole
  set, the load stays inside what the drives can pull (``MotorCore.load_limit_n``), turns stay clean.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from app.motor.calibration.procedures.common import SIDE_LABEL, Context, Outcome, Procedure, line, recenter
from app.motor.calibration.procedures.feel import FEEL_SPEED_MM_S, TURN_STICK_S, _end, _reps, _turns
from app.motor.calibration.procedures.motion import land
from app.motor.calibration.procedures.trainer import Row, Trainer, drive
from app.motor.calibration.runner import Command, ProcedureEnvelope, ProcedureError
from app.motor.force.load_models import LoadSetpoint
from app.motor.units import SIDES, kgf_to_n, n_to_kgf

# ---------------------------------------------------------------- N1
N1_LEVELS = (0.2, 0.6, -0.2, -0.6)
N1_STEP_S = 0.8
N1_MAX_HEIGHT_MM = 12.0


def pull_scale(ctx: Context) -> Procedure:
    weight = {side: min(w for _, w in ctx.profile.side(side).gravity_map.value) for side in SIDES}
    frame = yield Command(None, note="проверка нижних упоров", progress=0.0)
    rows = []
    if any(frame.x(side) > N1_MAX_HEIGHT_MM or abs(frame.v(side)) > 5 for side in SIDES):
        raise ProcedureError("Для N1 уложите гриф на нижние упоры и дождитесь остановки")
    for index, level in enumerate(N1_LEVELS):
        forces = {side: level * weight[side] for side in SIDES}
        samples = {side: [] for side in SIDES}
        start = frame.t
        direction = "вверх" if level > 0 else "вниз"
        while frame.t - start < N1_STEP_S:
            fraction = (index + (frame.t - start) / N1_STEP_S) / len(N1_LEVELS)
            frame = yield Command(forces, note=f"Замер {index + 1}/4 · {direction} · {abs(level):.0%} веса грифа", progress=fraction)
            if any(frame.x(side) > N1_MAX_HEIGHT_MM or abs(frame.v(side)) > 10 for side in SIDES):
                raise ProcedureError("Гриф сдвинулся с упоров. Проверьте ноль B7 и вес грифа S3")
            if frame.t - start >= N1_STEP_S / 2:
                for side in SIDES:
                    sample = frame.samples[side]
                    if sample.command_raw is not None:
                        raw = sample.command_raw * ctx.profile.side(side).sign
                        samples[side].append((raw, sample.motor_force_n))
        if any(len(samples[side]) < 3 for side in SIDES):
            raise ProcedureError("Недостаточно отсчётов команды и момента. Проверьте связь B1")
        rows.append({
            "level": level,
            "raw": {side: median(raw for raw, _ in samples[side]) for side in SIDES},
            "forceN": {side: median(force for _, force in samples[side]) for side in SIDES},
        })
    yield Command(None, note="поддержка", progress=1.0)
    return {"rows": rows}


def fit_pull_scale(data: dict[str, Any], _ctx: Context) -> Outcome:
    # Actual signed PA_12C includes the current profile compensation and any drive-side command clamp.
    # Using its slope against PA_1C4 makes the estimate independent of the preceding calibration.
    report = []
    sides = {}
    rows = data["rows"]
    for side in SIDES:
        gains = []
        for low, high in ((rows[0], rows[1]), (rows[2], rows[3])):
            delta = high["raw"][side] - low["raw"][side]
            gain = (high["forceN"][side] - low["forceN"][side]) / delta if delta else 0
            if gain <= 0:
                return Outcome(report=report, data=data, error=f"{SIDE_LABEL[side]} · нет отклика момента на изменение команды. Проверьте B5, D1 и предел момента")
            gains.append(gain)
        scale = gains[1] / gains[0]
        valid = 0.6 <= scale <= 1.5
        report.append(line(f"{SIDE_LABEL[side]} · момент привода", f"вверх {gains[0]:.3f}, вниз {gains[1]:.3f} Н/ед.", valid))
        report.append(line(f"{SIDE_LABEL[side]} · масштаб тяги вниз", f"{scale:.1%}", valid))
        if not valid:
            return Outcome(report=report, data=data, error=f"{SIDE_LABEL[side]} · масштаб тяги {scale:.0%} вне диапазона 60–150 %. Проверьте пределы момента PA_05E и PA_05F")
        sides[side] = {"pull_scale": (round(scale, 3), None)}
    return Outcome(report=report, sides=sides, data=data)


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
    "N1": (lambda ctx: (pull_scale(ctx), ProcedureEnvelope(max_speed_mm_s=25.0, max_x_mm=N1_MAX_HEIGHT_MM)), fit_pull_scale),
    "N2": (lambda ctx: (heavy_check(ctx), ProcedureEnvelope(max_speed_mm_s=FEEL_SPEED_MM_S, max_x_mm=340.0)), fit_heavy_check),
}

__all__ = ["SPECS"]
