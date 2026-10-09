"""Feel calibrations with the operator: D5 mass by a reference weight, L3 friction compensation under load,
G3 hand check of the free-weight feel.

* D5 — the D4 force meander without and with a hung reference weight: the mass must grow by exactly
  the hung mass; the ratio corrects the reflected mass (and shows if S9 and D4 disagree);
* L3 — the trainer's law carries the hung weight (load = −ΔW): a coast after a push must decelerate
  with the same residual friction as the empty bar; the L1/L2 growth of friction with the screw load
  is compensated with the gain that matches them;
* G3 — the operator does reps with 6 and 16 kg in the trainer's law and rates how close it is to a free
  weight (1–5); the record shows the reps, the speeds and the user force the model estimated.
"""

from __future__ import annotations

from typing import Any

from app.motor.calibration.procedures.common import Context, Gen, Outcome, Procedure, ask, line, mean, recenter, resting
from app.motor.calibration.procedures.feel import _with, _wobble
from app.motor.calibration.procedures.loaded import _balance, _window
from app.motor.calibration.procedures.motion import Balance, hold_still, land
from app.motor.calibration.procedures.trainer import Row, Trainer, drive, handoff, reversals, slope
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError, Prompt
from app.motor.force.load_models import LoadSetpoint
from app.motor.supervisor.modes import Mode
from app.motor.units import SIDES, kgf_to_n

SIDE_LABEL = {"left": "Л", "right": "П"}


def _hang(ctx: Context, frame: Frame, kg: float, progress: float) -> Gen:
    prompt = Prompt(f"Повесьте на гриф груз {kg:g} кг — по {kg / 2:g} кг на каждую сторону — и нажмите «Готово»")
    frame, _ = yield from ask(ctx.operator, prompt, resting(ctx.balance), frame, progress=progress)
    start = {side: ctx.balance.edge(side, 0.0, -1) for side in SIDES}
    frame, window = yield from _window(start, frame, "с грузом", (progress, progress + 0.1))
    return frame, window


def _unhang(ctx: Context, frame: Frame, balance: Balance, progress: float) -> Gen:
    frame = yield from land(balance, frame, progress=progress)
    frame, _ = yield from ask(ctx.operator, Prompt("Снимите груз с грифа и нажмите «Готово»"), resting(balance), frame, progress=progress)
    return frame


# ---------------------------------------------------------------- D5
def mass_reference(ctx: Context) -> Procedure:
    """The felt mass without the law's inertia compensation (= the machine mass), empty and with the weight."""

    kg = float(ctx.options["referenceKg"])
    frame = yield Command(None, note="старт", progress=0.0)
    frame, empty = yield from _wobble(ctx, frame, 0.0, note="масса без груза", progress=0.1, inertia=0.0, plain=True)
    frame = yield from land(ctx.balance, frame, progress=0.3)
    frame, window = yield from _hang(ctx, frame, kg, 0.35)
    loaded_balance = _balance(window)
    # the law carries the hung weight (load −ΔW): the bar is weightless, the mass is machine + weight
    frame, loaded = yield from _wobble(ctx, frame, -kg / 2, note="масса с грузом", progress=0.6, inertia=0.0, balance=loaded_balance, held_n=0.0, plain=True)
    frame = yield from _unhang(ctx, frame, loaded_balance, 0.95)
    return {"empty": empty, "loaded": loaded, "referenceKg": kg}


def fit_mass_reference(data: dict[str, Any], ctx: Context) -> Outcome:
    """The empty bar's felt mass is the machine mass (friction cancels in the swing); the weight checks the method."""

    empty, loaded = data["empty"]["mass_kg"], data["loaded"]["mass_kg"]
    if empty is None or loaded is None:
        raise ProcedureError("покачивание не измерено: проверьте M2 и W1")
    added = data["referenceKg"] / 2
    delta = loaded - empty
    previous = mean([float(ctx.profile.side(side).moving_mass_kg.value) for side in SIDES])
    ratio = delta / added
    report = [
        line("Масса без груза (покачивание 1 Гц)", f"{empty:.1f} кг на сторону (D4: {previous:.1f})", abs(empty - previous) <= 0.15 * previous or None),
        line("С грузом", f"{loaded:.1f} кг: прирост {delta:+.1f} кг при {added:g} кг на сторону ({ratio:.0%})", 0.6 <= ratio <= 1.6),
    ]
    if not 0.6 <= ratio <= 1.6:
        return Outcome(report=report, error=f"прирост массы {ratio:.0%} от груза: груз не повешен, или шкала силы (S9) неверна")
    if abs(empty - previous) > 0.15 * previous:
        report.append(line("D4 расходится", f"на {empty - previous:+.1f} кг: компенсация инерции (F1, F2) настраивалась по неточной массе — повторите их", False))
    sides = {side: {"moving_mass_kg": (round(empty, 1), None)} for side in SIDES}
    return Outcome(report=report, sides=sides, data={"ratio": ratio})


