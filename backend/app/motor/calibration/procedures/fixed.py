"""H3 exercises the actual fixed-position controller with a bounded, unloaded disturbance."""

from typing import Any

from app.motor.calibration.procedures.common import Context, Outcome, Procedure, line
from app.motor.calibration.procedures.motion import START_TOLERANCE_MM, land, position_for_start
from app.motor.calibration.runner import Command, ProcedureEnvelope, ProcedureError
from app.motor.core import FIXED_STILL_DEADBAND_MM, MotorCore
from app.motor.supervisor.modes import Mode
from app.motor.units import SIDES, clamp

MIN_PROBE_N, MAX_PROBE_N = 30.0, 55.0  # bounded command component per side
RAMP_S, PLATEAU_S, RECOVER_S = 0.75, 0.75, 2.5
PHASE_S = 2 * RAMP_S + PLATEAU_S + RECOVER_S
PEAK_LIMIT_MM = 12.0


def fixed_response(ctx: Context, target: float, ceiling_n: float) -> Procedure:
    frame = yield Command(None, note="Подготовка к проверке фиксации", progress=0.0)
    frame = yield from position_for_start(ctx.balance, frame, target, ctx.safety, note="Подвод к точке фиксации", progress=(0.0, 0.18))
    if frame.target_error(target) > START_TOLERANCE_MM or frame.max_abs_speed > 2.0:
        raise ProcedureError("Обе каретки должны остановиться у заданной высоты. Проверьте подвод M6.")
    core = MotorCore(ctx.profile, ctx.tunables, ctx.safety)
    core.command("ready")
    core.command("hold")
    core.command("fixed")
    core.hold_at(dict.fromkeys(SIDES, target))
    previous = {s: frame.samples[s].motor_force_n for s in SIDES}
    core.previous = previous.copy()
    runs = []
    last_t = frame.t
    for index, direction in enumerate((0, -1, 1)):
        start = frame.t
        duration = PHASE_S if direction else 1.0
        breakaway = {s: ctx.balance.friction(s, direction) for s in SIDES} if direction else {}
        probe_n = clamp(1.1 * min(breakaway.values()), MIN_PROBE_N, MAX_PROBE_N) if direction else 0.0
        origin = {s: frame.x(s) for s in SIDES}
        peak = dict.fromkeys(SIDES, 0.0)
        excursion = dict.fromkeys(SIDES, 0.0)
        rebound = dict.fromkeys(SIDES, 0.0)
        tail = dict.fromkeys(SIDES, 0.0)
        applied = 0.0
        plateau_s = tail_s = 0.0
        while frame.t - start < duration:
            elapsed = frame.t - start
            share = max(0.0, min(1.0, elapsed / RAMP_S, (2 * RAMP_S + PLATEAU_S - elapsed) / RAMP_S))
            probe = direction * probe_n * share
            output = core.step(frame.samples, frame.t)
            if output.mode != Mode.FIXED:
                raise ProcedureError(core.supervisor.reason or "Режим фиксации прерван")
            forces = {}
            delivered = []
            slew = ctx.safety.max_rate_n_per_s * max(0.0, frame.t - last_t)
            for side in SIDES:
                scale = ctx.profile.side(side)
                push = min(ceiling_n, ctx.safety.max_raw * scale.n_per_raw_value)
                pull = min(ceiling_n, ctx.safety.max_raw * scale.n_per_raw_value * scale.pull_scale_value)
                base = output.forces_n[side]
                command = clamp(base + probe, previous[side] - slew, previous[side] + slew)
                forces[side] = clamp(command, -pull, push)
                delivered.append(direction * (forces[side] - base))
            if RAMP_S <= elapsed <= RAMP_S + PLATEAU_S:
                applied = max(applied, min(delivered))
            action = "Исходная высота" if not direction else ("Возврат в точку" if not probe and elapsed > RAMP_S else
                                                             "Пробное усилие вниз" if direction < 0 else "Пробное усилие вверх")
            previous, last_t = forces, frame.t
            frame = yield Command(forces, note=f"{action} · удержание {target:.0f} мм", progress=0.18 + 0.66 * (index + elapsed / duration) / 3, hold_target_mm=target)
            end = frame.t - start
            if end - elapsed <= ctx.safety.stale_frame_limit_s:
                if min(delivered) >= 0.95 * probe_n:
                    plateau_s += max(0.0, min(end, RAMP_S + PLATEAU_S) - max(elapsed, RAMP_S))
                tail_s += max(0.0, min(end, duration) - max(elapsed, duration - .5))
            for side in SIDES:
                error = frame.x(side) - target
                peak[side] = max(peak[side], abs(error))
                shift = direction * (frame.x(side) - origin[side])
                excursion[side] = max(excursion[side], shift)
                if elapsed >= 2 * RAMP_S + PLATEAU_S:
                    rebound[side] = max(rebound[side], -shift)
                if end >= duration - 0.5:
                    tail[side] = max(tail[side], abs(error))
            if frame.target_error(target) > 2 * PEAK_LIMIT_MM or frame.max_abs_speed > 65:
                raise ProcedureError(f"Фиксация прервана · Л {frame.x('left') - target:+.1f} / П {frame.x('right') - target:+.1f} мм от цели, скорость до {frame.max_abs_speed:.0f} мм/с. Проверьте H1 и B3.")
        if direction:
            runs.append({"direction": direction, "targetN": probe_n, "appliedN": applied, "plateauS": plateau_s, "breakawayN": breakaway,
                         "peak": peak, "excursion": excursion, "rebound": rebound, "tail": tail, "tailS": tail_s})
    yield from land(ctx.balance, frame, progress=0.9)
    return {"targetMm": target, "runs": runs}


