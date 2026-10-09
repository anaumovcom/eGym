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
0.25·Fc up to +2·Fc (stuck on the stops after a long rest, a tight spot); once it moves
the force drops back at once so the released adhesion does not throw the bar.
Speed comes from PA_1C1 cross-checked with the encoder: a single register
glitch (seen on the A6: 90 mm/s on a resting bar) is replaced by Δx/Δt.

Positioning up moves (and B8, M4) also set the drive speed limit PA_056 to the
target speed: the drive's own speed loop catches the stiction release, the force
keeps its margin and tight spots pass without stick-slip. The runner restores
PA_056 after the move.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from app.motor.calibration.runner import Command, Frame, ProcedureError
from app.motor.profile import DEFAULT_MOVING_MASS_KG, MachineProfile, Tunables
from app.motor.units import SIDES, Side

Gen = Generator[Command, Frame, Any]
STILL_MM_S = 1.0
NO_MOTION_TIMEOUT_S = 60.0  # fallback; normally the move gives up 2·ESCALATE_S after the full cap
ESCALATE_MAX_FC = 2.0  # tight spots (A6 bench: up to W + 2.5·Fc at 110–190 mm) need room above the normal cap
FEED_SPEED_MM_S = 20.0  # M2 reference speed
STOPS_MM = 3.0  # below: the side rests on the bottom stops
ESCALATE_S = 3.0  # at the cap and still this long → raise the cap
GLITCH_MM_S = 20.0  # PA_1C1 vs Δx/Δt disagreement treated as a register glitch
DEFAULT_BRAKE_LAG_S = 0.1
LANDED_MM = 20.0
RUNAWAY_MM_S = 70.0  # below the procedure envelope (120 mm/s)
# governed transit (B8 rise, short moves, the fallback of a fast move): as fast as the speed governor safely allows.
# Up is drive-limited (PA_056); down has no drive limit, so it keeps margin below the per-side runaway (80 mm/s)
TRANSIT_UP_MM_S = 60.0
TRANSIT_DOWN_MM_S = 40.0
# fast transit (to a start height, back to the stops; measures nothing): a smooth reference x/v/a is tracked with
# feed-forward (window edge + m·a + viscous) and a slow PI on the tracking error (bus delay ~1–2 frames)
FAST_UP_MM_S = 400.0
FAST_DOWN_MM_S = 300.0
FAST_ACCEL_MM_S2 = 1000.0  # m·a ≈ 60 N at 60 kg; also the bound of the reference's own slowdown
FAST_DECEL_MM_S2 = 800.0  # the end of the move: below the ramp, the bar lags the reference by the bus delay
FAST_SMOOTH_S = 0.3  # the reference speed follows its cap with this time constant: no steps in a_ref
# speed near the end stops: an abort leaves the bar on support, which hardly brakes a descent (≈ viscous only)
# and lets gravity brake a rise — so from any point the bar reaches a stop no faster than FAST_END_MM_S
FAST_END_MM_S = 60.0
FAST_COAST_DOWN_MM_S2 = 250.0
FAST_COAST_UP_MM_S2 = 800.0
FAST_COAST_MASS_KG = 60.0  # the coasting decelerations above at this reflected mass; scaled down for a heavier one
FAST_MIN_MM = 80.0  # shorter moves are governed moves
FAST_START_MM = 3.0  # the governed start breaks the bar free (stops, stiction, M1) before the reference runs
FAST_TOLERANCE_MM = 15.0  # farther from the target after the fast move → a governed correction
FAST_SETTLE_S = 2.0  # after the reference arrived: the PI pulls the bar into the tolerance (stiction at the end)
FAST_KX = 0.8  # N/mm
FAST_KV = 0.4  # N per mm/s (≤ 0.5: m/Kv ≥ 0.12 s against the bus delay)
FAST_MASS_SHARE = 0.75  # m·a feed-forward with an under-estimated mass: a lag is caught by the PI, an overshoot is not
FAST_KI = 1.0  # N/(mm·s)
FAST_LAG_MM = 25.0  # the bar behind the reference by more → the reference waits for it
FAST_LEAD_MM = 25.0  # the bar ahead by more → the reference catches up
# a side faster than the reference by max(margin, share·v), skew or a stall → brake, governed rest
FAST_RUNAWAY_MARGIN_MM_S = 60.0
FAST_RUNAWAY_SHARE = 0.25
FAST_OVER_TOP_MM_S = 40.0  # a side faster than the top speed + this → brake (well before the envelope)
FAST_SKEW_MM = 25.0
FAST_STALL_S = 1.5  # the bar still this long during a fast move → governed rest (escalations)
FAST_ENVELOPE_MARGIN_MM_S = 120.0  # runner speed allowance above the move's top speed
FAST_DRIVE_LIMIT_MM_S = 450.0  # PA_056 during a fast move (≤ SafetyEnvelope.max_speed_mm_s, below the 533 mm/s alarm)
FAST_BRAKE_MM_S2 = 1200.0  # brake of a failed fast move, until FAST_BRAKE_END_MM_S, then the middle of the window
FAST_BRAKE_END_MM_S = 80.0
MIN_PROFILE_SPEED_MM_S = 5.0
SYNC_LIMIT_FC = 0.3  # sync correction ≤ 0.3·Fc per side
# before X3: the runtime default; without it one side stays stuck while the other runs and the bar racks
DEFAULT_SYNC_K_N_PER_MM = Tunables().sync_k_n_per_mm
# drive-limited up moves (PA_056 = target speed): the drive's own speed loop (kHz, its encoder) catches the
# stiction release that a 70 ms bus loop cannot, so the force keeps a margin instead of hunting the edge
DRIVE_LIMIT_AIM = 1.3  # the integrator aims 30 % above the limit: the force stays at the cap, PA_056 holds the speed
DRIVE_LIMIT_RATE = 3.0  # integrator rate × (from a standstill to the cap in < 1 s)
DRIVE_LIMIT_ESCALATE_S = 1.0  # at the cap and still this long → raise the cap (tight spots)
SKEW_SLOW_MM = 4.0  # a side ahead by more than this is limited to SKEW_SLOW_SHARE of the target speed
SKEW_SLOW_SHARE = 0.3


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
    mass_kg: dict[Side, float] = field(default_factory=lambda: {side: DEFAULT_MOVING_MASS_KG for side in SIDES})  # D4, fast moves
    viscous: dict[Side, float] = field(default_factory=lambda: {side: 0.05 for side in SIDES})  # N per mm/s
    travel_mm: float = 1400.0  # B8: the upper end for the speed bound of fast moves
    stribeck_extra: dict[Side, float] = field(default_factory=dict)  # D2: breakaway above the kinetic friction

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
            sync_k=_value(profile.sync_k_n_per_mm) or DEFAULT_SYNC_K_N_PER_MM,
            mass_kg={side: _value(profile.side(side).moving_mass_kg) or DEFAULT_MOVING_MASS_KG for side in SIDES},
            viscous={side: max(0.0, _value(profile.side(side).viscous_n_per_mm_s) or 0.0) for side in SIDES},
            travel_mm=_value(profile.travel_mm) or 1400.0,
            stribeck_extra={side: max(0.0, _value(profile.side(side).stribeck_extra_n) or 0.0) for side in SIDES},
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