# ---------------------------------------------------------------- L3
L3_GAINS = (0.0, 0.5, 1.0, 1.5)


def _coast_residual(ctx: Context, frame: Frame, balance: Balance, trainer: Trainer, direction: int, mass_kg: float, *, note: str, progress: float) -> Gen:
    """Push at 40 mm/s, then the law alone: the deceleration × mass = friction the law left to the user."""

    frame = yield from recenter(balance, frame, 150.0 if direction > 0 else 260.0, progress)
    frame = yield from handoff(balance, frame, direction, 40.0, note=f"{note}: разгон", progress=progress)
    rows: list[Row] = []
    x0 = frame.x_mean
    frame, _ = yield from drive(trainer, frame, lambda _f: 0.0, seconds=1.5, note=f"{note}: выбег", progress=progress, rows=rows,
                                until=lambda f: abs(f.v_mean) < 1.0, x_range=(x0 - 80.0, x0 + 80.0), speed_cap=100.0)
    frame = yield from hold_still(balance, frame, progress=progress)
    points = [(r.t, r.v) for r in rows[1:] if direction * r.v > 5.0]
    decel = slope(points)
    return frame, (None if decel is None else round(-direction * decel * mass_kg / 1000, 2))


def load_friction(ctx: Context, gains: tuple[float, ...] = L3_GAINS) -> Procedure:
    kg = float(ctx.options["referenceKg"])
    added = kgf_to_n(kg / 2)
    mass = mean([float(ctx.profile.side(side).moving_mass_kg.value) for side in SIDES])
    frame = yield Command(None, note="старт", progress=0.0)
    empty = {}
    for direction in (1, -1):
        trainer = Trainer(ctx, inertia=0.0)
        frame, empty[direction] = yield from _coast_residual(ctx, frame, ctx.balance, trainer, direction, mass, note="без груза", progress=0.1)
    frame = yield from land(ctx.balance, frame, progress=0.2)
    frame, window = yield from _hang(ctx, frame, kg, 0.22)
    loaded_balance = _balance(window)
    runs = []
    for index, gain in enumerate(gains):
        progress = 0.35 + 0.5 * index / len(gains)
        profile = _with(ctx.profile, friction_load_gain=gain)
        residual = {}
        for direction in (1, -1):
            trainer = Trainer(ctx, load=LoadSetpoint(load_n=-added), profile=profile, inertia=0.0)  # the law carries the hung weight
            frame, residual[direction] = yield from _coast_residual(ctx, frame, loaded_balance, trainer, direction, mass + kg / 2, note=f"с грузом, рост трения {gain:.0%}", progress=progress)
        runs.append({"gain": gain, "residual": {str(k): v for k, v in residual.items()}})
    frame = yield from _unhang(ctx, frame, loaded_balance, 0.95)
    return {"empty": {str(k): v for k, v in empty.items()}, "runs": runs, "referenceKg": kg}


def fit_load_friction(data: dict[str, Any], _ctx: Context) -> Outcome:
    empty = data["empty"]
    if any(v is None for v in empty.values()):
        raise ProcedureError("выбег без груза не измерен: проверьте M2 и W1")
    report = [line("Без груза: трение, оставленное пользователю", f"вверх {empty['1']:+.1f} Н, вниз {empty['-1']:+.1f} Н")]
    scored = []
    for run in data["runs"]:
        residual = run["residual"]
        if any(v is None for v in residual.values()):
            report.append(line(f"Рост трения {run['gain']:.0%}", "выбег не измерен", False))
            continue
        mismatch = mean([abs(residual[k] - empty[k]) for k in ("1", "-1")])
        scored.append((mismatch, run["gain"]))
        report.append(line(f"С грузом {data['referenceKg']:g} кг, рост трения {run['gain']:.0%}", f"вверх {residual['1']:+.1f} Н, вниз {residual['-1']:+.1f} Н: отличие от пустого {mismatch:.1f} Н"))
    if not scored:
        return Outcome(report=report, error="выбег с грузом не измерен")
    mismatch, gain = min(scored)
    report.append(line("Выбрано", f"{gain:.0%} от L1/L2: с грузом гриф ощущается так же, как пустой (разница {mismatch:.1f} Н)", mismatch <= 5.0))
    return Outcome(report=report, machine={"friction_load_gain": (gain, None)}, data={"scored": scored})


# ---------------------------------------------------------------- G3
G3_LOADS_KGF = (3.0, 8.0)
REPS_TIMEOUT_S = 120.0


