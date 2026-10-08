"""Friction model: Coulomb up/down, viscous, Stribeck, smoothed sign (plan 15 §1)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.motor.profile import SideProfile
from app.motor.units import smooth_sign


@dataclass(frozen=True)
class FrictionModel:
    coulomb_up_n: float
    coulomb_down_n: float
    viscous_n_per_mm_s: float = 0.0
    stribeck_extra_n: float = 0.0
    stribeck_v_mm_s: float = 5.0

    @staticmethod
    def from_profile(profile: SideProfile) -> FrictionModel:
        return FrictionModel(
            float(profile.coulomb_up_n.value),
            float(profile.coulomb_down_n.value),
            float(profile.viscous_n_per_mm_s.value),
            float(profile.stribeck_extra_n.value),
            float(profile.stribeck_v_mm_s.value),
        )

    def force(self, v_mm_s: float, blend_mm_s: float = 0.0) -> float:
        """Friction resisting motion (same sign as v): what the motor must add to cancel it."""

        s = smooth_sign(v_mm_s, blend_mm_s)
        coulomb = self.coulomb_up_n if s >= 0 else self.coulomb_down_n
        stribeck = self.stribeck_extra_n * math.exp(-((v_mm_s / max(self.stribeck_v_mm_s, 1e-6)) ** 2))
        return s * (coulomb + stribeck) + self.viscous_n_per_mm_s * v_mm_s

    def compensation(self, v_mm_s: float, gain_up: float, gain_down: float, blend_mm_s: float) -> float:
        force = self.force(v_mm_s, blend_mm_s)
        return force * (gain_up if force >= 0 else gain_down)

    def window(self, weight_n: float) -> tuple[float, float]:
        """Static window [F_dn, F_up]: any motor force inside it keeps the bar still."""

        return weight_n - self.coulomb_down_n - self.stribeck_extra_n, weight_n + self.coulomb_up_n + self.stribeck_extra_n
