from __future__ import annotations

import itertools
import typing

import pytest

from app.motor.core import MotorCore
from app.motor.drive.protocol import DriveSample
from app.motor.profile import MachineProfile
from app.motor.supervisor.modes import TRANSITIONS, Event, Mode, Supervisor, TransitionError, transition
from app.motor.supervisor.reps import RepCounter

EVENTS = typing.get_args(Event)


@pytest.mark.parametrize(("mode", "event"), list(itertools.product(Mode, EVENTS)))
def test_every_transition_is_defined_or_rejected(mode: Mode, event: str) -> None:
    if event == "estop":
        assert transition(mode, event) == Mode.ESTOP
    elif event in {"fault", "overspeed"}:
        assert transition(mode, event) == (Mode.ESTOP if mode == Mode.ESTOP else Mode.FAULT)
    elif (mode, event) in TRANSITIONS:
        assert transition(mode, event) == TRANSITIONS[(mode, event)]
    else:
        with pytest.raises(TransitionError):
            transition(mode, event)


@pytest.mark.parametrize("mode", list(Mode))
def test_estop_from_any_mode(mode: Mode) -> None:
    supervisor = Supervisor()
    supervisor.mode = mode
    assert supervisor.handle("estop") == Mode.ESTOP
    assert supervisor.output == "support"


def test_overspeed_zero_latch_survives_estop_and_clear() -> None:
    supervisor = Supervisor()
    supervisor.handle("ready")
    supervisor.handle("overspeed")
    assert supervisor.output == "zero"
    supervisor.handle("estop")
    assert supervisor.output == "zero"
    supervisor.handle("estop_clear")
    assert supervisor.output == "zero"
    supervisor.handle("fault")
    supervisor.handle("reset")
    assert supervisor.output == "support"


def test_one_side_fault_both_sides() -> None:
    core = MotorCore(MachineProfile())
    core.command("ready")
    core.command("weightless")
    samples = {
        "left": DriveSample("left", 1.0, ok=True, position_mm=300.0),
        "right": DriveSample("right", 1.0, ok=False, alarm=16, error="Err 16"),
    }
    out = core.step(samples, 1.0)
    assert out.mode == Mode.FAULT
    assert out.kind == "support"
    assert set(out.forces_n) == {"left", "right"}


def test_rep_counter_full_and_partial() -> None:
    counter = RepCounter(lower_mm=500, upper_mm=1000)
    path = [*range(500, 1001, 10), *range(1000, 499, -10), *range(500, 751, 10), *range(750, 499, -10), *range(500, 600, 10), *range(600, 499, -10)]
    events = [event for x in path if (event := counter.update(float(x)))]
    assert events == ["full", "partial"]
    assert (counter.full, counter.partial) == (1, 1)
