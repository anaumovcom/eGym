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

from app.motor.calibration.procedures.bus import ZERO_DRIFT_LIMIT_MM
from app.motor.calibration.procedures.common import Context, Outcome, Procedure, line, mean, observe
from app.motor.calibration.procedures.motion import land, travel
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
TRACK_BIN_MM = 20.0


def _track_keys(low: float, high: float, bin_mm: float) -> range:
    margin = min(40.0, 0.1 * (high - low))
    return range(math.ceil((low + margin) / bin_mm), math.floor((high - margin) / bin_mm))


def _track_bin(elapsed: float, x: float, speed: float, extra: float, target: float, bin_mm: float) -> int | None:
    if elapsed >= 0.6 and math.isfinite(x) and math.isfinite(extra) and 0.6 * target <= speed <= 1.4 * target:
        return math.floor(x / bin_mm)
    return None


def friction_track(ctx: Context, *, low_mm: float = 40.0, speed_mm_s: float = 30.0) -> Procedure:
    balance = ctx.balance
    top = ctx.top_mm
    expected = _track_keys(low_mm, top, TRACK_BIN_MM)
    heights = [(k + 0.5) * TRACK_BIN_MM for k in expected]
    coverage = {s: [0] * len(expected) for s in SIDES}
    ctx.friction_coverage = {"heightsMm": heights, "sides": coverage}
    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, low_mm, progress_span=(0.0, 0.03))
    data = {"low_mm": low_mm, "high_mm": top, "speed_mm_s": speed_mm_s}
    for name, direction, target, span in (("up", 1, top, (0.03, 0.45)), ("down", -1, low_mm, (0.45, 0.90))):
        traces = {side: [] for side in SIDES}
        counts = {side: {} for side in SIDES}
        start = frame.t

        def record(sample: Frame, start: float = start, direction: int = direction, traces: dict = traces, counts: dict = counts) -> None:
            nonlocal coverage
            for side in SIDES:
                x = sample.x(side)
                extra = direction * (sample.samples[side].motor_force_n - balance.edge(side, x, direction))
                row = (sample.t - start, x, direction * sample.v(side), extra)
                traces[side].append(row)
                k = _track_bin(*row, speed_mm_s, TRACK_BIN_MM)
                if k is not None and k in expected:
                    counts[side][k] = counts[side].get(k, 0) + 1
                    if counts[side][k] == 3:
                        # Publish immutable snapshots: a response may be encoded after releasing the motor lock.
                        marks = coverage[side].copy()
                        marks[k - expected.start] |= 1 if direction > 0 else 2
                        coverage = {**coverage, side: marks}
                        ctx.friction_coverage = {"heightsMm": heights, "sides": coverage}

        note = "Карта усилия · подъём" if direction > 0 else "Карта усилия · опускание"
        frame = yield from observe(travel(balance, frame, target, speed_mm_s=speed_mm_s, note=note, progress_span=span), record)
        data[name] = traces
    yield from land(balance, frame, progress=0.95)
    return data


def _bins(trace: list, target: float, bin_mm: float) -> dict[int, float]:
    bins: dict[int, list[float]] = {}
    for elapsed, x, speed, extra in trace:
        k = _track_bin(elapsed, x, speed, extra, target, bin_mm)
        if k is not None:
            bins.setdefault(k, []).append(extra)
    return {key: statistics.median(values) for key, values in bins.items() if len(values) >= 3}


