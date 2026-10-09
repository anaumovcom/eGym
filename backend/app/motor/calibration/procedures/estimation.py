"""Motion estimate (V1–V3) and the friction map along the travel (S10).

V1–V3 record ordinary governed moves and fit offline — no extra motion per candidate:

* V1 — PA_1C1 speed register vs the encoder derivative (centred, no lag): scale and lag of the register;
* V2 — the observer's acceleration filter: replay the observer with each smoothing and compare with a
  centred (non-causal) reference; the smallest total error = the best noise/lag balance. The inertia
  compensation multiplies this acceleration by up to the machine mass (60 kg: 0.1 m/s² error = 6 N);
* V3 — the command acts after the bus delay d = B3 + B2: friction is compensated for v(t + h) predicted
  as v + a·h; h with the smallest error against the real v(t + d).

S10: rises and descents over the whole travel at 30 mm/s. Per 20-mm bin the force beyond the window edge
up (``e⁺ = ΔW + ΔF``) and down (``e⁻ = −ΔW + ΔF``) separate into the friction map ``ΔF = (e⁺ + e⁻)/2``
and the residual weight ``ΔW = (e⁺ − e⁻)/2`` (a check of S7).
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from app.motor.calibration.procedures.common import Context, Outcome, Procedure, line, mean, observe, steady
from app.motor.calibration.procedures.motion import Motion, land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError
from app.motor.estimation.friction import interpolate
from app.motor.estimation.observer import AlphaBetaObserver
from app.motor.profile import MachineProfile
from app.motor.units import SIDES, Side

SIDE_LABEL = {"left": "Л", "right": "П"}
LAGS_S = tuple(k * 0.005 for k in range(41))  # 0…200 ms
SMOOTHINGS = (0.08, 0.15, 0.25, 0.35, 0.5, 0.7, 1.0)
HORIZON_SHARES = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5)
MIN_SPEED_MM_S = 5.0


def _recorder(rows: list[list[float]]) -> Any:
    def on_frame(frame: Frame) -> None:
        rows.append([frame.t, frame.x("left"), frame.x("right"), frame.v("left"), frame.v("right")])

    return on_frame


def _moves(ctx: Context, plan: list[tuple[float, float]], *, start_mm: float, rest_s: float = 0.0) -> Procedure:
    """Governed moves (target, speed) recorded frame by frame; optional rest in the window middle first."""

    balance = ctx.balance
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, start_mm, progress_span=(0.0, 0.05))
    rows: list[list[float]] = []
    record = _recorder(rows)
    t0 = frame.t
    while frame.t - t0 < rest_s:
        record(frame)
        frame = yield Command(balance.mid(frame), note="покой: шум скорости и ускорения", progress=0.06)
    for index, (target, speed_mm_s) in enumerate(plan):
        span = (0.08 + 0.82 * index / len(plan), 0.08 + 0.82 * (index + 1) / len(plan))
        frame = yield from observe(travel(balance, frame, target, speed_mm_s=speed_mm_s, note=f"{'подъём' if target > frame.x_mean else 'опускание'} {speed_mm_s:.0f} мм/с", progress_span=span), record)
    yield from land(balance, frame, progress=0.95)
    return {"rows": rows, "rest_s": rest_s}


def _columns(rows: list[list[float]], side: Side) -> tuple[list[float], list[float], list[float]]:
    k = 0 if side == "left" else 1
    return [r[0] for r in rows], [r[1 + k] for r in rows], [r[3 + k] for r in rows]


def _derivative(t: list[float], y: list[float]) -> list[tuple[float, float]]:
    """Centred difference (t_i, (y_{i+1} − y_{i−1}) / (t_{i+1} − t_{i−1})): no lag."""

    return [(t[i], (y[i + 1] - y[i - 1]) / (t[i + 1] - t[i - 1])) for i in range(1, len(t) - 1) if t[i + 1] > t[i - 1]]


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0


# ---------------------------------------------------------------- V1
def fit_speed(data: dict[str, Any], _ctx: Context) -> Outcome:
    rows = data["rows"]
    if len(rows) < 40:
        raise ProcedureError("мало кадров движения")
    report, lags, scales, per_side = [], [], [], {}
    for side in SIDES:
        t, x, v = _columns(rows, side)
        derivative = _derivative(t, x)
        best: tuple[float, float, float] | None = None  # (rms, lag, scale)
        for lag in LAGS_S:
            pairs = [(v[i], d) for i in range(2, len(t) - 2) if t[i] - lag >= derivative[0][0] and abs(d := interpolate(derivative, t[i] - lag)) > MIN_SPEED_MM_S]
            if len(pairs) < 20:
                continue
            den = sum(d * d for _, d in pairs)
            scale = sum(vv * d for vv, d in pairs) / den
            error = _rms([vv - scale * d for vv, d in pairs])
            if best is None or error < best[0]:
                best = (error, lag, scale)
        if best is None:
            raise ProcedureError("скорость не совпала с энкодером ни при какой задержке")
        error, lag, scale = best
        lags.append(lag)
        scales.append(scale)
        per_side[side] = {"lag_s": lag, "scale": scale, "rms_mm_s": error}
        report.append(line(f"{SIDE_LABEL[side]}: PA_1C1 против энкодера", f"запаздывание {1000 * lag:.0f} мс, масштаб {scale:.3f}, расхождение {error:.1f} мм/с", abs(scale - 1) <= 0.05))
    lag, scale = mean(lags), mean(scales)
    report.append(line("Поправка наблюдателя", f"скорость ÷ {scale:.3f} + a·{1000 * lag:.0f} мс" + ("; вес скорости привода снижен" if lag > 0.02 else "")))
    return Outcome(
        report=report,
        machine={"speed_lag_s": (round(lag, 3), None), "speed_scale": (round(scale, 4), None)},
        data={"sides": per_side, "frames": len(rows)},
        error=None if 0.8 <= scale <= 1.2 else f"скорость привода расходится с энкодером в {scale:.2f} раза: проверьте единицы PA_1C1 и шаг винта (B6)",
    )


# ---------------------------------------------------------------- V2 / V3 replay
def _replay(rows: list[list[float]], side: Side, profile: MachineProfile, smoothing: float | None = None) -> tuple[list[float], list[float]]:
    """The core's observer over the recorded frames: (v_est, a_est) per frame."""

    observer = AlphaBetaObserver.from_profile(profile, smoothing)
    t, x, v = _columns(rows, side)
    v_est, a_est = [], []
    for ti, xi, vi in zip(t, x, v, strict=True):
        state = observer.update(xi, vi, ti)
        v_est.append(state.v_mm_s)
        a_est.append(state.a_mm_s2)
    return v_est, a_est