def side_speed(frame: Frame, previous: Frame | None, side: Side) -> float:
    """Speed of one side from PA_1C1; a register glitch (disagrees with its encoder by > 20 mm/s) → Δx/Δt."""

    v = frame.v(side)
    if previous is None or frame.t <= previous.t:
        return v
    v_pos = (frame.x(side) - previous.x(side)) / (frame.t - previous.t)
    return v_pos if abs(v - v_pos) > GLITCH_MM_S else v


def _still(frame: Frame) -> bool:
    return all(abs(frame.v(side)) < STILL_MM_S for side in SIDES)


def hold_still(
    balance: Balance,
    frame: Frame,
    *,
    note: str = "остановка",
    progress: float | None = None,
    timeout_s: float = 4.0,
    liftoff: bool = False,
    speed_limit_mm_s: float | None = None,
) -> Gen:
    """Middle of the window until both sides are still for 5 frames.

    ``speed_limit_mm_s`` keeps the PA_056 limit of a drive-limited move: lifted together with the force
    step down, it would let the force held back by the drive throw the bar for the bus delay.
    """

    limits = {side: speed_limit_mm_s for side in SIDES} if speed_limit_mm_s is not None else None
    still = 0
    start = frame.t
    while still < 5:
        if frame.t - start > timeout_s:
            raise ProcedureError("гриф не останавливается серединой окна невесомости: повторите S3")
        frame = yield Command(balance.mid(frame), note=note, progress=progress, liftoff=liftoff, speed_limit_mm_s=limits)
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
    at_full_cap: bool = False  # every escalation spent (+ESCALATE_MAX_FC·Fc) and the extra is at that cap


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
    drive_limit: bool = False,
) -> Gen:
    """Move in ``direction`` at about ``speed_mm_s`` until ``done(frame, extra)``; returns the last frame.

    ``remaining(frame)`` (mm to the stop point) lets the A2 ramp-down slow the move; the A1 ramp-up starts
    at 5 mm/s. ``force_offset(frame)`` adds a test force (a simulated load) to both sides.

    The integrator works in N/s (frame period independent) and starts at the M2 feed force if measured.
    At the cap and still for ``ESCALATE_S`` the cap rises by 0.25·Fc (up to +2·Fc); the first motion
    after that (or after leaving the stops with the M1 lift-off force) drops the extra back to the
    normal cap so the released stiction does not throw the bar.

    ``drive_limit`` (up moves only; PA_056 does not brake a descent under gravity): the drive limits the
    speed to the target, the force stays at the cap with a margin, escalations come every second and are
    given back slowly while moving — no stick-slip on tight spots. Not for moves that measure the force.
    """

    state = state if state is not None else Motion()
    friction = {side: balance.friction(side, direction) for side in SIDES}
    limited = drive_limit and direction > 0
    escalate_s = DRIVE_LIMIT_ESCALATE_S if limited else ESCALATE_S

    def start() -> dict[Side, float]:
        return {side: feed if (feed := balance.feed(side, direction, speed_mm_s)) is not None else -0.15 * friction[side] for side in SIDES}

    extra = start()
    decay = {side: max(4.0, 0.2 * friction[side]) for side in SIDES}  # N/s
    rate = {side: decay[side] * (DRIVE_LIMIT_RATE if limited else 1.0) for side in SIDES}
    # P term on the speed error: answers the friction drop right after breakaway (stick-slip) at once;
    # ≤ 0.5 N per mm/s keeps m/Kp ≥ ~0.12 s against a 1–3 frame bus delay with m ≈ 60 kg
    kp = {side: min(0.5, 0.4 * friction[side] / max(speed_mm_s, 5.0)) for side in SIDES}
    p_cap = {side: 0.5 * friction[side] for side in SIDES}
    # the post-breakaway overshoot (stiction drop) is the P term's job; stop the move only on a real runaway
    # (fast moves of F3 need room above their own speed; their envelope is wider)
    runaway_mm_s = min(max(2.5 * speed_mm_s, speed_mm_s + 30.0), max(RUNAWAY_MM_S, speed_mm_s + 40.0))
    # one side breaking free while the other is stuck (racking): the mean speed hides it, the envelope does not
    side_runaway_mm_s = max(RUNAWAY_MM_S, runaway_mm_s)
    cap0 = {side: max(0.6 * friction[side], 10.0) for side in SIDES}
    cap = dict(cap0)
    cap_max = {side: cap0[side] + ESCALATE_MAX_FC * friction[side] for side in SIDES}
    previous: Frame | None = None
    moving_at, stuck_since, t_prev = frame.t, None, frame.t
    lifting = direction > 0 and any(frame.x(side) < STOPS_MM for side in SIDES)
    standing = True
    t_start = frame.t
    while True:
        v = direction * speed(frame, previous)
        # per side: a side that breaks free while the other is stuck is braked by its own P term at once
        side_v = {side: direction * side_speed(frame, previous, side) for side in SIDES}
        fastest = max(side_v.values())
        state.v, state.extra, state.moving = v, extra, v > STILL_MM_S
        state.at_full_cap = all(cap[side] >= cap_max[side] - 1e-6 and extra[side] >= cap[side] - 0.5 for side in SIDES)
        target_v = balance.target_speed(speed_mm_s, frame.t - t_start, remaining(frame) if remaining else None)
        state.target_v = target_v
        if done(frame, extra):
            break
        dt = min(max(frame.t - t_prev, 0.0), 0.25)
        t_prev, previous = frame.t, frame
        if v > runaway_mm_s or fastest > side_runaway_mm_s:
            frame = yield from hold_still(
                balance, frame, note=f"{note}: торможение", progress=progress(frame), liftoff=lifting or cap != cap0 or _freshly_lifted(state, frame),
                speed_limit_mm_s=target_v if limited else None,
            )
            extra, previous, t_prev = start(), None, frame.t
            continue
        if v > STILL_MM_S:
            moving_at, stuck_since = frame.t, None
            if limited:
                # PA_056 holds the speed: keep the force that broke the bar free, give the escalation back slowly
                if standing and (cap != cap0 or lifting):
                    state.released_at = frame.t
                if lifting and all(frame.x(side) >= STOPS_MM for side in SIDES):
                    lifting = False
                cap = {side: max(cap0[side], cap[side] - decay[side] * dt) for side in SIDES}
            elif cap != cap0 or (lifting and all(frame.x(side) >= STOPS_MM for side in SIDES)):
                # stiction released: back to the normal band at once
                extra = {side: min(extra[side], start()[side] + 0.3 * friction[side]) for side in SIDES}
                cap, lifting = dict(cap0), False
                state.released_at = frame.t
            standing = False
        else:
            standing = True
            at_cap = all(extra[side] >= cap[side] - 1e-6 for side in SIDES)
            stuck_since = (stuck_since or frame.t) if at_cap else None
            # the escalations alone take ~20 s (4 × (ESCALATE_S + ramp)): give up only once the full cap has failed
            full_cap_failed = state.at_full_cap and stuck_since is not None and frame.t - stuck_since > 2 * escalate_s
            if full_cap_failed or frame.t - moving_at > NO_MOTION_TIMEOUT_S:
                raise ProcedureError(
                    "гриф не трогается с места даже с запасом силы +2·трение: выполните M1 (отрыв от упоров), проверьте окно невесомости (S3) и предел момента привода (PA_05E)"
                )
            if stuck_since is not None and frame.t - stuck_since > escalate_s and any(cap[side] < cap_max[side] for side in SIDES):
                cap = {side: min(cap[side] + 0.25 * friction[side], cap_max[side]) for side in SIDES}
                stuck_since, state.escalations = None, state.escalations + 1
        aim = DRIVE_LIMIT_AIM * target_v if limited else target_v
        for side in SIDES:
            # integral of the speed error: ``rate`` N/s at half the target speed missing, twice that when too fast
            error = max(-2.0, min(1.0, (aim - side_v[side]) / (0.5 * target_v)))
            extra[side] = min(extra[side] + rate[side] * error * dt, cap[side])
        forces = {}
        effective = {}
        limits: dict[Side, float] | None = {} if limited else None
        for side in SIDES:
            # 90 % of the M1 lift-off force: the integrator adds the rest gently instead of overshooting it
            lift = 0.9 * balance.liftoff.get(side, 0.0) if direction > 0 and frame.x(side) < STOPS_MM else 0.0
            p_term = max(-p_cap[side], min(p_cap[side], kp[side] * (aim - side_v[side])))
            if lift > 0 or side_v[side] <= STILL_MM_S:
                # standing (on the stops or held by stiction): the speed is 0 by contact, not by too little force —
                # a P kick here only makes the breakaway violent; the integrator finds the force
                p_term = min(p_term, 0.0)
            other: Side = "right" if side == "left" else "left"
            sync = max(-SYNC_LIMIT_FC * friction[side], min(SYNC_LIMIT_FC * friction[side], balance.sync_k * (frame.x(other) - frame.x(side))))
            effective[side] = extra[side] + p_term
            offset = force_offset(frame) if force_offset else 0.0
            forces[side] = balance.edge(side, frame.x(side), direction) + direction * (extra[side] + lift + p_term) + sync + offset
            if limits is not None:
                # racking: the side ahead waits at a crawl for the stuck one instead of running away from it
                ahead = frame.x(side) - frame.x(other) > SKEW_SLOW_MM
                limits[side] = target_v * (SKEW_SLOW_SHARE if ahead else 1.0)
        if state.trace is not None:
            state.trace.append((frame.t, frame.x_mean, v, effective))
        if state.profile_trace is not None:
            state.profile_trace.append((frame.t, target_v, v))
        frame = yield Command(
            forces, note=note, progress=progress(frame), liftoff=lifting or cap != cap0 or _freshly_lifted(state, frame), speed_limit_mm_s=limits,
        )
    return frame


