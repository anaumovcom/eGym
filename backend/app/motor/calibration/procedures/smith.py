"""G4 compares unloaded passes at matched heights and speeds, using drive torque feedback."""

from __future__ import annotations

from statistics import median
from typing import Any

from app.motor.calibration.procedures.common import SIDE_LABEL, Context, Outcome, Procedure, line, observe
from app.motor.calibration.procedures.motion import land, travel
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope
from app.motor.units import SIDES, kgf_to_n

PASSES = 3
SPEED_MM_S = 30.0
BINS = 3
MIN_SAMPLES = 4


def repeatability(ctx: Context, low: float, high: float) -> Procedure:
    frame = yield Command(None, note="подготовка", progress=0.0)
    frame = yield from travel(ctx.balance, frame, low, progress_span=(0.0, 0.08))
    passes = []
    peak_skew: float | None = None
    # Discard the first and last fifth of the stroke (breakaway and braking).
    begin = low + (high - low) * 0.2
    width = (high - low) * 0.6 / BINS
    heights = [round(begin + (i + 0.5) * width) for i in range(BINS)]
    for index in range(2 * PASSES):
        direction = 1 if index % 2 == 0 else -1
        cells: dict[str, list[list[float]]] = {side: [[] for _ in range(BINS)] for side in SIDES}

        def record(sample: Frame, direction: int = direction, cells: dict = cells) -> None:
            nonlocal peak_skew
            if sample.skew_mm is not None:
                peak_skew = max(peak_skew or 0.0, abs(sample.skew_mm))
            for side in SIDES:
                slot = int((sample.x(side) - begin) // width)
                velocity = direction * sample.v(side)
                if 0 <= slot < BINS and 0.7 * SPEED_MM_S <= velocity <= 1.3 * SPEED_MM_S:
                    cells[side][slot].append(sample.samples[side].motor_force_n)

        note = f"проход {index // 2 + 1} из {PASSES}, {'вверх' if direction > 0 else 'вниз'}"
        section = (0.08 + 0.14 * index, 0.08 + 0.14 * (index + 1))
        move = travel(ctx.balance, frame, high if direction > 0 else low, speed_mm_s=SPEED_MM_S, note=note, progress_span=section)
        frame = yield from observe(move, record)
        passes.append({side: [median(values) if len(values) >= MIN_SAMPLES else None for values in cells[side]] for side in SIDES})
        if ctx.publish_plot:
            ctx.publish_plot({"passes": passes, "heightsMm": heights})
    yield from land(ctx.balance, frame, progress=0.96)
    return {"passes": passes, "heightsMm": heights, "peakSkewMm": peak_skew}


def fit_repeatability(data: dict[str, Any], ctx: Context) -> Outcome:
    report = []
    limits = {key: {side: [None] * len(data["heightsMm"]) for side in SIDES} for key in ("up", "down")}
    complete = True
    repeatable = True
    for offset, direction in enumerate(("подъём", "опускание")):
        for side in SIDES:
            for i, height in enumerate(data["heightsMm"]):
                label = f"{SIDE_LABEL[side]} · {direction} · {height} мм"
                values = [run[side][i] for run in data["passes"][offset::2] if run[side][i] is not None]
                if len(values) != PASSES:
                    complete = False
                    report.append(line(label, f"замер на рабочей скорости в {len(values)} из {PASSES} проходов", False))
                    continue
                spread = max(values) - min(values)
                limit = max(kgf_to_n(0.5), 0.10 * abs(median(values)))
                limits[("up", "down")[offset]][side][i] = limit
                repeatable &= spread <= limit
                report.append(line(label, f"разброс {spread:.1f} Н, допуск {limit:.1f} Н", spread <= limit)
                              | {"comparison": {"value": spread, "limit": limit}})
    peak = data["peakSkewMm"]
    skew_ok = peak is not None and peak < ctx.safety.sync_warning_mm
    row = line("Максимальный перекос", f"{peak:.1f} мм, допуск {ctx.safety.sync_warning_mm:g} мм" if peak is not None else "Нет парного замера", skew_ok)
    if peak is not None:
        row["comparison"] = {"value": peak, "limit": ctx.safety.sync_warning_mm}
    report.append(row)
    error = None
    if not complete:
        error = "не хватило повторных измерений на рабочей скорости, проверьте перемещение M2"
    elif not repeatable or not skew_ok:
        error = "ход различается между проходами, проверьте трение по высоте (S7, S10) и синхронизацию (X3)"
    return Outcome(report=report, data={**data, "spreadLimitsN": limits}, error=error)


def build_repeatability(ctx: Context) -> tuple[Procedure, ProcedureEnvelope]:
    if ctx.working_window is None:
        raise ValueError("Для G4 необходима подтверждённая средняя зона")
    low, high = ctx.working_window
    return repeatability(ctx, low, high), ProcedureEnvelope(max_x_mm=high + 60.0)
