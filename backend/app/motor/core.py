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
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
        self.load = LoadSetpoint()
        self.virtual_mass_kg = 0.0
        self.phase = PhaseTracker(self.tunables.phase_hysteresis_mm_s, self.tunables.phase_blend_s)
        self.calibration_force: dict[Side, float] | None = None
        self.load_relief: dict[Side, float] = {side: 1.0 for side in SIDES}
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
        mode = self.supervisor.handle(event, reason)
        if mode in {Mode.HOLD, Mode.FIXED, Mode.ISOMETRIC}:
            self.hold_target = {side: None for side in SIDES}  # hold-catch from the current position
            self._hold_caught = {side: False for side in SIDES}
        if event == "reset":
            for monitor in self.comm.values():
                monitor.reset()
        return mode

    def set_load(self, setpoint: LoadSetpoint) -> None:
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
                    brake = mass * decel / 1000 + max(self.load.load_n * self.load_relief[side], 0.0)
                    force += brake * min(1.0, excess / CUSHION_BLEND_MM_S) + CUSHION_GAIN_N_PER_MM_S * excess
        top = _value(self.profile.cushion_top_mm)
        if top and state.v_mm_s > 0:
            distance = self.envelope.soft_max_mm - state.x_mm
            if distance < top:
                decel = CUSHION_DECEL_SHARE * (_value(self.profile.brake_decel_up_mm_s2, CUSHION_DECEL_MM_S2) or CUSHION_DECEL_MM_S2)
                excess = state.v_mm_s - (landing * landing + 2 * decel * max(distance - ahead - CUSHION_MARGIN_MM, 0.0)) ** 0.5
                if excess > 0:
                    force -= mass * decel / 1000 * min(1.0, excess / CUSHION_BLEND_MM_S) + CUSHION_GAIN_N_PER_MM_S * excess
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
        for side in SIDES:
            sample = samples.get(side)
            ok = sample is not None and sample.ok and now - sample.t <= self.envelope.stale_frame_limit_s
            comm_states[side] = self.comm[side].update(ok, write_ok)
            if ok and sample is not None:
                states[side] = self.observers[side].update(sample.position_mm, sample.speed_mm_s, sample.t)
            else:
                states[side] = self.observers[side].miss(now)
            if sample is not None and sample.alarm and self.supervisor.mode not in {Mode.FAULT, Mode.ESTOP}:
                self.command("fault", f"Авария привода {side}: {sample.error}")
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
            return CoreOutput("zero", dict(self.previous), self.supervisor.mode, states, user_force, phase)
        if output == "support" or (output == "idle" and all(states[side].x_mm < ON_STOPS_MM for side in SIDES)):
            self.previous = {side: self._support_force(side) for side in SIDES}
            return CoreOutput("support", dict(self.previous), self.supervisor.mode, states, user_force, phase)

        forces: dict[Side, float] = {}
        for side in SIDES:
            other: Side = "right" if side == "left" else "left"
            state = states[side]
            target = self._law(output, side, state, states[other], blend)
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
        return CoreOutput("force", dict(forces), self.supervisor.mode, states, user_force, phase)

    def _law(self, output: str, side: Side, state: ObservedState, other: ObservedState, blend: float) -> float:
        profile = self.profile.side(side)
        t = self.tunables
        model = self.friction[side]
        weight = compensation.gravity(profile, state.x_mm) + model.ripple(state.x_mm)
        # the command acts after the bus delay: friction sign and size for the velocity then (V3)
        v_ahead = state.v_mm_s + state.a_mm_s2 * self.horizon_s
        # screw load beyond the bar weight: friction grows with it (L1/L2); below the weight the preload keeps it
        axial = max(0.0, abs(self.previous[side]) - weight)
        friction = compensation.friction(model, v_ahead, t, x_mm=state.x_mm, axial_excess_n=axial) * self._breakaway_scale(side)
        sync = side_sync(state.x_mm, other.x_mm, t.sync_k_n_per_mm, t.sync_max_n)
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
            spring = virtual_spring(state.x_mm, state.v_mm_s, target, k, c, limit_n=float(profile.coulomb_up_n.value) * 2 + 50)
            return weight + friction + spring + sync + speed_guard
        # train
        descent_onset = 0.6 * self.envelope.max_descent_mm_s
        if state.v_mm_s < -descent_onset:
            self.load_relief[side] = max(0.0, self.load_relief[side] - self._dt / LOAD_RELIEF_DROP_S)
        elif state.v_mm_s > -0.5 * descent_onset:
            self.load_relief[side] = min(1.0, self.load_relief[side] + self._dt / LOAD_RELIEF_RECOVER_S)
        load = load_force(self.load, state.x_mm, blend) * self.load_relief[side]
        inertia = compensation.inertia(float(profile.moving_mass_kg.value), self.virtual_mass_kg, state.a_mm_s2, self.inertia_share(side))
        return weight + friction + inertia - load + sync + speed_guard
