"""Motion on top of a known static window (S3): governed travel, stop, landing on the stops.

Every move is built on the window ``[W − Fc⁻, W + Fc⁺]``: the force sits just
beyond the edge in the direction of travel and an integrator (N/s, independent
of the frame period) keeps the speed inside a band. Above 2.2× the target speed
the force jumps to the middle of the window — dry friction stops the bar — and
the move restarts. The middle of the window holds the bar still; the stops end
a descent.

What the motion calibrations add (all optional, defaults work without them):

* M1 ``liftoff``: force beyond the up edge needed to leave the bottom stops
  (adhesion, dwell) — a feed-forward while a side rests on the stops;
* M2 ``feed_up``/``feed_down``: force beyond the edge that keeps ~20 mm/s —
  the integrator starts there instead of below the edge;
* M3 ``brake_lag_s``/``brake_decel``: the stopping distance of the middle of
  the window — a move switches to the stop that much before the target.

If the bar does not move at the integrator cap, the cap grows in steps of
0.25·Fc up to +1·Fc (stuck on the stops after a long rest); once it moves
the force drops back at once so the released adhesion does not throw the bar.
Speed comes from PA_1C1 cross-checked with the encoder: a single register
glitch (seen on the A6: 90 mm/s on a resting bar) is replaced by Δx/Δt.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.profile import MachineProfile
from app.motor.units import SIDES, Side

Gen = Generator[Command, Frame, Any]
STILL_MM_S = 1.0
NO_MOTION_TIMEOUT_S = 20.0
FEED_SPEED_MM_S = 20.0  # M2 reference speed
STOPS_MM = 3.0  # below: the side rests on the bottom stops
ESCALATE_S = 3.0  # at the cap and still this long → raise the cap
GLITCH_MM_S = 20.0  # PA_1C1 vs Δx/Δt disagreement treated as a register glitch
DEFAULT_BRAKE_LAG_S = 0.1
LANDED_MM = 20.0
RUNAWAY_MM_S = 70.0  # below the procedure envelope (80 mm/s)
MIN_PROFILE_SPEED_MM_S = 5.0
SYNC_LIMIT_FC = 0.3  # sync correction ≤ 0.3·Fc per side


def _value(item: Any) -> float | None:
    value = getattr(item, "value", None)
    return None if value is None else float(value)


@dataclass
class Balance:
    points: dict[Side, list[tuple[float, float]]]  # [(x, W)] sorted by x
    coulomb_up: dict[Side, float]
    coulomb_down: dict[Side, float]
    liftoff: dict[Side, float] = field(default_factory=dict)  # M1: beyond the up edge, on the stops
    feed_up: dict[Side, float] = field(default_factory=dict)  # M2: beyond the edge at FEED_SPEED_MM_S
    feed_down: dict[Side, float] = field(default_factory=dict)
    brake_lag_s: float | None = None  # M3
    brake_decel: dict[int, float] = field(default_factory=dict)  # direction → mm/s²
    table_up: dict[Side, list[tuple[float, float]]] = field(default_factory=dict)  # P1: [(v, extra)]
    table_down: dict[Side, list[tuple[float, float]]] = field(default_factory=dict)  # P2
    accel_mm_s2: float | None = None  # A1: target speed ramps up at this rate
    decel_mm_s2: float | None = None  # A2: target speed ramps down to the stop point
    landing_speed_mm_s: float | None = None  # A3
    sync_k: float = 0.0  # X3: force per mm of skew, pulls the sides together during moves

    @classmethod
    def from_profile(cls, profile: MachineProfile) -> Balance:
        """Window edges = breakaway: kinetic Coulomb + stiction extra (D2 splits them, the window stays the same)."""

        def breakaway(side: Side, key: str) -> float:
            data = profile.side(side)
            return float(getattr(data, key).value) + float(data.stribeck_extra_n.value or 0.0)

        def table(key: str) -> dict[Side, float]:
            return {side: v for side in SIDES if (v := _value(getattr(profile.side(side), key))) is not None}

        def curve(key: str) -> dict[Side, list[tuple[float, float]]]:
            return {side: sorted((float(v), float(f)) for v, f in points) for side in SIDES if (points := getattr(profile.side(side), key).value)}

        decel = {d: v for d, key in ((1, "brake_decel_up_mm_s2"), (-1, "brake_decel_down_mm_s2")) if (v := _value(getattr(profile, key))) is not None and v > 0}
        return cls(
            {side: sorted((float(x), float(w)) for x, w in profile.side(side).gravity_map.value) for side in SIDES},
            {side: breakaway(side, "coulomb_up_n") for side in SIDES},
            {side: breakaway(side, "coulomb_down_n") for side in SIDES},
            liftoff=table("liftoff_extra_n"),
            feed_up=table("travel_extra_up_n"),
            feed_down=table("travel_extra_down_n"),
            brake_lag_s=_value(profile.brake_lag_s),
            brake_decel=decel,
            table_up=curve("travel_table_up"),
            table_down=curve("travel_table_down"),
            accel_mm_s2=_value(profile.accel_mm_s2),
            decel_mm_s2=_value(profile.decel_mm_s2),
            landing_speed_mm_s=_value(profile.landing_speed_mm_s),
            sync_k=_value(profile.sync_k_n_per_mm) or 0.0,
        )

    def weight(self, side: Side, x_mm: float) -> float:
        points = self.points[side]
        if len(points) == 1:
            return points[0][1]
        xs = [p[0] for p in points]
        i = bisect.bisect_left(xs, x_mm)
        if i <= 0:
            return points[0][1]
        if i >= len(points):
            return points[-1][1]
        (x0, w0), (x1, w1) = points[i - 1], points[i]
        return w0 + (w1 - w0) * (x_mm - x0) / (x1 - x0)

    def friction(self, side: Side, direction: int) -> float:
        return self.coulomb_up[side] if direction > 0 else self.coulomb_down[side]

    def edge(self, side: Side, x_mm: float, direction: int) -> float:
        return self.weight(side, x_mm) + direction * self.friction(side, direction)

    def mid(self, frame: Frame) -> dict[Side, float]:
        return {side: self.weight(side, frame.x(side)) for side in SIDES}

    def set_point(self, side: Side, x_mm: float, weight_n: float, merge_mm: float = 20.0) -> None:
        kept = [p for p in self.points[side] if abs(p[0] - x_mm) > merge_mm]
        self.points[side] = sorted([*kept, (x_mm, weight_n)])

    def feed(self, side: Side, direction: int, speed_mm_s: float = FEED_SPEED_MM_S) -> float | None:
        """Force beyond the edge for a steady ``speed_mm_s``: P1/P2 table (interpolated), else the M2 point."""

        points = (self.table_up if direction > 0 else self.table_down).get(side)
        if points:
            if len(points) == 1 or speed_mm_s <= points[0][0]:
                return points[0][1]
            if speed_mm_s >= points[-1][0]:
                return points[-1][1]
            i = bisect.bisect_left([v for v, _ in points], speed_mm_s)
            (v0, f0), (v1, f1) = points[i - 1], points[i]
            return f0 + (f1 - f0) * (speed_mm_s - v0) / (v1 - v0)
        return (self.feed_up if direction > 0 else self.feed_down).get(side)

    def target_speed(self, speed_mm_s: float, elapsed_s: float, remaining_mm: float | None) -> float:
        """Speed profile of a move: A1 ramp-up from 5 mm/s, A2 ramp-down √(2·a·d) to the stop point."""

        v = speed_mm_s
        if self.accel_mm_s2:
            v = min(v, MIN_PROFILE_SPEED_MM_S + self.accel_mm_s2 * elapsed_s)
        if self.decel_mm_s2 and remaining_mm is not None:
            v = min(v, MIN_PROFILE_SPEED_MM_S + math.sqrt(2 * self.decel_mm_s2 * max(remaining_mm, 0.0)))
        return max(v, MIN_PROFILE_SPEED_MM_S)

    def brake_distance(self, direction: int, speed_mm_s: float) -> float:
        """Distance the bar runs after the force switches to the middle of the window (M3; lag only before it)."""

        v = max(0.0, speed_mm_s)
        lag = self.brake_lag_s if self.brake_lag_s is not None else DEFAULT_BRAKE_LAG_S
        decel = self.brake_decel.get(direction)
        return v * lag + (v * v / (2 * decel) if decel else 0.0)


def speed(frame: Frame, previous: Frame | None) -> float:
    """Mean bar speed from PA_1C1; a register glitch (disagrees with the encoder by > 20 mm/s) → Δx/Δt."""

    v = frame.v_mean
    if previous is None or frame.t <= previous.t:
        return v
    v_pos = (frame.x_mean - previous.x_mean) / (frame.t - previous.t)
    return v_pos if abs(v - v_pos) > GLITCH_MM_S else v


def _still(frame: Frame) -> bool:
    return all(abs(frame.v(side)) < STILL_MM_S for side in SIDES)


def hold_still(
    balance: Balance, frame: Frame, *, note: str = "остановка", progress: float | None = None, timeout_s: float = 4.0, liftoff: bool = False,
) -> Gen:
    """Middle of the window until both sides are still for 5 frames."""

    still = 0
    start = frame.t
    while still < 5:
        if frame.t - start > timeout_s:
            raise ProcedureError("гриф не останавливается серединой окна невесомости: повторите S3")
        frame = yield Command(balance.mid(frame), note=note, progress=progress, liftoff=liftoff)
        still = still + 1 if _still(frame) else 0
    return frame


@dataclass
class Motion:
    """State of a governed move, readable by ``done`` callbacks and procedures that measure the move (M2, M3)."""

    v: float = 0.0  # robust bar speed in the move direction, mm/s
    extra: dict[Side, float] = field(default_factory=dict)  # force beyond the window edge (integrator)
    moving: bool = False
    escalations: int = 0  # times the cap was raised because the bar stayed put
    target_v: float = 0.0  # current target of the speed profile
    profile_trace: list[tuple[float, float, float]] | None = None  # (t, target_v, v) if recorded
    released_at: float | None = None  # first motion after an escalation or a lift-off from the stops
    trace: list[tuple[float, float, float, dict[Side, float]]] | None = None  # (t, x_mean, v, extra) if recorded


def _governed(
    balance: Balance,
    frame: Frame,
    direction: int,
    speed_mm_s: float,
    done: Any,
    *,
    note: str,
    progress: Any,
    state: Motion | None = None,
    remaining: Any = None,
    force_offset: Any = None,
) -> Gen:
    """Move in ``direction`` at about ``speed_mm_s`` until ``done(frame, extra)``; returns the last frame.

    ``remaining(frame)`` (mm to the stop point) lets the A2 ramp-down slow the move; the A1 ramp-up starts
    at 5 mm/s. ``force_offset(frame)`` adds a test force (a simulated load) to both sides.

    The integrator works in N/s (frame period independent) and starts at the M2 feed force if measured.
    At the cap and still for ``ESCALATE_S`` the cap rises by 0.25·Fc (up to +1·Fc); the first motion
    after that (or after leaving the stops with the M1 lift-off force) drops the extra back to the
    normal cap so the released stiction does not throw the bar.
    """

    state = state if state is not None else Motion()
    friction = {side: balance.friction(side, direction) for side in SIDES}

    def start() -> dict[Side, float]:
        return {side: feed if (feed := balance.feed(side, direction, speed_mm_s)) is not None else -0.15 * friction[side] for side in SIDES}

    extra = start()
    rate = {side: max(4.0, 0.2 * friction[side]) for side in SIDES}  # N/s
    # P term on the speed error: answers the friction drop right after breakaway (stick-slip) at once;
    # ≤ 0.5 N per mm/s keeps m/Kp ≥ ~0.12 s against a 1–3 frame bus delay with m ≈ 60 kg
    kp = {side: min(0.5, 0.4 * friction[side] / max(speed_mm_s, 5.0)) for side in SIDES}
    p_cap = {side: 0.5 * friction[side] for side in SIDES}
    # the post-breakaway overshoot (stiction drop) is the P term's job; stop the move only on a real runaway
    # (fast moves of F3 need room above their own speed; their envelope is wider)
    runaway_mm_s = min(max(2.5 * speed_mm_s, speed_mm_s + 30.0), max(RUNAWAY_MM_S, speed_mm_s + 40.0))
    cap0 = {side: max(0.6 * friction[side], 10.0) for side in SIDES}
    cap = dict(cap0)
    cap_max = {side: cap0[side] + friction[side] for side in SIDES}
    previous: Frame | None = None
    moving_at, stuck_since, t_prev = frame.t, None, frame.t
    lifting = direction > 0 and any(frame.x(side) < STOPS_MM for side in SIDES)
    t_start = frame.t
    while True:
        v = direction * speed(frame, previous)
        state.v, state.extra, state.moving = v, extra, v > STILL_MM_S
        target_v = balance.target_speed(speed_mm_s, frame.t - t_start, remaining(frame) if remaining else None)
        state.target_v = target_v
        if done(frame, extra):
            break
        dt = min(max(frame.t - t_prev, 0.0), 0.25)
        t_prev, previous = frame.t, frame
        if v > runaway_mm_s:
            frame = yield from hold_still(
                balance, frame, note=f"{note}: торможение", progress=progress(frame), liftoff=lifting or cap != cap0 or _freshly_lifted(state, frame),
            )
            extra, previous, t_prev = start(), None, frame.t
            continue
        if v > STILL_MM_S:
            moving_at, stuck_since = frame.t, None
            if cap != cap0 or (lifting and all(frame.x(side) >= STOPS_MM for side in SIDES)):
                # stiction released: back to the normal band at once
                extra = {side: min(extra[side], start()[side] + 0.3 * friction[side]) for side in SIDES}
                cap, lifting = dict(cap0), False
                state.released_at = frame.t
        else:
            if frame.t - moving_at > NO_MOTION_TIMEOUT_S:
                raise ProcedureError(
                    "гриф не трогается с места даже с запасом силы +1·трение: выполните M1 (отрыв от упоров) и проверьте окно невесомости (S3)"
                )
            at_cap = all(extra[side] >= cap[side] - 1e-6 for side in SIDES)
            stuck_since = (stuck_since or frame.t) if at_cap else None
            if stuck_since is not None and frame.t - stuck_since > ESCALATE_S and any(cap[side] < cap_max[side] for side in SIDES):
                cap = {side: min(cap[side] + 0.25 * friction[side], cap_max[side]) for side in SIDES}
                stuck_since, state.escalations = None, state.escalations + 1
        for side in SIDES:
            # integral of the speed error: ``rate`` N/s at half the target speed missing, twice that when too fast
            error = max(-2.0, min(1.0, (target_v - v) / (0.5 * target_v)))
            extra[side] = min(extra[side] + rate[side] * error * dt, cap[side])
        forces = {}
        effective = {}
        for side in SIDES:
            # 90 % of the M1 lift-off force: the integrator adds the rest gently instead of overshooting it
            lift = 0.9 * balance.liftoff.get(side, 0.0) if direction > 0 and frame.x(side) < STOPS_MM else 0.0
            p_term = max(-p_cap[side], min(p_cap[side], kp[side] * (target_v - v)))
            if lift > 0 or v <= STILL_MM_S:
                # standing (on the stops or held by stiction): the speed is 0 by contact, not by too little force —
                # a P kick here only makes the breakaway violent; the integrator finds the force
                p_term = min(p_term, 0.0)
            other: Side = "right" if side == "left" else "left"
            sync = max(-SYNC_LIMIT_FC * friction[side], min(SYNC_LIMIT_FC * friction[side], balance.sync_k * (frame.x(other) - frame.x(side))))
            effective[side] = extra[side] + p_term
            offset = force_offset(frame) if force_offset else 0.0
            forces[side] = balance.edge(side, frame.x(side), direction) + direction * (extra[side] + lift + p_term) + sync + offset
        if state.trace is not None:
            state.trace.append((frame.t, frame.x_mean, v, effective))
        if state.profile_trace is not None:
            state.profile_trace.append((frame.t, target_v, v))
        frame = yield Command(forces, note=note, progress=progress(frame), liftoff=lifting or cap != cap0 or _freshly_lifted(state, frame))
    return frame


def _freshly_lifted(state: Motion, frame: Frame) -> bool:
    """Within 1.5 s after the bar left the stops (or broke free at an escalated force)."""

    return state.released_at is not None and frame.t - state.released_at < 1.5


def travel(
    balance: Balance,
    frame: Frame,
    target_mm: float,
    *,
    speed_mm_s: float = 15.0,
    note: str | None = None,
    progress_span: tuple[float, float] | float | None = None,
    state: Motion | None = None,
) -> Gen:
    """Governed move to ``target_mm`` (bar mean), then a stop in the middle of the window.

    The stop is commanded the braking distance (M3) before the target, so the bar stops on it.
    """

    start = frame.x_mean
    direction = 1 if target_mm > start else -1
    label = note or f"{'подъём' if direction > 0 else 'опускание'} на {target_mm:.0f} мм"
    if isinstance(progress_span, tuple):
        p0, p1 = progress_span
        distance = abs(target_mm - start) or 1.0

        def progress(f: Frame) -> float | None:
            return p0 + (p1 - p0) * min(1.0, max(0.0, abs(f.x_mean - start) / distance))
    else:
        def progress(f: Frame) -> float | None:
            return progress_span  # type: ignore[return-value]

    state = state if state is not None else Motion()

    def arrived(f: Frame, _extra: dict[Side, float]) -> bool:
        return direction * (target_mm - f.x_mean) <= balance.brake_distance(direction, state.v)

    def remaining(f: Frame) -> float:
        return direction * (target_mm - f.x_mean) - balance.brake_distance(direction, state.v)

    if abs(target_mm - start) > 1.0:
        frame = yield from _governed(balance, frame, direction, speed_mm_s, arrived, note=label, progress=progress, state=state, remaining=remaining)
    return (yield from hold_still(balance, frame, note=label, progress=progress(frame)))


def land(balance: Balance, frame: Frame, *, speed_mm_s: float | None = None, progress: float | None = None, state: Motion | None = None) -> Gen:
    """Down to the stops: pushing ≥ 0.25·Fc⁻ below the window, low and still for 1 s = resting on the stops."""

    speed_mm_s = speed_mm_s if speed_mm_s is not None else (balance.landing_speed_mm_s or 15.0)
    if frame.x_mean > 60.0:
        frame = yield from travel(balance, frame, 30.0, speed_mm_s=max(speed_mm_s, 20.0), progress_span=progress)
    rested: dict[str, float | None] = {"since": None}

    def done(f: Frame, extra: dict[Side, float]) -> bool:
        pressing = all(extra[side] >= 0.25 * balance.coulomb_down[side] for side in SIDES)
        if pressing and _still(f) and f.x_mean < LANDED_MM:
            rested["since"] = rested["since"] if rested["since"] is not None else f.t
        else:
            rested["since"] = None
        return rested["since"] is not None and f.t - rested["since"] >= 1.0

    frame = yield from _governed(balance, frame, -1, speed_mm_s, done, note="опускание на упоры", progress=lambda _f: progress, state=state)
    forces = {side: balance.weight(side, frame.x(side)) - 0.5 * balance.coulomb_down[side] for side in SIDES}
    return (yield Command(forces, note="гриф на упорах", progress=progress))
