"""Holding, weightlessness and side sync (H1, H2, W1, W2, X3).

* H1 hold under load: the core's hold law (window + friction compensation in
  motion + spring ``k·(x0 − x) − c·v``) at 80 mm; a load is simulated by a force
  step beyond the friction (expected deflection 4 mm) up and down. Stiffness
  0.15…0.5·K_u: the stiffest one without oscillation → ``hold_k``, ``hold_c``.
* H2 hold by hand: the operator presses the held bar down and pulls it up;
  deflection, return and oscillation after release. Check only.
* W1 weightless gains: the core's weightless law ``W + g·Fc·sign(v) − c·v``; a
  short push up (down) and the coast after it. The largest ``g`` with which the
  bar still stops by itself within 40 mm → ``weightless_gain_up/down``.
* W2 weightless by hand: the operator lifts the bar by ~10 cm and lowers it;
  the estimated hand force (model) and the drift after release. Check only.
* X3 side sync: moves with a skew correction ``k·(x_other − x)``; the gain
  with the smallest skew (no oscillation) → ``sync_k_n_per_mm``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from app.motor.calibration.procedures.common import (
    Context,
    Outcome,
    Procedure,
    ask,
    hold_gains,
    line,
    mean,
    observe,
    recenter,
    sign_changes,
    spring_forces,
    weightless_forces,
)
from app.motor.calibration.procedures.motion import Balance, hold_still, land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError, Prompt
from app.motor.units import SIDES, Side, n_to_kgf

SIDE_LABEL = {"left": "Л", "right": "П"}
HOLD_ABORT_MM = 40.0
LOAD_RATE_PER_S = 0.5  # H1: share of 2·Fc added per second until the bar yields
COAST_LIMIT_MM = 20.0  # W1: after a push the bar must stop by itself within this
UNSTABLE_MM_S = 65.0  # a candidate that throws the bar faster is unstable: stop it before the envelope (80 mm/s)


def _gains(ctx: Context) -> tuple[float, float]:
    up, down = ctx.profile.weightless_gain_up.value, ctx.profile.weightless_gain_down.value
    return (float(up) if up is not None else 0.6, float(down) if down is not None else 0.6)


def _hold_law(balance: Balance, x0: dict[Side, float], k: float, c: float, gains: tuple[float, float]) -> Callable[[Frame], dict[Side, float]]:
    """The core's hold: window + friction compensation in motion + a spring limited to 2·Fc + 50 N."""

    limit = 2 * max(balance.coulomb_up.values()) + 50.0

    def forces(frame: Frame) -> dict[Side, float]:
        base = weightless_forces(balance, frame, gains[0], gains[1], damping=0.0)
        spring = spring_forces(balance, frame, x0, k, c, limit_n=limit)
        return {side: base[side] + spring[side] - balance.weight(side, frame.x(side)) for side in SIDES}

    return forces


