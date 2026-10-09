"""MachineProfile (identified physics), Tunables (behaviour), SafetyEnvelope (hard limits).

Every identified value carries provenance (plan 14 §3.5, §5).
"""

from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Literal

from app.motor.units import SIDES, Side, kgf_to_n, passport_mm_per_pulse, passport_n_per_raw

Provenance = Literal["measured", "derived", "default", "manual"]
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Measured:
    value: Any
    ci95: float | None = None
    provenance: Provenance = "default"
    run_id: str | None = None
    measured_at: str | None = None
    temperature_c: float | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Measured:
        return Measured(**{key: data.get(key) for key in ("value", "ci95", "provenance", "run_id", "measured_at", "temperature_c") if key in data})


def _d(value: Any, ci95: float | None = None, provenance: Provenance = "default") -> Measured:
    return Measured(value, ci95, provenance)


@dataclass(frozen=True)
class SideProfile:
    n_per_raw: Measured = field(default_factory=lambda: _d(passport_n_per_raw(), 0.15 * passport_n_per_raw(), "derived"))
    direction_sign: Measured = field(default_factory=lambda: _d(1))
    mm_per_pulse: Measured = field(default_factory=lambda: _d(passport_mm_per_pulse(), None, "derived"))
    # [(x_mm, W_n), ...] sorted by x; one point = constant weight
    gravity_map: Measured = field(default_factory=lambda: _d([(0.0, kgf_to_n(7.0))]))
    coulomb_up_n: Measured = field(default_factory=lambda: _d(kgf_to_n(5.0)))
    coulomb_down_n: Measured = field(default_factory=lambda: _d(kgf_to_n(5.0)))
    viscous_n_per_mm_s: Measured = field(default_factory=lambda: _d(0.05))
    stribeck_v_mm_s: Measured = field(default_factory=lambda: _d(5.0))
    stribeck_extra_n: Measured = field(default_factory=lambda: _d(0.0))
    moving_mass_kg: Measured = field(default_factory=lambda: _d(60.0))
    support_raw: Measured = field(default_factory=lambda: _d(100))
    zero_counts: Measured = field(default_factory=lambda: _d(None))
    # motion (M1, M2): force beyond the window edge; None = not measured, the motion primitives adapt
    liftoff_extra_n: Measured = field(default_factory=lambda: _d(None))
    travel_extra_up_n: Measured = field(default_factory=lambda: _d(None))
    travel_extra_down_n: Measured = field(default_factory=lambda: _d(None))
    # positioning (P1, P2): force beyond the window edge by speed [(v_mm_s, extra_n)]
    travel_table_up: Measured = field(default_factory=lambda: _d(None))
    travel_table_down: Measured = field(default_factory=lambda: _d(None))
    # friction under an axial load (L1, L2): ΔFc = coeff · ΔW
    friction_load_up: Measured = field(default_factory=lambda: _d(None))
    friction_load_down: Measured = field(default_factory=lambda: _d(None))
    # breakaway growth with the time at rest (S5): + n·(1 − exp(−t/τ))
    dwell_extra_n: Measured = field(default_factory=lambda: _d(None))
    dwell_tau_s: Measured = field(default_factory=lambda: _d(None))
    # force ripple with the screw revolution (S6)
    screw_ripple_n: Measured = field(default_factory=lambda: _d(None))
    screw_ripple_phase_rad: Measured = field(default_factory=lambda: _d(None))
    deadband_raw: Measured = field(default_factory=lambda: _d(None))  # D1
    # kinetic friction at exercise speeds (F3): [(v_mm_s, F_n)], total friction force in the direction of motion
    friction_table_up: Measured = field(default_factory=lambda: _d(None))
    friction_table_down: Measured = field(default_factory=lambda: _d(None))
    # friction along the travel (S10): [(x_mm, ΔF_n)] beyond the usual friction, both directions
    friction_map: Measured = field(default_factory=lambda: _d(None))
    # downward (pulling) force per raw relative to the upward one (N1): heavy loads make the motor pull the bar down
    pull_scale: Measured = field(default_factory=lambda: _d(None))

    def weight_n(self, x_mm: float) -> float:
        points: list[tuple[float, float]] = [tuple(p) for p in self.gravity_map.value]  # type: ignore[misc]
        if len(points) == 1:
            return float(points[0][1])
        xs = [p[0] for p in points]
        i = bisect.bisect_left(xs, x_mm)
        if i <= 0:
            return float(points[0][1])
        if i >= len(points):
            return float(points[-1][1])
        (x0, w0), (x1, w1) = points[i - 1], points[i]
        return float(w0 + (w1 - w0) * (x_mm - x0) / (x1 - x0))

    @property
    def n_per_raw_value(self) -> float:
        return float(self.n_per_raw.value)

    @property
    def pull_scale_value(self) -> float:
        value = self.pull_scale.value
        return float(value) if value else 1.0

    @property
    def sign(self) -> int:
        return int(self.direction_sign.value)