def fit_fixed(data: dict[str, Any], _ctx: Context) -> Outcome:
    report = [line("Общая высота фиксации", f"{data['targetMm']:.0f} мм")]
    masked = False
    for run in data["runs"]:
        direction = "вниз" if run["direction"] < 0 else "вверх"
        report.append(line(f"Пробная команда {direction}", f"{run['appliedN']:.1f} из {run['targetN']:.1f} Н на сторону, полное усилие {run['plateauS']:.2f} с",
                           run["appliedN"] >= 0.95 * run["targetN"] and run["plateauS"] >= PLATEAU_S / 2))
        for side, label in zip(SIDES, ("Левая", "Правая"), strict=True):
            peak, tail = run["peak"][side], run["tail"][side]
            below_breakaway = run["excursion"][side] < 1.0 and run["appliedN"] <= run["breakawayN"][side]
            masked |= below_breakaway
            response = (f"отскок {run['rebound'][side]:.1f} мм" if run["excursion"][side] >= 1.0
                        else "сдвиг от пробы меньше 1 мм, отскок не измерен")
            if below_breakaway:
                response += f", результат может объясняться трением покоя ({run['breakawayN'][side]:.1f} Н)"
            report.append(line(f"{label} · {direction}",
                               f"пик от цели {peak:.1f} мм, {response}, за последние 0,5 с до {tail:.1f} мм",
                               not below_breakaway and run["tailS"] >= .25 and peak <= PEAK_LIMIT_MM and tail <= FIXED_STILL_DEADBAND_MM))
    failed = any(row["ok"] is False for row in report)
    error = None
    if failed:
        error = ("Трение покоя могло удержать гриф само. Сверьте карту направляющих S8 и баланс S7 перед повтором H3." if masked else
                 "Фиксация не подтверждена. Проверьте баланс S7, задержку B3 и удержание H1.")
    return Outcome(report=report, data=data, error=error)


def build_fixed(ctx: Context) -> tuple[Procedure, ProcedureEnvelope]:
    if ctx.working_window is None:
        raise ValueError("Для H3 нужна подтверждённая средняя зона")
    low, high = ctx.working_window
    envelope = ProcedureEnvelope(max_x_mm=min(high + 60, ctx.safety.soft_max_mm), max_force_n=min(600.0, ctx.safety.max_force_n_per_side))
    return fixed_response(ctx, (low + high) / 2, envelope.max_force_n), envelope
