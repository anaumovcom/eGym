"""Motor core: one tick read → estimate → supervise → force law → safety. Pure, no I/O.

The same core runs against the twin (tests, autotuning) and later inside
``motor-rt`` against the real drives (plan 16, stage 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.motor.drive.protocol import DriveSample
from app.motor.estimation.friction import FrictionModel
from app.motor.estimation.observer import AlphaBetaObserver, ObservedState
from app.motor.estimation.user_force import UserForceEstimate, estimate_user_force
from app.motor.force import compensation
from app.motor.force.load_models import LoadSetpoint, PhaseTracker, load_force
from app.motor.force.shaping import governor, rate_limit, side_sync, virtual_spring
from app.motor.profile import MachineProfile, SafetyEnvelope, Tunables
from app.motor.supervisor.modes import Mode, Supervisor
from app.motor.supervisor.safety import CommMonitor, SafetyInput, apply_envelope
from app.motor.units import SIDES, Side, rpm_to_mm_s

ON_STOPS_MM = 5.0
HOLD_CATCH_SPEED_MM_S = 5.0
LOAD_RELIEF_DROP_S = 0.15  # full load → 0 when the bar runs away downwards
LOAD_RELIEF_RECOVER_S = 0.5


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
        self.tunables = tunables or Tunables()
        self.envelope = envelope or SafetyEnvelope()
        self.supervisor = Supervisor()
        self.observers = {side: AlphaBetaObserver() for side in SIDES}
        self.comm = {side: CommMonitor(self.envelope.comm_freeze_frames, self.envelope.comm_fault_frames) for side in SIDES}
        self.friction = {side: FrictionModel.from_profile(profile.side(side)) for side in SIDES}
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
        weight = compensation.gravity(profile, state.x_mm)
        friction = compensation.friction(self.friction[side], state.v_mm_s, t)
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
        inertia = compensation.inertia(float(profile.moving_mass_kg.value), self.virtual_mass_kg, state.a_mm_s2, t.inertia_gain)
        return weight + friction + inertia - load + sync + speed_guard