# ---------------------------------------------------------------- H1
def hold_under_load(ctx: Context, *, fractions: tuple[float, ...] = (0.15, 0.25, 0.35, 0.5), x_mm: float = 80.0, step_s: float = 1.5) -> Procedure:
    balance = ctx.balance
    k_u, period = ctx.profile.hold_ultimate_k_n_per_mm.value, ctx.profile.hold_ultimate_period_s.value
    if k_u is None or period is None:
        raise ProcedureError("нет результата C1 (предельная жёсткость удержания)")
    k_u, period = float(k_u), float(period)
    gains = _gains(ctx)
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, fraction in enumerate(fractions):
        progress = 0.05 + 0.85 * index / len(fractions)
        frame = yield from recenter(balance, frame, x_mm, progress)
        k, c = fraction * k_u, 0.25 * k_u * period / 6.3
        x0 = {side: frame.x(side) for side in SIDES}
        x0_mean = mean(list(x0.values()))
        law = _hold_law(balance, x0, k, c, gains)
        # the "user": the load grows at LOAD_RATE until the bar yields (> 1 mm), then stays — like a hand pushing
        cap = {1: {side: 2.0 * balance.coulomb_up[side] for side in SIDES}, -1: {side: 2.0 * balance.coulomb_down[side] for side in SIDES}}
        applied: dict[int, float] = {}
        phases = ((0, 1.0), (1, step_s), (0, step_s), (-1, step_s), (0, step_s))
        rows: list[tuple[int, int, float, float]] = []  # (phase index, load sign, dx, v)
        aborted = False
        for phase_index, (sign, seconds) in enumerate(phases):
            t_phase, end, share, yielded = frame.t, frame.t + seconds, 0.0, False
            while frame.t < end:
                forces = law(frame)
                if sign:
                    if not yielded:
                        share = min(1.0, LOAD_RATE_PER_S * (frame.t - t_phase))
                    forces = {side: forces[side] + sign * share * cap[sign][side] for side in SIDES}
                frame = yield Command(forces, note=f"удержание k = {k:.2f} Н/мм: {'нагрузка вверх' if sign > 0 else 'нагрузка вниз' if sign < 0 else 'без нагрузки'}", progress=progress)
                dx = frame.x_mean - x0_mean
                rows.append((phase_index, sign, dx, frame.v_mean))
                if sign and not yielded and sign * dx > 1.0:
                    yielded = True
                if abs(dx) > HOLD_ABORT_MM or abs(frame.v_mean) > UNSTABLE_MM_S:
                    aborted = True
                    break
            if sign:
                applied[sign] = share * mean(list(cap[sign].values()))
            if aborted:
                break
        # in motion the law compensates g·Fc: the load beyond the rest of friction is taken by the spring alone
        friction = {1: (1 - gains[0]) * mean(list(balance.coulomb_up.values())), -1: (1 - gains[1]) * mean(list(balance.coulomb_down.values()))}
        expected = {sign: max(load - friction[sign], 0.0) / k for sign, load in applied.items()}
        frame = yield from hold_still(balance, frame, progress=progress)
        runs.append({"k": k, "c": c, "fraction": fraction, "rows": rows, "aborted": aborted, "load": {str(key): value for key, value in applied.items()}, "expected_mm": {str(key): value for key, value in expected.items()}})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "k_u": k_u}


def _hold_metrics(run: dict[str, Any]) -> dict[str, Any]:
    rows = run["rows"]
    up = max((dx for _p, sign, dx, _v in rows if sign > 0), default=0.0)
    down = min((dx for _p, sign, dx, _v in rows if sign < 0), default=0.0)
    released = [v for p, sign, _dx, v in rows if sign == 0 and p > 0]
    oscillation = sign_changes(released, 2.0)
    expected = run["expected_mm"]
    stable = not run["aborted"] and oscillation <= 2 and up <= 2 * expected.get("1", 0.0) + 4 and -down <= 2 * expected.get("-1", 0.0) + 4
    return {"up_mm": up, "down_mm": down, "oscillation": oscillation, "stable": stable}