@dataclass(frozen=True)
class MachineProfile:
    version: int = 0
    left: SideProfile = field(default_factory=SideProfile)
    right: SideProfile = field(default_factory=SideProfile)
    loop_period_s: Measured = field(default_factory=lambda: _d(0.04))
    loop_delay_s: Measured = field(default_factory=lambda: _d(0.04))
    jitter_p95_s: Measured = field(default_factory=lambda: _d(0.01))
    hold_ultimate_k_n_per_mm: Measured = field(default_factory=lambda: _d(None))
    hold_ultimate_period_s: Measured = field(default_factory=lambda: _d(None))
    side_coupling_n_per_mm: Measured = field(default_factory=lambda: _d(None))
    travel_mm: Measured = field(default_factory=lambda: _d(1400.0, None, "manual"))
    # M3: stopping by the middle of the static window
    brake_lag_s: Measured = field(default_factory=lambda: _d(None))
    brake_decel_up_mm_s2: Measured = field(default_factory=lambda: _d(None))
    brake_decel_down_mm_s2: Measured = field(default_factory=lambda: _d(None))
    # automatic moves (P, A)
    position_speed_up_mm_s: Measured = field(default_factory=lambda: _d(None))
    position_speed_down_mm_s: Measured = field(default_factory=lambda: _d(None))
    accel_mm_s2: Measured = field(default_factory=lambda: _d(None))
    decel_mm_s2: Measured = field(default_factory=lambda: _d(None))
    landing_speed_mm_s: Measured = field(default_factory=lambda: _d(None))
    stop_overshoot_mm: Measured = field(default_factory=lambda: _d(None))  # E1
    reversal_stick_s: Measured = field(default_factory=lambda: _d(None))  # R1
    torque_lag_s: Measured = field(default_factory=lambda: _d(None))  # B2
    tight_spots: Measured = field(default_factory=lambda: _d(None))  # S8: [(x_mm, extra_n)]
    # behaviour identified on the machine; override the Tunables defaults when measured
    hold_k_n_per_mm: Measured = field(default_factory=lambda: _d(None))  # H1
    hold_c_n_per_mm_s: Measured = field(default_factory=lambda: _d(None))
    sync_k_n_per_mm: Measured = field(default_factory=lambda: _d(None))  # X3
    weightless_gain_up: Measured = field(default_factory=lambda: _d(None))  # W1
    weightless_gain_down: Measured = field(default_factory=lambda: _d(None))
    # motion estimate (V1–V3)
    speed_lag_s: Measured = field(default_factory=lambda: _d(None))  # PA_1C1 behind the encoder
    speed_scale: Measured = field(default_factory=lambda: _d(None))  # PA_1C1 / true speed
    accel_smoothing: Measured = field(default_factory=lambda: _d(None))  # observer acceleration filter
    accel_noise_mm_s2: Measured = field(default_factory=lambda: _d(None))
    predict_horizon_s: Measured = field(default_factory=lambda: _d(None))  # friction/inertia use v(t + h)
    # free-weight feel (F1–F11, X4, L3)
    inertia_ratio_max: Measured = field(default_factory=lambda: _d(None))  # F1: compensated mass / machine mass, stable
    inertia_table: Measured = field(default_factory=lambda: _d(None))  # F2: [(load_n per side, gain)]
    feel_blend_mm_s: Measured = field(default_factory=lambda: _d(None))  # F4
    feel_phase_hysteresis_mm_s: Measured = field(default_factory=lambda: _d(None))  # F5
    feel_phase_blend_s: Measured = field(default_factory=lambda: _d(None))
    breakaway_soft_s: Measured = field(default_factory=lambda: _d(None))  # F6
    track_comp_gain: Measured = field(default_factory=lambda: _d(None))  # F7: screw ripple + friction map
    deadband_comp_gain: Measured = field(default_factory=lambda: _d(None))  # F8
    dither_n: Measured = field(default_factory=lambda: _d(None))  # F9
    cushion_bottom_mm: Measured = field(default_factory=lambda: _d(None))  # F10
    cushion_top_mm: Measured = field(default_factory=lambda: _d(None))
    feel_release_force_n: Measured = field(default_factory=lambda: _d(None))  # F11
    feel_release_timeout_s: Measured = field(default_factory=lambda: _d(None))
    sync_k_train_n_per_mm: Measured = field(default_factory=lambda: _d(None))  # X4
    friction_load_gain: Measured = field(default_factory=lambda: _d(None))  # L3

    def side(self, side: Side) -> SideProfile:
        return self.left if side == "left" else self.right

    def with_side(self, side: Side, profile: SideProfile) -> MachineProfile:
        return replace(self, **{side: profile})

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA_VERSION, **asdict(self)}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> MachineProfile:
        def side_from(raw: dict[str, Any]) -> SideProfile:
            known = {f.name for f in fields(SideProfile)}
            return SideProfile(**{key: Measured.from_dict(value) for key, value in raw.items() if key in known})

        machine_fields = {f.name for f in fields(MachineProfile)} - {"version", "left", "right"}
        return MachineProfile(
            version=int(data.get("version", 0)),
            left=side_from(data.get("left", {})),
            right=side_from(data.get("right", {})),
            **{key: Measured.from_dict(value) for key, value in data.items() if key in machine_fields},
        )


