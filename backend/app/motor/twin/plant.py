"""Two-side mechanics with dry/viscous/Stribeck friction, stiction, end stops and bar coupling."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from app.motor.units import SIDES, Side, kgf_to_n, passport_n_per_raw


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

    def weight_at(self, x_mm: float) -> float:
        return self.weight_n + self.weight_slope_n_per_mm * x_mm + kgf_to_n(self.extra_mass_kg)

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


class Plant:
    """Integrates with a 1 ms sub-step; forces in N, positions in mm."""

    SUBSTEP_S = 0.001

    def __init__(self, params: PlantParams, x0_mm: float = 0.0) -> None:
        self.params = params
        self.state: dict[Side, SideState] = {side: SideState(x_mm=x0_mm) for side in SIDES}
        self.t = 0.0

    def _friction(self, physics: SidePhysics, v: float) -> float:
        coulomb = physics.coulomb_up_n if v > 0 else physics.coulomb_down_n
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
                    breakaway_up = physics.coulomb_up_n + physics.stiction_extra_n
                    breakaway_dn = physics.coulomb_down_n + physics.stiction_extra_n
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
                    net = drive - self._friction(physics, s.v_mm_s)
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
