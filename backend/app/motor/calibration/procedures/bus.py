"""B0 drive configuration, B1 bus timing and rest noise, B3 control delay, B7 absolute zero (plan 15 §2.1)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from app.motor.calibration.fit import percentile, stat
from app.motor.calibration.procedures.motion import Balance, hold_still, land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.drive.protocol import TorqueDrive
from app.motor.units import SIDES, Side

Procedure = Generator[Command, Frame, dict[str, Any]]
REST_NOISE_LIMIT_MM = 0.05


# ---------------------------------------------------------------- B0
def config_check(drives: dict[Side, TorqueDrive]) -> Procedure:
    """Read-only: commissioning registers of both drives against the reference; support stays on."""

    yield Command(None, note="чтение регистров привода", progress=0.2)
    report: dict[Side, list[dict[str, Any]]] = {}
    for side in SIDES:
        reader = getattr(drives[side], "config_report", None)
        report[side] = reader() if reader is not None else [
            {"register": "-", "label": "Привод не поддерживает чтение конфигурации", "value": None, "ok": False, "detail": None}
        ]
    yield Command(None, note="сверка с эталоном", progress=0.9)
    return {"sides": report}


def fit_config(data: dict[str, Any]) -> dict[str, Any]:
    bad = [f"{'Л' if side == 'left' else 'П'}: {item['label']}" + (f" = {item['value']}" if item["value"] is not None else "") + (f" ({item['detail']})" if item.get("detail") else "")
           for side in SIDES for item in data["sides"][side] if not item["ok"]]
    return {"sides": data["sides"], "mismatches": bad, "ok": not bad}


# ---------------------------------------------------------------- B1
def bus_timing(frames: int = 200) -> Procedure:
    """The bar rests on support; every tick is a full read + write cycle; frame times are recorded."""

    frame = yield Command(None, note="замер цикла", progress=0.0)
    ts = [frame.t]
    reads = [frame.t - min(sample.t for sample in frame.samples.values())]
    xs: dict[Side, list[float]] = {side: [frame.x(side)] for side in SIDES}
    vs: dict[Side, list[float]] = {side: [frame.v(side)] for side in SIDES}
    for index in range(frames):
        frame = yield Command(None, note=f"замер цикла {index + 1}/{frames}", progress=index / frames)
        ts.append(frame.t)
        reads.append(frame.t - min(sample.t for sample in frame.samples.values()))
        for side in SIDES:
            xs[side].append(frame.x(side))
            vs[side].append(frame.v(side))
    return {"t": ts, "read_s": reads, "x": xs, "v": vs}


def fit_bus_timing(data: dict[str, Any]) -> dict[str, Any]:
    ts = data["t"]
    periods = [b - a for a, b in zip(ts, ts[1:], strict=False)]
    if len(periods) < 20:
        raise ProcedureError("слишком мало циклов для оценки")
    p50 = percentile(periods, 0.5)
    deviations = [abs(p - p50) for p in periods]
    result = {
        "loop_period_s": sum(periods) / len(periods),
        "p50_s": p50,
        "p95_s": percentile(periods, 0.95),
        "p99_s": percentile(periods, 0.99),
        "max_s": max(periods),
        "jitter_p95_s": percentile(deviations, 0.95),
        "read_mean_s": sum(data["read_s"]) / len(data["read_s"]),
        "late_frames": sum(1 for p in periods if p > 2 * p50),
        "cycles": len(periods),
    }
    result["ok"] = result["p99_s"] < 2 * p50
    if "x" in data:
        result["noise_mm"] = max(stat(data["x"][side]).std for side in SIDES)
        result["noise_mm_s"] = max(stat(data["v"][side]).std for side in SIDES)
        result["noise_ok"] = result["noise_mm"] < REST_NOISE_LIMIT_MM
    return result


# ---------------------------------------------------------------- B3
def control_delay(balance: Balance, *, repeats: int = 5, height_mm: float = 25.0, kick: float = 0.5, moving_mm_s: float = 1.5) -> Procedure:
    """Step the force from the middle of the window to ``edge + kick·Fc``; count the time to the first moving frame."""

    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from travel(balance, frame, height_mm, progress_span=(0.0, 0.15))
    delays: list[float] = []
    periods: list[float] = []
    for index in range(repeats):
        progress = 0.15 + 0.75 * index / repeats
        frame = yield from hold_still(balance, frame, note=f"остановка перед ступенью {index + 1}/{repeats}", progress=progress)
        for _ in range(4):  # settle: a few frames at rest to measure the frame period
            previous = frame.t
            frame = yield Command(balance.mid(frame), note="покой", progress=progress)
            periods.append(frame.t - previous)
        forces = {side: balance.edge(side, frame.x(side), +1) + kick * balance.coulomb_up[side] for side in SIDES}
        t0 = frame.t
        while True:
            frame = yield Command(forces, note=f"ступень силы {index + 1}/{repeats}", progress=progress)
            if frame.v_mean > moving_mm_s:
                delays.append(frame.t - t0)
                break
            if frame.t - t0 > 2.0:
                raise ProcedureError("гриф не трогается ступенью силы за 2 с: повторите S3")
        frame = yield from hold_still(balance, frame, progress=progress)
        if frame.x_mean > height_mm + 15:
            frame = yield from travel(balance, frame, height_mm, progress_span=progress)
    yield from land(balance, frame, progress=0.95)
    return {"delays": delays, "periods": periods}


def fit_delay(data: dict[str, Any]) -> dict[str, Any]:
    delays = data["delays"]
    if len(delays) < 3:
        raise ProcedureError("мало ступеней для оценки задержки")
    delay = stat(delays)
    period = percentile(data["periods"], 0.5)
    spread = max(delays) - min(delays)
    return {
        "delay_s": delay.mean,
        "ci95": delay.ci95,
        "min_s": min(delays),
        "max_s": max(delays),
        "period_s": period,
        "frames": delay.mean / period if period > 0 else None,
        "ok": spread <= 1.5 * period,
        "steps": len(delays),
    }


# ---------------------------------------------------------------- B7
def absolute_zero(balance: Balance, seconds: float = 2.0) -> Procedure:
    """Land on the stops (if not already), then average the raw absolute encoder counts."""

    frame = yield Command(None, note="старт", progress=0.0)
    frame = yield from land(balance, frame, progress=0.3)
    forces = {side: balance.weight(side, frame.x(side)) - 0.5 * balance.coulomb_down[side] for side in SIDES}
    counts: dict[Side, list[int | None]] = {side: [] for side in SIDES}
    positions: dict[Side, list[float]] = {side: [] for side in SIDES}
    end = frame.t + seconds
    start = {side: frame.x(side) for side in SIDES}
    while frame.t < end:
        frame = yield Command(dict(forces), note="замер нуля на упорах", progress=0.5 + 0.5 * (1 - (end - frame.t) / seconds))
        for side in SIDES:
            counts[side].append(frame.samples[side].counts)
            positions[side].append(frame.x(side))
            if abs(frame.x(side) - start[side]) > 0.2:  # by the encoder: PA_1C1 has single-frame glitches
                raise ProcedureError("гриф сдвинулся во время замера нуля")
    return {"counts": counts, "positions": positions}


def fit_zero(data: dict[str, Any], mm_per_pulse: dict[Side, float], previous: dict[Side, int | None]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for side in SIDES:
        raw = data["counts"][side]
        if not raw or any(value is None for value in raw):
            raise ProcedureError("привод не отдаёт показания абсолютного энкодера")
        spread_mm = (max(raw) - min(raw)) * mm_per_pulse[side]
        if spread_mm > 0.1:
            raise ProcedureError(f"{side}: показания энкодера на упорах плавают на {spread_mm:.2f} мм")
        counts = stat([float(value) for value in raw])
        zero = round(counts.mean)
        old = previous[side]
        result[side] = {
            "zero_counts": zero,
            "spread_mm": spread_mm,
            "offset_mm": sum(data["positions"][side]) / len(data["positions"][side]),
            "drift_mm": None if old is None else (zero - old) * mm_per_pulse[side],
        }
    return result
