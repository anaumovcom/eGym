"""Random machines around the passport (plan 14 §7.1). Fixed seed → reproducible failures."""

from __future__ import annotations

import random
from dataclasses import replace

from app.motor.twin.plant import PlantParams, SidePhysics
from app.motor.units import kgf_to_n, passport_n_per_raw


def random_side(rng: random.Random, base: SidePhysics | None = None) -> SidePhysics:
    base = base or SidePhysics()
    return replace(
        base,
        weight_n=kgf_to_n(rng.uniform(4.0, 15.0)),
        mass_kg=rng.uniform(25.0, 90.0),
        coulomb_up_n=kgf_to_n(rng.uniform(1.0, 7.0)),
        coulomb_down_n=kgf_to_n(rng.uniform(1.0, 7.0)),
        stiction_extra_n=kgf_to_n(rng.uniform(0.0, 0.8)),
        stribeck_v_mm_s=rng.uniform(2.0, 10.0),
        viscous_n_per_mm_s=rng.uniform(0.01, 0.15),
        weight_slope_n_per_mm=rng.uniform(-0.005, 0.005),
        n_per_raw=passport_n_per_raw() * rng.uniform(0.75, 1.25),
        direction_sign=rng.choice((1, -1)),
    )


def random_machine(seed: int, *, max_delay_ticks: int = 3, noise_mm: float = 0.01) -> PlantParams:
    rng = random.Random(seed)
    left = random_side(rng)
    asym = rng.uniform(0.85, 1.15)
    right = replace(
        random_side(rng, left),
        weight_n=left.weight_n * asym,
        mass_kg=left.mass_kg * rng.uniform(0.9, 1.1),
    )
    return PlantParams(
        left=left,
        right=right,
        coupling_n_per_mm=rng.uniform(10.0, 80.0),
        command_delay_ticks=rng.randint(1, max_delay_ticks),
        read_delay_ticks=rng.randint(0, 1),
        position_noise_mm=noise_mm,
    )
