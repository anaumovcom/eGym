"""Read-only study of an unloaded bar using the active profile and its M5 record."""

import math
from typing import Any

from app.motor.calibration.middle_zone import TRAVEL_MARGIN_MM
from app.motor.estimation.observer import AlphaBetaObserver
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope
from app.motor.units import SIDES, mm_s_to_rpm, passport_mm_per_pulse, rpm_to_mm_s


def _measured(item: Measured) -> float | None:
    value = item.value
    return float(value) if item.provenance == "measured" and isinstance(value, int | float) and math.isfinite(value) else None


def _replay_reversal(profile: MachineProfile, target: float) -> dict[str, Any] | None:
    """One unloaded 400 mm sinusoidal stroke through the production observer, with one warm-up cycle."""
    stroke = 400.0
    omega = 2 * target / stroke
    duration = 2 * math.pi / omega
    configured_period = profile.loop_period_s.value
    dt = float(configured_period) if configured_period is not None else 0.04
    if not math.isfinite(dt) or dt <= 0 or not 6 <= duration / dt <= 20_000:
        return None
    observer = AlphaBetaObserver.from_profile(profile)
    ticks = math.ceil(duration / dt)
    stride = max(1, math.ceil(ticks / 150))
    pitch = passport_mm_per_pulse()
    points = []
    squared_error = 0.0
    previous = None
    crossing = None
    for i in range(-ticks, ticks + 1):
        t = i * dt
        position = stroke / 2 * (1 - math.cos(omega * t))
        reference = target * math.sin(omega * t)
        register = observer.speed_scale * target * math.sin(omega * (t - observer.speed_lag_s))
        feedback = rpm_to_mm_s(round(mm_s_to_rpm(register)))
        state = observer.update(round(position / pitch) * pitch, feedback, (i + ticks) * dt)
        if i >= 0:
            squared_error += (state.v_mm_s - reference) ** 2
            if i % stride == 0 or i == ticks:
                points.append([round(t, 4), round(reference, 2), round(state.v_mm_s, 2)])
            if crossing is None and t >= duration / 4 and previous is not None and previous > 0 >= state.v_mm_s:
                crossing = t - dt + dt * previous / (previous - state.v_mm_s)
        previous = state.v_mm_s
    return {
        "strokeMm": stroke, "cycleMs": dt * 1000, "cycleSource": profile.loop_period_s.provenance if configured_period is not None else "default",
        "periodS": duration, "rmsMmS": math.sqrt(squared_error / (ticks + 1)),
        "turnDelayMs": (crossing - duration / 2) * 1000 if crossing is not None else None,
        "points": points,
    }


def speed_study(profile: MachineProfile, envelope: SafetyEnvelope, target: float, brake_runs: list[dict[str, Any]], *, braking_matches_source: bool = True) -> dict[str, Any]:
    travel = _measured(profile.travel_mm)
    center = None
    if (travel is not None and all(_measured(profile.side(side).zero_counts) is not None for side in SIDES)
            and 0 <= envelope.soft_min_mm < travel / 2 < envelope.soft_max_mm <= travel - TRAVEL_MARGIN_MM):
        center = travel / 2
    lag = _measured(profile.fast_brake_lag_s)
    period = _measured(profile.loop_period_s)
    drive_limit = rpm_to_mm_s(envelope.speed_limit_rpm)
    alarm = rpm_to_mm_s(envelope.overspeed_rpm_alarm)
    directions = {}
    for name, direction, decel_item in (("up", 1, profile.fast_brake_up_mm_s2), ("down", -1, profile.fast_brake_down_mm_s2)):
        decel = _measured(decel_item)
        consistent = braking_matches_source and bool(decel_item.run_id and decel_item.run_id == profile.fast_brake_lag_s.run_id)
        measured = [
            r["brake_v_mm_s"] for r in brake_runs
            if r.get("direction") == direction and r.get("mode") == "brake" and r.get("ok") is True
            and isinstance(r.get("brake_v_mm_s"), int | float) and math.isfinite(r["brake_v_mm_s"]) and r["brake_v_mm_s"] > 50
        ] if consistent else []
        distance = None
        if consistent and lag is not None and lag >= 0 and decel is not None and decel > 0:
            distance = target * lag + target ** 2 / (2 * decel)
        available = None
        if center is not None:
            available = envelope.soft_max_mm - center if direction > 0 else center - envelope.soft_min_mm
        limit = min(envelope.max_speed_mm_s, drive_limit, alarm)
        if direction < 0:
            limit = min(limit, envelope.max_descent_mm_s)
        directions[name] = {
            "profileLimitMmS": round(limit, 1),
            "insideLimits": target <= limit and target < alarm,
            "measuredMinMmS": round(min(measured), 1) if measured else None,
            "measuredMaxMmS": round(max(measured), 1) if measured else None,
            "insideMeasuredRange": bool(measured and min(measured) <= target <= max(measured)),
            "brakingMm": distance,
            "availableMm": round(available, 1) if available is not None else None,
        }
    return {
        "profileVersion": profile.version, "targetMmS": target, "targetRpm": round(mm_s_to_rpm(target), 1),
        "driveLimitRpm": envelope.speed_limit_rpm, "alarmRpm": envelope.overspeed_rpm_alarm,
        "cycleMs": 1000 * period if period is not None and period > 0 else None,
        "travelPerCycleMm": target * period if period is not None and period > 0 else None,
        "centerMm": center, "directions": directions, "replay": _replay_reversal(profile, target),
    }
