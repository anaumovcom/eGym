"""SafetyEnvelope filter (last instance before the drive) and comm degradation policy (plan 14 §13.8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.motor.force.shaping import rate_limit
from app.motor.profile import SafetyEnvelope
from app.motor.units import clamp

CommState = Literal["ok", "extrapolate", "freeze", "fault"]


@dataclass(frozen=True)
class SafetyInput:
    target_n: float
    previous_n: float
    x_mm: float
    weight_n: float
    dt: float
    stale: bool = False


def apply_envelope(envelope: SafetyEnvelope, data: SafetyInput) -> float:
    force = clamp(data.target_n, -envelope.max_force_n_per_side, envelope.max_force_n_per_side)
    if data.stale:  # R13: no growth on a stale frame
        force = clamp(force, -abs(data.previous_n), abs(data.previous_n))
    force = rate_limit(data.previous_n, force, envelope.max_rate_n_per_s, data.dt)  # R12
    # R11: never push beyond the soft limits (gravity may still lower the bar onto the stops)
    if data.x_mm <= envelope.soft_min_mm:
        force = max(force, 0.0)
    if data.x_mm >= envelope.soft_max_mm:
        force = min(force, data.weight_n)
    return clamp(force, -envelope.max_force_n_per_side, envelope.max_force_n_per_side)


class CommMonitor:
    """1 missed frame — extrapolate; 2..fault−1 — freeze and decay to support; ≥ fault or write error — FAULT."""

    def __init__(self, freeze_frames: int, fault_frames: int) -> None:
        self.freeze_frames = freeze_frames
        self.fault_frames = fault_frames
        self.missed = 0
        self.latched = False

    def update(self, frame_ok: bool, write_ok: bool = True) -> CommState:
        if not write_ok:
            self.latched = True
        self.missed = 0 if frame_ok else self.missed + 1
        if self.latched or self.missed >= self.fault_frames:
            self.latched = True
            return "fault"
        if self.missed >= self.freeze_frames:
            return "freeze"
        if self.missed == 1:
            return "extrapolate"
        return "ok"

    def reset(self) -> None:
        self.missed = 0
        self.latched = False