def _reference_accel(t: list[float], v: list[float]) -> list[float | None]:
    """Centred acceleration over ±2 frames of a 5-frame centred mean speed (non-causal: no lag)."""

    n = len(t)
    smooth = [mean(v[max(0, i - 2): i + 3]) for i in range(n)]
    out: list[float | None] = [None] * n
    for i in range(4, n - 4):
        if t[i + 2] > t[i - 2]:
            out[i] = (smooth[i + 2] - smooth[i - 2]) / (t[i + 2] - t[i - 2])
    return out


def fit_accel(data: dict[str, Any], ctx: Context) -> Outcome:
    rows = data["rows"]
    if len(rows) < 60:
        raise ProcedureError("мало кадров движения")
    rest_end = rows[0][0] + data.get("rest_s", 0.0)
    results = []
    for smoothing in SMOOTHINGS:
        errors, rest = [], []
        for side in SIDES:
            t, _x, v = _columns(rows, side)
            _v_est, a_est = _replay(rows, side, ctx.profile, smoothing)
            reference = _reference_accel(t, v)
            errors += [a - r for a, r, ti in zip(a_est, reference, t, strict=True) if r is not None and ti > rest_end]
            rest += [a for a, ti in zip(a_est, t, strict=True) if rows[0][0] + 0.5 < ti <= rest_end]
        results.append({"smoothing": smoothing, "rms_mm_s2": _rms(errors), "rest_mm_s2": _rms(rest)})
    best = min(results, key=lambda r: r["rms_mm_s2"])
    mass = mean([float(ctx.profile.side(side).moving_mass_kg.value) for side in SIDES])
    report = [
        line(f"Сглаживание {r['smoothing']:.2f}", f"ошибка ускорения {r['rms_mm_s2']:.0f} мм/с², в покое {r['rest_mm_s2']:.0f} мм/с²", r is best or None)
        for r in results
    ]
    noise_n = mass * best["rms_mm_s2"] / 1000
    report.append(line("Выбрано", f"{best['smoothing']:.2f}: ошибка {best['rms_mm_s2']:.0f} мм/с² ≈ {noise_n:.1f} Н при полной компенсации массы {mass:.0f} кг", noise_n <= 15.0))
    return Outcome(
        report=report,
        machine={"accel_smoothing": (best["smoothing"], None), "accel_noise_mm_s2": (round(best["rms_mm_s2"], 1), None)},
        data={"candidates": results},
    )


