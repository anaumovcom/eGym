"""Drive response and scale checks (B2, D1, B6).

* B2 torque lag: on the stops, force steps between 35 % and 85 % of the weight
  (the bar stays pressed to the stops); time from the command to 63 % of the
  step in the drive's torque feedback PA_1C4 — the drive + bus part of the loop.
* D1 dead band: on the stops, PA_12C levels 0…60 in steps of 4; the smallest
  command the drive actually turns into torque (A6: «torque command < 5 %»).
* B6 encoder scale with a tape: the machine lifts the bar to 250 mm, the
  operator measures the carriage height and enters it; check, no change.
"""

from __future__ import annotations

from typing import Any

from app.motor.calibration.fit import least_squares, stat
from app.motor.calibration.procedures.common import Context, Outcome, Procedure, ask, finite, line, mean
from app.motor.calibration.procedures.motion import Balance, hold_still, land, travel
from app.motor.calibration.runner import Command, ProcedureEnvelope, ProcedureError, Prompt
from app.motor.units import SIDES, Side

ON_STOPS = ProcedureEnvelope(max_x_mm=15.0)


# ---------------------------------------------------------------- B2
def torque_lag(balance: Balance, *, repeats: int = 5, plateau_s: float = 0.8) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    if frame.x_mean > 5.0:
        frame = yield from land(balance, frame, progress=0.05)
    low = {side: 0.35 * balance.weight(side, 0.0) for side in SIDES}
    high = {side: 0.85 * balance.weight(side, 0.0) for side in SIDES}
    rows: list[tuple[float, float, int]] = []  # (t, measured mean force, step index)
    steps: list[tuple[float, int]] = []  # (t sent, +1 up / −1 down)
    for index in range(2 * repeats):
        target, direction = (high, 1) if index % 2 == 0 else (low, -1)
        steps.append((frame.t, direction))
        end = frame.t + plateau_s
        while frame.t < end:
            frame = yield Command(dict(target), note=f"ступень момента {index // 2 + 1}/{repeats}", progress=0.1 + 0.85 * index / (2 * repeats))
            rows.append((frame.t, mean([frame.samples[side].motor_force_n for side in SIDES]), index))
    return {"rows": rows, "steps": steps, "low": mean(list(low.values())), "high": mean(list(high.values()))}


def fit_torque_lag(data: dict[str, Any], _ctx: Context) -> Outcome:
    low, high = data["low"], data["high"]
    lags: list[float] = []
    plateaus: dict[int, list[float]] = {1: [], -1: []}
    for index, (t_sent, direction) in enumerate(data["steps"]):
        rows = [(t, f) for t, f, i in data["rows"] if i == index]
        if len(rows) < 3:
            continue
        plateaus[direction].extend(f for _t, f in rows[-3:])
        level = low + 0.63 * (high - low) if direction > 0 else high - 0.63 * (high - low)
        previous = (t_sent, low if direction > 0 else high)
        for t, f in rows:
            if direction * (f - level) >= 0:
                t0, f0 = previous
                share = (level - f0) / (f - f0) if f != f0 else 1.0
                lags.append(t0 + share * (t - t0) - t_sent)
                break
            previous = (t, f)
    if len(lags) < 3:
        raise ProcedureError("момент привода (PA_1C4) не следует за командой: проверьте чтение телеметрии")
    lag = stat(lags)
    gain = (mean(plateaus[1]) - mean(plateaus[-1])) / (high - low)
    return Outcome(
        report=[
            line("Задержка команда → момент (63 %)", f"{lag.mean * 1000:.0f} ± {(finite(lag.ci95) or 0) * 1000:.0f} мс"),
            line("Отношение момента к команде", f"{gain:.2f}", 0.85 <= gain <= 1.15),
            line("Ступеней", str(len(lags))),
        ],
        machine={"torque_lag_s": (round(lag.mean, 4), finite(lag.ci95))},
        data={"lag_s": lag.mean, "gain": gain, "lags": lags},
        error=None if 0.6 <= gain <= 1.4 else f"момент привода {gain:.2f} от команды: проверьте масштаб и предел PA_05E",
    )


# ---------------------------------------------------------------- D1
def deadband_scan(balance: Balance, signs: dict[Side, int], n_per_raw: dict[Side, float], *, step_raw: int = 4, max_raw: int = 60, dwell_s: float = 0.4) -> Procedure:
    frame = yield Command(None, note="старт", progress=0.0)
    if frame.x_mean > 5.0:
        frame = yield from land(balance, frame, progress=0.05)
    top = min(max_raw, int(0.8 * min(balance.weight(side, 0.0) / n_per_raw[side] for side in SIDES)))
    levels = list(range(0, top + 1, step_raw))
    rows: list[tuple[int, dict[Side, float]]] = []
    for index, level in enumerate(levels):
        end = frame.t + dwell_s
        samples: dict[Side, list[float]] = {side: [] for side in SIDES}
        while frame.t < end:
            frame = yield Command(raw={side: level * signs[side] for side in SIDES}, note=f"команда {level} ед.", progress=0.1 + 0.85 * index / len(levels))
            for side in SIDES:
                samples[side].append(frame.samples[side].motor_force_n / n_per_raw[side])
        rows.append((level, {side: mean(values[-2:]) for side, values in samples.items()}))
    return {"rows": rows, "step": step_raw}


