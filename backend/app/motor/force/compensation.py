"""Compensation: gravity W(x), friction g_f·F_f(v), inertia g_m·(m − M)·a_ref."""

from __future__ import annotations

from app.motor.estimation.friction import FrictionModel
from app.motor.profile import SideProfile, Tunables


def gravity(profile: SideProfile, x_mm: float) -> float:
    return profile.weight_n(x_mm)


def friction(
    model: FrictionModel, v_mm_s: float, tunables: Tunables, *, x_mm: float | None = None, axial_excess_n: float | None = None, motor_sign: int = 1,
) -> float:
    return model.compensation(
        v_mm_s, tunables.friction_gain_up, tunables.friction_gain_down, tunables.friction_blend_mm_s, x_mm=x_mm, axial_excess_n=axial_excess_n,
        motor_sign=motor_sign,
    )


def inertia(machine_mass_kg: float, virtual_mass_kg: float, a_ref_mm_s2: float, gain: float) -> float:
    """Cancel a share of the machine mass above the virtual one, or add virtual mass (stable side)."""

    excess = machine_mass_kg - virtual_mass_kg
    share = gain if excess > 0 else 1.0
    return share * excess * a_ref_mm_s2 / 1000
