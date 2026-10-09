"""Friction under load (L1 lifting, L2 lowering) with the operator hanging a reference weight.

The friction of a ball screw grows with the axial load: the compensation
measured on the empty bar is too small under 50–100 kg. One run moves the
empty bar at 20 mm/s in the tested direction, asks the operator to hang the
weight, measures the loaded window and repeats the move with the weight:

    F⁺ = W + Fc⁺(load) + c·v,   ΔF⁺ = ΔW·(1 + μ⁺)   (L1)
    F⁻ = W − Fc⁻(load) − c·v,   ΔF⁻ = ΔW·(1 − μ⁻)   (L2)

ΔW is the hung weight (kg·g/2 per side): the window alone cannot split μ⁺
from μ⁻ (its midpoint shifts by (μ⁺ − μ⁻)·ΔW/2), so the result relies on the
force scale (S9). The scale-free mean (μ⁺ + μ⁻)/2 from the window widening
is reported as a cross-check.
"""

from __future__ import annotations

from typing import Any

from app.motor.calibration.procedures.common import Context, Outcome, Procedure, ask, line, mean, resting, steady
from app.motor.calibration.procedures.motion import Balance, Motion, land, travel
from app.motor.calibration.procedures.statics import fit_balance, lift_off, measure_window
from app.motor.calibration.runner import Command, ProcedureEnvelope, ProcedureError, Prompt
from app.motor.units import SIDES, G, Side, n_to_kgf

SIDE_LABEL = {"left": "Л", "right": "П"}
SPEED_MM_S = 20.0


def _window(start: dict[Side, float], frame: Any, label: str, progress: tuple[float, float]) -> Any:
    forces = dict(start)
    frame = yield from lift_off(forces, frame, clearance_mm=30.0, progress=progress[0])
    frame, data = yield from measure_window(forces, frame, repeats=2, progress_span=progress, label=f"{label} ")
    return frame, data


def _balance(data: dict[str, Any]) -> Balance:
    estimate = fit_balance(data)
    return Balance(
        {side: [(estimate.height_mm, estimate.weight_n[side].mean)] for side in SIDES},
        {side: max(estimate.coulomb_up_n[side].mean, 1.0) for side in SIDES},
        {side: max(estimate.coulomb_down_n[side].mean, 1.0) for side in SIDES},
    )


def _move(balance: Balance, frame: Any, direction: int, label: str, progress: tuple[float, float]) -> Any:
    """A governed 20 mm/s move over 40…140 mm; returns the steady force per side (edge + extra)."""

    low, high = 40.0, 140.0
    state = Motion(trace=[])
    if direction > 0:
        frame = yield from travel(balance, frame, low, speed_mm_s=SPEED_MM_S, note=f"{label}: к началу", progress_span=(progress[0], progress[0]))
        frame = yield from travel(balance, frame, high, speed_mm_s=SPEED_MM_S, state=state, note=f"{label}: подъём {SPEED_MM_S:.0f} мм/с", progress_span=progress)
    else:
        frame = yield from travel(balance, frame, high, speed_mm_s=SPEED_MM_S, note=f"{label}: подъём к началу", progress_span=(progress[0], progress[0]))
        frame = yield from travel(balance, frame, low, speed_mm_s=SPEED_MM_S, state=state, note=f"{label}: опускание {SPEED_MM_S:.0f} мм/с", progress_span=progress)
    speeds, extras = steady(state.trace or [], SPEED_MM_S)
    if len(speeds) < 5:
        raise ProcedureError(f"{label}: гриф не вышел на {SPEED_MM_S:.0f} мм/с — выполните M2")
    x_mid = (low + high) / 2
    force = {side: balance.edge(side, x_mid, direction) + direction * mean(extras[side]) for side in SIDES}
    return frame, {"force": force, "speed": mean(speeds), "samples": len(speeds)}