def _freshly_lifted(state: Motion, frame: Frame) -> bool:
    """Within 1.5 s after the bar left the stops (or broke free at an escalated force)."""

    return state.released_at is not None and frame.t - state.released_at < 1.5


def _end_bound(balance: Balance, x_mm: float, direction: int) -> float:
    """Top speed at ``x_mm``: an abort (support) still reaches the end stop ahead at ≤ ``FAST_END_MM_S``."""

    room, coast = (balance.travel_mm - x_mm, FAST_COAST_UP_MM_S2) if direction > 0 else (x_mm, FAST_COAST_DOWN_MM_S2)
    # the coasting decelerations hold for FAST_COAST_MASS_KG: a heavier bar (screw inertia) coasts farther
    coast *= min(1.0, FAST_COAST_MASS_KG / max(min(balance.mass_kg.values()), 1.0))
    return math.sqrt(FAST_END_MM_S**2 + 2 * coast * max(0.0, room))


def _fast(balance: Balance, frame: Frame, target_mm: float, *, note: str, progress: Any) -> Gen:
    """Fast transit to ``target_mm``; returns the frame after a stop in the middle of the window.

    A governed start breaks the bar free (stops, stiction, M1 lift-off), then a smooth reference
    (speed follows min(top speed, end-stop bound, √(2·decel·remaining)) with ``FAST_SMOOTH_S``) is
    tracked: window edge + viscous·v + m·a feed-forward, PI on the tracking error per side, sync.
    The bar falling behind makes the reference wait; the bar ahead, a side faster than the reference,
    skew or a stall end the fast move with a brake — the caller finishes with a governed move.
    """

    direction = 1 if target_mm > frame.x_mean else -1
    top = FAST_UP_MM_S if direction > 0 else FAST_DOWN_MM_S
    allowance = top + FAST_ENVELOPE_MARGIN_MM_S
    # up: the drive clamps an overshoot over the top speed itself (PA_056); down it does not brake gravity
    limits = {side: min(FAST_DRIVE_LIMIT_MM_S, top + 20.0) if direction > 0 else FAST_DRIVE_LIMIT_MM_S for side in SIDES}
    x0 = frame.x_mean

    def started(f: Frame, _extra: dict[Side, float]) -> bool:
        return direction * (f.x_mean - x0) >= FAST_START_MM

    start_speed = TRANSIT_UP_MM_S if direction > 0 else TRANSIT_DOWN_MM_S
    frame = yield from _governed(balance, frame, direction, start_speed, started, note=note, progress=progress, drive_limit=True)
    friction = {side: balance.friction(side, direction) for side in SIDES}
    # moving: kinetic friction (D2 splits off the stiction extra), the breakaway edge would push the bar ahead
    kinetic = {side: friction[side] - balance.stribeck_extra.get(side, 0.0) for side in SIDES}
    fb_max = {side: 1.5 * friction[side] + 40.0 for side in SIDES}
    x_ref, v_ref = frame.x_mean, max(0.0, direction * frame.v_mean)
    x_seen, v_seen = x_ref, v_ref  # the reference one frame back: what the bar can show now (bus delay)
    integral = {side: 0.0 for side in SIDES}
    previous: Frame | None = None
    t_prev = frame.t
    still_since: float | None = None
    arrived_at: float | None = None
    failed = False
    while True:
        dt = min(max(frame.t - t_prev, 0.0), 0.25)
        t_prev = frame.t
        side_v = {side: side_speed(frame, previous, side) for side in SIDES}
        v_bar = direction * speed(frame, previous)
        previous = frame
        lead = max(direction * (frame.x(side) - x_seen) for side in SIDES)
        if lead > FAST_LEAD_MM:
            # the bar ahead of the reference (friction lower than the model): the reference catches up, the
            # remaining distance — and the slowdown to the target — stay real
            shift = direction * (lead - FAST_LEAD_MM)
            x_ref, x_seen = x_ref + shift, x_seen + shift
            v_ref = max(v_ref, min(v_bar, top))
        behind = {side: direction * (x_seen - frame.x(side)) for side in SIDES}  # > 0: the side lags the reference
        fastest = max(direction * side_v[side] for side in SIDES)
        skew = abs(frame.x("left") - frame.x("right"))
        still_since = None if abs(v_bar) > STILL_MM_S else (still_since if still_since is not None else frame.t)
        stalled = arrived_at is None and still_since is not None and frame.t - still_since > FAST_STALL_S
        v_allowed = max(v_ref, v_seen)
        runaway = fastest > min(top + FAST_OVER_TOP_MM_S, v_allowed + max(FAST_RUNAWAY_MARGIN_MM_S, FAST_RUNAWAY_SHARE * v_allowed))
        if runaway or skew > FAST_SKEW_MM or stalled:
            failed = True
            break
        if arrived_at is not None and (
            (abs(target_mm - frame.x_mean) <= FAST_TOLERANCE_MM and abs(v_bar) < 20.0) or frame.t - arrived_at > FAST_SETTLE_S
        ):
            break
        v_cmp = v_seen
        x_seen, v_seen = x_ref, v_ref
        a_ref = 0.0
        if arrived_at is None:
            remaining = direction * (target_mm - x_ref)
            cap = min(top, _end_bound(balance, x_ref, direction), math.sqrt(2 * FAST_DECEL_MM_S2 * max(0.0, remaining - v_ref * FAST_SMOOTH_S)))
            if max(behind.values()) > FAST_LAG_MM:
                cap = min(cap, max(0.0, v_bar))  # wait for the bar (a tight spot): the force does not run away
            a_ref = max(-FAST_ACCEL_MM_S2, min(FAST_ACCEL_MM_S2, (cap - v_ref) / FAST_SMOOTH_S))
            v_next = max(0.0, v_ref + a_ref * dt)
            x_ref += direction * 0.5 * (v_ref + v_next) * dt
            v_ref = v_next
            left = direction * (target_mm - x_ref)
            if left <= 0.0 or (v_ref < 5.0 and left < 5.0):
                x_ref, v_ref, a_ref, arrived_at = target_mm, 0.0, 0.0, frame.t
        forces = {}
        for side in SIDES:
            other: Side = "right" if side == "left" else "left"
            error_x = direction * behind[side]  # up-positive tracking error
            error_v = direction * v_cmp - side_v[side]
            integral[side] = max(-friction[side], min(friction[side], integral[side] + FAST_KI * error_x * dt))
            feedback = max(-fb_max[side], min(fb_max[side], FAST_KX * error_x + FAST_KV * error_v + integral[side]))
            sync = max(-SYNC_LIMIT_FC * friction[side], min(SYNC_LIMIT_FC * friction[side], balance.sync_k * (frame.x(other) - frame.x(side))))
            if v_ref <= STILL_MM_S:
                resist = friction[side]
            else:
                # M2/P1/P2: measured beyond the breakaway edge; else the kinetic friction
                feed = balance.feed(side, direction, max(v_ref, FEED_SPEED_MM_S))
                resist = friction[side] + feed if feed is not None else kinetic[side]
            ahead = resist + balance.viscous[side] * v_ref + FAST_MASS_SHARE * balance.mass_kg[side] * a_ref / 1000.0
            forces[side] = balance.weight(side, frame.x(side)) + direction * ahead + feedback + sync
        frame = yield Command(forces, note=note, progress=progress(frame), speed_limit_mm_s=limits, max_speed_mm_s=allowance)
    if failed:
        t0 = frame.t
        while direction * frame.v_mean > FAST_BRAKE_END_MM_S and frame.t - t0 < 2.0:
            forces = {
                side: balance.weight(side, frame.x(side)) + direction * (friction[side] - balance.mass_kg[side] * FAST_BRAKE_MM_S2 / 1000.0)
                for side in SIDES
            }
            frame = yield Command(forces, note=f"{note}: торможение", progress=progress(frame), speed_limit_mm_s=limits, max_speed_mm_s=allowance)
        note = f"{note}: медленный режим"
    return (yield from hold_still(balance, frame, note=note, progress=progress(frame)))


