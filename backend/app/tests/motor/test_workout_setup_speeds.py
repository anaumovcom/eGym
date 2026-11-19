"""Setup speed multipliers do not change calibrations, precision corrections or transit safety caps."""

from dataclasses import replace

import pytest

from app.motor import workout
from app.motor.calibration.procedures import motion
from app.motor.calibration.runner import Frame
from app.motor.drive.protocol import DriveSample
from app.motor.profile import SafetyEnvelope
from app.motor.units import SIDES


def frame(x: float, v: float = 0.0) -> Frame:
    return Frame(1.0, {side: DriveSample(side, 1.0, True, position_mm=x, speed_mm_s=v) for side in SIDES})


@pytest.fixture
def balance() -> motion.Balance:
    return motion.Balance(
        {side: [(0.0, 300.0), (1400.0, 300.0)] for side in SIDES},
        {side: 30.0 for side in SIDES}, {side: 30.0 for side in SIDES},
        position_speed={1: 100.0, -1: 100.0},
    )


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("scale", [1.0, 3.0, 30.0])
def test_fast_transit_respects_calibrated_directional_speed(monkeypatch, balance, direction, scale):
    seen = []
    target = 500.0 + direction * 300.0

    def fast(b, f, x, **kwargs):
        seen.append(kwargs["top_mm_s"])
        if False:
            yield
        return frame(x)

    monkeypatch.setattr(motion, "_fast", fast)
    list(motion.travel(balance, frame(500.0), target, speed_scale=scale))
    assert seen == [100.0]


@pytest.mark.parametrize("direction, measured, expected", [(1, 200, 180), (-1, 300, 120), (1, 50, 50), (-1, 20, 20)])
def test_short_transit_accelerates_within_its_measured_speed(monkeypatch, balance, direction, measured, expected):
    seen = []
    balance = replace(balance, position_speed={direction: measured})

    def governed(b, f, d, speed, done, **kwargs):
        seen.append((d, speed))
        if False:
            yield
        return f

    def hold(b, f, **kwargs):
        if False:
            yield
        return f

    monkeypatch.setattr(motion, "_governed", governed)
    monkeypatch.setattr(motion, "hold_still", hold)
    list(motion.travel(balance, frame(500.0), 500.0 + direction * 40.0, speed_scale=3.0))
    assert seen == [(direction, expected)]


@pytest.mark.parametrize("direction, measured, expected", [(1, 100, 100), (-1, 20, 20), (1, 300, 120)])
def test_setup_jog_respects_calibrated_speed_and_brakes_before_limit(monkeypatch, balance, direction, measured, expected):
    seen = []
    balance = replace(balance, brake_decel={1: 100.0, -1: 100.0}, position_speed={direction: measured})
    limit = 500.0 + direction * 200.0

    def governed(b, f, d, speed, done, **kwargs):
        seen.append((d, speed))
        assert not done(f, {})
        # 120 mm/s needs > 72 mm to stop: release the drive before the physical limit.
        assert done(frame(limit - direction * 50.0, direction * 120.0), {})
        if False:
            yield
        return f

    def hold(b, f, **kwargs):
        if False:
            yield
        return f

    monkeypatch.setattr(workout, "_governed", governed)
    monkeypatch.setattr(workout, "hold_still", hold)
    gen = workout._jog(balance, frame(500.0), direction, lambda f: True, limit)
    next(gen)
    with pytest.raises(StopIteration):
        gen.send(frame(500.0))
    assert seen == [(direction, expected)]


def test_go_to_start_uses_measured_speed_without_exceeding_descent_limit(monkeypatch, balance):
    seen = []

    def travel(b, f, x, **kwargs):
        seen.append((b.position_speed, kwargs.get("speed_mm_s")))
        if False:
            yield
        return frame(x)

    monkeypatch.setattr(motion, "travel", travel)
    gen = workout._goto(balance, frame(500.0), 300.0, "start", SafetyEnvelope(max_descent_mm_s=50))
    next(gen)
    with pytest.raises(StopIteration):
        gen.send(frame(500.0))
    assert seen == [({1: 100, -1: 50}, None)]


@pytest.mark.parametrize("direction", (1, -1))
def test_fast_approach_brakes_short_then_finishes_at_the_prescribed_point(monkeypatch, balance, direction):
    seen = []
    target = 500 + direction * 400

    def cruise(b, f, x, **kwargs):
        seen.append((x, kwargs["top_mm_s"]))
        yield motion.Command(b.mid(f))
        return frame(x + direction * 12)  # residual cruise travel from friction and bus delay

    def finish(b, f, x, **kwargs):
        seen.append((x, kwargs["speed_mm_s"]))
        yield motion.Command(b.mid(f))
        return frame(x)

    monkeypatch.setattr(motion, "_fast", cruise)
    monkeypatch.setattr(motion, "travel", finish)
    list(motion.position_for_start(balance, frame(500), target, SafetyEnvelope(), note="подвод"))
    assert seen == [(target - direction * 30, 100), (target, 60 if direction > 0 else 40)]