def hand_feel(ctx: Context, loads: tuple[float, ...] = G3_LOADS_KGF) -> Procedure:
    balance = ctx.balance
    frame = yield Command(None, note="старт", progress=0.0)
    items = []
    for index, load in enumerate(loads):
        progress = 0.05 + 0.85 * index / len(loads)
        frame = yield from recenter(balance, frame, 250.0, progress)
        holder = Trainer(ctx, mode="hold")
        prompt = Prompt(f"Нагрузка {2 * load:g} кг на гриф. Нажмите «Готово», затем за 3 с возьмитесь за гриф обеими руками")
        frame, _ = yield from ask(ctx.operator, prompt, holder.forces, frame, progress=progress)
        frame, _ = yield from drive(holder, frame, lambda _f: 0.0, seconds=3.0, note="возьмитесь за гриф", progress=progress)
        trainer = Trainer(ctx, load=LoadSetpoint(load_n=0.0), release=True)
        target = kgf_to_n(load)
        rows: list[Row] = []
        state = {"t0": frame.t, "still": 0.0, "t": frame.t}

        def law(f: Frame, trainer: Trainer = trainer, target: float = target, rows: list[Row] = rows, state: dict[str, float] = state) -> dict[str, float]:
            trainer.set_load(LoadSetpoint(load_n=target * min(1.0, (f.t - state["t0"]) / 1.0)))  # the load comes in over 1 s
            forces = trainer.forces(f)
            rows.append(Row(f.t, f.x_mean, f.v_mean, 0.0, mean(list(forces.values())), trainer.user, trainer.phase, f.x("left") - f.x("right")))
            state["still"] = state["still"] + (f.t - state["t"]) if abs(f.v_mean) < 1.0 else 0.0
            state["t"] = f.t
            return forces

        def finished(f: Frame, trainer: Trainer = trainer, state: dict[str, float] = state) -> bool:
            resting_low = f.x_mean < ctx.safety.soft_min_mm + 5.0
            released = trainer.core.supervisor.mode == Mode.HOLD
            return (resting_low or released) and state["still"] >= 1.0 and f.t - state["t0"] > 2.0

        action = Prompt("Сделайте 3–5 спокойных повторений вверх-вниз на 20–30 см, затем опустите гриф до упоров и отпустите", kind="action")
        frame, _ = yield from ask(ctx.operator, action, law, frame, progress=progress + 0.1, done=finished, timeout_s=REPS_TIMEOUT_S)
        if frame.x_mean > 30.0:
            frame = yield from hold_still(balance, frame, progress=progress + 0.2)
        frame = yield from land(balance, frame, progress=progress + 0.25)
        rating_prompt = Prompt(f"Насколько {2 * load:g} кг ощущались как свободный вес? 1 — совсем не похоже, 5 — не отличить", kind="input", label="Оценка", unit="балл", min=1, max=5)
        frame, rating = yield from ask(ctx.operator, rating_prompt, resting(balance), frame, progress=progress + 0.3)
        up = [r.user for r in rows if r.v > 20.0]
        down = [r.user for r in rows if r.v < -20.0]
        items.append({
            "load_kgf": load, "rating": rating, "turns": len(reversals(rows)), "frames": len(rows),
            "speed_max_mm_s": round(max((abs(r.v) for r in rows), default=0.0)),
            "felt_up_n": round(mean(up), 1) if up else None, "felt_down_n": round(mean(down), 1) if down else None,
        })
    return {"items": items}


def fit_hand_feel(data: dict[str, Any], _ctx: Context) -> Outcome:
    report, low = [], []
    for item in data["items"]:
        label = f"{2 * item['load_kgf']:g} кг на гриф"
        rating = item["rating"]
        reps = item["turns"] // 2
        report.append(line(f"{label}: оценка", f"{rating:g} из 5" if rating is not None else "нет оценки", rating is not None and rating >= 3))
        felt = ", ".join(f"{name} ≈ {value:.0f} Н" for name, value in (("подъём", item["felt_up_n"]), ("опускание", item["felt_down_n"])) if value is not None)
        report.append(line(f"{label}: движение", f"повторений ≈ {reps}, скорость до {item['speed_max_mm_s']} мм/с" + (f"; усилие по модели: {felt} (нагрузка {kgf_to_n(item['load_kgf']):.0f} Н)" if felt else "")))
        if rating is None or rating < 3:
            low.append(label)
    return Outcome(report=report, data=data, error=f"оценка ниже 3 ({', '.join(low)}): повторите F2, F3, F4 и G2" if low else None)


SPECS = {
    "D5": (lambda ctx: (mass_reference(ctx), ProcedureEnvelope(max_x_mm=360.0, max_speed_mm_s=160.0)), fit_mass_reference),
    "L3": (lambda ctx: (load_friction(ctx), ProcedureEnvelope(max_x_mm=400.0, max_speed_mm_s=120.0)), fit_load_friction),
    "G3": (lambda ctx: (hand_feel(ctx), ProcedureEnvelope(max_x_mm=ctx.top_mm + 60.0, max_speed_mm_s=400.0)), fit_hand_feel),
}
