"""Setup speed multipliers do not change calibrations, precision corrections or transit safety caps."""

from dataclasses import replace

import pytest

from app.motor import workout
from app.motor.calibration.procedures import motion
from app.motor.calibration.runner import Frame
from app.motor.drive.protocol import DriveSample
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
@pytest.mark.parametrize("scale, expected", [(1.0, 100.0), (3.0, 300.0), (30.0, 410.0)])
def test_fast_transit_scales_speed_but_keeps_existing_ceiling(monkeypatch, balance, direction, scale, expected):
    seen = []
    target = 500.0 + direction * 300.0

    def fast(b, f, x, **kwargs):
        seen.append(kwargs["top_mm_s"])
        if False:
            yield
        return frame(x)

    monkeypatch.setattr(motion, "_fast", fast)
    list(motion.travel(balance, frame(500.0), target, speed_scale=scale))
    assert seen == [expected]


@pytest.mark.parametrize("direction, expected", [(1, 180.0), (-1, 120.0)])
def test_short_start_move_is_three_times_faster(monkeypatch, balance, direction, expected):
    seen = []

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


@pytest.mark.parametrize("direction", [1, -1])
def test_setup_jog_uses_120_mm_s_and_brakes_before_limit(monkeypatch, balance, direction):
    seen = []
    balance = replace(balance, brake_decel={1: 100.0, -1: 100.0})
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
    assert seen == [(direction, 120.0)]


def test_go_to_start_requests_speed_scale_only_for_exercise_move(monkeypatch, balance):
    seen = []

    def travel(b, f, x, **kwargs):
        seen.append(kwargs["speed_scale"])
        if False:
            yield
        return f

    monkeypatch.setattr(workout, "travel", travel)
    gen = workout._goto(balance, frame(500.0), 700.0, "start")
    next(gen)
    with pytest.raises(StopIteration):
        gen.send(frame(500.0))
    assert seen == [3.0]