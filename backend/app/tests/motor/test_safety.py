from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.motor.profile import SafetyEnvelope
from app.motor.supervisor.safety import CommMonitor, SafetyInput, apply_envelope

ENV = SafetyEnvelope()
forces = st.floats(-3000, 3000, allow_nan=False)
positions = st.floats(-50, 1500, allow_nan=False)
dts = st.floats(0.005, 0.1)


@given(forces, forces, positions, dts, st.booleans())
def test_output_is_always_within_max_force(target: float, previous: float, x: float, dt: float, stale: bool) -> None:
    out = apply_envelope(ENV, SafetyInput(target, previous, x, 70.0, dt, stale))
    assert -ENV.max_force_n_per_side <= out <= ENV.max_force_n_per_side


@given(forces, forces, st.floats(-50, ENV.soft_min_mm), dts)
def test_soft_limit_never_pushes_out_bottom(target: float, previous: float, x: float, dt: float) -> None:
    assert apply_envelope(ENV, SafetyInput(target, previous, x, 70.0, dt)) >= 0.0


@given(forces, forces, st.floats(ENV.soft_max_mm, 1500), dts, st.floats(20, 200))
def test_soft_limit_never_pushes_out_top(target: float, previous: float, x: float, dt: float, weight: float) -> None:
    assert apply_envelope(ENV, SafetyInput(target, previous, x, weight, dt)) <= weight + 1e-9


@given(st.floats(0, 700), st.floats(0, 700), st.floats(100, 1200), dts)
def test_rate_limit(target: float, previous: float, x: float, dt: float) -> None:
    out = apply_envelope(ENV, SafetyInput(target, previous, x, 70.0, dt))
    assert abs(out - previous) <= ENV.max_rate_n_per_s * dt + 1e-6


@given(forces, st.floats(-700, 700), st.floats(100, 1200), dts)
def test_stale_frame_no_growth(target: float, previous: float, x: float, dt: float) -> None:
    out = apply_envelope(ENV, SafetyInput(target, previous, x, 70.0, dt, stale=True))
    assert abs(out) <= abs(previous) + 1e-9


def test_comm_degradation_policy() -> None:
    monitor = CommMonitor(freeze_frames=2, fault_frames=6)
    assert monitor.update(True) == "ok"
    assert monitor.update(False) == "extrapolate"
    assert monitor.update(False) == "freeze"
    assert monitor.update(True) == "ok"
    states = [monitor.update(False) for _ in range(6)]
    assert states == ["extrapolate", "freeze", "freeze", "freeze", "freeze", "fault"]
    assert monitor.update(True) == "fault"  # latched until reset
    monitor.reset()
    assert monitor.update(True) == "ok"
    assert monitor.update(True, write_ok=False) == "fault"