def travel(
    balance: Balance,
    frame: Frame,
    target_mm: float,
    *,
    speed_mm_s: float | None = None,
    note: str | None = None,
    progress_span: tuple[float, float] | float | None = None,
    state: Motion | None = None,
    drive_limit: bool | None = None,
) -> Gen:
    """Governed move to ``target_mm`` (bar mean), then a stop in the middle of the window.

    The stop is commanded the braking distance (M3) before the target, so the bar stops on it.
    ``drive_limit`` (see ``_governed``) defaults to on for plain positioning moves and off when the
    caller records the move (``state``): those measure the governor's own force and speed.
    Without ``speed_mm_s`` (and ``state``) it is a transit move: a fast move (``_fast``, up to
    ``FAST_UP_MM_S`` / ``FAST_DOWN_MM_S``) if the distance is at least ``FAST_MIN_MM``; a governed move at
    ``TRANSIT_UP_MM_S`` / ``TRANSIT_DOWN_MM_S`` corrects the rest beyond ``FAST_TOLERANCE_MM`` or after a failed fast move.
    """

    drive_limit = state is None if drive_limit is None else drive_limit
    start = frame.x_mean
    fast = speed_mm_s is None and state is None and abs(target_mm - start) >= FAST_MIN_MM
    if isinstance(progress_span, tuple):
        p0, p1 = progress_span
        distance = abs(target_mm - start) or 1.0

        def progress(f: Frame) -> float | None:
            return p0 + (p1 - p0) * min(1.0, max(0.0, abs(f.x_mean - start) / distance))
    else:
        def progress(f: Frame) -> float | None:
            return progress_span  # type: ignore[return-value]

    def label_for(direction: int) -> str:
        return note or f"{'подъём' if direction > 0 else 'опускание'} на {target_mm:.0f} мм"

    if fast:
        frame = yield from _fast(balance, frame, target_mm, note=label_for(1 if target_mm > start else -1), progress=progress)
        if abs(target_mm - frame.x_mean) <= FAST_TOLERANCE_MM:
            return frame
    direction = 1 if target_mm > frame.x_mean else -1
    if speed_mm_s is None:
        speed_mm_s = TRANSIT_UP_MM_S if direction > 0 else TRANSIT_DOWN_MM_S
    label = label_for(direction)
    state = state if state is not None else Motion()

    def arrived(f: Frame, _extra: dict[Side, float]) -> bool:
        return direction * (target_mm - f.x_mean) <= balance.brake_distance(direction, state.v)

    def remaining(f: Frame) -> float:
        return direction * (target_mm - f.x_mean) - balance.brake_distance(direction, state.v)

    if abs(target_mm - frame.x_mean) > 1.0:
        frame = yield from _governed(
            balance, frame, direction, speed_mm_s, arrived, note=label, progress=progress, state=state, remaining=remaining, drive_limit=drive_limit,
        )
    held = state.target_v if drive_limit and direction > 0 and state.target_v > 0 else None
    return (yield from hold_still(balance, frame, note=label, progress=progress(frame), speed_limit_mm_s=held))


def land(balance: Balance, frame: Frame, *, speed_mm_s: float | None = None, progress: float | None = None, state: Motion | None = None) -> Gen:
    """Down to the stops: transit to 30 mm (fast from high up, slowing towards the stops), then ``speed_mm_s``
    (A3 landing speed) until pressing ≥ 0.25·Fc⁻ below the window, low and still for 1 s = resting on the stops."""

    speed_mm_s = speed_mm_s if speed_mm_s is not None else (balance.landing_speed_mm_s or 15.0)
    if frame.x_mean > 60.0:
        frame = yield from travel(balance, frame, 30.0, progress_span=progress)
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