def fit_hold(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = [{**run, **_hold_metrics(run)} for run in data["runs"]]
    stable = [run for run in runs if run["stable"]]
    best = max(stable, key=lambda run: run["k"]) if stable else None
    report = [
        line(
            f"k = {run['k']:.2f} Н/мм ({run['fraction']:.2f}·Kᵤ)",
            "раскачка — прервано" if run["aborted"] else
            f"гриф поддался при {run['load'].get('1', 0):.0f} / {run['load'].get('-1', 0):.0f} Н: прогиб +{run['up_mm']:.1f} / {run['down_mm']:.1f} мм, колебаний после снятия {run['oscillation']}",
            run["stable"],
        )
        for run in runs
    ]
    if best:
        report.append(line("Выбрано удержание", f"k = {best['k']:.2f} Н/мм, c = {best['c']:.2f} Н·с/мм ({n_to_kgf(best['k'] * 10):.1f} кгс на 10 мм сверх трения)"))
    return Outcome(
        report=report,
        machine={"hold_k_n_per_mm": (round(best["k"], 3), None), "hold_c_n_per_mm_s": (round(best["c"], 3), None)} if best else {},
        data={"runs": [{key: value for key, value in run.items() if key != "rows"} for run in runs]},
        error=None if best else "ни одна жёсткость не держит гриф без раскачки: повторите C1",
    )


# ---------------------------------------------------------------- H2
def hold_by_hand(ctx: Context, *, x_mm: float = 100.0) -> Procedure:
    balance = ctx.balance
    k, c = hold_gains(ctx.profile)
    gains = _gains(ctx)
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from recenter(balance, frame, x_mm, 0.1)
    x0 = {side: frame.x(side) for side in SIDES}
    x0_mean = mean(list(x0.values()))
    law = _hold_law(balance, x0, k, c, gains)
    runs = []
    for index, (direction, text) in enumerate(((-1, "Плавно надавите на гриф вниз (5–10 кг), подержите 2 с и отпустите"), (1, "Плавно потяните гриф вверх (5–10 кг), подержите 2 с и отпустите"))):
        progress = 0.2 + 0.35 * index
        peak = {"dx": 0.0}

        def pressed(f: Frame, direction: int = direction, peak: dict[str, float] = peak) -> bool:
            peak["dx"] = max(peak["dx"], direction * (f.x_mean - x0_mean))
            return peak["dx"] > 3.0

        frame, _ = yield from ask(ctx.operator, Prompt(text, kind="action"), law, frame, progress=progress, done=pressed)
        released_v: list[float] = []
        still, t_wait = 0, frame.t
        while still < 20 and frame.t - t_wait < 20.0:  # until the bar stands 1 s (release)
            frame = yield Command(law(frame), note="ждём, пока гриф отпустят и он остановится", progress=progress + 0.2)
            peak["dx"] = max(peak["dx"], direction * (frame.x_mean - x0_mean))
            released_v.append(frame.v_mean)
            still = still + 1 if abs(frame.v_mean) < 1.0 else 0
        runs.append({"direction": direction, "deflection_mm": peak["dx"], "residual_mm": frame.x_mean - x0_mean, "oscillation": sign_changes(released_v[-60:], 2.0), "stopped": still >= 20})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "k": k, "c": c, "friction": {"1": mean(list(balance.coulomb_up.values())), "-1": mean(list(balance.coulomb_down.values()))}}


def fit_hold_by_hand(data: dict[str, Any], _ctx: Context) -> Outcome:
    k = data["k"]
    report, failed = [], []
    for run in data["runs"]:
        friction = data["friction"][str(run["direction"])]
        force = friction + k * max(run["deflection_mm"], 0.0)
        ok = run["stopped"] and run["oscillation"] <= 2
        if not ok:
            failed.append("вниз" if run["direction"] < 0 else "вверх")
        report.append(line(
            f"Нажим {'вниз' if run['direction'] < 0 else 'вверх'}",
            f"прогиб {run['deflection_mm']:.1f} мм (≈ {n_to_kgf(2 * force):.1f} кгс на гриф), остался {run['residual_mm']:+.1f} мм, колебаний {run['oscillation']}",
            ok,
        ))
    report.append(line("Удержание", f"k = {k:.2f} Н/мм, c = {data['c']:.2f} Н·с/мм"))
    return Outcome(report=report, data={"runs": data["runs"]}, error=f"после нажима {', '.join(failed)} гриф раскачивается или не останавливается: повторите H1" if failed else None)


# ---------------------------------------------------------------- W1
def weightless_tuning(ctx: Context, *, candidates: tuple[float, ...] = (0.3, 0.5, 0.7, 0.85), x_mm: float = 100.0, push_fc: float = 1.3, push_s: float = 0.4) -> Procedure:
    balance = ctx.balance
    frame = yield Command(None, note="старт", progress=0.0)
    best = {1: 0.5, -1: 0.5}
    runs: list[dict[str, Any]] = []
    total = 2 * len(candidates)
    count = 0
    for direction in (1, -1):
        for gain in candidates:
            progress = 0.05 + 0.85 * count / total
            count += 1
            frame = yield from recenter(balance, frame, x_mm, progress)
            gains = (gain, best[-1]) if direction > 0 else (best[1], gain)
            x_rest = frame.x_mean
            end = frame.t + 1.0
            while frame.t < end:
                frame = yield Command(weightless_forces(balance, frame, *gains), note=f"невесомость g = {gain:.2f}: покой", progress=progress)
            drift = abs(frame.x_mean - x_rest)
            end = frame.t + push_s
            while frame.t < end and direction * frame.v_mean < 25.0:
                forces = weightless_forces(balance, frame, *gains)
                push = {side: direction * push_fc * balance.friction(side, direction) for side in SIDES}
                frame = yield Command({side: forces[side] + push[side] for side in SIDES}, note=f"невесомость g = {gain:.2f}: толчок {'вверх' if direction > 0 else 'вниз'}", progress=progress)
            x_release, t_release, still = frame.x_mean, frame.t, 0
            runaway = False
            while still < 5:
                frame = yield Command(weightless_forces(balance, frame, *gains), note=f"невесомость g = {gain:.2f}: выбег", progress=progress)
                still = still + 1 if abs(frame.v_mean) < 1.0 else 0
                if frame.t - t_release > 4.0 or abs(frame.x_mean - x_release) > 50.0 or abs(frame.v_mean) > UNSTABLE_MM_S:
                    runaway = True
                    break
            if runaway:
                frame = yield from hold_still(balance, frame, progress=progress)
            coast = direction * (frame.x_mean - x_release)
            ok = not runaway and coast <= COAST_LIMIT_MM and drift < 2.0
            runs.append({"direction": direction, "gain": gain, "coast_mm": coast, "drift_mm": drift, "runaway": runaway, "ok": ok})
            if not ok:
                break
            best[direction] = gain
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "best": {str(key): value for key, value in best.items()}}