def fit_prediction(data: dict[str, Any], ctx: Context) -> Outcome:
    rows = data["rows"]
    if len(rows) < 60:
        raise ProcedureError("мало кадров движения")
    delay = float(ctx.profile.loop_delay_s.value or 0.04) + float(ctx.profile.torque_lag_s.value or 0.0)
    scale = float(ctx.profile.speed_scale.value or 1.0)
    results = []
    for share in HORIZON_SHARES:
        horizon = share * delay
        errors = []
        for side in SIDES:
            t, _x, v = _columns(rows, side)
            v_est, a_est = _replay(rows, side, ctx.profile)
            future = list(zip(t, [vv / scale for vv in v], strict=True))
            for i, ti in enumerate(t):
                if ti + delay > t[-1] or abs(v[i]) < 1.0 and abs(a_est[i]) < 50:
                    continue
                errors.append(v_est[i] + a_est[i] * horizon - interpolate(future, ti + delay))
        results.append({"horizon_s": horizon, "rms_mm_s": _rms(errors)})
    best = min(results, key=lambda r: r["rms_mm_s"])
    base = results[0]["rms_mm_s"]
    report = [line(f"Упреждение {1000 * r['horizon_s']:.0f} мс", f"ошибка скорости через {1000 * delay:.0f} мс: {r['rms_mm_s']:.1f} мм/с", r is best or None) for r in results]
    gain = 100 * (1 - best["rms_mm_s"] / base) if base > 0 else 0.0
    report.append(line("Выбрано", f"{1000 * best['horizon_s']:.0f} мс: ошибка меньше на {gain:.0f} % — компенсация трения меняет знак вовремя на развороте"))
    return Outcome(report=report, machine={"predict_horizon_s": (round(best["horizon_s"], 3), None)}, data={"candidates": results, "delay_s": delay})


# ---------------------------------------------------------------- S10
def friction_track(ctx: Context, *, low_mm: float = 40.0, speed_mm_s: float = 30.0) -> Procedure:
    balance = ctx.balance
    top = ctx.top_mm
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, low_mm, progress_span=(0.0, 0.03))
    up, down = Motion(trace=[]), Motion(trace=[])
    frame = yield from travel(balance, frame, top, speed_mm_s=speed_mm_s, state=up, note=f"подъём по всему ходу {speed_mm_s:.0f} мм/с", progress_span=(0.03, 0.45))
    frame = yield from travel(balance, frame, low_mm, speed_mm_s=speed_mm_s, state=down, note=f"опускание по всему ходу {speed_mm_s:.0f} мм/с", progress_span=(0.45, 0.9))
    yield from land(balance, frame, progress=0.95)
    return {"up": up.trace or [], "down": down.trace or [], "speed_mm_s": speed_mm_s}


