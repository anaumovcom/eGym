"""Motor core: one tick read → estimate → supervise → force law → safety. Pure, no I/O.

The same core runs against the twin (tests, autotuning) and later inside
``motor-rt`` against the real drives (plan 16, stage 5).

Free-weight feel (all parts off until their calibration is measured):

* friction compensation at the velocity predicted for when the command acts (V3), with the F3 speed
  table, the S10/S8 track map and S6 screw ripple (× F7 gain), the L1/L2 load growth (× L3 gain);
* inertia compensation share by load (F2 table) or from the stable ratio (F1);
* softened friction compensation right after a breakaway from rest (F6);
* deadband inverse (D1 × F8), dither against static friction (F9), speed cushions at the ends (F10);
* release detection in training (F11): the user let go → hold.

A load heavier than the bar makes the motor pull down (F < 0): the friction growth swaps its quadrant,
the pull is sent through the N1 scale, and ``set_load`` caps the load at what the drives can pull
(``load_limit_n``); a fast fall with such a load is caught by the load relief and the cushions.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Literal

from app.motor.drive.protocol import DriveSample
from app.motor.estimation.friction import FrictionModel, interpolate
from app.motor.estimation.observer import AlphaBetaObserver, ObservedState
from app.motor.estimation.user_force import UserForceEstimate, estimate_user_force
from app.motor.force import compensation
from app.motor.force.load_models import LoadSetpoint, PhaseTracker, load_force
from app.motor.force.shaping import governor, rate_limit, side_sync, virtual_spring
from app.motor.profile import MachineProfile, Measured, SafetyEnvelope, Tunables, calibrated_tunables
from app.motor.supervisor.modes import Mode, Supervisor
from app.motor.supervisor.safety import CommMonitor, SafetyInput, apply_envelope
from app.motor.units import SIDES, Side, rpm_to_mm_s, smooth_sign

ON_STOPS_MM = 5.0
HOLD_CATCH_SPEED_MM_S = 5.0
LOAD_RELIEF_DROP_S = 0.15  # full load → 0 when the bar runs away downwards
LOAD_RELIEF_RECOVER_S = 0.5
STILL_MM_S = 1.0
BREAKAWAY_REST_S = 0.5  # F6 softening applies after at least this long at rest
DITHER_SPEED_MM_S = 2.0  # F9 dither only while (almost) still
DEADBAND_BLEND_N = 3.0  # F8: the deadband inverse switches sign smoothly around 0
CUSHION_GAIN_N_PER_MM_S = 0.6  # F10: like the governor, low enough for 1–3 frames of bus delay
CUSHION_DECEL_MM_S2 = 800.0  # without M3: a typical braking deceleration by the window middle
CUSHION_DECEL_SHARE = 0.35  # the cushion asks for a third of it: room for the delay and the load
CUSHION_BLEND_MM_S = 10.0
CUSHION_MARGIN_MM = 10.0  # the landing speed is reached this far before the soft limit
DEFAULT_LANDING_MM_S = 15.0
# fixed / isometric: the user's force is read from the bar's momentum (m·Δv against the modelled drive force, weight and
# friction over each fresh frame), not integrated slowly from the position error: the bias follows a hanging user
# within ~FIXED_OBSERVER_S instead of seconds. On a still bar the same balance integrates the spring at k/FIXED_OBSERVER_S.
# 0.17 s: twin-validated incl. 2× bus delay and ±30 % mass; 0.13 s already rings (limit cycle) at 2× delay + 80 kg,
# slower ones sag more and hunt (stick-slip) longer.
FIXED_OBSERVER_S = 0.17
FIXED_STILL_MM_S = 1.0
FIXED_STILL_DEADBAND_MM = 6.0  # stick-slip jumps were ~13 mm p-p (2× bus delay twin)
FIXED_COMMAND_HISTORY = 16
FIXED_DAMPING_RATIO = 0.7
# Keep c·delay/m below this share (the damping acts a loop delay late).
FIXED_DAMPING_DELAY_SHARE = 0.5
LOAD_RESERVE_SHARE = 0.1  # of the strongest pull: inertia, cushions and the sync act on top of the load
# a load below the screw's static friction never moves a released bar: after a rest the law breaks it away downwards
FALL_STATIC_MARGIN = 1.15  # × static friction down, at rest
# a stop at the top of a rep is short: the push starts soon after it, or the user has to drag the bar down
FALL_REST_S = 0.2
FALL_RAMP_N_PER_S = 120.0
FALL_DROP_N_PER_S = 400.0  # the user lifts: the assist goes at once
# extra descent friction compensation (train_friction_gain_down) fades out above a rep's speed, down to the base gain
# at the load-relief onset: a released bar keeps the screw friction as a brake
DESCENT_GAIN_FADE_START = 0.4  # × max_descent_mm_s
# range guard of a set, judged on the bar as a whole (the mean of the sides: per-side decisions near a point give one
# side its load and not the other, a racking force). Below the lower point the load ramps out, a damper (delay-limited)
# slows the fall and a soft spring returns the bar up to the point. Its force is small: whatever the law pushes acts a
# loop delay (~0.12 s on the bench) after the bar has stopped, and 200 N there threw the bar back into the range,
# where the load came back and dropped it again (the bar bounced on the point)…
FLOOR_K_N_PER_MM = 3.0
FLOOR_MAX_N = 120.0
FLOOR_RETURN_MM_S = 60.0  # …and fades out above this return speed
# above the upper point a brake stops the bar's momentum within RANGE_STOP_MM
RANGE_STOP_MM = 25.0
RANGE_STOP_MIN_MM = 5.0
RANGE_BRAKE_MAX_N = 250.0
CEILING_K_N_PER_MM = 1.0  # a light spring turns the bar back down from above the upper point
CEILING_MAX_N = 60.0
RANGE_DAMPING_N_PER_MM_S = 0.6  # at most; c·delay/m below FIXED_DAMPING_DELAY_SHARE (the damper acts a loop delay late)
# side sync in free motion (weightless, training). Under the user's hands the real bar barely couples the sides (skews
# of 130 mm with no sign of the bench's 4.5 N/mm), so the skew is a free mass on ~0.12 s of bus + torque delay:
# * a stiff spring (3 N/mm) arrives late and pumps it; an integral on a free mass is worse still (its force follows
#   the skew rate: the sides were thrown up and down against each other at the ±60 N limit);
# * a damper is safe up to c·delay/m = FIXED_DAMPING_DELAY_SHARE, and a weak spring with its corner a third of the
#   damper's crossover (k = c²/(3·m)) only pulls a lasting skew back, slowly.
# Holds keep the tunable spring (their own springs damp the bar).
SYNC_SPRING_CORNER = 3.0


def _value(item: Measured, default: float | None = None) -> float | None:
    return float(item.value) if item.value is not None else default


@dataclass(frozen=True)
class CoreOutput:
    kind: Literal["support", "zero", "force"]
    forces_n: dict[Side, float]
    mode: Mode
    states: dict[Side, ObservedState]
    user_force: dict[Side, UserForceEstimate] = field(default_factory=dict)
    phase: str = "still"


class MotorCore:
    def __init__(self, profile: MachineProfile, tunables: Tunables | None = None, envelope: SafetyEnvelope | None = None) -> None:
        self.profile = profile
        self.tunables = calibrated_tunables(profile, tunables or Tunables())
        self.envelope = envelope or SafetyEnvelope()
        self.supervisor = Supervisor()
        self.observers = {side: AlphaBetaObserver.from_profile(profile) for side in SIDES}
        self.comm = {side: CommMonitor(self.envelope.comm_freeze_frames, self.envelope.comm_fault_frames) for side in SIDES}
        self.friction = {side: FrictionModel.from_profile(profile.side(side), profile) for side in SIDES}
        self.previous: dict[Side, float] = {side: self._support_force(side) for side in SIDES}
        self.hold_target: dict[Side, float | None] = {side: None for side in SIDES}
        self._hold_caught: dict[Side, bool] = {side: False for side in SIDES}
        self.fixed_integral: dict[Side, float] = {side: 0.0 for side in SIDES}
        self._fixed_sample_t: dict[Side, float | None] = {side: None for side in SIDES}
        self._fixed_fresh: dict[Side, bool] = {side: False for side in SIDES}
        # observer state: the last fresh frame (t, v) and the drive force modelled at that time
        self._fixed_last: dict[Side, tuple[float, float] | None] = {side: None for side in SIDES}
        self._fixed_applied: dict[Side, float] = {side: 0.0 for side in SIDES}
        self._commands: dict[Side, deque[tuple[float, float]]] = {side: deque(maxlen=FIXED_COMMAND_HISTORY) for side in SIDES}
        self.load = LoadSetpoint()
        self.load_capped = False
        self.virtual_mass_kg = 0.0
        self.phase = PhaseTracker(self.tunables.phase_hysteresis_mm_s, self.tunables.phase_blend_s)
        self.calibration_force: dict[Side, float] | None = None
        self.load_relief: dict[Side, float] = {side: 1.0 for side in SIDES}
        self.fall_assist: dict[Side, float] = {side: 0.0 for side in SIDES}
        self.floor_cut = 0.0  # share of the load ramped out below the set's range
        self.range_force_n = 0.0  # the range guard's force, the same on both sides
        self._bar_x_mm = 0.0
        self._bar_v_mm_s = 0.0
        self.sync_left_n = 0.0  # the sync force of the left side, the right one gets the opposite
        self._bar_a_mm_s2 = 0.0
        self._dt = 0.0
        self._t: float | None = None
        # free-weight feel
        self.horizon_s = _value(profile.predict_horizon_s, 0.0) or 0.0  # V3
        self.inertia_override: float | None = None  # calibrations try a share directly
        self.release_enabled = True
        self._still_s: dict[Side, float] = {side: 0.0 for side in SIDES}
        self._moving_s: dict[Side, float] = {side: 0.0 for side in SIDES}
        self._rested_s: dict[Side, float] = {side: 0.0 for side in SIDES}  # rest before the current motion
        self._dither_sign = 1.0
        self._released_s = 0.0

    # ------------------------------------------------------------ commands
    def command(self, event: str, reason: str | None = None) -> Mode:
        holds = {Mode.HOLD, Mode.FIXED, Mode.ISOMETRIC}
        before = self.supervisor.mode
        mode = self.supervisor.handle(event, reason)
        if mode in holds and before not in holds:
            # hold-catch from the current position; HOLD ↔ FIXED / ISOMETRIC keeps the caught point (a push right
            # after the switch must meet the spring, not drag the target along)
            self.hold_target = {side: None for side in SIDES}
            self._hold_caught = {side: False for side in SIDES}
        if mode != before and (mode in holds or before in {Mode.FIXED, Mode.ISOMETRIC}):
            self.fixed_integral = {side: 0.0 for side in SIDES}
            self._fixed_last = {side: None for side in SIDES}
        if mode != before:
            self.fall_assist = {side: 0.0 for side in SIDES}
            self.floor_cut = 0.0
        if event == "reset":
            for monitor in self.comm.values():
                monitor.reset()
        return mode

    def hold_at(self, positions: dict[Side, float]) -> None:
        """Hold exactly here (a scripted move has just stopped the bar): no hold-catch that a quick push could drag."""

        self.hold_target = {side: positions[side] for side in SIDES}
        self._hold_caught = {side: True for side in SIDES}

    def load_limit_n(self, load_direction: Literal["down", "up"] = "down") -> float:
        """Heaviest load per side the drives can make: bar weight + the strongest pull down, less the friction reserve.

        Above the bar weight the motor pulls the bar down; the pull is limited by the envelope and by PA_05E
        (times the N1 pull scale). Lowering adds the friction compensation to the pull, so it is kept in reserve.
        Upward loads reserve the calibrated positive compensation over the soft travel / upward speed domain,
        with full training gain and feedback at the push cap; the safety envelope remains the final filter.
        """

        limits = []
        for side in SIDES:
            profile = self.profile.side(side)
            weights = [float(w) for _x, w in profile.gravity_map.value]
            if load_direction == "up":
                from app.motor.estimation.friction import SPOT_HALF_WIDTH_MM
                from app.motor.units import SCREW_LEAD_MM

                push = min(self.envelope.max_force_n_per_side, self.envelope.max_raw * profile.n_per_raw_value)
                model = self.friction[side]
                low, high = self.envelope.soft_min_mm, self.envelope.soft_max_mm
                positions = {low, high}
                positions.update(x for x, _ in profile.gravity_map.value if low <= x <= high)
                positions.update(x for x, _ in model.track if low <= x <= high)
                # Without S10, overlapping S8 windows change at their edges, not just at their centres.
                if not model.track:
                    for centre, _ in model.spots:
                        for edge in (centre - SPOT_HALF_WIDTH_MM, centre + SPOT_HALF_WIDTH_MM):
                            positions.update(x for x in (math.nextafter(edge, -math.inf), edge, math.nextafter(edge, math.inf)) if low <= x <= high)
                # Ripple is weight-like in _law, and also changes the feedback axial excess.
                if model.track_gain and model.ripple_n:
                    first = math.ceil((2 * math.pi * low / SCREW_LEAD_MM + model.ripple_phase_rad - math.pi / 2) / math.pi)
                    last = math.floor((2 * math.pi * high / SCREW_LEAD_MM + model.ripple_phase_rad - math.pi / 2) / math.pi)
                    positions.update((math.pi / 2 + k * math.pi - model.ripple_phase_rad) * SCREW_LEAD_MM / (2 * math.pi) for k in range(first, last + 1))
                ripple_low = min(model.ripple(x) for x in positions)
                ripple_high = max(model.ripple(x) for x in positions)
                weight_low = min(profile.weight_n(x) for x in positions) + ripple_low
                weight_high = max(profile.weight_n(x) for x in positions) + ripple_high
                # previous is feedback, not the requested nominal load: it can already be at the push cap.
                axial = max(0.0, push - weight_low)
                max_speed = max(0.0, self.envelope.max_speed_mm_s)
                speeds = {0.0, max_speed}
                if max_speed > 0:
                    speeds.add(math.nextafter(0.0, math.inf))  # one-sided static/Stribeck limit
                speeds.update(v for v, _ in model.table_up if 0 <= v <= max_speed)
                if model.table_up and 0 < model.table_up[0][0] <= max_speed:
                    speeds.add(math.nextafter(model.table_up[0][0], 0.0))
                # Below the first F3 knot (or without F3), linear + Stribeck can have an interior maximum.
                end = min(max_speed, model.table_up[0][0]) if model.table_up else max_speed
                slope = ((model.table_up[0][1] - model.coulomb_up_n) / max(model.table_up[0][0], 1e-6)
                         if model.table_up else model.viscous_n_per_mm_s)
                width = max(model.stribeck_v_mm_s, 1e-6)
                upper = min(end, width / math.sqrt(2))
                extra = model.stribeck_extra_n
                if slope > 0 and extra > 0 and slope < 2 * extra * upper / width**2 * math.exp(-(upper / width)**2):
                    lower = 0.0
                    for _ in range(48):
                        middle = (lower + upper) / 2
                        if slope > 2 * extra * middle / width**2 * math.exp(-(middle / width)**2):
                            lower = middle
                        else:
                            upper = middle
                    speeds.add((lower + upper) / 2)
                # Zero blend bounds the positive smoothed force; breakaway/relief only reduce it.
                # Both L1/L2 quadrants matter when previous changes sign; negative coefficients peak at zero excess.
                friction = max(0.0, *(model.force(v, x_mm=x, axial_excess_n=excess, motor_sign=sign)
                                     for v in speeds for x in positions for excess in (0.0, axial) for sign in (1, -1)))
                gain = max(0.0, self.tunables.friction_gain_up, self.tunables.train_friction_gain_down)
                reserve = gain * friction + LOAD_RESERVE_SHARE * push
                limits.append(push - weight_high - reserve)
                continue
            pull = min(self.envelope.max_force_n_per_side, self.envelope.max_raw * profile.n_per_raw_value * profile.pull_scale_value)
            reserve = float(profile.coulomb_down_n.value) + LOAD_RESERVE_SHARE * pull
            limits.append(min(weights) + pull - reserve)
        return max(0.0, min(limits))

    def set_load(self, setpoint: LoadSetpoint) -> None:
        if setpoint.load_direction not in ("down", "up"):
            raise ValueError("Invalid load direction")
        # Legacy calibration uses signed down-loads to model a hung reference mass (D5).
        if not math.isfinite(setpoint.load_n) or (setpoint.load_direction == "up" and setpoint.load_n < 0):
            raise ValueError("Load must be finite; upward load must be nonnegative")
        limit = self.load_limit_n(setpoint.load_direction)
        if setpoint.load_direction == "up":
            # Reserve headroom for the strongest phase / curve point, not just the nominal load.
            factors = {"assist_up": (setpoint.alpha,), "eccentric": (setpoint.beta,), "curve": (setpoint.curve_start, setpoint.curve_end)}.get(setpoint.mode, ())
            if any(not math.isfinite(value) or value < 0 for value in factors):
                raise ValueError("Load multipliers must be finite and nonnegative")
            peak = max(1.0, *factors) if factors else 1.0
            limit /= peak
        self.load_capped = setpoint.load_n > limit
        if self.load_capped:  # a set the drives cannot make: the user gets the heaviest honest load, not a saturated one
            setpoint = replace(setpoint, load_n=limit)
        self.load = setpoint
        self.virtual_mass_kg = setpoint.load_n / 9.80665

    def hold_gains(self) -> tuple[float, float]:
        measured_k, measured_c = self.profile.hold_k_n_per_mm.value, self.profile.hold_c_n_per_mm_s.value
        if measured_k is not None and measured_c is not None:  # H1: tuned on this machine under load
            return float(measured_k), float(measured_c)
        k_u = self.profile.hold_ultimate_k_n_per_mm.value
        period = self.profile.hold_ultimate_period_s.value
        if k_u is None or period is None:
            return self.tunables.hold_k_default_n_per_mm, self.tunables.hold_c_default_n_per_mm_s
        k = self.tunables.hold_k_fraction * float(k_u)
        # Tyreus–Luyben-like damping from the ultimate period
        c = self.tunables.hold_c_fraction * float(k_u) * float(period) / 6.3
        return k, c

    def _fixed_damping(self, side: Side, k: float, c: float) -> float:
        """Original PI damping; changing its delay bound needs separate plant validation."""

        mass = float(self.profile.side(side).moving_mass_kg.value)
        wanted = FIXED_DAMPING_RATIO * 2.0 * math.sqrt(max(k, 0.0) * mass / 1000.0)
        delay = _value(self.profile.loop_delay_s, 0.0) or 0.0
        if delay > 0:
            wanted = min(wanted, FIXED_DAMPING_DELAY_SHARE * mass / (1000.0 * delay))
        return max(c, wanted)

    def _update_sync(self, output: str, states: dict[Side, ObservedState]) -> None:
        """Once per tick: the sync force of the left side (the right one gets the opposite)."""

        t = self.tunables
        if output not in {"weightless", "idle", "train"}:
            self.sync_left_n = side_sync(states["left"].x_mm, states["right"].x_mm, t.sync_k_n_per_mm, t.sync_max_n)
            return
        skew = states["left"].x_mm - states["right"].x_mm
        skew_rate = states["left"].v_mm_s - states["right"].v_mm_s
        mass = min(float(self.profile.side(side).moving_mass_kg.value) for side in SIDES) / 1000.0  # N·s²/mm
        c = FIXED_DAMPING_DELAY_SHARE * mass / self._loop_delay()
        k = min(t.sync_k_n_per_mm, c * c / (SYNC_SPRING_CORNER * mass))
        self.sync_left_n = max(-t.sync_max_n, min(t.sync_max_n, -(k * skew + c * skew_rate) / 2))

    def _support_force(self, side: Side) -> float:
        profile = self.profile.side(side)
        return float(profile.support_raw.value) * profile.n_per_raw_value

    def inertia_share(self, side: Side) -> float:
        """Share of (m − M) cancelled: F2 table by load, else the F1 stable ratio, else the tunable."""

        if self.inertia_override is not None:
            return self.inertia_override
        machine = float(self.profile.side(side).moving_mass_kg.value)
        excess = machine - self.virtual_mass_kg
        if excess <= 0:
            return 1.0
        table = self.profile.inertia_table.value
        if table:
            # above 1 when the model mass is low (F2 measured the true one)
            return max(0.0, min(1.5, interpolate(sorted((float(a), float(b)) for a, b in table), self.load.load_n)))
        ratio = _value(self.profile.inertia_ratio_max)
        if ratio is not None:
            # stability limits the compensated mass relative to the machine mass, not the share
            return max(0.0, min(1.0, ratio * machine / excess))
        return self.tunables.inertia_gain

    def _breakaway_scale(self, side: Side) -> float:
        """F6: friction compensation ramps in over ``breakaway_soft_s`` after a start from rest."""

        soft = _value(self.profile.breakaway_soft_s, 0.0) or 0.0
        if soft <= 0 or self._rested_s[side] < BREAKAWAY_REST_S:
            return 1.0
        return min(1.0, self._moving_s[side] / soft)

    def _track_motion(self, states: dict[Side, ObservedState], dt: float) -> None:
        for side in SIDES:
            if abs(states[side].v_mm_s) < STILL_MM_S:
                self._still_s[side] += dt
                self._moving_s[side] = 0.0
            else:
                if self._moving_s[side] == 0.0:
                    self._rested_s[side], self._still_s[side] = self._still_s[side], 0.0
                self._moving_s[side] += dt

    def _released(self, user_force: dict[Side, UserForceEstimate], dt: float) -> None:
        """F11: the user pushes less than ``release_force_n`` for ``release_timeout_s`` in training → hold."""

        if not self.release_enabled or self.supervisor.mode != Mode.TRAINING:
            self._released_s = 0.0
            return
        if self.load.load_direction == "up":
            values = [-item.value_n if item.confidence == "moving" else -item.low_n for item in user_force.values()]
        else:
            values = [item.value_n if item.confidence == "moving" else item.high_n for item in user_force.values()]
        if sum(values) / len(values) < self.tunables.release_force_n:
            self._released_s += dt
        else:
            self._released_s = 0.0
        if self._released_s >= self.tunables.release_timeout_s:
            self._released_s = 0.0
            self.command("release", "Гриф отпущен")

    def _cushion(self, side: Side, state: ObservedState) -> float:
        """F10: within ``cushion`` mm of a soft limit the speed must stay under √(v_land² + 2·a·d).

        Above that curve the law brakes with the force that follows it (mass·a, plus the load at the bottom)
        and a damper on the excess; a = 35 % of the M3 braking deceleration, d is taken one bus delay ahead.
        Slow motion is never touched.
        """

        force = 0.0
        landing = _value(self.profile.landing_speed_mm_s, DEFAULT_LANDING_MM_S) or DEFAULT_LANDING_MM_S
        mass = float(self.profile.side(side).moving_mass_kg.value)
        # the brake acts after the bus delay: judge the curve where the bar will be by then
        lag = (_value(self.profile.loop_delay_s, 0.04) or 0.04) + (_value(self.profile.torque_lag_s, 0.0) or 0.0)
        ahead = abs(state.v_mm_s) * lag
        bottom = _value(self.profile.cushion_bottom_mm)
        if bottom and state.v_mm_s < 0:
            distance = state.x_mm - self.envelope.soft_min_mm
            if distance < bottom:
                decel = CUSHION_DECEL_SHARE * (_value(self.profile.brake_decel_down_mm_s2, CUSHION_DECEL_MM_S2) or CUSHION_DECEL_MM_S2)
                excess = -state.v_mm_s - (landing * landing + 2 * decel * max(distance - ahead - CUSHION_MARGIN_MM, 0.0)) ** 0.5
                if excess > 0:
                    load = self.load.load_n * self.load_relief[side] if self.load.load_direction == "down" else 0.0
                    brake = mass * decel / 1000 + max(load, 0.0)
                    force += brake * min(1.0, excess / CUSHION_BLEND_MM_S) + CUSHION_GAIN_N_PER_MM_S * excess
        top = _value(self.profile.cushion_top_mm)
        if top and state.v_mm_s > 0:
            distance = self.envelope.soft_max_mm - state.x_mm
            if distance < top:
                decel = CUSHION_DECEL_SHARE * (_value(self.profile.brake_decel_up_mm_s2, CUSHION_DECEL_MM_S2) or CUSHION_DECEL_MM_S2)
                excess = state.v_mm_s - (landing * landing + 2 * decel * max(distance - ahead - CUSHION_MARGIN_MM, 0.0)) ** 0.5
                if excess > 0:
                    load = 0.0
                    if self.load.load_direction == "up" and self.supervisor.output == "train":
                        load = load_force(self.load, state.x_mm, self.phase.blend * self.phase.blend * (3 - 2 * self.phase.blend)) * self.load_relief[side] * (1.0 - self.floor_cut)
                    force -= (mass * decel / 1000 + load) * min(1.0, excess / CUSHION_BLEND_MM_S) + CUSHION_GAIN_N_PER_MM_S * excess
        return force

    def _shape(self, output: str, side: Side, state: ObservedState, force: float) -> float:
        """Cushions and dither (free motion only), then the deadband inverse."""

        if output in {"weightless", "idle", "train"}:
            force += self._cushion(side, state)
            dither = _value(self.profile.dither_n, 0.0) or 0.0
            if dither and abs(state.v_mm_s) < DITHER_SPEED_MM_S:
                force += dither * self._dither_sign
        gain = _value(self.profile.deadband_comp_gain, 0.0) or 0.0
        deadband = _value(self.profile.side(side).deadband_raw, 0.0) or 0.0
        if gain and deadband:
            force += gain * deadband * self.profile.side(side).n_per_raw_value * smooth_sign(force, DEADBAND_BLEND_N)
        return force

    # ---------------------------------------------------------------- tick
    def step(self, samples: dict[Side, DriveSample], now: float, write_ok: bool = True) -> CoreOutput:
        dt = 0.0 if self._t is None else max(now - self._t, 1e-4)
        self._t = now
        self._dt = dt
        states: dict[Side, ObservedState] = {}
        comm_states = {}
        fixed_fresh: dict[Side, bool] = {}
        for side in SIDES:
            sample = samples.get(side)
            ok = sample is not None and sample.ok and now - sample.t <= self.envelope.stale_frame_limit_s
            last_t = self._fixed_sample_t[side]
            fixed_fresh[side] = bool(ok and sample is not None and (last_t is None or sample.t > last_t))
            if fixed_fresh[side] and sample is not None:
                self._fixed_sample_t[side] = sample.t
            comm_states[side] = self.comm[side].update(ok, write_ok)
            if ok and sample is not None:
                states[side] = self.observers[side].update(sample.position_mm, sample.speed_mm_s, sample.t)
            else:
                states[side] = self.observers[side].miss(now)
            if sample is not None and sample.alarm and self.supervisor.mode not in {Mode.FAULT, Mode.ESTOP}:
                self.command("fault", f"Авария привода {side}: {sample.error}")
        self._fixed_fresh = fixed_fresh
        if any(state == "fault" for state in comm_states.values()) and self.supervisor.mode not in {Mode.FAULT, Mode.ESTOP}:
            self.command("fault", "Потеря связи с приводом")
        overspeed = rpm_to_mm_s(self.envelope.overspeed_rpm_alarm)
        if not self.supervisor.overspeed_latched and any(abs(states[side].v_mm_s) >= overspeed for side in SIDES):
            self.command("overspeed", "Превышение скорости")

        v_mean = (states["left"].v_mm_s + states["right"].v_mm_s) / 2
        phase, blend = self.phase.update(v_mean, dt)
        self._track_motion(states, dt)
        self._dither_sign = -self._dither_sign
        user_force = {
            side: estimate_user_force(
                motor_force_n=self.previous[side],
                weight_n=self.profile.side(side).weight_n(states[side].x_mm),
                v_mm_s=states[side].v_mm_s,
                a_mm_s2=states[side].a_mm_s2,
                mass_kg=float(self.profile.side(side).moving_mass_kg.value),
                friction=self.friction[side],
            )
            for side in SIDES
        }
        self._released(user_force, dt)

        output = self.supervisor.output
        if output == "zero":
            self.previous = {side: 0.0 for side in SIDES}
            self._record_commands(now)
            return CoreOutput("zero", dict(self.previous), self.supervisor.mode, states, user_force, phase)
        if output == "support" or (output == "idle" and all(states[side].x_mm < ON_STOPS_MM for side in SIDES)):
            self.previous = {side: self._support_force(side) for side in SIDES}
            self._record_commands(now)
            return CoreOutput("support", dict(self.previous), self.supervisor.mode, states, user_force, phase)

        forces: dict[Side, float] = {}
        self._update_sync(output, states)
        if output == "train":
            self._update_range(states)
        for side in SIDES:
            other: Side = "right" if side == "left" else "left"
            state = states[side]
            bias_before = self.fixed_integral[side]
            target = self._law(output, side, state, states[other], blend)
            # The bias candidate must be judged against the FULL shaped output and the
            # same envelope used below, including raw torque (asymmetric pull scale):
            # the bias may only grow as far as the drive output can follow it.
            if output == "hold" and self.supervisor.mode != Mode.HOLD:
                shaped = self._shape(output, side, state, target)
                limited = apply_envelope(self.envelope, SafetyInput(
                    shaped, self.previous[side], state.x_mm,
                    self.profile.side(side).weight_n(state.x_mm), max(dt, 1e-3),
                    stale=comm_states[side] != "ok",
                ))
                profile = self.profile.side(side)
                push = self.envelope.max_raw * profile.n_per_raw_value
                limited = max(-push * profile.pull_scale_value, min(push, limited))
                delta = self.fixed_integral[side] - bias_before
                excess = shaped - limited
                if not fixed_fresh[side] or (delta * excess > 1e-9 and abs(excess) >= abs(delta)):
                    self.fixed_integral[side] = bias_before
                    target -= delta
                elif delta * excess > 1e-9:
                    cut = math.copysign(min(abs(delta), abs(excess)), delta)
                    self.fixed_integral[side] -= cut
                    target -= cut
            if output != "calibrate":
                target = self._shape(output, side, state, target)
            if comm_states[side] == "freeze":
                target = rate_limit(self.previous[side], self._support_force(side), self.envelope.max_rate_n_per_s / 4, dt)
            forces[side] = apply_envelope(self.envelope, SafetyInput(
                target_n=target,
                previous_n=self.previous[side],
                x_mm=state.x_mm,
                weight_n=self.profile.side(side).weight_n(state.x_mm),
                dt=max(dt, 1e-3),
                stale=comm_states[side] != "ok",
            ))
        self.previous = forces
        self._record_commands(now)
        return CoreOutput("force", dict(forces), self.supervisor.mode, states, user_force, phase)

    def _law(self, output: str, side: Side, state: ObservedState, other: ObservedState, blend: float) -> float:
        profile = self.profile.side(side)
        t = self.tunables
        model = self.friction[side]
        weight = compensation.gravity(profile, state.x_mm) + model.ripple(state.x_mm)
        # the command acts after the bus delay: friction sign and size for the velocity then (V3)
        v_ahead = state.v_mm_s + state.a_mm_s2 * self.horizon_s
        # screw load beyond the bar weight: friction grows with it (L1/L2); below the weight the preload keeps it.
        # A load heavier than the bar makes the motor pull down: |F| − W again, with the power flow swapped
        axial = max(0.0, abs(self.previous[side]) - weight)
        motor_sign = 1 if self.previous[side] >= 0 else -1
        load, gain_down = 0.0, None
        if output == "train":
            load = load_force(self.load, state.x_mm, blend) * self.load_relief[side] * (1.0 - self.floor_cut)
            gain_down = self._descent_gain(side, load)
        friction_t = t
        if output == "train" and self.load.load_direction == "up":
            friction_t = replace(t, friction_gain_up=self._descent_gain(side, load))
            gain_down = None
        friction = compensation.friction(
            model, v_ahead, friction_t, x_mm=state.x_mm, axial_excess_n=axial, motor_sign=motor_sign, gain_down=gain_down,
        ) * self._breakaway_scale(side)
        sync = self.sync_left_n if side == "left" else -self.sync_left_n
        speed_guard = governor(state.v_mm_s, self.envelope.max_speed_mm_s, self.envelope.max_descent_mm_s)
        if output == "calibrate":
            return (self.calibration_force or {}).get(side, weight)
        if output in {"weightless", "idle"}:
            return weight + friction - t.weightless_damping_n_per_mm_s * state.v_mm_s + sync + speed_guard
        if output == "hold":
            # hold-catch: the target follows the bar until it stops, then stays fixed
            target = self.hold_target[side]
            if target is None or not self._hold_caught[side]:
                target = state.x_mm
                self._hold_caught[side] = abs(state.v_mm_s) < HOLD_CATCH_SPEED_MM_S
            self.hold_target[side] = target
            k, c = self.hold_gains()
            if self.supervisor.mode != Mode.HOLD:
                c = self._fixed_damping(side, k, c)
            limit = float(profile.coulomb_up_n.value) * 2 + 50 if self.supervisor.mode == Mode.HOLD else self.envelope.max_force_n_per_side
            spring = virtual_spring(state.x_mm, state.v_mm_s, target, k, c, limit_n=limit)
            if self.supervisor.mode != Mode.HOLD:
                self._observe_fixed(side, state, target, limit)
                spring += self.fixed_integral[side]
            return weight + friction + spring + sync + speed_guard
        # train
        # on the bar's acceleration, not the side's: cancelled mass on a skew (delayed, per side) makes it lighter and
        # livelier, the sides race each other
        inertia = compensation.inertia(float(profile.moving_mass_kg.value), self.virtual_mass_kg, self._bar_a_mm_s2, self.inertia_share(side))
        fall = self._fall_assist(side, state, load)
        if self.load.load_direction == "up":
            return weight + friction + inertia + load + fall + self.range_force_n + sync + speed_guard
        return weight + friction + inertia - load - fall + self.range_force_n + sync + speed_guard

    def _loop_delay(self) -> float:
        return (_value(self.profile.loop_delay_s, 0.04) or 0.04) + (_value(self.profile.torque_lag_s, 0.0) or 0.0)

    def _record_commands(self, now: float) -> None:
        for side in SIDES:
            self._commands[side].append((now, self.previous[side]))

    def _command_at(self, side: Side, t: float) -> float:
        """The force command in effect at ``t`` (the last one written by then)."""

        history = self._commands[side]
        for written, force in reversed(history):
            if written <= t:
                return force
        return history[0][1] if history else self.previous[side]

    def _observe_fixed(self, side: Side, state: ObservedState, target: float, limit: float) -> None:
        """Fixed / isometric bias = the user's force, read from the bar's momentum over the last fresh frame.

        m·Δv = ∫(F_drive + F_user − W − F_friction)dt, with F_drive modelled from the written commands (bus delay,
        then the torque lag). A still bar has no friction model: the stiction joins the estimate, so the balance
        integrates the spring there instead. The bias follows the estimate with ``FIXED_OBSERVER_S``.
        """

        if not self._fixed_fresh[side]:
            return
        t1 = self._fixed_sample_t[side]
        assert t1 is not None
        delay = _value(self.profile.loop_delay_s, 0.04) or 0.04
        lag = _value(self.profile.torque_lag_s, 0.0) or 0.0
        last = self._fixed_last[side]
        self._fixed_last[side] = (t1, state.v_mm_s)
        if last is None:
            self._fixed_applied[side] = self._command_at(side, t1 - delay)
            return
        t0, v0 = last
        dt = t1 - t0
        if dt <= 0:
            return
        f0 = self._fixed_applied[side]
        command = self._command_at(side, t1 - delay)
        f1 = command if lag <= 0 else f0 + (command - f0) * (1.0 - math.exp(-dt / lag))
        self._fixed_applied[side] = f1
        still = max(abs(v0), abs(state.v_mm_s)) < FIXED_STILL_MM_S
        if still and abs(target - state.x_mm) < FIXED_STILL_DEADBAND_MM:
            return  # stuck close enough: integrating the spring further only breaks it loose (stick-slip hunting)
        profile = self.profile.side(side)
        model = self.friction[side]
        v = (v0 + state.v_mm_s) / 2
        weight = compensation.gravity(profile, state.x_mm) + model.ripple(state.x_mm)
        drag = model.force(v, self.tunables.friction_blend_mm_s, x_mm=state.x_mm)
        momentum = float(profile.moving_mass_kg.value) * (state.v_mm_s - v0) / 1000.0 / dt
        needed = (f0 + f1) / 2 - weight - drag - momentum  # = −F_user: what the bias must add
        share = 1.0 - math.exp(-dt / FIXED_OBSERVER_S)
        bias = self.fixed_integral[side] + (needed - self.fixed_integral[side]) * share
        self.fixed_integral[side] = max(-limit, min(limit, bias))

    def _descent_gain(self, side: Side, load: float) -> float:
        """Friction compensation going down in training: from the weightless gain to ``train_friction_gain_down`` as the
        load grows to the static friction (a bar without a load has nothing pulling it down and must stop by itself).
        A bar running away downwards (load relief) gets the friction back as a brake."""

        t = self.tunables
        if self.load.load_direction == "up":
            share = max(0.0, min(1.0, load / max(self.friction[side].coulomb_up_n, 1.0))) * self.load_relief[side]
            start, end = DESCENT_GAIN_FADE_START * self.envelope.max_speed_mm_s, 0.6 * self.envelope.max_speed_mm_s
            v_ahead = self._bar_v_mm_s + self._bar_a_mm_s2 * self._loop_delay()
            share *= max(0.0, min(1.0, (end - v_ahead) / (end - start)))
            return t.friction_gain_up + (t.train_friction_gain_down - t.friction_gain_up) * share
        share = max(0.0, min(1.0, load / max(self.friction[side].coulomb_down_n, 1.0))) * self.load_relief[side]
        start, end = DESCENT_GAIN_FADE_START * self.envelope.max_descent_mm_s, 0.6 * self.envelope.max_descent_mm_s
        v_ahead = self._bar_v_mm_s + self._bar_a_mm_s2 * self._loop_delay()
        share *= max(0.0, min(1.0, (end + v_ahead) / (end - start)))
        return t.friction_gain_down + (t.train_friction_gain_down - t.friction_gain_down) * share

    def _range_damping(self) -> float:
        mass = min(float(self.profile.side(side).moving_mass_kg.value) for side in SIDES)
        return min(RANGE_DAMPING_N_PER_MM_S, FIXED_DAMPING_DELAY_SHARE * mass / (1000.0 * self._loop_delay()))

    def _update_range(self, states: dict[Side, ObservedState]) -> None:
        """Once per tick, on the bar as a whole: the load relief, the floor cut and the range force of both sides.

        A bar running away downwards loses its load (relief). Below the lower point the load ramps out (in time, at
        the load ramp rate: a position fade of a heavy load would be a stiff spring that rings with the bus delay),
        a brake stops the fall and a soft spring returns the bar up to the point at no more than
        ``FLOOR_RETURN_MM_S``; the load ramps in again once the bar is lifted back into the range by more than the
        rep hysteresis. Above the upper point a brake stops the bar's momentum within ``RANGE_STOP_MM`` and a light
        spring turns it back down. Moving back into the range is not resisted.
        With an upward load the bounds are mirrored, but the unloaded return damper is not: pulling down from
        the upper point must not add an upward kick on top of the load ramp.
        """

        x = (states["left"].x_mm + states["right"].x_mm) / 2
        v = (states["left"].v_mm_s + states["right"].v_mm_s) / 2
        a = (states["left"].a_mm_s2 + states["right"].a_mm_s2) / 2
        self._bar_x_mm = x
        self._bar_v_mm_s = v
        self._bar_a_mm_s2 = a
        upward = self.load.load_direction == "up"
        if upward:
            # Work in the original downward-load coordinates; preserve physical bar state for inertia / friction.
            x, v, a = self.load.lower_mm + self.load.upper_mm - x, -v, -a
        descent_onset = 0.6 * (self.envelope.max_speed_mm_s if upward else self.envelope.max_descent_mm_s)
        relief = self.load_relief["left"]
        # judged on the speed a loop delay ahead while the bar speeds up downwards: the relief acts that late
        v_relief = v + min(0.0, a) * self._loop_delay()
        if v_relief < -descent_onset:
            relief = max(0.0, relief - self._dt / LOAD_RELIEF_DROP_S)
        elif v > -0.5 * descent_onset:
            relief = min(1.0, relief + self._dt / LOAD_RELIEF_RECOVER_S)
        self.load_relief = {side: relief for side in SIDES}
        self.range_force_n = 0.0
        if not self.load.range_guard:
            self.floor_cut = 0.0
            return
        below = self.load.lower_mm - x
        step = self.tunables.load_ramp_n_per_s * self._dt / max(self.load.load_n, 1.0)
        if below > 0:
            self.floor_cut = min(1.0, self.floor_cut + step)
        elif -below > self.tunables.reps_hysteresis_mm:
            self.floor_cut = max(0.0, self.floor_cut - step)  # lifted back into the range: the load ramps in
        mass = sum(float(self.profile.side(side).moving_mass_kg.value) for side in SIDES) / 2
        damping = self._range_damping()
        # the brakes act a loop delay late: sized for the speed by then, gone once the bar will have stopped (a brake
        # still on after the stop throws the bar back)
        v_ahead = v + a * self._loop_delay()
        if below > 0:
            spring = min(FLOOR_K_N_PER_MM * below, FLOOR_MAX_N) * max(0.0, min(1.0, (FLOOR_RETURN_MM_S - v) / FLOOR_RETURN_MM_S))
            self.range_force_n = spring + damping * max(-v, 0.0)
        if not upward and self.floor_cut > 0 and v > 0:
            # without its load a free bar thrown up off the floor would coast high into the range, meet the load there
            # and drop again: the damper stays while the load is out (the user lifting feels it instead of the load)
            self.range_force_n -= damping * self.floor_cut * v
        if below > 0:
            if upward:
                self.range_force_n = -self.range_force_n
            return
        above = x - self.load.upper_mm
        if above > 0:
            brake = 0.0
            if v > 0 and v_ahead > 0:
                room = max(RANGE_STOP_MM - above, RANGE_STOP_MIN_MM)
                brake = min(mass * v_ahead**2 / (2000.0 * room), RANGE_BRAKE_MAX_N) + damping * v
            self.range_force_n = -(min(CEILING_K_N_PER_MM * above, CEILING_MAX_N) + brake)
        if upward:
            self.range_force_n = -self.range_force_n

    def _fall_assist(self, side: Side, state: ObservedState, load: float) -> float:
        """A light load (below the static friction) left alone must sink like a free weight, not stick.

        After ``FALL_REST_S`` at rest the law adds a downward push that ramps up to the static friction
        (less the load). Moving down it is cut to the friction the compensation leaves (1 − gain), so the bar
        falls with its load, as a free weight does; moving up it goes at once.
        """

        model = self.friction[side]
        assist = self.fall_assist[side]
        upward = self.load.load_direction == "up"
        velocity = -state.v_mm_s if upward else state.v_mm_s
        outside = self._bar_x_mm > self.load.upper_mm if upward else self._bar_x_mm < self.load.lower_mm
        coulomb = model.coulomb_up_n if upward else model.coulomb_down_n
        if load <= 1.0 or (self.load.range_guard and outside):
            assist = 0.0  # no load: nothing pulls a free bar down; below the set's range the bar goes up
        elif velocity > STILL_MM_S:
            assist = max(0.0, assist - FALL_DROP_N_PER_S * self._dt)
        elif velocity < -STILL_MM_S:
            residual = (1.0 - self._descent_gain(side, load)) * coulomb * self.load_relief[side]
            assist = min(assist, max(0.0, residual))
        else:
            static = max(0.0, FALL_STATIC_MARGIN * (coulomb + model.stribeck_extra_n) - load)
            if self._still_s[side] >= FALL_REST_S:
                assist = min(static, assist + FALL_RAMP_N_PER_S * self._dt)
            assist = min(assist, static)
        self.fall_assist[side] = assist
        return assist
