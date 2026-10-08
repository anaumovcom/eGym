"""Commissioning wizard, first stages (plan 15 §3): B5 → S1–S3 → C1 → candidate MachineProfile.

Every stage runs through ``CalibrationRunner`` (dead-man, envelope, abort).
The result is a *candidate*: it becomes active only after verification and
operator acceptance (``store.save_version``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from app.motor.calibration.procedures.direction import direction_test
from app.motor.calibration.procedures.relay import fit_relay, relay_test
from app.motor.calibration.procedures.statics import balance_and_friction, fit_balance
from app.motor.calibration.runner import CalibrationRunner, ProcedureEnvelope, ProcedureError
from app.motor.drive.protocol import TorqueDrive
from app.motor.profile import MachineProfile, Measured
from app.motor.units import SIDES, Side

DIRECTION_ENVELOPE = ProcedureEnvelope(max_speed_mm_s=200.0, min_x_mm=-30.0, max_x_mm=30.0)


@dataclass
class WizardReport:
    profile: MachineProfile
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    ok: bool = True
    error: str | None = None


def _measured(value: Any, ci95: float | None, run_id: str) -> Measured:
    return Measured(value, ci95, "measured", run_id, datetime.now(UTC).isoformat())


def _set_profiles(drives: dict[Side, TorqueDrive], profile: MachineProfile) -> None:
    for side in SIDES:
        drive = drives[side]
        if hasattr(drive, "profile"):
            drive.profile = profile.side(side)  # type: ignore[attr-defined]


def commission(
    drives: dict[Side, TorqueDrive],
    tick: Callable[[], float],
    profile: MachineProfile,
    *,
    dead_man: Callable[[], bool] = lambda: True,
    envelope: ProcedureEnvelope | None = None,
) -> WizardReport:
    report = WizardReport(profile)
    runner = CalibrationRunner(drives, tick, envelope, dead_man)
    try:
        # B5: direction (the bar rests on the bottom stops; stiction may make it hop a few mm)
        run_id = f"B5-{uuid.uuid4().hex[:8]}"
        result = runner.run(direction_test({side: profile.side(side).sign for side in SIDES}), envelope=DIRECTION_ENVELOPE)
        report.stages["B5"] = {"status": result.status, "reason": result.reason, **result.data}
        if result.status != "done":
            raise ProcedureError(f"B5: {result.reason}")
        for side in SIDES:
            sign = result.data["sides"][side]["direction_sign"]
            profile = profile.with_side(side, replace(profile.side(side), direction_sign=_measured(sign, None, run_id)))
        _set_profiles(drives, profile)

        # S1–S3: static window just above the stops
        run_id = f"S3-{uuid.uuid4().hex[:8]}"
        result = runner.run(balance_and_friction({side: 0.0 for side in SIDES}))
        report.stages["S3"] = {"status": result.status, "reason": result.reason}
        if result.status != "done":
            raise ProcedureError(f"S3: {result.reason}")
        estimate = fit_balance(result.data)
        report.stages["S3"].update(estimate.to_dict())
        for side in SIDES:
            current = profile.side(side)
            profile = profile.with_side(side, replace(
                current,
                gravity_map=_measured([(estimate.height_mm, estimate.weight_n[side].mean)], estimate.weight_n[side].ci95, run_id),
                coulomb_up_n=_measured(estimate.coulomb_up_n[side].mean, estimate.coulomb_up_n[side].ci95, run_id),
                coulomb_down_n=_measured(estimate.coulomb_down_n[side].mean, estimate.coulomb_down_n[side].ci95, run_id),
                stribeck_extra_n=_measured(0.0, None, run_id),  # stiction is inside the measured window
            ))
        _set_profiles(drives, profile)

        # C1: relay test around the current height
        run_id = f"C1-{uuid.uuid4().hex[:8]}"
        window = {side: (estimate.weight_n[side].mean - estimate.coulomb_down_n[side].mean, estimate.weight_n[side].mean + estimate.coulomb_up_n[side].mean) for side in SIDES}
        relay: dict[str, float] | None = None
        for relay_n in (6.0, 12.0):  # a stronger relay if dry friction makes the cycle irregular
            result = runner.run(relay_test(window, relay_n=relay_n))
            report.stages["C1"] = {"status": result.status, "reason": result.reason, "relay_n": relay_n}
            if result.status != "done":
                raise ProcedureError(f"C1: {result.reason}")
            try:
                relay = fit_relay(result.data)
                break
            except ProcedureError as error:
                report.stages["C1"]["reason"] = str(error)
        if relay is None:
            raise ProcedureError("C1: устойчивый предельный цикл не получен")
        report.stages["C1"].update(relay)
        profile = replace(
            profile,
            hold_ultimate_k_n_per_mm=_measured(relay["k_u_n_per_mm"], None, run_id),
            hold_ultimate_period_s=_measured(relay["period_s"], None, run_id),
        )
    except ProcedureError as error:
        report.ok = False
        report.error = str(error)
        for drive in drives.values():
            drive.support()
    report.profile = profile
    return report
