"""Shared pieces of the extended calibrations: context, outcome, operator prompts, hold and weightless laws."""

from __future__ import annotations

import math
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.motor.calibration.procedures.motion import Balance, Motion, hold_still
from app.motor.calibration.runner import Command, Frame, ProcedureEnvelope, ProcedureError, Prompt
from app.motor.drive.protocol import TorqueDrive
from app.motor.profile import MachineProfile, SafetyEnvelope
from app.motor.units import SIDES, Side

Gen = Generator[Command, Frame, Any]
Procedure = Generator[Command, Frame, dict[str, Any]]
PROMPT_TIMEOUT_S = 300.0
SIDE_LABEL = {"left": "Л", "right": "П"}


class Operator:
    """Reply channel from the UI to a running procedure."""

    def __init__(self) -> None:
        self.reply: tuple[float | None] | None = None  # (value,) once answered
        self.prompt: Prompt | None = None

    def answer(self, value: float | None) -> None:
        self.reply = (value,)


@dataclass
class Context:
    profile: MachineProfile
    balance: Balance
    safety: SafetyEnvelope
    options: dict[str, Any]
    operator: Operator
    drives: dict[Side, TorqueDrive]

    @property
    def top_mm(self) -> float:
        return min(float(self.profile.travel_mm.value) - 20.0, self.safety.soft_max_mm) - 80.0


@dataclass
class Outcome:
    report: list[dict[str, Any]]
    sides: dict[Side, dict[str, tuple[Any, float | None]]] = field(default_factory=dict)
    machine: dict[str, tuple[Any, float | None]] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None  # the check failed: the report is kept, the profile is not changed


Build = Callable[[Context], tuple[Procedure, ProcedureEnvelope | None]]
Fit = Callable[[dict[str, Any], Context], Outcome]


def line(label: str, value: str, ok: bool | None = None) -> dict[str, Any]:
    return {"label": label, "value": value, "ok": ok}


