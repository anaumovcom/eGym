"""S9 force scale and G1 static accuracy with a reference weight on the bar (plan 15 §2.2, §2.7).

The operator hangs a known weight on the bar (half on each side) before the
start. The window is measured as in S3 at ~10 mm and the shift of the balance
against the stored, unloaded W(x) is compared with m·g:

* S9: ``n_per_raw ← n_per_raw · m·g / ΔW`` and every force identified in the
  old units is rescaled by the same ratio;
* G1: the error ``ΔW − m·g`` in kg is the static accuracy of the load.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Generator
from typing import Any

from app.motor.calibration.fit import Stat
from app.motor.calibration.procedures.motion import Balance, land
from app.motor.calibration.procedures.statics import fit_balance, lift_off, measure_window
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.units import SIDES, G, Side, kgf_to_n

Procedure = Generator[Command, Frame, dict[str, Any]]
SCALE_LIMITS = (0.5, 2.0)


def loaded_window(start_forces: dict[Side, float], *, repeats: int = 3, clearance_mm: float = 10.0) -> Procedure:
    forces = dict(start_forces)
    frame = yield Command(dict(forces), note="старт", progress=0.0)
    frame = yield from lift_off(forces, frame, clearance_mm=clearance_mm, progress=0.05)
    frame, data = yield from measure_window(forces, frame, repeats=repeats, progress_span=(0.1, 0.9))
    estimate = fit_balance(data)
    balance = Balance(
        {side: [(estimate.height_mm, estimate.weight_n[side].mean)] for side in SIDES},
        {side: max(estimate.coulomb_up_n[side].mean, 1.0) for side in SIDES},
        {side: max(estimate.coulomb_down_n[side].mean, 1.0) for side in SIDES},
    )
    yield from land(balance, frame, progress=0.95)
    return data


def _ci(value: Stat) -> float:
    return value.ci95 if math.isfinite(value.ci95) else 0.0


def weight_shift(data: dict[str, Any], unloaded: Callable[[Side, float], float], reference_kg: float) -> dict[Side, dict[str, float]]:
    """ΔW per side against the stored W(x) at the measured height; half the reference on each side."""

    estimate = fit_balance(data)
    expected = kgf_to_n(reference_kg / 2)
    shifts: dict[Side, dict[str, float]] = {}
    for side in SIDES:
        loaded = estimate.weight_n[side]
        empty = unloaded(side, estimate.height_mm)
        shifts[side] = {
            "loaded_n": loaded.mean,
            "unloaded_n": empty,
            "delta_n": loaded.mean - empty,
            "delta_ci95": _ci(loaded),
            "expected_n": expected,
            "height_mm": estimate.height_mm,
        }
    return shifts


def fit_scale(shifts: dict[Side, dict[str, float]], n_per_raw: dict[Side, float], n_per_raw_ci: dict[Side, float | None]) -> dict[Side, dict[str, float]]:
    result: dict[Side, dict[str, float]] = {}
    for side in SIDES:
        shift = shifts[side]
        if shift["delta_n"] < 0.3 * shift["expected_n"]:
            raise ProcedureError(f"{side}: груз не обнаружен (ΔW = {shift['delta_n']:.1f} Н при ожидаемых {shift['expected_n']:.1f} Н)")
        ratio = shift["expected_n"] / shift["delta_n"]
        if not SCALE_LIMITS[0] <= ratio <= SCALE_LIMITS[1]:
            raise ProcedureError(f"{side}: масштаб отличается от текущего в {ratio:.2f} раза — проверьте массу груза")
        value = n_per_raw[side] * ratio
        relative = shift["delta_ci95"] / shift["delta_n"]
        result[side] = {"ratio": ratio, "n_per_raw": value, "ci95": value * relative, "old_n_per_raw": n_per_raw[side], "old_ci95": n_per_raw_ci[side] or 0.0}
    return result


def fit_accuracy(shifts: dict[Side, dict[str, float]], reference_kg: float, tolerance: float = 0.05, floor_kg: float = 0.5) -> dict[str, Any]:
    side_kg = reference_kg / 2
    limit = max(tolerance * side_kg, floor_kg)
    sides = {}
    for side in SIDES:
        shift = shifts[side]
        error_kg = (shift["delta_n"] - shift["expected_n"]) / G
        sides[side] = {"measured_kg": shift["delta_n"] / G, "expected_kg": side_kg, "error_kg": error_kg, "error_pct": 100 * error_kg / side_kg, "ok": abs(error_kg) <= limit}
    return {"sides": sides, "limit_kg": limit, "ok": all(item["ok"] for item in sides.values())}