def fit_weightless(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    report = [
        line(
            f"{'↑' if run['direction'] > 0 else '↓'} g = {run['gain']:.2f}",
            "уплывает" if run["runaway"] else f"выбег {run['coast_mm']:.0f} мм, дрейф в покое {run['drift_mm']:.1f} мм",
            run["ok"],
        )
        for run in runs
    ]
    up, down = data["best"]["1"], data["best"]["-1"]
    report.append(line("Компенсация трения в невесомости", f"вверх {up:.2f}, вниз {down:.2f}"))
    return Outcome(report=report, machine={"weightless_gain_up": (up, None), "weightless_gain_down": (down, None)}, data=data)


# ---------------------------------------------------------------- W2
def weightless_by_hand(ctx: Context, *, x_mm: float = 100.0, stroke_mm: float = 60.0) -> Procedure:
    balance = ctx.balance
    gains = _gains(ctx)
    masses = {side: float(ctx.profile.side(side).moving_mass_kg.value) for side in SIDES}
    viscous = {side: float(ctx.profile.side(side).viscous_n_per_mm_s.value) for side in SIDES}
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from recenter(balance, frame, x_mm, 0.1)
    runs = []
    for index, (direction, text) in enumerate(((1, "Невесомость включена. Медленно поднимите гриф руками примерно на 10 см и отпустите"), (-1, "Медленно опустите гриф руками примерно на 10 см и отпустите"))):
        progress = 0.2 + 0.35 * index
        x_start = frame.x_mean
        effort: list[float] = []
        previous = {"frame": frame}

        def track(f: Frame, effort: list[float] = effort, previous: dict[str, Frame] = previous) -> dict[Side, float]:
            forces = weightless_forces(balance, f, *gains)
            prev = previous["frame"]
            dt = f.t - prev.t
            if dt > 0 and abs(f.v_mean) > 5.0:
                total = 0.0
                for side in SIDES:
                    v = f.v(side)
                    a = (v - prev.v(side)) / dt
                    friction = (balance.coulomb_up[side] if v > 0 else -balance.coulomb_down[side]) + viscous[side] * v
                    total += masses[side] * a / 1000 + balance.weight(side, f.x(side)) + friction - forces[side]
                effort.append(total)
            previous["frame"] = f
            return forces

        state = {"still": 0}

        def moved(f: Frame, direction: int = direction, x_start: float = x_start, state: dict[str, int] = state) -> bool:
            far = direction * (f.x_mean - x_start) > stroke_mm
            state["still"] = state["still"] + 1 if far and abs(f.v_mean) < 1.0 else 0
            return state["still"] >= 20

        frame, _ = yield from ask(ctx.operator, Prompt(text, kind="action"), track, frame, progress=progress, done=moved)
        x_release, t_release = frame.x_mean, frame.t
        while frame.t - t_release < 3.0:
            frame = yield Command(weightless_forces(balance, frame, *gains), note="гриф отпущен: проверка дрейфа", progress=progress + 0.2)
        runs.append({"direction": direction, "effort_n": mean(effort), "peak_n": max((direction * e for e in effort), default=0.0), "drift_mm_s": abs(frame.x_mean - x_release) / 3.0, "samples": len(effort)})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "gains": list(gains)}