def fit_friction_track(data: dict[str, Any], ctx: Context, *, bin_mm: float = TRACK_BIN_MM) -> Outcome:
    # Exclude acceleration and braking at the ends. A long hole would turn into invented friction
    # when the production interpolator joins the samples on either side.
    low, high = data["low_mm"], data["high_mm"]
    expected = _track_keys(low, high, bin_mm)
    if len(expected) < 5:
        raise ProcedureError("Слишком короткий участок для карты трения")
    target = data["speed_mm_s"]
    track = {"heightsMm": [(k + 0.5) * bin_mm for k in expected], "sides": {}, "summary": {},
             "binMm": bin_mm, "speedMmS": target, "zeroToleranceMm": ZERO_DRIFT_LIMIT_MM,
             "directionalN": {}, "reference": {}, "coverageOk": {}}
    sides, report, incomplete = {}, [], []
    for side in SIDES:
        up, down = (_bins(data[leg][side], target, bin_mm) for leg in ("up", "down"))
        # The trace is relative to the directional edge W ± Fc. Adding Fc back gives
        # the measured drive effort relative to balance, positive against the motion.
        fc_up, fc_down = ctx.balance.coulomb_up[side], ctx.balance.coulomb_down[side]
        track["directionalN"][side] = {
            "up": [round(up[k] + fc_up, 1) if k in up else None for k in expected],
            "down": [round(down[k] + fc_down, 1) if k in down else None for k in expected],
        }
        profile = ctx.profile.side(side)
        track["reference"][side] = {"zeroCounts": profile.zero_counts.value, "mmPerPulse": profile.mm_per_pulse.value,
                                    "nPerRaw": profile.n_per_raw_value, "sign": profile.sign}
        keys = [k for k in expected if k in up and k in down]
        coverage = len(keys) / len(expected)
        measured_keys = set(keys)
        gap = longest = 0
        for k in expected:
            gap = 0 if k in measured_keys else gap + 1
            longest = max(longest, gap)
        ok = len(keys) >= 5 and coverage >= 0.8 and longest <= 3
        track["coverageOk"][side] = ok
        name = SIDE_LABEL[side]
        report.append(line(f"{name} · покрытие в обоих направлениях", f"{len(keys)} из {len(expected)} участков, наибольшой пропуск {longest * bin_mm:g} мм", ok))
        if not ok:
            incomplete.append(name)
        friction = {k: (up[k] + down[k]) / 2 for k in keys}
        baseline = statistics.median(friction.values()) if keys else 0
        values = {k: round(friction[k] - baseline, 1) for k in keys}
        track["sides"][side] = [values.get(k) for k in expected]
        if not keys:
            continue
        points = [((k + 0.5) * bin_mm, values[k]) for k in keys]
        peak_x, peak = max(points, key=lambda p: p[1])
        mad = statistics.median(abs(v - baseline) for v in friction.values())
        threshold = round(max(4.0, 0.1 * fc_up, 3 * 1.4826 * mad), 1)
        report.append(line(f"{name} · самый тугой участок", f"{peak_x:g} мм, на {peak:.1f} Н выше обычного" if peak > threshold else "выраженного пика не обнаружено"))
        weight = [(up[k] - down[k]) / 2 for k in keys]
        middle = statistics.median(weight)
        residual = max(abs(w - middle) for w in weight)
        weight_ok = residual <= max(3.0, 0.03 * ctx.balance.weight(side, 100.0))
        report.append(line(f"{name} · остаток веса по высоте", f"до {residual:.1f} Н", weight_ok))
        track["summary"][side] = {"peakMm": peak_x if peak > threshold else None, "peakN": peak if peak > threshold else None,
                                  "typicalN": round(baseline + (fc_up + fc_down) / 2, 1), "thresholdN": threshold,
                                  "weightResidualN": round(residual, 1), "weightWithinTolerance": weight_ok}
        sides[side] = {"friction_map": (points, None)}
    error = None
    if incomplete:
        error = f"Карта трения неполная ({', '.join(incomplete)}). Осмотрите направляющие на высотах с пропусками, проверьте перемещение M2 и повторите замер"
    return Outcome(report=report, sides={} if error else sides, error=error, data={"track": track, "bins": len(expected)})


def _observer_moves(ctx: Context, start: float, legs: list[tuple[float, float]], rest_s: float = 0.0) -> tuple[Procedure, ProcedureEnvelope]:
    low = ctx.working_window[0] if ctx.working_window else start
    plan = [(low + distance, speed) for distance, speed in legs]
    high = max(target for target, _ in plan)
    return _moves(ctx, plan, start_mm=low, rest_s=rest_s), ProcedureEnvelope(max_x_mm=high + 60.0)


SPECS = {
    "V1": (lambda ctx: _observer_moves(ctx, 40, [(200, 25), (0, 25), (200, 50), (0, 50)]), fit_speed),
    "V2": (lambda ctx: _observer_moves(ctx, 120, [(200, 40), (0, 40), (200, 70), (0, 70)], rest_s=2.5), fit_accel),
    "V3": (lambda ctx: _observer_moves(ctx, 130, [(35, 30), (0, 30), (35, 30), (0, 30), (170, 60), (0, 60)]), fit_prediction),
    "S10": (lambda ctx: (friction_track(ctx), ProcedureEnvelope(max_x_mm=ctx.top_mm + 60.0)), fit_friction_track),
}
