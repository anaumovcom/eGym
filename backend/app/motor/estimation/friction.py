"""Friction model: Coulomb up/down, viscous, Stribeck, smoothed sign (plan 15 §1).

Optional calibrated parts (all off until measured):

* F3 ``table_up``/``table_down`` — total kinetic friction at exercise speeds; replaces Coulomb + viscous
  above the first table speed (below it blends linearly into the static model);
* S10 ``track`` (or S8 ``spots``) — extra friction along the travel, × ``track_gain`` (F7);
* S6 ``ripple`` — weight-like force with the screw revolution, × ``track_gain`` (``ripple(x)``);
* L1/L2 ``load_up``/``load_down`` — Coulomb grows with the axial load on the screw beyond the bar weight,
  × ``load_gain`` (L3).
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.motor.profile import SideProfile
from app.motor.units import SCREW_LEAD_MM, smooth_sign

if TYPE_CHECKING:
    from app.motor.profile import MachineProfile

SPOT_HALF_WIDTH_MM = 15.0  # S8 reports the centre of a tight spot; its width is about one 10-mm bin each side
MIN_FRICTION_SHARE = 0.3  # the load/track corrections never take the friction below 30 % of Coulomb

Curve = tuple[tuple[float, float], ...]


def interpolate(points: Sequence[tuple[float, float]], x: float, *, extrapolate: bool = False) -> float:
    """Piecewise-linear; flat beyond the ends unless ``extrapolate`` (then the last segment's slope)."""

    if len(points) == 1:
        return points[0][1]
    xs = [p[0] for p in points]
    i = bisect.bisect_left(xs, x)
    if i <= 0:
        i = 1
        if not extrapolate:
            return points[0][1]
    elif i >= len(points):
        i = len(points) - 1
        if not extrapolate:
            return points[-1][1]
    (x0, y0), (x1, y1) = points[i - 1], points[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 != x0 else y0


def _curve(value: object) -> Curve:
    return tuple(sorted((float(a), float(b)) for a, b in value)) if value else ()  # type: ignore[union-attr]


def _number(value: object, default: float = 0.0) -> float:
    return float(value) if value is not None else default  # type: ignore[arg-type]


@dataclass(frozen=True)
class FrictionModel:
    coulomb_up_n: float
    coulomb_down_n: float
    viscous_n_per_mm_s: float = 0.0
    stribeck_extra_n: float = 0.0
    stribeck_v_mm_s: float = 5.0
    table_up: Curve = ()
    table_down: Curve = ()
    track: Curve = ()  # (x, ΔF)
    spots: Curve = ()  # (x centre, ΔF), used without a track map
    ripple_n: float = 0.0
    ripple_phase_rad: float = 0.0
    track_gain: float = 0.0
    load_up: float = 0.0
    load_down: float = 0.0
    load_gain: float = 0.0

    @staticmethod
    def from_profile(profile: SideProfile, machine: MachineProfile | None = None) -> FrictionModel:
        load_gain = 0.0
        track_gain = 0.0
        spots: Curve = ()
        if machine is not None:
            load_gain = _number(machine.friction_load_gain.value, 1.0)  # L1/L2 are physical: on unless L3 says otherwise
            track_gain = _number(machine.track_comp_gain.value)  # needs the F7 check: a wrong phase would double the ripple
            spots = _curve(machine.tight_spots.value)
        return FrictionModel(
            float(profile.coulomb_up_n.value),
            float(profile.coulomb_down_n.value),
            float(profile.viscous_n_per_mm_s.value),
            float(profile.stribeck_extra_n.value),
            float(profile.stribeck_v_mm_s.value),
            table_up=_curve(profile.friction_table_up.value),
            table_down=_curve(profile.friction_table_down.value),
            track=_curve(profile.friction_map.value),
            spots=spots,
            ripple_n=_number(profile.screw_ripple_n.value),
            ripple_phase_rad=_number(profile.screw_ripple_phase_rad.value),
            track_gain=track_gain,
            load_up=_number(profile.friction_load_up.value),
            load_down=_number(profile.friction_load_down.value),
            load_gain=load_gain,
        )

    def _kinetic(self, speed: float, direction: int) -> float:
        """Friction magnitude at ``speed`` ≥ 0 in ``direction`` (Coulomb + Stribeck + viscous or the F3 table)."""

        coulomb = self.coulomb_up_n if direction > 0 else self.coulomb_down_n
        stribeck = self.stribeck_extra_n * math.exp(-((speed / max(self.stribeck_v_mm_s, 1e-6)) ** 2))
        table = self.table_up if direction > 0 else self.table_down
        if not table:
            return coulomb + stribeck + self.viscous_n_per_mm_s * speed
        v0, f0 = table[0]
        if speed >= v0:
            return interpolate(table, speed, extrapolate=True)
        return coulomb + stribeck + (f0 - coulomb) * speed / max(v0, 1e-6)

    def track_extra(self, x_mm: float) -> float:
        """Extra friction at height ``x`` (S10 map, else S8 tight spots), × the F7 gain."""

        if not self.track_gain:
            return 0.0
        if self.track:
            return self.track_gain * interpolate(self.track, x_mm)
        return self.track_gain * sum(extra for centre, extra in self.spots if abs(x_mm - centre) <= SPOT_HALF_WIDTH_MM)

    def ripple(self, x_mm: float) -> float:
        """Weight-like force with the screw revolution (S6), × the F7 gain: add it to the weight."""

        if not self.track_gain or not self.ripple_n:
            return 0.0
        return self.track_gain * self.ripple_n * math.sin(2 * math.pi * x_mm / SCREW_LEAD_MM + self.ripple_phase_rad)

    def force(
        self, v_mm_s: float, blend_mm_s: float = 0.0, *, x_mm: float | None = None, axial_excess_n: float | None = None, motor_sign: int = 1,
    ) -> float:
        """Friction resisting motion (same sign as v): what the motor must add to cancel it.

        ``axial_excess_n`` — axial load on the screw beyond the bar weight (|motor force| − W): the L1/L2 growth.
        ``motor_sign`` — sign of the motor force. L1/L2 measure with the motor pushing up: "up" is the motor
        driving the motion, "down" the motion back-driving the motor. A heavy load makes the motor pull down,
        and the two swap: lifting back-drives the screw, lowering is driven.
        """

        s = smooth_sign(v_mm_s, blend_mm_s)
        direction = 1 if s >= 0 else -1
        base = self.coulomb_up_n if direction > 0 else self.coulomb_down_n
        magnitude = self._kinetic(abs(v_mm_s), direction)
        if x_mm is not None:
            magnitude += self.track_extra(x_mm)
        if axial_excess_n is not None and self.load_gain:
            driving = direction * (1 if motor_sign >= 0 else -1) > 0
            magnitude += self.load_gain * (self.load_up if driving else self.load_down) * axial_excess_n
        magnitude = max(magnitude, MIN_FRICTION_SHARE * base)
        if self.table_up or self.table_down:
            return s * magnitude
        # Coulomb + Stribeck switch with the smoothed sign; the viscous part is continuous in v
        viscous = self.viscous_n_per_mm_s * abs(v_mm_s)
        return s * (magnitude - viscous) + self.viscous_n_per_mm_s * v_mm_s

    def compensation(
        self, v_mm_s: float, gain_up: float, gain_down: float, blend_mm_s: float, *, x_mm: float | None = None, axial_excess_n: float | None = None,
        motor_sign: int = 1,
    ) -> float:
        force = self.force(v_mm_s, blend_mm_s, x_mm=x_mm, axial_excess_n=axial_excess_n, motor_sign=motor_sign)
        return force * (gain_up if force >= 0 else gain_down)

    def window(self, weight_n: float) -> tuple[float, float]:
        """Static window [F_dn, F_up]: any motor force inside it keeps the bar still."""

        return weight_n - self.coulomb_down_n - self.stribeck_extra_n, weight_n + self.coulomb_up_n + self.stribeck_extra_n