def _bins(trace: list[Any], target: float, bin_mm: float) -> dict[Side, dict[int, float]]:
    speeds, _ = steady(trace, target)
    if len(speeds) < 20:
        raise ProcedureError("скорость не держалась на проходе по ходу — повторите M2")
    t_first = trace[0][0] if trace else 0.0
    out: dict[Side, dict[int, list[float]]] = {side: {} for side in SIDES}
    for t, x, v, extra in trace:
        if t - t_first < 0.6 or abs(v - target) > 0.6 * target:
            continue
        for side in SIDES:
            out[side].setdefault(int(x // bin_mm), []).append(extra[side])
    return {side: {key: mean(values) for key, values in bins.items() if len(values) >= 2} for side, bins in out.items()}


def fit_friction_track(data: dict[str, Any], ctx: Context, *, bin_mm: float = 20.0) -> Outcome:
    target = data["speed_mm_s"]
    up, down = _bins(data["up"], target, bin_mm), _bins(data["down"], target, bin_mm)
    sides: dict[Side, dict[str, tuple[Any, float | None]]] = {}
    report = []
    for side in SIDES:
        keys = sorted(set(up[side]) & set(down[side]))
        if len(keys) < 5:
            raise ProcedureError("мало участков хода, пройденных в обе стороны")
        friction = {k: (up[side][k] + down[side][k]) / 2 for k in keys}
        weight = {k: (up[side][k] - down[side][k]) / 2 for k in keys}
        f0, w0 = statistics.median(friction.values()), statistics.median(weight.values())
        points = [((k + 0.5) * bin_mm, round(friction[k] - f0, 1)) for k in keys]
        worst = max(points, key=lambda p: abs(p[1]))
        bumps = [p for p in points if p[1] > max(4.0, 0.1 * ctx.balance.coulomb_up[side])]
        residual = max(abs(weight[k] - w0) for k in keys)
        sides[side] = {"friction_map": (points, None)}
        report.append(line(f"{SIDE_LABEL[side]}: трение по ходу", f"{points[0][0]:.0f}…{points[-1][0]:.0f} мм, наибольшее отклонение {worst[1]:+.1f} Н на {worst[0]:.0f} мм"))
        report.append(line(f"{SIDE_LABEL[side]}: тугие участки", ", ".join(f"{x:.0f} мм (+{f:.0f} Н)" for x, f in bumps[:6]) if bumps else "нет", not bumps))
        report.append(line(f"{SIDE_LABEL[side]}: остаток веса по высоте (проверка S7)", f"до {residual:.1f} Н", residual <= max(3.0, 0.03 * ctx.balance.weight(side, 100.0))))
    report.append(line("Применение", "компенсируется в тренировке с коэффициентом F7 (сглаживание хода)"))
    return Outcome(report=report, sides=sides, data={"bins": len(keys)})


SPECS = {
    "V1": (lambda ctx: (_moves(ctx, [(240.0, 25.0), (40.0, 25.0), (240.0, 50.0), (40.0, 50.0)], start_mm=40.0), ProcedureEnvelope(max_x_mm=300.0)), fit_speed),
    "V2": (lambda ctx: (_moves(ctx, [(320.0, 40.0), (120.0, 40.0), (320.0, 70.0), (120.0, 70.0)], start_mm=120.0, rest_s=2.5), ProcedureEnvelope(max_x_mm=380.0, max_speed_mm_s=120.0)), fit_accel),
    "V3": (lambda ctx: (_moves(ctx, [(165.0, 30.0), (130.0, 30.0), (165.0, 30.0), (130.0, 30.0), (300.0, 60.0), (130.0, 60.0)], start_mm=130.0), ProcedureEnvelope(max_x_mm=360.0, max_speed_mm_s=120.0)), fit_prediction),
    "S10": (lambda ctx: (friction_track(ctx), ProcedureEnvelope(max_x_mm=ctx.top_mm + 60.0)), fit_friction_track),
}
