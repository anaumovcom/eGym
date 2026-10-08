"""Mode machine (plan 14 §4.3): a pure transition table, every transition is tested."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class Mode(StrEnum):
    SUPPORT = "support"
    IDLE = "idle"
    WEIGHTLESS = "weightless"
    JOG = "jog"
    HOLD = "hold"
    TRAINING = "training"
    FIXED = "fixed"
    ISOMETRIC = "isometric"
    CALIBRATING = "calibrating"
    FAULT = "fault"
    ESTOP = "estop"


Event = Literal[
    "ready", "weightless", "jog", "jog_end", "hold", "train", "pause", "release", "failure",
    "fixed", "isometric", "calibrate", "calibration_done", "fault", "overspeed", "reset", "estop", "estop_clear", "idle",
]
Output = Literal["support", "zero", "idle", "weightless", "hold", "train", "calibrate"]


class TransitionError(PermissionError):
    pass


TRANSITIONS: dict[tuple[Mode, str], Mode] = {
    (Mode.SUPPORT, "ready"): Mode.IDLE,
    (Mode.IDLE, "weightless"): Mode.WEIGHTLESS,
    (Mode.IDLE, "hold"): Mode.HOLD,
    (Mode.IDLE, "calibrate"): Mode.CALIBRATING,
    (Mode.WEIGHTLESS, "jog"): Mode.JOG,
    (Mode.WEIGHTLESS, "hold"): Mode.HOLD,
    (Mode.WEIGHTLESS, "idle"): Mode.IDLE,
    (Mode.JOG, "jog_end"): Mode.WEIGHTLESS,
    (Mode.HOLD, "train"): Mode.TRAINING,
    (Mode.HOLD, "fixed"): Mode.FIXED,
    (Mode.HOLD, "isometric"): Mode.ISOMETRIC,
    (Mode.HOLD, "weightless"): Mode.WEIGHTLESS,
    (Mode.HOLD, "idle"): Mode.IDLE,
    (Mode.TRAINING, "pause"): Mode.HOLD,
    (Mode.TRAINING, "release"): Mode.HOLD,
    (Mode.TRAINING, "failure"): Mode.HOLD,
    (Mode.FIXED, "pause"): Mode.HOLD,
    (Mode.FIXED, "release"): Mode.HOLD,
    (Mode.ISOMETRIC, "pause"): Mode.HOLD,
    (Mode.ISOMETRIC, "release"): Mode.HOLD,
    (Mode.CALIBRATING, "calibration_done"): Mode.HOLD,
    (Mode.CALIBRATING, "release"): Mode.HOLD,  # dead-man released
    (Mode.FAULT, "reset"): Mode.SUPPORT,
    (Mode.ESTOP, "estop_clear"): Mode.SUPPORT,
}

OUTPUT: dict[Mode, Output] = {
    Mode.SUPPORT: "support",
    Mode.IDLE: "idle",
    Mode.WEIGHTLESS: "weightless",
    Mode.JOG: "weightless",
    Mode.HOLD: "hold",
    Mode.TRAINING: "train",
    Mode.FIXED: "hold",
    Mode.ISOMETRIC: "hold",
    Mode.CALIBRATING: "calibrate",
    Mode.FAULT: "support",
    Mode.ESTOP: "support",
}


def transition(mode: Mode, event: str) -> Mode:
    if event == "estop":  # accepted from any mode, never bypassed (R15)
        return Mode.ESTOP
    if event in {"fault", "overspeed"}:
        return mode if mode == Mode.ESTOP else Mode.FAULT
    target = TRANSITIONS.get((mode, event))
    if target is None:
        raise TransitionError(f"Переход {mode.value} → «{event}» запрещён")
    return target


class Supervisor:
    """Holds the mode and the overspeed latch; both sides always share one mode (R14)."""

    def __init__(self) -> None:
        self.mode = Mode.SUPPORT
        self.overspeed_latched = False
        self.reason: str | None = None

    def handle(self, event: str, reason: str | None = None) -> Mode:
        new_mode = transition(self.mode, event)
        if event == "overspeed":
            self.overspeed_latched = True
        if event == "reset" or (event == "estop_clear" and not self.overspeed_latched):
            self.reason = None
        if event == "reset":
            self.overspeed_latched = False
        if reason and new_mode in {Mode.FAULT, Mode.ESTOP}:
            self.reason = self.reason or reason
        self.mode = new_mode
        return new_mode

    @property
    def output(self) -> Output:
        if self.overspeed_latched:
            return "zero"  # R5: not overridden by idle/support/shutdown
        return OUTPUT[self.mode]