def fit_deadband(data: dict[str, Any], _ctx: Context) -> Outcome:
    step = data["step"]
    sides: dict[Side, dict[str, tuple[Any, float | None]]] = {}
    report = []
    for side in SIDES:
        points = [(level, measured[side]) for level, measured in data["rows"]]
        dead = [level for level, measured in points if level > 0 and measured < 0.5 * level]
        active = [(level, measured) for level, measured in points if level > 0 and measured >= 0.5 * level]
        deadband = max(dead) + step / 2 if dead else 0.0
        if dead and not active:
            raise ProcedureError(f"{side}: привод не отвечает моментом на команды до {points[-1][0]} ед.")
        gain = least_squares([[1.0, level] for level, _ in active], [measured for _, measured in active]).coef[1] if len(active) >= 3 else None
        sides[side] = {"deadband_raw": (round(deadband), None)}
        report.append(line(f"{SIDE_LABEL[side]}: мёртвая зона команды", f"{deadband:.0f} ед. ({deadband / 10:.1f} % номинала)", deadband <= 50))
        if gain is not None:
            report.append(line(f"{SIDE_LABEL[side]}: наклон момент / команда выше зоны", f"{gain:.2f}", 0.8 <= gain <= 1.2))
    return Outcome(report=report, sides=sides, data={"rows": data["rows"]})


# ---------------------------------------------------------------- B6
def tape_check(ctx: Context, *, height_mm: float = 250.0) -> Procedure:
    balance = ctx.balance
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, height_mm, speed_mm_s=20.0, progress_span=(0.0, 0.4))
    frame = yield from hold_still(balance, frame, progress=0.45)
    encoder: dict[Side, list[float]] = {side: [] for side in SIDES}

    def hold(f):  # noqa: ANN001, ANN202
        for side in SIDES:
            encoder[side].append(f.x(side))
        return balance.mid(f)

    prompt = Prompt(
        "Гриф поднят и стоит. Измерьте рулеткой, на сколько каретка поднялась над своим положением на нижних упорах, и введите результат",
        kind="input", label="Высота по рулетке", unit="мм", min=50, max=600,
    )
    frame, value = yield from ask(ctx.operator, prompt, hold, frame, progress=0.6)
    yield from land(balance, frame, progress=0.9)
    return {"tape_mm": value, "encoder": {side: mean(values[-20:]) for side, values in encoder.items()}}


def fit_tape(data: dict[str, Any], ctx: Context) -> Outcome:
    tape = data["tape_mm"]
    if tape is None:
        raise ProcedureError("высота по рулетке не введена")
    encoder = mean(list(data["encoder"].values()))
    error = encoder - tape
    limit = 1.0 + 0.003 * tape
    current = float(ctx.profile.left.mm_per_pulse.value)
    suggested = current * tape / encoder if encoder > 0 else current
    ok = abs(error) <= limit
    return Outcome(
        report=[
            line("По рулетке / по энкодеру", f"{tape:.1f} / {encoder:.1f} мм (Л {data['encoder']['left']:.1f}, П {data['encoder']['right']:.1f})"),
            line("Расхождение", f"{error:+.1f} мм ({100 * error / tape:+.2f} %), допуск ±{limit:.1f} мм", ok),
            line("Ход на импульс: текущий → по рулетке", f"{current * 1000:.4f} → {suggested * 1000:.4f} мкм"),
        ],
        data={"tape_mm": tape, "encoder_mm": encoder, "error_mm": error, "suggested_mm_per_pulse": suggested},
        error=None if ok else f"энкодер расходится с рулеткой на {error:+.1f} мм — проверьте шаг винта и измерение",
    )


SIDE_LABEL = {"left": "Л", "right": "П"}

SPECS = {
    "B2": (lambda ctx: (torque_lag(ctx.balance), ON_STOPS), fit_torque_lag),
    "D1": (
        lambda ctx: (
            deadband_scan(ctx.balance, {side: ctx.profile.side(side).sign for side in SIDES}, {side: ctx.profile.side(side).n_per_raw_value for side in SIDES}),
            ON_STOPS,
        ),
        fit_deadband,
    ),
    "B6": (lambda ctx: (tape_check(ctx), ProcedureEnvelope(max_x_mm=320.0)), fit_tape),
}
