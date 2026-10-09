"""Two-side mechanics with dry/viscous/Stribeck friction, stiction, end stops and bar coupling."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from app.motor.units import SCREW_LEAD_MM, SIDES, Side, kgf_to_n, passport_n_per_raw


@dataclass(frozen=True)
class SidePhysics:
    weight_n: float = kgf_to_n(7.0)
    mass_kg: float = 60.0  # reflected: bar share + carriage + screw + rotor
    coulomb_up_n: float = kgf_to_n(5.0)
    coulomb_down_n: float = kgf_to_n(5.0)
    stiction_extra_n: float = 0.0  # Fs − Fc at breakaway
    stribeck_v_mm_s: float = 5.0
    viscous_n_per_mm_s: float = 0.05
    weight_slope_n_per_mm: float = 0.0  # W(x) = weight_n + slope·x
    n_per_raw: float = passport_n_per_raw()
    direction_sign: int = 1
    extra_mass_kg: float = 0.0  # reference weight hung on this side
    stop_adhesion_n: float = 0.0  # extra breakaway force when resting on the bottom stops (sticking, grease)
    friction_load_up: float = 0.0  # Coulomb grows with the screw load beyond the bar weight while the motor drives the motion
    friction_load_down: float = 0.0  # … and while the motion drives the motor (back-driving)
    pull_scale: float = 1.0  # downward motor force per raw relative to the upward one
    dwell_stiction_n: float = 0.0  # breakaway grows with the time at rest: + n · (1 − exp(−t/τ))
    dwell_tau_s: float = 5.0
    ripple_n: float = 0.0  # force ripple with the screw revolution (lead 32 mm)
    ripple_phase_rad: float = 0.0
    tight_spots: tuple[tuple[float, float, float], ...] = ()  # (x_mm, half width mm, extra friction N)

    def weight_at(self, x_mm: float) -> float:
        ripple = self.ripple_n * math.sin(2 * math.pi * x_mm / SCREW_LEAD_MM + self.ripple_phase_rad) if self.ripple_n else 0.0
        return self.weight_n + self.weight_slope_n_per_mm * x_mm + kgf_to_n(self.extra_mass_kg) + ripple

    def coulomb(self, direction: int, x_mm: float, motor_force_n: float | None = None) -> float:
        """Kinetic Coulomb friction; the screw load beyond the bare bar weight adds the L1/L2 growth.

        Without ``motor_force_n`` the motor is taken to hold the bar and the hung weight. The coefficient
        follows the power flow: "up" when the motor drives the motion (force along it), "down" when back-driven.
        """

        base = self.coulomb_up_n if direction > 0 else self.coulomb_down_n
        bare = self.weight_n + self.weight_slope_n_per_mm * x_mm
        force = bare + kgf_to_n(self.extra_mass_kg) if motor_force_n is None else motor_force_n
        excess = max(0.0, abs(force) - bare)
        driving = direction * (1 if force >= 0 else -1) > 0
        load = (self.friction_load_up if driving else self.friction_load_down) * excess
        spot = sum(extra for center, half, extra in self.tight_spots if abs(x_mm - center) <= half)
        return base + load + spot

    @property
    def total_mass_kg(self) -> float:
        return self.mass_kg + self.extra_mass_kg


@dataclass(frozen=True)
class PlantParams:
    left: SidePhysics = field(default_factory=SidePhysics)
    right: SidePhysics = field(default_factory=SidePhysics)
    coupling_n_per_mm: float = 40.0
    coupling_damping_n_per_mm_s: float = 2.0
    travel_mm: float = 1400.0
    # drive
    max_raw: int = 1000
    deadband_raw: int = 0
    torque_lag_s: float = 0.005
    speed_limit_rpm: float = 1000.0
    # bus
    command_delay_ticks: int = 1
    read_delay_ticks: int = 0
    drop_probability: float = 0.0
    position_noise_mm: float = 0.0
    speed_lag_s: float = 0.0  # PA_1C1 filter: the speed register follows the true speed with this time constant
    encoder_zero_counts: int = 0  # absolute encoder reading on the bottom stops

    def side(self, side: Side) -> SidePhysics:
        return self.left if side == "left" else self.right

    def with_side(self, side: Side, physics: SidePhysics) -> PlantParams:
        return replace(self, **{side: physics})


@dataclass
class SideState:
    x_mm: float = 0.0
    v_mm_s: float = 0.0
    a_mm_s2: float = 0.0
    motor_force_n: float = 0.0  # after lag and clamps
    stuck: bool = True
    stuck_s: float = 0.0  # time at rest (dwell stiction)


class Plant:
    """Integrates with a 1 ms sub-step; forces in N, positions in mm."""

    SUBSTEP_S = 0.001

    def __init__(self, params: PlantParams, x0_mm: float = 0.0) -> None:
        self.params = params
        self.state: dict[Side, SideState] = {side: SideState(x_mm=x0_mm) for side in SIDES}
        self.t = 0.0

    def _friction(self, physics: SidePhysics, v: float, x: float, motor_force_n: float | None = None) -> float:
        coulomb = physics.coulomb(1 if v > 0 else -1, x, motor_force_n)
        stribeck = physics.stiction_extra_n * math.exp(-((v / max(physics.stribeck_v_mm_s, 1e-6)) ** 2))
        return math.copysign(coulomb + stribeck, v) + physics.viscous_n_per_mm_s * v

    def step(self, motor_target_n: dict[Side, float], user_force_n: dict[Side, float], dt: float) -> None:
        steps = max(1, round(dt / self.SUBSTEP_S))
        h = dt / steps
        p = self.params
        lag = 1.0 if p.torque_lag_s <= 0 else 1 - math.exp(-h / p.torque_lag_s)
        for _ in range(steps):
            snapshot = {side: (s.x_mm, s.v_mm_s) for side, s in self.state.items()}
            for side in SIDES:
                physics = p.side(side)
                s = self.state[side]
                other_x, other_v = snapshot["right" if side == "left" else "left"]
                target = motor_target_n.get(side, 0.0)
                rpm = abs(s.v_mm_s) * 60 / 32
                if s.v_mm_s > 0 and target > 0 and rpm > p.speed_limit_rpm:
                    # PA_056 limits the motor only while it drives the motion (not descent under gravity)
                    target *= max(0.0, 1 - (rpm - p.speed_limit_rpm) / (0.1 * p.speed_limit_rpm))
                s.motor_force_n += (target - s.motor_force_n) * lag
                coupling = p.coupling_n_per_mm * (other_x - s.x_mm) + p.coupling_damping_n_per_mm_s * (other_v - s.v_mm_s)
                drive = s.motor_force_n + user_force_n.get(side, 0.0) - physics.weight_at(s.x_mm) + coupling
                mass = physics.total_mass_kg
                if s.stuck:
                    on_stops = s.x_mm <= 0.0
                    s.stuck_s += h
                    dwell = physics.dwell_stiction_n * (1 - math.exp(-s.stuck_s / physics.dwell_tau_s)) if physics.dwell_stiction_n else 0.0
                    breakaway_up = physics.coulomb(1, s.x_mm, s.motor_force_n) + physics.stiction_extra_n + dwell + (physics.stop_adhesion_n if on_stops else 0.0)
                    breakaway_dn = physics.coulomb(-1, s.x_mm, s.motor_force_n) + physics.stiction_extra_n + dwell
                    on_bottom = s.x_mm <= 0.0 and drive < 0
                    on_top = s.x_mm >= p.travel_mm and drive > 0
                    if drive > breakaway_up and not on_top:
                        s.stuck = False
                        net = drive - breakaway_up
                    elif drive < -breakaway_dn and not on_bottom:
                        s.stuck = False
                        net = drive + breakaway_dn
                    else:
                        s.a_mm_s2 = 0.0
                        continue
                    s.a_mm_s2 = 1000 * net / mass
                    s.v_mm_s = s.a_mm_s2 * h
                else:
                    s.stuck_s = 0.0
                    net = drive - self._friction(physics, s.v_mm_s, s.x_mm, s.motor_force_n)
                    s.a_mm_s2 = 1000 * net / mass
                    v_new = s.v_mm_s + s.a_mm_s2 * h
                    if v_new * s.v_mm_s < 0 or v_new == 0:
                        v_new = 0.0
                        s.stuck = True
                    s.v_mm_s = v_new
                s.x_mm += s.v_mm_s * h
                if s.x_mm <= 0.0 and s.v_mm_s < 0:
                    s.x_mm, s.v_mm_s, s.stuck = 0.0, 0.0, True
                elif s.x_mm >= p.travel_mm and s.v_mm_s > 0:
                    s.x_mm, s.v_mm_s, s.stuck = p.travel_mm, 0.0, True
            self.t += h
