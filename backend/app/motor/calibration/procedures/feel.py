"""Free-weight feel (F1–F11, X4, G2): the trainer's own law with a virtual user.

A free weight of load L has the weight L·g *and* the inertia M = L/g, no friction, no stiction, no
dead zone and nothing at the ends of the travel. The machine has ≈60 kg of reflected mass per side,
friction that depends on speed, height and load, a bus delay and a torque dead zone. Each calibration
here tunes one compensation of the trainer's law (``MotorCore``) so that what is left for the user is as
close as possible to L·g + M·a:

* F1 — how much of the machine mass the law may cancel before the delayed acceleration feedback rings;
* F2 — the share for each load so that the felt mass is M (two pushes: m = ΔP/Δa, friction-free);
* F3 — friction at exercise speeds (40…160 mm/s) instead of the 12–40 mm/s extrapolation;
* F4 — friction sign smoothing at the turn of a rep: least sticking without chatter;
* F5 — phase hysteresis and blend (eccentric load) without flicker at the turn;
* F6 — softened compensation right after a start from rest: no jump when the stiction lets go;
* F7 — compensation of the screw ripple and the friction map along the travel (S6, S8/S10);
* F8 — inverse of the torque dead zone around zero force (D1);
* F9 — dither against the static friction window (the bar held still feels the exact load);
* F10 — cushions at the ends of the travel: a dropped or thrown bar is braked softly;
* F11 — release detection: what the user-force estimate shows while held vs released;
* X4 — side synchronisation at exercise speed;
* G2 — check: felt mass, residual friction and sticking at the turn for 5/10/20 kg per side.

The virtual user is a force added to the law's command (``trainer.py``): known exactly, applied through
the same drive and bus delay as a hand. Its speed correction is kept weak (m/4T) so it does not ring.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from app.motor.calibration.fit import least_squares
from app.motor.calibration.procedures.common import (
    Context,
    Gen,
    Outcome,
    Procedure,
    line,
    mean,
    recenter,
    sign_changes,
    steady,
)
from app.motor.calibration.procedures.motion import Balance, Motion, hold_still, land, travel
from app.motor.calibration.procedures.trainer import (
    Row,
    Trainer,
    drive,
    expected,
    handoff,
    rep_user,
    reversals,
    slope,
    user_gain,
)
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError
from app.motor.core import DEADBAND_BLEND_N
from app.motor.force.load_models import LoadSetpoint
from app.motor.profile import MachineProfile, Measured
from app.motor.units import SIDES, Side, kgf_to_n, n_to_kgf, smooth_sign

SIDE_LABEL = {"left": "Л", "right": "П"}
FEEL_SPEED_MM_S = 160.0  # envelope of the virtual-user tests
PUSH_START_MM = 100.0


def _with(profile: MachineProfile, **values: Any) -> MachineProfile:
    return replace(profile, **{key: Measured(value, None, "measured") for key, value in values.items()})


def _end(balance: Balance, frame: Frame, progress: float) -> Gen:
    frame = yield from hold_still(balance, frame, progress=progress)
    return frame


# ---------------------------------------------------------------- F1
F1_RATIOS = (0.2, 0.35, 0.5, 0.65, 0.8, 0.9)
BRAKE_S = 0.1
DEFAULT_RATIO = 0.5  # without F1: half of the machine mass at most


def _coast(rows: list[Row], x0: float) -> dict[str, Any]:
    if not rows:
        return {"coast_mm": 0.0, "stopped": False, "swings": 0, "peak_after_mm_s": 0.0, "force_swing_n": 0.0}
    stop = next((i for i, r in enumerate(rows) if abs(r.v) < 2.0), None)
    after = rows[stop:] if stop is not None else []
    return {
        "coast_mm": round(((rows[stop].x if stop is not None else rows[-1].x) - x0) if rows else 0.0, 1),
        "stopped": stop is not None,
        "swings": sign_changes([r.v for r in after], 3.0),
        "peak_after_mm_s": round(max((abs(r.v) for r in after), default=0.0), 1),
        "force_swing_n": round(max((r.force for r in after), default=0.0) - min((r.force for r in after), default=0.0), 1),
    }


def inertia_limit(ctx: Context, ratios: tuple[float, ...] = F1_RATIOS) -> Procedure:
    balance = ctx.balance
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, ratio in enumerate(ratios):
        progress = 0.05 + 0.85 * index / len(ratios)
        result: dict[str, Any] = {"ratio": ratio, "runs": [], "stable": True}
        for direction in (1, -1):
            frame = yield from recenter(balance, frame, 150.0 if direction > 0 else 260.0, progress)
            frame = yield from handoff(balance, frame, direction, 30.0, note=f"компенсация инерции {ratio:.0%}: разгон", progress=progress)
            trainer = Trainer(ctx, inertia=ratio)
            rows: list[Row] = []
            x0 = frame.x_mean
            # a hand brakes the bar sharply for two frames (~0.5 m/s² beyond the friction), then lets go: the delayed
            # acceleration feedback rings after such a stop if the share is too high
            machine = mean([float(ctx.profile.side(side).moving_mass_kg.value) for side in SIDES])
            brake = machine * (1 - ratio) * 0.5 + mean([balance.friction(side, direction) for side in SIDES])
            t_brake = frame.t

            def probe(f: Frame, direction: int = direction, brake: float = brake, t_brake: float = t_brake) -> float:
                return -direction * brake if f.t - t_brake < BRAKE_S else 0.0

            frame, why = yield from drive(
                trainer, frame, probe, seconds=1.5, note=f"компенсация инерции {ratio:.0%}: торможение и выбег {'вверх' if direction > 0 else 'вниз'}",
                progress=progress, rows=rows, x_range=(x0 - 60, x0 + 60), speed_cap=90.0,
            )
            frame = yield from _end(balance, frame, progress)
            settle = t_brake + BRAKE_S + 0.1  # judge the coast after the hand let go (and one frame of delay)
            metrics = _coast([r for r in rows if r.t >= settle], x0)
            ok = why == "time" and metrics["stopped"] and metrics["swings"] <= 1 and metrics["peak_after_mm_s"] <= 15.0
            result["runs"].append({"direction": direction, "why": why, "ok": ok, **metrics})
            if not ok:
                result["stable"] = False
                break
        runs.append(result)
        if not result["stable"]:
            break
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_inertia_limit(data: dict[str, Any], _ctx: Context) -> Outcome:
    report = []
    last = None
    for run in data["runs"]:
        parts = [
            f"{'↑' if r['direction'] > 0 else '↓'} выбег {r['coast_mm']:+.0f} мм, колебаний {r['swings']}, после остановки до {r['peak_after_mm_s']:.0f} мм/с" + ("" if r["why"] == "time" else " — прервано")
            for r in run["runs"]
        ]
        report.append(line(f"Компенсация {run['ratio']:.0%} массы", "; ".join(parts), run["stable"]))
        if run["stable"]:
            last = run["ratio"]
    if last is None:
        return Outcome(report=report, error="компенсация инерции раскачивает гриф даже на 20 %: проверьте задержку (B3) и фильтр ускорения (V2)")
    limit = round(0.8 * last, 2)
    report.append(line("Предел компенсации (80 % от устойчивой)", f"{limit:.0%} массы машины"))
    return Outcome(report=report, machine={"inertia_ratio_max": (limit, None)}, data={"last_stable": last})


# ---------------------------------------------------------------- F2 / G2: felt mass by a wobbling hand
F2_LOADS_KGF = (2.0, 5.0, 10.0, 20.0)
F2_SHARES = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25)
WOBBLE_HZ = 1.0  # a rep-like frequency; the screw ripple at 50 mm/s is at 1.6 Hz
WOBBLE_S = 2.2
WOBBLE_SPEED_MM_S = 60.0
MASS_TOLERANCE = 1.4  # one wobble scatters ±15–20 % (screw ripple, short window): G2 only catches gross overshoot
WOBBLE_SWING_MM_S = 15.0  # target speed swing: the bar keeps moving up (one friction sign)
TRIM_S = 0.2  # before the swing the hand finds the force that keeps the speed


def _wobble(
    ctx: Context, frame: Frame, load_kgf: float, *, note: str, progress: float, profile: MachineProfile | None = None, inertia: float | None = None,
    balance: Balance | None = None, held_n: float | None = None, plain: bool = False,
) -> Gen:
    """The bar moving up at 50 mm/s in the law at ``load_kgf``; the virtual user adds A·sin(ωt).

    With one friction sign the friction is a constant: the speed swings by A/(m·ω) — the mass the user feels
    at a rep-like frequency, including what the delayed inertia compensation really does. The mean
    acceleration gives the friction the law left to the user.
    """

    balance = balance or ctx.balance  # moves to the start; the law itself works from the profile
    load_n = kgf_to_n(load_kgf)
    mass, residual = expected(ctx, load_n, speed_mm_s=WOBBLE_SPEED_MM_S, profile=profile, inertia=inertia)
    omega = 2 * math.pi * WOBBLE_HZ
    amplitude = max(5.0, mass * omega * WOBBLE_SWING_MM_S / 1000)
    # what the hand holds: the virtual load (a real hung weight carried by the law is not the hand's)
    held = load_n if held_n is None else held_n
    base = held + residual
    frame = yield from recenter(balance, frame, PUSH_START_MM, progress)
    frame = yield from handoff(balance, frame, +1, WOBBLE_SPEED_MM_S, note=f"{note}: разгон", progress=progress)
    trainer = Trainer(ctx, load=LoadSetpoint(load_n=load_n), profile=profile, inertia=inertia, plain=plain)
    x0 = frame.x_mean
    trim: list[Row] = []
    frame, _ = yield from drive(trainer, frame, lambda _f: base, seconds=TRIM_S, note=f"{note}: подбор усилия", progress=progress, rows=trim,
                                x_range=(x0 - 40.0, x0 + 190.0), speed_cap=FEEL_SPEED_MM_S - 10)
    drift = slope([(r.t, r.v) for r in trim[1:]])
    if drift is not None:  # the friction the model did not know: the hand adds what stops the drift
        base -= mass * drift / 1000
    rows: list[Row] = []
    t0 = frame.t
    gain = user_gain(ctx, mass)
    recent: list[tuple[float, float]] = []

    def hand(f: Frame) -> float:
        # the hand keeps the mean speed: its correction uses the speed averaged over one swing period,
        # which has no component at the swing frequency and so does not bias the felt mass
        recent.append((f.t, f.v_mean))
        while recent and f.t - recent[0][0] > 1.0 / WOBBLE_HZ:
            recent.pop(0)
        steady_speed = mean([v for _t, v in recent])
        return base + gain * (WOBBLE_SPEED_MM_S - steady_speed) + amplitude * math.sin(omega * (f.t - t0))

    frame, why = yield from drive(
        trainer, frame, hand, seconds=WOBBLE_S, note=f"{note}: покачивание {WOBBLE_HZ:g} Гц", progress=progress,
        rows=rows, until=lambda f: f.x_mean > x0 + 170.0, x_range=(x0 - 40.0, x0 + 190.0), speed_cap=FEEL_SPEED_MM_S - 10,
    )
    frame = yield from _end(balance, frame, progress)
    usable = [r for r in rows[2:] if r.v > 3.0]
    result: dict[str, Any] = {"amplitude_n": round(amplitude, 2), "base_n": round(base, 2), "frames": len(usable), "why": why, "share": trainer.core.inertia_share("left"), "mass_kg": None, "residual_n": None}
    if len(usable) >= 12:
        try:
            fit = least_squares([[1.0, r.t - t0, (r.t - t0) ** 2, math.sin(omega * (r.t - t0)), math.cos(omega * (r.t - t0))] for r in usable], [r.v for r in usable])
        except ValueError:
            return frame, result
        swing = math.hypot(fit.coef[3], fit.coef[4])
        if swing > 1.0:
            # impedance Z = F/V = c + jωm: the push acts after the bus delay τ (phasor A·e^(−jωτ)); sin ↔ 1, cos ↔ j.
            # The real part is damping (viscous friction, the law's own speed terms, friction growing with the
            # force) — taking |Z| as ωm would count it as mass
            tau = (_value_or(ctx.profile.loop_delay_s, 0.04)) + (_value_or(ctx.profile.torque_lag_s, 0.0))
            push = complex(math.cos(omega * tau), -math.sin(omega * tau)) * amplitude
            impedance = push / complex(fit.coef[3], fit.coef[4])
            felt = 1000 * impedance.imag / omega
            if felt <= 0:
                return frame, result
            accel = fit.coef[1] + fit.coef[2] * (usable[0].t + usable[-1].t - 2 * t0)  # mean slope over the window
            result.update(
                mass_kg=round(felt, 1), residual_n=round(base - held - felt * accel / 1000, 1), swing_mm_s=round(swing, 1),
                damping_n_per_mm_s=round(impedance.real, 3),
            )
    return frame, result


def _value_or(item: Any, default: float) -> float:
    return float(item.value) if item.value is not None else default


def _felt_item(ctx: Context, frame: Frame, load_kgf: float, *, progress: float, note: str, profile: MachineProfile | None = None) -> Gen:
    frame, wobble = yield from _wobble(ctx, frame, load_kgf, note=note, progress=progress, profile=profile)
    return frame, {"load_kgf": load_kgf, "load_n": kgf_to_n(load_kgf), "wobble": wobble}


def _felt(item: dict[str, Any]) -> dict[str, Any] | None:
    wobble = item["wobble"]
    if wobble["mass_kg"] is None:
        return None
    return {"mass_kg": wobble["mass_kg"], "residual_n": wobble["residual_n"], "share": wobble["share"]}


def inertia_by_load(ctx: Context, loads: tuple[float, ...] = F2_LOADS_KGF, shares: tuple[float, ...] = F2_SHARES) -> Procedure:
    """For each load: the felt mass at each compensation share within the F1 stability limit."""

    machine = mean([float(ctx.profile.side(side).moving_mass_kg.value) for side in SIDES])
    ratio = float(ctx.profile.inertia_ratio_max.value or DEFAULT_RATIO)
    frame = yield Command(None, note="старт", progress=0.0)
    items = []
    count = len(loads) * len(shares)
    for index, load in enumerate(loads):
        trials = []
        for k, share in enumerate(shares):
            if share * max(machine - load, 0.0) > ratio * machine + 1e-6:
                break  # beyond the F1 limit: the compensation would ring
            progress = 0.05 + 0.85 * (index * len(shares) + k) / count
            frame, wobble = yield from _wobble(ctx, frame, load, note=f"нагрузка {2 * load:g} кг на гриф, компенсация {share:.0%}", progress=progress, inertia=share)
            trials.append({"share": share, **wobble})
        items.append({"load_kgf": load, "load_n": kgf_to_n(load), "trials": trials})
    yield from land(ctx.balance, frame, progress=0.95)
    return {"items": items, "machine_kg": machine, "ratio": ratio}


def fit_inertia_by_load(data: dict[str, Any], _ctx: Context) -> Outcome:
    report, table = [], []
    for item in data["items"]:
        virtual = item["load_kgf"]
        label = f"{2 * virtual:g} кг на гриф"
        trials = [t for t in item["trials"] if t["mass_kg"] is not None]
        if not trials:
            report.append(line(label, "масса не измерена: гриф не прошёл покачивание", False))
            continue
        best = min(trials, key=lambda t: (abs(t["mass_kg"] - virtual), t["share"]))
        table.append((round(item["load_n"], 1), best["share"]))
        felt = ", ".join(f"{t['share']:.0%} → {t['mass_kg']:.0f}" for t in trials)
        report.append(line(
            label,
            f"ощущаемая масса на сторону по доле компенсации: {felt} кг; выбрано {best['share']:.0%}: {best['mass_kg']:.0f} кг при {virtual:g} у свободного веса, остаточное трение {best['residual_n']:+.0f} Н",
            best["mass_kg"] <= virtual + max(8.0, 0.5 * virtual),
        ))
    if not table:
        return Outcome(report=report, error="ни одна нагрузка не измерена: проверьте F1 и M2")
    report.append(line("Предел устойчивости (F1)", f"{data['ratio']:.0%} массы машины {data['machine_kg']:.0f} кг"))
    report.append(line("Таблица компенсации инерции", ", ".join(f"{n_to_kgf(n):.0f} кгс → {g:.0%}" for n, g in table)))
    return Outcome(report=report, machine={"inertia_table": (table, None)}, data={"items": data["items"]})


# ---------------------------------------------------------------- F3
F3_SPEEDS = (40.0, 80.0, 120.0, 160.0)


def friction_speed(ctx: Context, speeds: tuple[float, ...] = F3_SPEEDS) -> Procedure:
    balance = ctx.balance
    low = 80.0
    high = min(ctx.top_mm, low + 520.0)
    if high - low < 250.0:
        raise ProcedureError("для скоростей упражнения нужно ≥ 330 мм хода: выполните B8")
    viscous = {side: float(ctx.profile.side(side).viscous_n_per_mm_s.value) for side in SIDES}
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, low, progress_span=(0.0, 0.03))
    runs = []
    guess: dict[int, dict[Side, float]] = {}
    previous: dict[int, float] = {}
    for index, speed_mm_s in enumerate(speeds):
        for direction in (1, -1):
            start = {side: balance.feed(side, direction, speed_mm_s) or 0.0 for side in SIDES}
            if direction in guess:  # extrapolate the last measured point with the viscous slope
                start = {side: guess[direction][side] + viscous[side] * (speed_mm_s - previous[direction]) for side in SIDES}
            table = {side: [(speed_mm_s, start[side])] for side in SIDES}
            moving = replace(balance, table_up=table) if direction > 0 else replace(balance, table_down=table)
            state = Motion(trace=[])
            span = (0.03 + 0.9 * (2 * index + (direction < 0)) / (2 * len(speeds)), 0.03 + 0.9 * (2 * index + 1 + (direction < 0)) / (2 * len(speeds)))
            frame = yield from travel(moving, frame, high if direction > 0 else low, speed_mm_s=speed_mm_s, state=state, note=f"{'подъём' if direction > 0 else 'опускание'} {speed_mm_s:.0f} мм/с", progress_span=span)
            trace = state.trace or []
            runs.append({"direction": direction, "speed_mm_s": speed_mm_s, "trace": trace})
            speeds_seen, extras = steady(trace, speed_mm_s)
            if len(speeds_seen) >= 4:
                guess[direction] = {side: mean(extras[side]) for side in SIDES}
                previous[direction] = mean(speeds_seen)
    yield from land(balance, frame, speed_mm_s=20.0, progress=0.95)
    return {"runs": runs}


def fit_friction_speed(data: dict[str, Any], ctx: Context) -> Outcome:
    balance = ctx.balance
    tables: dict[int, dict[Side, list[tuple[float, float]]]] = {1: {side: [] for side in SIDES}, -1: {side: [] for side in SIDES}}
    for run in data["runs"]:
        speeds, extras = steady(run["trace"], run["speed_mm_s"])
        if len(speeds) < 4:
            continue
        v = mean(speeds)
        for side in SIDES:
            tables[run["direction"]][side].append((round(v, 1), round(balance.friction(side, run["direction"]) + mean(extras[side]), 1)))
    report, sides = [], {}
    for side in SIDES:
        up, down = sorted(tables[1][side]), sorted(tables[-1][side])
        if len(up) < 2 or len(down) < 2:
            raise ProcedureError("скорость не установилась хотя бы на двух уровнях в каждую сторону: проверьте M2, A1/A2")
        sides[side] = {"friction_table_up": (up, None), "friction_table_down": (down, None)}
        for label, points in (("вверх", up), ("вниз", down)):
            slope_n = (points[-1][1] - points[0][1]) / (points[-1][0] - points[0][0])
            report.append(line(
                f"{SIDE_LABEL[side]}: трение {label}",
                ", ".join(f"{v:.0f} мм/с → {f:.0f} Н" for v, f in points) + f"; рост {slope_n:.2f} Н на мм/с (D2: {float(ctx.profile.side(side).viscous_n_per_mm_s.value):.2f})",
            ))
    report.append(line("Выше 160 мм/с", "продолжается по наклону двух последних точек"))
    return Outcome(report=report, sides=sides, data={"points": {str(k): v for k, v in tables.items()}})


# ---------------------------------------------------------------- reps (F4, F5, F7, F11, X4, G2)
def _reps(ctx: Context, frame: Frame, trainer: Trainer, load_n: float, *, low: float, high: float, speed_mm_s: float, seconds: float, note: str, progress: float, rows: list[Row]) -> Gen:
    mass, residual = expected(ctx, load_n, speed_mm_s=speed_mm_s, profile=trainer.core.profile, inertia=trainer.core.inertia_override)
    user = rep_user(load_n, low, high, speed_mm_s, gain=user_gain(ctx, mass), feed_n=residual)
    return (yield from drive(trainer, frame, user, seconds=seconds, note=note, progress=progress, rows=rows, x_range=(low - 60.0, high + 60.0), speed_cap=FEEL_SPEED_MM_S - 10))


def _turns(rows: list[Row], window_s: float = 0.4) -> dict[str, Any]:
    """At each turn of a rep: time nearly still, extra direction changes (chatter), force rate."""

    turns = reversals(rows)
    sticks, chatter, jerk = [], 0, 0.0
    for i in turns:
        t0 = rows[i].t
        near = [r for r in rows if abs(r.t - t0) <= window_s]
        if len(near) < 3:
            continue
        dt = (near[-1].t - near[0].t) / max(len(near) - 1, 1)
        sticks.append(sum(dt for r in near if abs(r.v) < 3.0))
        chatter += max(0, sign_changes([r.v for r in near], 3.0) - 1)
        rates = [abs(b.force - a.force) / (b.t - a.t) for a, b in zip(near, near[1:], strict=False) if b.t > a.t]
        jerk = max([jerk, *rates])
    return {"turns": len(turns), "stick_s": round(mean(sticks), 3) if sticks else None, "chatter": chatter, "jerk_n_s": round(jerk)}


F4_BLENDS = (2.0, 4.0, 8.0, 16.0)


def reversal_blend(ctx: Context, blends: tuple[float, ...] = F4_BLENDS) -> Procedure:
    balance = ctx.balance
    load = kgf_to_n(5.0)
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, blend in enumerate(blends):
        progress = 0.05 + 0.85 * index / len(blends)
        frame = yield from recenter(balance, frame, 160.0, progress)
        trainer = Trainer(ctx, load=LoadSetpoint(load_n=load), tunables={"friction_blend_mm_s": blend}, inertia=0.0)
        rows: list[Row] = []
        frame, why = yield from _reps(ctx, frame, trainer, load, low=150.0, high=240.0, speed_mm_s=60.0, seconds=8.0, note=f"повторения, сглаживание {blend:g} мм/с", progress=progress, rows=rows)
        frame = yield from _end(balance, frame, progress)
        runs.append({"blend": blend, "why": why, **_turns(rows)})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_reversal_blend(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    valid = [r for r in runs if r["why"] == "time" and r["turns"] >= 2 and r["stick_s"] is not None and r["chatter"] == 0]
    report = [
        line(f"Сглаживание {r['blend']:g} мм/с", "прервано" if r["why"] != "time" else f"разворотов {r['turns']}, залипание {1000 * (r['stick_s'] or 0):.0f} мс, дрожание {r['chatter']}, скорость изменения силы до {r['jerk_n_s']} Н/с", r in valid)
        for r in runs
    ]
    if not valid:
        return Outcome(report=report, error="на всех значениях гриф дрожит на развороте: повторите V3 и W1")
    best = min(valid, key=lambda r: (round(r["stick_s"], 2), -r["blend"]))
    report.append(line("Выбрано", f"{best['blend']:g} мм/с: залипание на развороте {1000 * best['stick_s']:.0f} мс без дрожания"))
    return Outcome(report=report, machine={"feel_blend_mm_s": (best["blend"], None)}, data={"runs": runs})


# ---------------------------------------------------------------- F5
F5_HYSTERESES = (3.0, 6.0, 10.0, 15.0, 25.0)


def phase_tuning(ctx: Context, hystereses: tuple[float, ...] = F5_HYSTERESES) -> Procedure:
    balance = ctx.balance
    load = kgf_to_n(8.0)
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, hysteresis in enumerate(hystereses):
        progress = 0.05 + 0.85 * index / len(hystereses)
        frame = yield from recenter(balance, frame, 160.0, progress)
        trainer = Trainer(ctx, load=LoadSetpoint(mode="eccentric", load_n=load, beta=1.2), tunables={"phase_hysteresis_mm_s": hysteresis, "phase_blend_s": 0.15}, inertia=0.0)
        rows: list[Row] = []
        frame, why = yield from _reps(ctx, frame, trainer, load, low=150.0, high=240.0, speed_mm_s=60.0, seconds=8.0, note=f"эксцентрика, гистерезис {hysteresis:g} мм/с", progress=progress, rows=rows)
        frame = yield from _end(balance, frame, progress)
        phases = [r.phase for r in rows if r.phase in ("up", "down")]
        flips = sum(1 for a, b in zip(phases, phases[1:], strict=False) if a != b)
        turns = reversals(rows)
        transit = []
        for i in turns:
            sign = 1 if rows[i].v > 0 else -1  # new direction
            before = next((rows[j].t for j in range(i, -1, -1) if -sign * rows[j].v >= hysteresis), None)
            after = next((rows[j].t for j in range(i, len(rows)) if sign * rows[j].v >= hysteresis), None)
            if before is not None and after is not None:
                transit.append(after - before)
        runs.append({"hysteresis": hysteresis, "why": why, "turns": len(turns), "flips": flips, "transit_s": round(mean(transit), 3) if transit else None})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_phase(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    valid = [r for r in runs if r["why"] == "time" and r["turns"] >= 2 and r["flips"] <= r["turns"] and r["transit_s"] is not None]
    report = [
        line(f"Гистерезис {r['hysteresis']:g} мм/с", "прервано" if r["why"] != "time" else f"разворотов {r['turns']}, смен фазы {r['flips']}, переход {1000 * (r['transit_s'] or 0):.0f} мс", r in valid)
        for r in runs
    ]
    if not valid:
        return Outcome(report=report, error="фаза мигает на развороте при любом гистерезисе: проверьте шум скорости (V1, V2)")
    best = min(valid, key=lambda r: r["hysteresis"])
    blend = round(max(0.08, min(0.4, 1.5 * best["transit_s"])), 2)
    report.append(line("Выбрано", f"гистерезис {best['hysteresis']:g} мм/с, переход нагрузки {1000 * blend:.0f} мс (1,5 × время разворота)"))
    return Outcome(report=report, machine={"feel_phase_hysteresis_mm_s": (best["hysteresis"], None), "feel_phase_blend_s": (blend, None)}, data={"runs": runs})


# ---------------------------------------------------------------- F6
F6_SOFTS = (0.0, 0.1, 0.2, 0.35)


def soft_breakaway(ctx: Context, softs: tuple[float, ...] = F6_SOFTS, *, rest_s: float = 3.0, target_mm_s: float = 20.0) -> Procedure:
    balance = ctx.balance
    load = kgf_to_n(5.0)
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, soft in enumerate(softs):
        progress = 0.05 + 0.85 * index / len(softs)
        frame = yield from recenter(balance, frame, 150.0, progress)
        profile = _with(ctx.profile, breakaway_soft_s=soft)
        mass, residual = expected(ctx, load, speed_mm_s=target_mm_s, profile=profile, inertia=0.0)
        gain = user_gain(ctx, mass)
        trainer = Trainer(ctx, load=LoadSetpoint(load_n=load), profile=profile, inertia=0.0)
        state: dict[str, float | None] = {"t0": None, "moved_at": None, "push": 0.0}
        x_start = frame.x_mean

        def user(f: Frame, state: dict[str, float | None] = state, x_start: float = x_start, gain: float = gain, residual: float = residual) -> float:
            if state["t0"] is None:
                state["t0"] = f.t
            elapsed = f.t - float(state["t0"])
            if elapsed < rest_s:
                return load  # holding the bar still
            if state["moved_at"] is None:
                if f.x_mean - x_start > 0.5 and f.v_mean > 2.0:
                    state["moved_at"] = f.t
                else:
                    state["push"] = float(state["push"] or 0.0) + 3.0  # ≈ 60 N/s
                    return load + float(state["push"])
            if f.t - float(state["moved_at"]) < 0.15:  # human reaction: the push stays
                return load + float(state["push"] or 0.0)
            return load + residual + max(-60.0, min(60.0, gain * (target_mm_s - f.v_mean)))

        rows: list[Row] = []
        frame, why = yield from drive(trainer, frame, user, seconds=rest_s + 5.0, note=f"трогание после стоянки, смягчение {1000 * soft:.0f} мс", progress=progress, rows=rows,
                                      until=lambda f: f.x_mean > 260.0, x_range=(90.0, 280.0), speed_cap=FEEL_SPEED_MM_S - 10)
        frame = yield from _end(balance, frame, progress)
        moved = state["moved_at"]
        after = [r for r in rows if moved is not None and 0.0 <= r.t - moved <= 0.8]
        peak = max((r.v for r in after), default=0.0)
        runs.append({
            "soft_s": soft, "why": why, "started": moved is not None,
            "breakaway_n": round(float(state["push"] or 0.0), 1), "peak_mm_s": round(peak, 1), "overshoot_mm_s": round(peak - target_mm_s, 1),
        })
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "target_mm_s": target_mm_s}


def fit_soft_breakaway(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    valid = [r for r in runs if r["started"] and r["why"] != "range"]
    report = [
        line(f"Смягчение {1000 * r['soft_s']:.0f} мс", f"трогание при +{r['breakaway_n']:.0f} Н сверх нагрузки, затем рывок до {r['peak_mm_s']:.0f} мм/с (цель {data['target_mm_s']:.0f})" if r["started"] else "гриф не тронулся", r in valid or None)
        for r in runs
    ]
    if not valid:
        return Outcome(report=report, error="гриф не тронулся: проверьте S3 и M1")
    best = min(valid, key=lambda r: (round(r["overshoot_mm_s"]), r["soft_s"]))
    report.append(line("Выбрано", f"{1000 * best['soft_s']:.0f} мс: рывок после трогания {best['overshoot_mm_s']:+.0f} мм/с сверх цели"))
    return Outcome(report=report, machine={"breakaway_soft_s": (best["soft_s"], None)}, data={"runs": runs})


# ---------------------------------------------------------------- F7
F7_GAINS = (0.0, 0.5, 1.0)


def _track_range(ctx: Context) -> tuple[float, float]:
    """A 360-mm stretch around the strongest bump of the S10 map / S8 spots (else the lower travel)."""

    top = ctx.top_mm
    bumps: list[tuple[float, float]] = []
    for side in SIDES:
        bumps += [(float(x), abs(float(f))) for x, f in (ctx.profile.side(side).friction_map.value or [])]
    bumps += [(float(x), float(f)) for x, f in (ctx.profile.tight_spots.value or [])]
    centre = max(bumps, key=lambda b: b[1])[0] if bumps else 280.0
    low = max(80.0, min(centre - 180.0, top - 360.0))
    return low, min(top, low + 360.0)


def track_smoothing(ctx: Context, gains: tuple[float, ...] = F7_GAINS, *, speed_mm_s: float = 50.0) -> Procedure:
    balance = ctx.balance
    load = kgf_to_n(5.0)
    low, high = _track_range(ctx)
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, gain in enumerate(gains):
        progress = 0.05 + 0.85 * index / len(gains)
        frame = yield from recenter(balance, frame, low + 10.0, progress)
        trainer = Trainer(ctx, load=LoadSetpoint(load_n=load), profile=_with(ctx.profile, track_comp_gain=gain), inertia=0.0)
        rows: list[Row] = []
        seconds = 2 * (high - low) / speed_mm_s + 3.0
        frame, why = yield from _reps(ctx, frame, trainer, load, low=low, high=high, speed_mm_s=speed_mm_s, seconds=seconds, note=f"ровность хода, компенсация {gain:.0%}", progress=progress, rows=rows)
        frame = yield from _end(balance, frame, progress)
        turns = {rows[i].t for i in reversals(rows)}
        # every frame inside the stretch away from the turns — a stall in a tight spot counts fully
        inside = [r for r in rows if low + 20.0 <= r.x <= high - 20.0 and all(abs(r.t - t) > 0.6 for t in turns) and r.t - rows[0].t > 1.0] if rows else []
        unevenness = (sum((abs(r.v) - speed_mm_s) ** 2 for r in inside) / len(inside)) ** 0.5 / speed_mm_s if len(inside) > 5 else None
        runs.append({"gain": gain, "why": why, "unevenness": round(unevenness, 4) if unevenness is not None else None, "frames": len(inside)})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "range": [low, high]}


def fit_track_smoothing(data: dict[str, Any], ctx: Context) -> Outcome:
    runs = data["runs"]
    valid = [r for r in runs if r["unevenness"] is not None and r["why"] == "time"]
    report = [line(f"Компенсация {r['gain']:.0%}", f"неравномерность скорости {100 * r['unevenness']:.1f} %" if r["unevenness"] is not None else "не измерено", r in valid or None) for r in runs]
    if not valid:
        return Outcome(report=report, error="ход не прошёл на установившейся скорости: проверьте M2 и F3")
    best = min(valid, key=lambda r: (round(r["unevenness"], 3), r["gain"]))
    has_data = any(ctx.profile.side(side).screw_ripple_n.value or ctx.profile.side(side).friction_map.value for side in SIDES) or ctx.profile.tight_spots.value
    report.append(line("Участок", f"{data['range'][0]:.0f}…{data['range'][1]:.0f} мм"))
    report.append(line("Выбрано", f"{best['gain']:.0%}" + ("" if has_data else " (S6/S8/S10 не измерены — компенсировать нечего)")))
    return Outcome(report=report, machine={"track_comp_gain": (best["gain"], None)}, data={"runs": runs})


# ---------------------------------------------------------------- F8
F8_GAINS = (0.0, 0.5, 1.0)


def deadband_crossing(ctx: Context, gains: tuple[float, ...] = F8_GAINS, *, step_s: float = 0.6) -> Procedure:
    """On the stops: small forces around zero with the dead-zone inverse; the drive reports its torque (PA_1C4)."""

    deadband = {side: float(ctx.profile.side(side).deadband_raw.value or 0.0) * ctx.profile.side(side).n_per_raw_value for side in SIDES}
    span = max(max(deadband.values()) * 3.0, 6.0)
    levels = [span * k / 4 for k in (-4, -3, -2, -1, 1, 2, 3, 4)]
    frame = yield Command(None, note="старт", progress=0.0)
    if any(frame.x(side) > 15.0 for side in SIDES):
        raise ProcedureError("гриф должен лежать на упорах")
    rows = []
    for index, gain in enumerate(gains):
        for level in levels:
            forces = {side: level + gain * deadband[side] * smooth_sign(level, DEADBAND_BLEND_N) for side in SIDES}
            end = frame.t + step_s
            samples: dict[Side, list[float]] = {side: [] for side in SIDES}
            while frame.t < end:
                frame = yield Command(forces, note=f"сила около нуля: {level:+.1f} Н, обратная мёртвая зона {gain:.0%}", progress=0.05 + 0.9 * index / len(gains))
                if end - frame.t < step_s / 2:
                    for side in SIDES:
                        samples[side].append(frame.samples[side].motor_force_n)
            rows.append({"gain": gain, "level": level, "torque": {side: mean(samples[side]) for side in SIDES}})
    yield Command(None, note="поддержка", progress=1.0)
    return {"rows": rows, "deadband_n": deadband}


def fit_deadband_crossing(data: dict[str, Any], _ctx: Context) -> Outcome:
    by_gain: dict[float, list[float]] = {}
    for row in data["rows"]:
        by_gain.setdefault(row["gain"], []).extend(row["torque"][side] - row["level"] for side in SIDES)
    errors = {gain: (sum(e * e for e in values) / len(values)) ** 0.5 for gain, values in by_gain.items()}
    report = [line(f"Обратная мёртвая зона {gain:.0%}", f"ошибка момента около нуля {error:.1f} Н") for gain, error in errors.items()]
    if not any(data["deadband_n"].values()):
        report.append(line("Мёртвая зона (D1)", "нет — компенсация не нужна", True))
        return Outcome(report=report, machine={"deadband_comp_gain": (0.0, None)}, data={"errors": errors})
    best = min(errors, key=lambda gain: (round(errors[gain], 1), gain))
    report.append(line("Выбрано", f"{best:.0%}: при нагрузке около веса грифа момент не «проваливается» в ноль"))
    return Outcome(report=report, machine={"deadband_comp_gain": (best, None)}, data={"errors": {str(k): v for k, v in errors.items()}})


# ---------------------------------------------------------------- F9
F9_SHARES = (0.0, 0.15, 0.3, 0.45)


def dither_test(ctx: Context, shares: tuple[float, ...] = F9_SHARES, *, rate_n_s: float = 12.0) -> Procedure:
    balance = ctx.balance
    friction = mean([balance.coulomb_up[side] for side in SIDES])
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, share in enumerate(shares):
        progress = 0.05 + 0.85 * index / len(shares)
        amplitude = round(share * friction, 1)
        profile = _with(ctx.profile, dither_n=amplitude)
        edges: dict[int, float | None] = {}
        rest: dict[str, float] = {}
        for direction in (1, -1):
            frame = yield from recenter(balance, frame, 150.0, progress)
            trainer = Trainer(ctx, profile=profile, inertia=0.0)  # the static window only: no light-mass jump at breakaway
            rows: list[Row] = []
            frame, _ = yield from drive(trainer, frame, lambda _f: 0.0, seconds=1.5, note=f"микровибрация {amplitude:.0f} Н: покой", progress=progress, rows=rows)
            xs = [r.x for r in rows[5:]]
            if direction > 0 and xs:
                rest = {"vibration_mm": round(max(xs) - min(xs), 2), "drift_mm": round(abs(xs[-1] - xs[0]), 2)}
            x0, t0 = frame.x_mean, frame.t
            ramp = {"value": 0.0}

            def push(f: Frame, direction: int = direction, t0: float = t0, ramp: dict[str, float] = ramp) -> float:
                ramp["value"] = direction * rate_n_s * (f.t - t0)
                return ramp["value"]

            frame, why = yield from drive(trainer, frame, push, seconds=2.5 * friction / rate_n_s, note=f"микровибрация {amplitude:.0f} Н: трогание {'вверх' if direction > 0 else 'вниз'}", progress=progress,
                                          until=lambda f, x0=x0: abs(f.x_mean - x0) > 1.5, speed_cap=60.0)
            edges[direction] = abs(ramp["value"]) if why == "until" else None
            frame = yield from _end(balance, frame, progress)
        runs.append({"dither_n": amplitude, "edge_up_n": edges.get(1), "edge_down_n": edges.get(-1), **rest})
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs}


def fit_dither(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = data["runs"]
    for run in runs:
        run["width_n"] = run["edge_up_n"] + run["edge_down_n"] if run["edge_up_n"] is not None and run["edge_down_n"] is not None else None
    base = runs[0]["width_n"]
    if not base:
        raise ProcedureError("окно трогания без микровибрации не измерено")
    report, valid = [], []
    for run in runs:
        if run["width_n"] is None:
            report.append(line(f"Микровибрация {run['dither_n']:.0f} Н", "трогание не найдено", False))
            continue
        narrowing = 1 - run["width_n"] / base
        calm = run.get("vibration_mm", 0.0) <= 0.5 and run.get("drift_mm", 0.0) <= 1.0
        if calm:
            valid.append((narrowing, run))
        report.append(line(f"Микровибрация {run['dither_n']:.0f} Н", f"окно трогания {run['width_n']:.0f} Н ({100 * narrowing:+.0f} %), дрожание в покое {run.get('vibration_mm', 0):.2f} мм", calm))
    narrowing, best = max(valid, key=lambda item: item[0]) if valid else (0.0, runs[0])
    chosen = best["dither_n"] if narrowing >= 0.15 else 0.0
    report.append(line("Выбрано", f"{chosen:.0f} Н" + (f": удерживаемый гриф ощущается точнее на {100 * narrowing:.0f} %" if chosen else ": заметного выигрыша нет, выключено")))
    return Outcome(report=report, machine={"dither_n": (chosen, None)}, data={"runs": runs})


# ---------------------------------------------------------------- F10
F10_ZONES = (150.0, 100.0, 60.0)


CUSHION_SPEED_MM_S = 150.0  # how fast the bar comes into a cushion zone


def cushions(ctx: Context, zones: tuple[float, ...] = F10_ZONES) -> Procedure:
    """A bar moving at 150 mm/s is handed to the law with nobody holding it, above / below a cushion zone.

    Bottom: a 4-kg bar let go while lowering (the load and the momentum carry it down); top: an empty bar
    thrown up (momentum only). The zone must bring it to the landing speed / stop it before the limit.
    """

    balance = ctx.balance
    safety = ctx.safety
    landing = float(ctx.profile.landing_speed_mm_s.value or 15.0)
    frame = yield Command(None, note="старт", progress=0.0)
    bottom, top = [], []
    load = kgf_to_n(2.0)
    for index, zone in enumerate(zones):
        progress = 0.05 + 0.4 * index / len(zones)
        frame = yield from recenter(balance, frame, safety.soft_min_mm + zone + 160.0, progress)
        frame = yield from handoff(balance, frame, -1, CUSHION_SPEED_MM_S, note=f"нижний упор, зона {zone:.0f} мм: разгон вниз", progress=progress, travel_mm=120.0)
        trainer = Trainer(ctx, load=LoadSetpoint(load_n=load), profile=_with(ctx.profile, cushion_bottom_mm=zone, cushion_top_mm=None))
        rows: list[Row] = []
        frame, why = yield from drive(trainer, frame, lambda _f: 0.0, seconds=6.0, note=f"нижний упор, зона {zone:.0f} мм: гриф отпущен", progress=progress, rows=rows,
                                      until=lambda f: f.x_mean < safety.soft_min_mm + 3.0 or abs(f.v_mean) < 0.5, speed_cap=260.0)
        near = [abs(r.v) for r in rows if r.x < safety.soft_min_mm + 4.0 and r.v < 0]
        touch = max(near, default=abs(frame.v_mean) if frame.x_mean < safety.soft_min_mm + 4.0 else 0.0)
        peak = max((-r.v for r in rows), default=0.0)
        frame = yield from land(balance, frame, progress=progress)
        ok = why != "fast" and touch <= max(2.0 * landing, 30.0)
        bottom.append({"zone_mm": zone, "touch_mm_s": round(touch, 1), "peak_mm_s": round(peak, 1), "why": why, "ok": ok})
        if not ok:
            break
    travel_top = float(ctx.profile.travel_mm.value) - 20.0
    if safety.soft_max_mm <= travel_top and safety.soft_max_mm - max(zones) - 300.0 > 300.0:
        for index, zone in enumerate(zones):
            progress = 0.5 + 0.4 * index / len(zones)
            release_at = safety.soft_max_mm - zone - 20.0
            frame = yield from recenter(balance, frame, release_at - 200.0, progress)
            frame = yield from handoff(balance, frame, +1, CUSHION_SPEED_MM_S, note=f"верхний предел, зона {zone:.0f} мм: бросок вверх", progress=progress, travel_mm=190.0)
            trainer = Trainer(ctx, profile=_with(ctx.profile, cushion_top_mm=zone, cushion_bottom_mm=None))
            rows = []
            frame, why = yield from drive(trainer, frame, lambda _f: 0.0, seconds=5.0, note=f"верхний предел, зона {zone:.0f} мм: гриф отпущен", progress=progress, rows=rows,
                                          until=lambda f: f.v_mean <= 0.5, speed_cap=260.0)
            highest = max((r.x for r in rows), default=frame.x_mean)
            frame = yield from _end(balance, frame, progress)
            ok = why != "fast" and highest <= safety.soft_max_mm - 2.0
            top.append({"zone_mm": zone, "highest_mm": round(highest, 1), "why": why, "ok": ok})
            if not ok:
                break
    yield from land(balance, frame, progress=0.95)
    return {"bottom": bottom, "top": top, "soft_min": safety.soft_min_mm, "soft_max": safety.soft_max_mm, "landing_mm_s": landing}


def fit_cushions(data: dict[str, Any], _ctx: Context) -> Outcome:
    report = []
    machine: dict[str, tuple[Any, float | None]] = {}
    for key, runs, label in (("cushion_bottom_mm", data["bottom"], "нижний"), ("cushion_top_mm", data["top"], "верхний")):
        for run in runs:
            value = f"касание {run['touch_mm_s']:.0f} мм/с (падал до {run['peak_mm_s']:.0f})" if "touch_mm_s" in run else f"выше всего {run['highest_mm']:.0f} мм при пределе {data['soft_max']:.0f}"
            report.append(line(f"{label.capitalize()} упор, зона {run['zone_mm']:.0f} мм", value + ("" if run["why"] != "fast" else " — слишком быстро, прервано"), run["ok"]))
        good = [run for run in runs if run["ok"]]
        if good:
            machine[key] = (min(run["zone_mm"] for run in good), None)
        elif runs:
            return Outcome(report=report, error=f"{label} упор: даже зона {runs[0]['zone_mm']:.0f} мм не тормозит гриф: проверьте M3 и A3")
    if not data["top"]:
        report.append(line("Верхний упор", "не проверялся: мало хода или верхний программный предел выше хода (B8)", None))
    report.append(line("Выбрано", ", ".join(f"{'низ' if k == 'cushion_bottom_mm' else 'верх'} {v:.0f} мм" for k, (v, _) in machine.items())))
    return Outcome(report=report, machine=machine, data={"bottom": data["bottom"], "top": data["top"]})


# ---------------------------------------------------------------- F11
def release_test(ctx: Context) -> Procedure:
    balance = ctx.balance
    # just above the static friction: a let-go bar must move (a lighter one stays put — harmless, nothing to
    # detect), but slowly enough to see the estimate for several frames
    load = mean([balance.coulomb_down[side] for side in SIDES]) + 15.0
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from recenter(balance, frame, 200.0, 0.05)
    trainer = Trainer(ctx, load=LoadSetpoint(load_n=load), inertia=0.0)
    held: list[Row] = []
    frame, why = yield from _reps(ctx, frame, trainer, load, low=170.0, high=250.0, speed_mm_s=40.0, seconds=8.0, note="пользователь делает повторения", progress=0.3, rows=held)
    if why != "time":
        raise ProcedureError("повторения прервались: проверьте F2/F4")
    mass, _residual = expected(ctx, load, inertia=0.0)
    gain = user_gain(ctx, mass)
    frame, _ = yield from drive(trainer, frame, lambda f: load + max(-40.0, min(40.0, -gain * f.v_mean)), seconds=1.5, note="пользователь держит гриф", progress=0.5, rows=held)
    released: list[Row] = []
    frame, _ = yield from drive(trainer, frame, lambda _f: 0.0, seconds=0.8, note="пользователь отпустил гриф", progress=0.7, rows=released,
                                until=lambda f: f.v_mean < -140.0 or f.x_mean < 110.0)
    frame = yield from _end(balance, frame, 0.8)
    yield from land(balance, frame, progress=0.95)
    return {"held": [(r.t, r.user) for r in held], "released": [(r.t, r.user) for r in released], "load_n": load, "period_s": float(ctx.profile.loop_period_s.value or 0.04)}


def _percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(share * (len(ordered) - 1))))]


def fit_release(data: dict[str, Any], _ctx: Context) -> Outcome:
    held = [u for _t, u in data["held"]]
    released = [u for _t, u in data["released"][1:]]  # the bus delay: the first frame still shows the hand
    if len(held) < 20 or len(released) < 3:
        raise ProcedureError("мало кадров для сравнения")
    held_low, released_high = _percentile(held, 0.1), _percentile(released, 0.9)
    report = [
        line("Усилие по оценке, пока гриф держат", f"от {held_low:.0f} Н (10 %) при нагрузке {data['load_n']:.0f} Н"),
        line("Усилие после отпускания", f"до {released_high:.0f} Н (90 %)"),
    ]
    if held_low - released_high < 5.0:
        return Outcome(report=report, error="оценка усилия не различает «держит» и «отпустил»: проверьте S3, D4 и V2")
    threshold = (held_low + released_high) / 2
    longest, run, previous = 0.0, 0.0, None
    for t, u in data["held"]:
        run = run + (t - previous) if previous is not None and u < threshold else 0.0
        longest, previous = max(longest, run), t
    timeout = round(max(0.2, longest + 2 * data["period_s"]), 2)
    detect = next((t - data["released"][0][0] for t, u in data["released"][1:] if u < threshold), None)
    report.append(line("Порог отпускания", f"{threshold:.0f} Н, держать {1000 * timeout:.0f} мс (самый долгий провал при удержании {1000 * longest:.0f} мс)"))
    report.append(line("Отпускание замечено через", f"{1000 * (detect + timeout):.0f} мс" if detect is not None else "не замечено за 0,8 с", detect is not None))
    return Outcome(report=report, machine={"feel_release_force_n": (round(threshold, 1), None), "feel_release_timeout_s": (timeout, None)}, data={"held_low": held_low, "released_high": released_high})


# ---------------------------------------------------------------- X4
X4_SHARES = (0.0, 0.05, 0.1, 0.2)


def sync_train(ctx: Context, shares: tuple[float, ...] = X4_SHARES, *, speed_mm_s: float = 100.0) -> Procedure:
    balance = ctx.balance
    coupling = float(ctx.profile.side_coupling_n_per_mm.value or 40.0)
    load = kgf_to_n(5.0)
    frame = yield Command(None, note="старт", progress=0.0)
    runs = []
    for index, share in enumerate(shares):
        progress = 0.05 + 0.85 * index / len(shares)
        k = round(share * coupling, 2)
        frame = yield from recenter(balance, frame, 150.0, progress)
        trainer = Trainer(ctx, load=LoadSetpoint(load_n=load), tunables={"sync_k_n_per_mm": k}, inertia=0.0)
        rows: list[Row] = []
        frame, why = yield from _reps(ctx, frame, trainer, load, low=140.0, high=320.0, speed_mm_s=speed_mm_s, seconds=8.0, note=f"синхронизация в упражнении k = {k:g} Н/мм", progress=progress, rows=rows)
        frame = yield from _end(balance, frame, progress)
        skews = [r.skew for r in rows if abs(r.v) > 10.0]
        centre = mean(skews)
        runs.append({
            "k": k, "why": why,
            "rms_mm": round((sum((s - centre) ** 2 for s in skews) / len(skews)) ** 0.5, 3) if skews else None,
            "max_mm": round(max((abs(s) for s in skews), default=0.0), 2),
            "swings": sign_changes([s - centre for s in skews], 0.3),
        })
    yield from land(balance, frame, progress=0.95)
    return {"runs": runs, "coupling": coupling}


def fit_sync_train(data: dict[str, Any], _ctx: Context) -> Outcome:
    runs = [r for r in data["runs"] if r["rms_mm"] is not None and r["why"] == "time"]
    if not runs:
        raise ProcedureError("повторения прервались: проверьте X3 и F2")
    best_rms = min(r["rms_mm"] for r in runs)
    calm = [r for r in runs if r["swings"] <= max(4, min(x["swings"] for x in runs) + 2)]
    best = min((r for r in calm if r["rms_mm"] <= 1.1 * best_rms + 0.05), key=lambda r: r["k"], default=runs[0])
    report = [line(f"k = {r['k']:g} Н/мм", f"перекос СКО {r['rms_mm']:.2f} мм, макс {r['max_mm']:.2f} мм, колебаний {r['swings']}", r is best or None) for r in runs]
    report.append(line("Выбрано для тренировки", f"{best['k']:g} Н/мм ({100 * best['k'] / data['coupling']:.0f} % жёсткости грифа)"))
    return Outcome(report=report, machine={"sync_k_train_n_per_mm": (best["k"], None)}, data={"runs": data["runs"]})


# ---------------------------------------------------------------- G2
G2_LOADS_KGF = (5.0, 10.0, 20.0)
TURN_STICK_S = 0.2


def feel_check(ctx: Context) -> Procedure:
    balance = ctx.balance
    frame = yield Command(None, note="старт", progress=0.0)
    items = []
    for index, load in enumerate(G2_LOADS_KGF):
        progress = 0.05 + 0.85 * index / len(G2_LOADS_KGF)
        frame, item = yield from _felt_item(ctx, frame, load, progress=progress, note=f"проверка {2 * load:g} кг на гриф")
        frame = yield from recenter(balance, frame, 160.0, progress)
        load_n = kgf_to_n(load)
        trainer = Trainer(ctx, load=LoadSetpoint(load_n=load_n))
        rows: list[Row] = []
        frame, why = yield from _reps(ctx, frame, trainer, load_n, low=150.0, high=260.0, speed_mm_s=80.0, seconds=8.0, note=f"проверка {2 * load:g} кг: повторения", progress=progress, rows=rows)
        frame = yield from _end(balance, frame, progress)
        items.append({**item, "turns": _turns(rows), "reps_why": why})
    yield from land(balance, frame, progress=0.95)
    return {"items": items}


def fit_feel_check(data: dict[str, Any], ctx: Context) -> Outcome:
    machine = mean([float(ctx.profile.side(side).moving_mass_kg.value) for side in SIDES])
    report, failed = [], []
    for item in data["items"]:
        virtual = item["load_kgf"]
        felt = _felt(item)
        label = f"{2 * virtual:g} кг на гриф"
        if felt is None:
            report.append(line(f"{label}: масса", "не измерена", False))
            failed.append(label)
            continue
        # the delay limits how much inertia can go: the check is that the compensation helps, the gap is shown
        mass_ok = felt["mass_kg"] <= max(machine, virtual) * MASS_TOLERANCE
        friction_ok = abs(felt["residual_n"]) <= max(kgf_to_n(2.0), 0.1 * item["load_n"])
        turns = item["turns"]
        turn_ok = item["reps_why"] == "time" and turns["chatter"] == 0 and (turns["stick_s"] or 0.0) <= TURN_STICK_S
        report.append(line(f"{label}: инерция", f"ощущается {felt['mass_kg']:.0f} кг на сторону: у свободного веса {virtual:g}, у машины без компенсации {machine:.0f}", mass_ok))
        report.append(line(f"{label}: лишнее трение", f"{felt['residual_n']:+.0f} Н ({n_to_kgf(felt['residual_n']):+.1f} кгс)", friction_ok))
        report.append(line(f"{label}: разворот", f"залипание {1000 * (turns['stick_s'] or 0):.0f} мс, дрожание {turns['chatter']}", turn_ok))
        if not (mass_ok and friction_ok and turn_ok):
            failed.append(label)
    return Outcome(report=report, data={"items": data["items"]}, error=f"не как свободный вес: {', '.join(failed)} — повторите F2 / F3 / F4" if failed else None)


def _envelope(top: float, speed: float = FEEL_SPEED_MM_S) -> ProcedureEnvelope:
    return ProcedureEnvelope(max_speed_mm_s=speed, max_x_mm=top)


SPECS = {
    "F1": (lambda ctx: (inertia_limit(ctx), _envelope(400.0, 120.0)), fit_inertia_limit),
    "F2": (lambda ctx: (inertia_by_load(ctx), _envelope(320.0)), fit_inertia_by_load),
    "F3": (lambda ctx: (friction_speed(ctx), _envelope(ctx.top_mm + 60.0, 230.0)), fit_friction_speed),
    "F4": (lambda ctx: (reversal_blend(ctx), _envelope(340.0)), fit_reversal_blend),
    "F5": (lambda ctx: (phase_tuning(ctx), _envelope(340.0)), fit_phase),
    "F6": (lambda ctx: (soft_breakaway(ctx), _envelope(320.0, 220.0)), fit_soft_breakaway),
    "F7": (lambda ctx: (track_smoothing(ctx), _envelope(ctx.top_mm + 80.0)), fit_track_smoothing),
    "F8": (lambda ctx: (deadband_crossing(ctx), _envelope(30.0, 30.0)), fit_deadband_crossing),
    "F9": (lambda ctx: (dither_test(ctx), _envelope(220.0, 80.0)), fit_dither),
    "F10": (lambda ctx: (cushions(ctx), ProcedureEnvelope(max_speed_mm_s=280.0, max_x_mm=ctx.safety.soft_max_mm + 20.0)), fit_cushions),
    "F11": (lambda ctx: (release_test(ctx), _envelope(320.0, 240.0)), fit_release),
    "X4": (lambda ctx: (sync_train(ctx), _envelope(400.0)), fit_sync_train),
    "G2": (lambda ctx: (feel_check(ctx), _envelope(360.0)), fit_feel_check),
}

__all__ = ["SPECS"]
