"""Quality metrics of a trace (plan 14 §7.2)."""

from __future__ import annotations

import math

from app.motor.twin.loop import Trace
from app.motor.units import SIDES


def _window(trace: Trace, start_s: float) -> range:
    first = next((i for i, t in enumerate(trace.t) if t >= trace.t[0] + start_s), len(trace.t))
    return range(first, len(trace.t))


def drift_mm_s(trace: Trace, start_s: float = 0.0) -> float:
    idx = _window(trace, start_s)
    if len(idx) < 2:
        return 0.0
    span = trace.t[idx[-1]] - trace.t[idx[0]]
    return max(abs(trace.x[side][idx[-1]] - trace.x[side][idx[0]]) / max(span, 1e-6) for side in SIDES)


def hold_osc_mm(trace: Trace, start_s: float = 1.0) -> float:
    idx = _window(trace, start_s)
    return max((max(trace.x[side][i] for i in idx) - min(trace.x[side][i] for i in idx)) for side in SIDES) if idx else 0.0


def limit_cycle(trace: Trace, center_mm: float, start_s: float = 0.0, threshold_mm: float = 1.0) -> int:
    idx = _window(trace, start_s)
    changes = 0
    for side in SIDES:
        sign = 0
        for i in idx:
            if abs(trace.x[side][i] - center_mm) <= threshold_mm or abs(trace.v[side][i]) < 0.5:
                continue
            s = 1 if trace.v[side][i] > 0 else -1
            if sign and s != sign:
                changes += 1
            sign = s
    return changes


def settle_s(trace: Trace, target_mm: float, band_mm: float = 2.0) -> float:
    last_out = 0.0
    for i, t in enumerate(trace.t):
        if any(abs(trace.x[side][i] - target_mm) > band_mm for side in SIDES):
            last_out = t - trace.t[0]
    return last_out


def sync_rms_mm(trace: Trace) -> float:
    if not trace.t:
        return 0.0
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(trace.x["left"], trace.x["right"], strict=True)) / len(trace.t))


def torque_rate_peak(trace: Trace) -> float:
    peak = 0.0
    for side in SIDES:
        f = trace.force[side]
        for i in range(1, len(f)):
            dt = trace.t[i] - trace.t[i - 1]
            if dt > 0 and trace.kind[i] == trace.kind[i - 1] == "force":
                peak = max(peak, abs(f[i] - f[i - 1]) / dt)
    return peak


def overspeed_events(trace: Trace, limit_mm_s: float) -> int:
    return sum(1 for side in SIDES for v in trace.v[side] if abs(v) > limit_mm_s)
