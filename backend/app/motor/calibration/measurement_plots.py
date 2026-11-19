"""The measured fields needed to draw a calibration stage, including older archived stages."""

from collections.abc import Callable
from typing import Any, Literal

from app.motor.units import SIDES

PlotStage = Literal["S7", "D2", "F3", "X3", "M5", "G4"]
PlotUpdate = Callable[[dict[str, Any]], None]
PLOT_ROOT = {"S7": "sides", "D2": "sides", "F3": "points", "X3": "runs", "M5": "runs", "G4": "passes"}


def plot_result(code: str, result: dict[str, Any]) -> dict[str, Any]:
    if code not in PLOT_ROOT or PLOT_ROOT[code] not in result:
        return {}
    progress = {"partial": True} if result.get("partial") else {}
    if code in ("S7", "D2"):
        keys = ("map", "edges") if code == "S7" else ("table_up", "table_down")
        sides = result.get("sides") or {}
        return {**progress, "sides": {side: {k: sides[side][k] for k in keys if k in sides[side]}
                          for side in SIDES if isinstance(sides.get(side), dict)}}
    if code == "G4":
        evidence = {k: result[k] for k in ("heightsMm", "passes", "spreadLimitsN") if k in result}
        # The original G4 emitted one report row per direction, side and height, then one skew row.
        # Recover the recorded thresholds only when that layout is complete.
        heights, report = result.get("heightsMm") or [], result.get("report") or []
        skew_index = 4 * len(heights)
        if ("spreadLimitsN" not in evidence and heights and len(report) > skew_index
                and report[skew_index].get("label") == "Максимальный перекос"):
            rows = iter(report)
            evidence["spreadLimitsN"] = {d: {side: [(next(rows).get("comparison") or {}).get("limit") for _ in heights]
                                              for side in SIDES} for d in ("up", "down")}
        return {**progress, **evidence}
    keys = {"M5": ("runs", "stopSpeedMmS"), "X3": ("runs", "warningMm", "selectedK"), "F3": ("points",)}
    return {**progress, **{k: result[k] for k in keys[code] if k in result}}
