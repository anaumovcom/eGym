"""C1: hold stability margin by relay feedback (plan 15 §2.6, Åström–Hägglund).

The bar is kept around ``x0`` by a relay on top of the static window:
F = F_up + h below the target, F = F_dn − h above it. The limit cycle
amplitude ``a`` and period ``T_u`` give the ultimate gain K_u = 4h/(π·a),
which already contains the real bus delay. Hold gains are fractions of K_u.
"""

from __future__ import annotations

import math
from collections.abc import Generator
from typing import Any

from app.motor.calibration.fit import limit_cycle
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, Side


def relay_test(window: dict[Side, tuple[float, float]], *, relay_n: float = 6.0, seconds: float = 12.0, max_amplitude_mm: float = 15.0) -> Generator[Command, Frame, dict[str, Any]]:
    frame = yield Command({side: (window[side][0] + window[side][1]) / 2 for side in SIDES}, note="старт")
    x0 = frame.x_mean
    ts: list[float] = []
    xs: list[float] = []
    end = frame.t + seconds
    while frame.t < end:
        below = frame.x_mean < x0
        forces = {side: (window[side][1] + relay_n) if below else (window[side][0] - relay_n) for side in SIDES}
        frame = yield Command(forces)
        ts.append(frame.t)
        xs.append(frame.x_mean)
        if abs(frame.x_mean - x0) > max_amplitude_mm:
            raise ProcedureError("амплитуда релейного цикла вне огибающей")
    return {"t": ts, "x": xs, "x0": x0, "relay_n": relay_n}


def fit_relay(data: dict[str, Any]) -> dict[str, float]:
    cycle = limit_cycle(data["t"], data["x"], data["x0"])
    if cycle.amplitude_mm <= 0 or not cycle.regular:
        raise ProcedureError("устойчивый предельный цикл не получен")
    k_u = 4 * data["relay_n"] / (math.pi * cycle.amplitude_mm)  # per side: the relay acts on each side
    return {"k_u_n_per_mm": k_u, "period_s": cycle.period_s, "amplitude_mm": cycle.amplitude_mm}