def fit_weightless_by_hand(data: dict[str, Any], _ctx: Context) -> Outcome:
    report, drifting = [], []
    for run in data["runs"]:
        label = "Подъём руками" if run["direction"] > 0 else "Опускание руками"
        ok = run["drift_mm_s"] < 2.0
        if not ok:
            drifting.append(label.lower())
        report.append(line(label, f"усилие ≈ {n_to_kgf(abs(run['effort_n'])):.1f} кгс (пик {n_to_kgf(run['peak_n']):.1f}), дрейф после отпускания {run['drift_mm_s']:.1f} мм/с", ok))
    report.append(line("Компенсация трения вверх / вниз", f"{data['gains'][0]:.2f} / {data['gains'][1]:.2f}"))
    return Outcome(report=report, data=data, error=f"гриф уплывает после отпускания ({', '.join(drifting)}): повторите W1" if drifting else None)


# ---------------------------------------------------------------- X3
def sync_tuning(ctx: Context, *, shares: tuple[float, ...] = (0.0, 0.05, 0.1, 0.2), low_mm: float = 40.0, high_mm: float = 160.0, speed_mm_s: float = 25.0) -> Procedure:
    balance = ctx.balance
    coupling = ctx.profile.side_coupling_n_per_mm.value
    coupling = float(coupling) if coupling else 40.0
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, share in enumerate(shares):
        progress = 0.05 + 0.85 * index / len(shares)
        k = share * coupling
        tuned = replace(balance, sync_k=k)
        frame = yield from recenter(tuned, frame, low_mm, progress)
        skews: list[float] = []

        def record(f: Frame, skews: list[float] = skews) -> None:
            if abs(f.v_mean) > 3.0:
                skews.append(f.x("left") - f.x("right"))

        frame = yield from observe(travel(tuned, frame, high_mm, speed_mm_s=speed_mm_s, note=f"синхронизация k = {k:.1f} Н/мм: вверх", progress_span=progress), record)
        frame = yield from observe(travel(tuned, frame, low_mm, speed_mm_s=speed_mm_s, note=f"синхронизация k = {k:.1f} Н/мм: вниз", progress_span=progress), record)
        if not skews:
            raise ProcedureError("гриф не двигался")
        avg = mean(skews)
        runs.append({
            "k": k,
            "rms_mm": (sum(s * s for s in skews) / len(skews)) ** 0.5,
            "max_mm": max(abs(s) for s in skews),
            "oscillation": sign_changes([s - avg for s in skews], 0.3),
        })
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "coupling": coupling}


def fit_sync(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    calm = [run for run in runs if run["oscillation"] <= 6] or runs
    floor = min(run["rms_mm"] for run in calm)
    best = min((run for run in calm if run["rms_mm"] <= 1.1 * floor + 0.05), key=lambda run: run["k"])
    report = [line(f"k = {run['k']:.1f} Н/мм", f"перекос СКО {run['rms_mm']:.2f} мм, макс {run['max_mm']:.2f} мм, колебаний {run['oscillation']}", run is best) for run in runs]
    report.append(line("Выравнивание сторон", f"{best['k']:.1f} Н/мм (жёсткость грифа {data['coupling']:.0f} Н/мм)", best["max_mm"] <= 5.0))
    return Outcome(report=report, machine={"sync_k_n_per_mm": (round(best["k"], 2), None)}, data={"runs": runs})


SPECS = {
    "H1": (lambda ctx: (hold_under_load(ctx), ProcedureEnvelope(max_x_mm=130.0)), fit_hold),
    "H2": (lambda ctx: (hold_by_hand(ctx), ProcedureEnvelope(max_x_mm=180.0)), fit_hold_by_hand),
    "W1": (lambda ctx: (weightless_tuning(ctx), ProcedureEnvelope(max_x_mm=170.0)), fit_weightless),
    "W2": (lambda ctx: (weightless_by_hand(ctx), ProcedureEnvelope(max_x_mm=260.0)), fit_weightless_by_hand),
    "X3": (lambda ctx: (sync_tuning(ctx), ProcedureEnvelope(max_x_mm=200.0)), fit_sync),
}
