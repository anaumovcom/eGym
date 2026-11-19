"""The trainer's own force law inside a calibration: ``MotorCore`` drives the bar, a probe force plays the user.

The feel calibrations (F, X4, G2, L3, G3) measure what the user will feel, so they run the production law,
not a copy. A *virtual user* is a force added on top of the law's command: the drive cannot tell it from a
hand, and it is known exactly — unlike a real hand, which needs a load cell.

* ``Trainer`` — a ``MotorCore`` in training / weightless / hold, started from the current frame;
* ``drive`` — command the law + a probe until a time, a condition, an x guard or a speed guard;
* ``rep_user`` — a person doing reps: a speed regulator around the load between two heights;
* ``handoff`` — a governed move up to speed, then the law takes the moving bar (no stiction start).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from app.motor.calibration.procedures.common import Context, Gen, mean
from app.motor.calibration.procedures.motion import Balance, Motion, _governed
from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.core import CoreOutput, MotorCore
from app.motor.force.load_models import LoadSetpoint
from app.motor.profile import MachineProfile
from app.motor.units import SIDES, Side

Probe = Callable[[Frame], float]
STUCK_BOOST_N_S = 120.0


@dataclass(frozen=True)
class Row:
    t: float
    x: float
    v: float
    probe: float  # virtual user force per side, N
    force: float  # the law's command, mean of the sides, N
    user: float  # the core's user force estimate (moving value or static upper bound), mean of the sides
    phase: str
    skew: float | None  # x_left − x_right on a shared timestamp


class Trainer:
    """``MotorCore`` started in ``mode`` from the current frame; release detection off unless asked."""

    def __init__(
        self,
        ctx: Context,
        *,
        mode: str = "train",
        load: LoadSetpoint | None = None,
        tunables: dict[str, float] | None = None,
        inertia: float | None = None,
        release: bool = False,
        profile: MachineProfile | None = None,
        balance: Balance | None = None,
        plain: bool = False,
    ) -> None:
        self.ctx = ctx
        self.balance = balance or ctx.balance
        self.core = MotorCore(profile or ctx.profile, envelope=ctx.safety)
        if tunables:
            self.core.tunables = replace(self.core.tunables, **tunables)
            self.core.phase.hysteresis = self.core.tunables.phase_hysteresis_mm_s
            self.core.phase.blend_s = max(self.core.tunables.phase_blend_s, 1e-6)
        self.core.inertia_override = inertia
        self.core.release_enabled = release
        if plain:  # the bare law W + g·F(v) − L: no prediction, no track/load corrections (a clean plant measurement)
            self.core.horizon_s = 0.0
            self.core.friction = {side: replace(model, track_gain=0.0, load_gain=0.0) for side, model in self.core.friction.items()}
        self.mode = mode
        self.load = load or LoadSetpoint()
        self.started = False
        self.last: CoreOutput | None = None

    def _start(self, frame: Frame) -> None:
        # no core step here: a second step on the same frame would give the observer dt → 0 and a huge acceleration
        core = self.core
        # start where the law will be (window middle minus the load), not rate-limited from elsewhere
        load = self.load.load_n if self.mode == "train" else 0.0
        core.previous = {side: force - load for side, force in self.balance.mid(frame).items()}
        # the first step must not be rate-limited as if no time passed: the friction compensation (tens of N)
        # comes in at once, like the governed move's force that held the bar a frame ago
        core._t = frame.t - float(self.ctx.profile.loop_period_s.value or 0.05)
        core.command("ready")
        core.command("hold")
        if self.mode == "train":
            core.command("train")
            core.set_load(self.load)
        elif self.mode == "weightless":
            core.command("weightless")
        self.started = True

    def set_load(self, load: LoadSetpoint) -> None:
        self.load = load
        if self.started and self.core.supervisor.mode.value == "training":
            self.core.set_load(load)

    def forces(self, frame: Frame) -> dict[Side, float]:
        if not self.started:
            self._start(frame)
        out = self.core.step(frame.samples, frame.t)
        self.last = out
        if out.kind != "force":
            raise ProcedureError(f"закон тренажёра перешёл в режим «{out.mode.value}» ({self.core.supervisor.reason or 'без причины'})")
        return dict(out.forces_n)

    @property
    def user(self) -> float:
        if self.last is None or not self.last.user_force:
            return 0.0
        return mean([u.value_n if u.confidence == "moving" else u.high_n for u in self.last.user_force.values()])

    @property
    def phase(self) -> str:
        return self.core.phase.phase


def drive(
    trainer: Trainer,
    frame: Frame,
    probe: Probe,
    *,
    seconds: float,
    note: str,
    progress: float | None,
    until: Callable[[Frame], bool] | None = None,
    rows: list[Row] | None = None,
    x_range: tuple[float, float] | None = None,
    speed_cap: float | None = None,
) -> Gen:
    """Law + probe until ``seconds`` / ``until`` / leaving ``x_range`` / faster than ``speed_cap``.

    Returns ``(frame, why)`` with ``why`` in ``time | until | range | fast``.
    """

    t0 = frame.t
    while frame.t - t0 < seconds:
        if until is not None and until(frame):
            return frame, "until"
        if x_range is not None and not x_range[0] <= frame.x_mean <= x_range[1]:
            return frame, "range"
        if speed_cap is not None and frame.max_abs_speed > speed_cap:
            return frame, "fast"
        push = probe(frame)
        forces = trainer.forces(frame)
        if rows is not None:
            rows.append(Row(frame.t, frame.x_mean, frame.v_mean, push, mean(list(forces.values())), trainer.user, trainer.phase, frame.skew_mm))
        frame = yield Command({side: forces[side] + push for side in SIDES}, note=note, progress=progress)
    return frame, "time"


def expected(ctx: Context, load_n: float, *, speed_mm_s: float = 60.0, profile: MachineProfile | None = None, inertia: float | None = None) -> tuple[float, float]:
    """What the law should leave to the user at ``load_n``: (effective mass kg, residual friction N up), per side."""

    core = MotorCore(profile or ctx.profile, envelope=ctx.safety)
    core.set_load(LoadSetpoint(load_n=load_n))
    core.inertia_override = inertia
    masses, residual = [], []
    for side in SIDES:
        machine = float(core.profile.side(side).moving_mass_kg.value)
        masses.append(machine - core.inertia_share(side) * (machine - core.virtual_mass_kg))
        residual.append((1 - core.tunables.friction_gain_up) * core.friction[side].force(speed_mm_s))
    return mean(masses), mean(residual)


def expected_down(ctx: Context, load_n: float, *, speed_mm_s: float = 60.0, profile: MachineProfile | None = None) -> float:
    """Residual friction going down at ``load_n`` (the law compensates more of it under a load), N per side."""

    core = MotorCore(profile or ctx.profile, envelope=ctx.safety)
    return mean([(1 - core._descent_gain(side, load_n)) * abs(core.friction[side].force(-speed_mm_s)) for side in SIDES])


def user_gain(ctx: Context, mass_kg: float) -> float:
    """Speed-correction gain of a virtual user, N per mm/s, stable against the bus delay for ``mass_kg``.

    The probe acts after period + delay like any controller; m/(4·T) keeps it well below the limit m/T.
    """

    period = float(ctx.profile.loop_period_s.value or 0.04) + float(ctx.profile.loop_delay_s.value or 0.04)
    return max(0.03, min(1.0, mass_kg / (4 * period) / 1000))


def rep_user(
    load_n: float, low_mm: float, high_mm: float, speed_mm_s: float, *, gain: float, feed_n: float = 0.0, feed_down_n: float | None = None, limit_n: float = 80.0,
    down_load_n: float | None = None, breakaway_n: float = 0.0, overspeed_damping: float = 0.0,
) -> Probe:
    """A person doing reps: holds ``load_n``, pushes ``feed_n`` with the motion (felt friction; ``feed_down_n`` going
    down, if it differs) and corrects the speed towards ±``speed_mm_s`` with ``gain`` (turns at the heights)."""

    direction = 1
    boost = 0.0
    previous_t: float | None = None
    braking_span = (high_mm - low_mm) / 4

    def probe(frame: Frame) -> float:
        nonlocal direction, boost, previous_t
        dt = min(0.1, max(0.0, frame.t - previous_t)) if previous_t is not None else 0.0
        previous_t = frame.t
        if (direction > 0 and frame.x_mean >= high_mm) or (direction < 0 and frame.x_mean <= low_mm):
            direction, boost = -direction, 0.0
        remaining = high_mm - frame.x_mean if direction > 0 else frame.x_mean - low_mm
        target = speed_mm_s * min(1.0, max(0.35, remaining / braking_span))
        along = direction * frame.v_mean
        # Start taking up stiction as the bar slows into a turn. Integrating through fast reverse
        # travel would store a large impulse and throw a low-inertia bar through its turnaround.
        if -0.5 * speed_mm_s < along < 2.0:
            boost = min(limit_n, max(boost, breakaway_n) + STUCK_BOOST_N_S * dt)
        elif along > 0.3 * target:
            boost = 0.0
        friction = feed_down_n if direction < 0 and feed_down_n is not None else feed_n
        correction = direction * (friction + boost) + gain * (direction * target - frame.v_mean)
        # During final verification a virtual lifter catches a bar that outruns the prescribed
        # pace by more than 25%. Ordinary variations around a turn must remain measurable.
        # The cap on total hand force still applies in each direction.
        excess = max(0.0, abs(frame.v_mean) - 1.25 * speed_mm_s)
        correction -= overspeed_damping * excess * (1 if frame.v_mean > 0 else -1)
        # Eccentric trials ask the virtual lifter to support more weight on descent. Base the
        # hand's feed-forward on observed motion independently of the phase detector under test.
        if down_load_n is not None:
            correction += (down_load_n - load_n) * max(0.0, min(1.0, -frame.v_mean / (0.35 * speed_mm_s)))
        return load_n + max(-limit_n, min(limit_n, correction))

    return probe


def handoff(balance: Balance, frame: Frame, direction: int, speed_mm_s: float, *, note: str, progress: float | None, travel_mm: float = 60.0) -> Gen:
    """Governed move until the bar runs steadily at ``speed_mm_s`` (or after ``travel_mm``): the law then starts moving."""

    start = frame.x_mean
    count = {"n": 0}

    def ready(f: Frame, _extra: dict[Side, float]) -> bool:
        count["n"] = count["n"] + 1 if direction * f.v_mean >= 0.8 * speed_mm_s else 0
        return count["n"] >= 3 or direction * (f.x_mean - start) > travel_mm

    return (yield from _governed(balance, frame, direction, speed_mm_s, ready, note=note, progress=lambda _f: progress, state=Motion()))


def slope(points: list[tuple[float, float]]) -> float | None:
    """Least-squares slope of (t, y)."""

    if len(points) < 3:
        return None
    t_mean = mean([t for t, _ in points])
    y_mean = mean([y for _, y in points])
    den = sum((t - t_mean) ** 2 for t, _ in points)
    return sum((t - t_mean) * (y - y_mean) for t, y in points) / den if den > 0 else None


def reversals(rows: list[Row], threshold_mm_s: float = 3.0) -> list[int]:
    """Indices where the bar's direction changed (speeds beyond ±threshold)."""

    found, sign = [], 0
    for i, row in enumerate(rows):
        if abs(row.v) < threshold_mm_s:
            continue
        s = 1 if row.v > 0 else -1
        if sign and s != sign:
            found.append(i)
        sign = s
    return found


def summary(rows: list[Row]) -> dict[str, Any]:
    return {"frames": len(rows), "x": [round(min((r.x for r in rows), default=0.0), 1), round(max((r.x for r in rows), default=0.0), 1)]}