def finite(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


# ---------------------------------------------------------------- operator
def ask(
    operator: Operator,
    prompt: Prompt,
    forces: Callable[[Frame], dict[Side, float] | None],
    frame: Frame,
    *,
    progress: float | None = None,
    done: Callable[[Frame], bool] | None = None,
    timeout_s: float = PROMPT_TIMEOUT_S,
) -> Generator[Command, Frame, tuple[Frame, float | None]]:
    """Show ``prompt`` and keep commanding ``forces`` until the operator answers (or ``done`` detects the action).

    Returns the last frame and the answer (``None`` for a confirmation or a detected action).
    """

    operator.reply, operator.prompt = None, prompt
    start = frame.t
    try:
        while True:
            if operator.reply is not None:
                return frame, operator.reply[0]
            if done is not None and done(frame):
                return frame, None
            if frame.t - start > timeout_s:
                raise ProcedureError(f"нет ответа оператора за {timeout_s / 60:.0f} мин: {prompt.text}")
            frame = yield Command(forces(frame), note=prompt.text, progress=progress, prompt=prompt)
    finally:
        operator.prompt = None


def resting(balance: Balance) -> Callable[[Frame], dict[Side, float]]:
    """Bar on the stops: pressed down lightly (the landing force)."""

    return lambda frame: {side: balance.weight(side, frame.x(side)) - 0.5 * balance.coulomb_down[side] for side in SIDES}


# ---------------------------------------------------------------- laws
def smooth_sign(v: float, blend_mm_s: float) -> float:
    return max(-1.0, min(1.0, v / blend_mm_s))


def weightless_forces(balance: Balance, frame: Frame, gain_up: float, gain_down: float, *, blend_mm_s: float = 8.0, damping: float = 0.3) -> dict[Side, float]:
    """``W(x) + g·Fc·sign(v) − c·v``: the weightless law of the core (compensation of friction in motion)."""

    forces = {}
    for side in SIDES:
        v = frame.v(side)
        s = smooth_sign(v, blend_mm_s)
        friction = gain_up * balance.coulomb_up[side] * max(s, 0.0) + gain_down * balance.coulomb_down[side] * min(s, 0.0)
        forces[side] = balance.weight(side, frame.x(side)) + friction - damping * v
    return forces


def spring_forces(balance: Balance, frame: Frame, x0: dict[Side, float], k: float, c: float, *, limit_n: float | None = None) -> dict[Side, float]:
    """Hold: ``W(x) + k·(x0 − x) − c·v`` per side (the core's virtual spring)."""

    forces = {}
    for side in SIDES:
        spring = k * (x0[side] - frame.x(side)) - c * frame.v(side)
        if limit_n is not None:
            spring = max(-limit_n, min(limit_n, spring))
        forces[side] = balance.weight(side, frame.x(side)) + spring
    return forces


def hold_gains(profile: MachineProfile) -> tuple[float, float]:
    """The same choice as ``MotorCore.hold_gains`` with the default fractions."""

    if profile.hold_k_n_per_mm.value is not None and profile.hold_c_n_per_mm_s.value is not None:
        return float(profile.hold_k_n_per_mm.value), float(profile.hold_c_n_per_mm_s.value)
    k_u, period = profile.hold_ultimate_k_n_per_mm.value, profile.hold_ultimate_period_s.value
    if k_u is None or period is None:
        return 0.5, 0.3
    return 0.25 * float(k_u), 0.25 * float(k_u) * float(period) / 6.3


# ---------------------------------------------------------------- analysis
def steady(trace: Sequence[tuple[float, float, float, dict[Side, float]]], target: float, *, band: float = 0.6, settle_s: float = 0.6) -> tuple[list[float], dict[Side, list[float]]]:
    """Speeds and forces beyond the edge in the settled part of a governed move.

    Frames from ``settle_s`` after the bar first reached half the target speed, with the speed within
    ±``band`` of the target. The band is wide on purpose: the screw ripple (32 mm) and stick-slip make the
    speed swing around the target; the mean over many swings is the steady force.
    """

    speeds: list[float] = []
    extras: dict[Side, list[float]] = {side: [] for side in SIDES}
    moving_from: float | None = None
    for t, _x, v, extra in trace:
        if moving_from is None and v >= 0.5 * target:
            moving_from = t
        if moving_from is None or t - moving_from < settle_s or abs(v - target) > band * target:
            continue
        speeds.append(v)
        for side in SIDES:
            extras[side].append(extra[side])
    return speeds, extras


def sign_changes(values: Sequence[float], threshold: float) -> int:
    """Number of sign changes among the values beyond ±threshold (oscillation count)."""

    signs = [1 if v > threshold else -1 for v in values if abs(v) > threshold]
    return sum(1 for a, b in zip(signs, signs[1:], strict=False) if a != b)


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def observe(gen: Gen, on_frame: Callable[[Frame], None]) -> Gen:
    """Run a sub-procedure and pass every frame it receives to ``on_frame`` (recording without changing it)."""

    command = next(gen)
    while True:
        frame = yield command
        on_frame(frame)
        try:
            command = gen.send(frame)
        except StopIteration as stop:
            return stop.value


def recenter(balance: Balance, frame: Frame, x_mm: float, progress: float | None, tolerance_mm: float = 8.0) -> Gen:
    from app.motor.calibration.procedures.motion import travel

    if abs(frame.x_mean - x_mm) > tolerance_mm:
        frame = yield from travel(balance, frame, x_mm, progress_span=progress)
    return (yield from hold_still(balance, frame, progress=progress))


__all__ = [
    "Build", "Context", "Fit", "Gen", "Motion", "Operator", "Outcome", "Procedure", "Prompt",
    "ask", "finite", "hold_gains", "line", "mean", "recenter", "resting", "sign_changes", "smooth_sign",
    "spring_forces", "steady", "weightless_forces",
]