def loaded_friction(ctx: Context, direction: int) -> Procedure:
    kg = float(ctx.options["referenceKg"])
    word = "подъём" if direction > 0 else "опускание"
    frame = yield Command(None, note="старт", progress=0.0)
    start = {side: ctx.balance.edge(side, 0.0, -1) for side in SIDES}
    frame, empty = yield from _window(start, frame, "без груза", (0.03, 0.2))
    empty_balance = _balance(empty)
    frame, empty_move = yield from _move(ctx.balance, frame, direction, f"без груза, {word}", (0.2, 0.35))
    frame = yield from land(ctx.balance, frame, progress=0.37)
    prompt = Prompt(f"Повесьте на гриф груз {kg:g} кг — по {kg / 2:g} кг на каждую сторону — и нажмите «Готово»")
    frame, _ = yield from ask(ctx.operator, prompt, resting(empty_balance), frame, progress=0.4)
    frame, loaded = yield from _window(start, frame, "с грузом", (0.42, 0.62))
    loaded_balance = _balance(loaded)
    frame, loaded_move = yield from _move(loaded_balance, frame, direction, f"с грузом, {word}", (0.62, 0.85))
    frame = yield from land(loaded_balance, frame, progress=0.88)
    frame, _ = yield from ask(ctx.operator, Prompt("Снимите груз с грифа и нажмите «Готово»"), resting(loaded_balance), frame, progress=0.95)
    return {"empty": empty, "loaded": loaded, "empty_move": empty_move, "loaded_move": loaded_move, "direction": direction, "referenceKg": kg}


def fit_loaded(data: dict[str, Any], _ctx: Context) -> Outcome:
    direction = data["direction"]
    kg = data["referenceKg"]
    empty, loaded = fit_balance(data["empty"]), fit_balance(data["loaded"])
    reference = kg / 2 * G
    key = "friction_load_up" if direction > 0 else "friction_load_down"
    word = "подъёма" if direction > 0 else "опускания"
    sides: dict[Side, dict[str, tuple[Any, float | None]]] = {}
    report = []
    for side in SIDES:
        delta_w = loaded.weight_n[side].mean - empty.weight_n[side].mean
        if delta_w < 0.3 * reference:
            raise ProcedureError(f"{side}: груз не обнаружен (ΔW = {delta_w:.0f} Н при ожидаемых ≈{reference:.0f} Н)")
        widening = (loaded.coulomb_up_n[side].mean + loaded.coulomb_down_n[side].mean - empty.coulomb_up_n[side].mean - empty.coulomb_down_n[side].mean) / 2
        mu_mean = widening / delta_w
        f_empty, f_loaded = data["empty_move"]["force"][side], data["loaded_move"]["force"][side]
        delta_f = f_loaded - f_empty
        mu = delta_f / reference - 1 if direction > 0 else 1 - delta_f / reference
        sides[side] = {key: (round(mu, 4), None)}
        report.append(line(
            f"{SIDE_LABEL[side]}: сила {word} 20 мм/с без груза → с грузом",
            f"{f_empty:.0f} → {f_loaded:.0f} Н при грузе {reference:.0f} Н: μ{'⁺' if direction > 0 else '⁻'} = {mu:+.3f}",
            -0.05 <= mu <= 0.5,
        ))
        report.append(line(
            f"{SIDE_LABEL[side]}: проверка по окну (без шкалы силы)",
            f"вес +{delta_w:.0f} Н, трение +{widening:.1f} Н: среднее (μ⁺ + μ⁻)/2 = {mu_mean:+.3f}",
        ))
        report.append(line(f"{SIDE_LABEL[side]}: сила {word} с грузом", f"{f_loaded:.0f} Н ({n_to_kgf(f_loaded):.1f} кгс)"))
    mean_mu = mean([sides[side][key][0] for side in SIDES])
    report.append(line("На 100 кг груза трение вырастет на", f"{n_to_kgf(mean_mu * 50 * G):.1f} кгс на сторону ({'вверх' if direction > 0 else 'вниз'})"))
    return Outcome(report=report, sides=sides, data={"referenceKg": kg, "empty_move": data["empty_move"], "loaded_move": data["loaded_move"]})


def _envelope() -> ProcedureEnvelope:
    return ProcedureEnvelope(max_x_mm=200.0)


SPECS = {
    "L1": (lambda ctx: (loaded_friction(ctx, +1), _envelope()), fit_loaded),
    "L2": (lambda ctx: (loaded_friction(ctx, -1), _envelope()), fit_loaded),
}