@dataclass(frozen=True)
class Tunables:
    """≈20 behaviour knobs; defaults are conservative, the autotuner replaces them (plan 14 §5.2)."""

    friction_gain_up: float = 0.6
    friction_gain_down: float = 0.6
    inertia_gain: float = 0.0
    friction_blend_mm_s: float = 8.0
    weightless_damping_n_per_mm_s: float = 0.3
    hold_k_fraction: float = 0.25
    hold_c_fraction: float = 0.25
    hold_k_default_n_per_mm: float = 0.5  # used until C1 relay test measured K_u
    hold_c_default_n_per_mm_s: float = 0.3
    load_ramp_n_per_s: float = 400.0
    phase_blend_s: float = 0.15
    phase_hysteresis_mm_s: float = 15.0
    assist_alpha: float = 0.7
    eccentric_beta: float = 1.2
    levitation_margin_mm: float = 30.0
    reps_full_percent: float = 85.0
    reps_partial_percent: float = 40.0
    reps_hysteresis_mm: float = 15.0
    release_force_n: float = 40.0
    release_timeout_s: float = 3.0
    sync_k_n_per_mm: float = 3.0
    sync_max_n: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Tunables:
        known = {f.name for f in fields(Tunables)}
        return Tunables(**{key: float(value) for key, value in data.items() if key in known})


@dataclass(frozen=True)
class SafetyEnvelope:
    """Hard limits; the last filter before the drive (plan 14 §5.3)."""

    max_force_n_per_side: float = 700.0
    max_raw: int = 1000  # PA_05E
    soft_min_mm: float = 20.0
    soft_max_mm: float = 1380.0
    max_speed_mm_s: float = 450.0  # below the drive limit PA_056 (480 mm/s), screw 0.8·n_cr ≈ 510 (plan 14 §2.8)
    max_descent_mm_s: float = 400.0
    overspeed_rpm_alarm: float = 1000.0  # 533 mm/s
    max_rate_n_per_s: float = 2000.0
    sync_warning_mm: float = 5.0
    sync_critical_mm: float = 15.0
    stale_frame_limit_s: float = 0.15
    comm_freeze_frames: int = 2
    comm_fault_frames: int = 6
    temp_max_c: float = 80.0
    speed_limit_rpm: int = 900  # PA_056 = 480 mm/s; must stay below the overspeed alarm
    fault_lockout: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SafetyEnvelope:
        known = {f.name: f for f in fields(SafetyEnvelope)}
        defaults = SafetyEnvelope()
        return SafetyEnvelope(**{key: type(getattr(defaults, key))(value) for key, value in data.items() if key in known})


def calibrated_tunables(profile: MachineProfile, tunables: Tunables) -> Tunables:
    """Tunables with the values identified by calibrations taking precedence (W1, X3/X4, F4, F5, F11)."""

    overrides: dict[str, float] = {}
    for key, path in CALIBRATED_TUNABLES:
        item: Measured = getattr(profile, path)
        if item.value is not None and item.provenance in ("measured", "manual"):
            overrides[key] = float(item.value)
    return replace(tunables, **overrides) if overrides else tunables


# (tunable, profile field); a later pair wins (X4 in training over X3 in moves)
CALIBRATED_TUNABLES: tuple[tuple[str, str], ...] = (
    ("friction_gain_up", "weightless_gain_up"),
    ("friction_gain_down", "weightless_gain_down"),
    ("sync_k_n_per_mm", "sync_k_n_per_mm"),
    ("sync_k_n_per_mm", "sync_k_train_n_per_mm"),
    ("friction_blend_mm_s", "feel_blend_mm_s"),
    ("phase_hysteresis_mm_s", "feel_phase_hysteresis_mm_s"),
    ("phase_blend_s", "feel_phase_blend_s"),
    ("release_force_n", "feel_release_force_n"),
    ("release_timeout_s", "feel_release_timeout_s"),
)


def default_profile() -> MachineProfile:
    return MachineProfile()


__all__ = ["SIDES", "MachineProfile", "Measured", "SafetyEnvelope", "SideProfile", "Tunables", "calibrated_tunables", "default_profile"]
