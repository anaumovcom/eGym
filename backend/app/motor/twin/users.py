"""Virtual users (plan 14 §7.3). A user returns the external force per side, N, up positive."""

from __future__ import annotations

import math

from app.motor.twin.bench import TwinBench, UserModel
from app.motor.units import SIDES, Side, kgf_to_n


def nobody() -> UserModel:
    return lambda t, bench: {}


def constant(force_n: float, *, start_s: float = 0.0, stop_s: float = math.inf) -> UserModel:
    def user(t: float, bench: TwinBench) -> dict[Side, float]:
        return {side: force_n for side in SIDES} if start_s <= t < stop_s else {}

    return user


def push(force_n: float, at_s: float, duration_s: float = 0.2) -> UserModel:
    return constant(force_n, start_s=at_s, stop_s=at_s + duration_s)


def steady(load_kgf_per_side: float, lower_mm: float, upper_mm: float, *, gain_n_per_mm_s: float = 4.0, speed_mm_s: float = 250.0) -> UserModel:
    """Lifts and lowers a weight of ``load_kgf_per_side`` between two points with a speed regulator."""

    direction = {"value": 1}

    def user(t: float, bench: TwinBench) -> dict[Side, float]:
        x, v = bench.true_state("left")
        if x >= upper_mm:
            direction["value"] = -1
        elif x <= lower_mm:
            direction["value"] = 1
        target_v = direction["value"] * speed_mm_s
        base = kgf_to_n(load_kgf_per_side)
        return {side: base + gain_n_per_mm_s * (target_v - bench.true_state(side)[1]) for side in SIDES}

    return user


def release_after(user: UserModel, at_s: float) -> UserModel:
    return lambda t, bench: user(t, bench) if t < at_s else {}
