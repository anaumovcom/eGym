"""Calibration runner: drives a procedure generator tick by tick with dead-man and an envelope.

A procedure is a generator: it receives ``Frame`` and yields ``Command``;
its return value is the raw data for ``fit``. Only torque (forces/raw) is
ever commanded. Any envelope violation, a released dead-man, a bad frame or
a timeout aborts the procedure and puts both drives on support.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import Any, Literal

from app.motor.drive.protocol import DriveSample, TorqueDrive
from app.motor.units import SIDES, Side


@dataclass(frozen=True)
class Frame:
    t: float
    samples: dict[Side, DriveSample]

    def x(self, side: Side) -> float:
        return self.samples[side].position_mm

    def v(self, side: Side) -> float:
        return self.samples[side].speed_mm_s

    @property
    def x_mean(self) -> float:
        return (self.x("left") + self.x("right")) / 2

    @property
    def v_mean(self) -> float:
        return (self.v("left") + self.v("right")) / 2


@dataclass(frozen=True)
class Command:
    forces_n: dict[Side, float] | None = None  # None → support
    raw: dict[Side, int] | None = None  # direct PA_12C (direction test only)
    note: str = ""
    progress: float | None = None  # 0..1 inside the procedure, for the UI


Procedure = Generator[Command, Frame, dict[str, Any]]


@dataclass(frozen=True)
class ProcedureEnvelope:
    max_speed_mm_s: float = 80.0
    min_x_mm: float = -5.0
    max_x_mm: float = 1500.0
    max_force_n: float = 600.0


@dataclass
class RunResult:
    status: Literal["done", "aborted", "failed"]
    data: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    log: list[tuple[float, float, float, float, float, float, float]] = field(default_factory=list)


class CalibrationRunner:
    """``run`` owns the loop (tests, scripts); ``begin``/``feed``/``cancel`` let a host loop step it."""

    def __init__(
        self,
        drives: dict[Side, TorqueDrive],
        tick: Callable[[], float] | None = None,
        envelope: ProcedureEnvelope | None = None,
        dead_man: Callable[[], bool] = lambda: True,
    ) -> None:
        self.drives = drives
        self.tick = tick
        self.envelope = envelope or ProcedureEnvelope()
        self.dead_man = dead_man
        self._procedure: Procedure | None = None
        self._command = Command()
        self._result = RunResult("done")
        self._run_envelope = self.envelope
        self._max_s = 600.0
        self._t0: float | None = None
        self.note = ""
        self.progress = 0.0

    @property
    def active(self) -> bool:
        return self._procedure is not None

    @property
    def command(self) -> Command:
        return self._command

    @property
    def result(self) -> RunResult:
        return self._result

    def _check(self, frame: Frame, envelope: ProcedureEnvelope) -> str | None:
        if not self.dead_man():
            return "кнопка удержания отпущена"
        for side, sample in frame.samples.items():
            if not sample.ok:
                return f"{side}: {sample.error}"
            if abs(sample.speed_mm_s) > envelope.max_speed_mm_s:
                return f"{side}: скорость {sample.speed_mm_s:.0f} мм/с вне огибающей"
            if not envelope.min_x_mm <= sample.position_mm <= envelope.max_x_mm:
                return f"{side}: позиция {sample.position_mm:.0f} мм вне огибающей"
        return None

    def _write(self, command: Command) -> dict[Side, str]:
        errors: dict[Side, str] = {}
        for side in SIDES:
            drive = self.drives[side]
            if command.raw is not None:
                error = drive.write_raw(command.raw[side])
            elif command.forces_n is None:
                error = drive.support()
            else:
                force = max(-self._run_envelope.max_force_n, min(self._run_envelope.max_force_n, command.forces_n[side]))
                error = drive.write_force(force)
            if error:
                errors[side] = error
        return errors

    def _finish(self, status: Literal["done", "aborted", "failed"], reason: str | None = None, *, support: bool = True) -> RunResult:
        if self._procedure is not None:
            self._procedure.close()
            self._procedure = None
        if support and status != "done":
            for drive in self.drives.values():
                drive.support()
        self._result.status = status
        self._result.reason = reason
        return self._result

    def begin(self, procedure: Procedure, max_s: float = 600.0, envelope: ProcedureEnvelope | None = None) -> RunResult | None:
        """Write the first command; ``RunResult`` if the procedure ended at once."""

        self._run_envelope = envelope or self.envelope
        self._max_s = max_s
        self._t0 = None
        self._result = RunResult("done")
        self.note = ""
        self.progress = 0.0
        try:
            command = next(procedure)
        except StopIteration as stop:
            self._result.data = stop.value or {}
            return self._result
        self._procedure = procedure
        return self._send(command)

    def _send(self, command: Command) -> RunResult | None:
        self._command = command
        self.note = command.note or self.note
        if command.progress is not None:
            self.progress = max(0.0, min(1.0, command.progress))
        errors = self._write(command)
        if errors:
            return self._finish("failed", "запись PA_12C: " + "; ".join(f"{side}: {error}" for side, error in errors.items()))
        return None

    def feed(self, frame: Frame) -> RunResult | None:
        """One step after the host read ``frame``: check, advance the procedure, write. ``RunResult`` when finished."""

        if self._procedure is None:
            return self._result
        command = self._command
        self._t0 = frame.t if self._t0 is None else self._t0
        if command.raw is not None:
            shown = {side: float(command.raw[side]) for side in SIDES}
        else:
            shown = command.forces_n or {side: 0.0 for side in SIDES}
        self._result.log.append((frame.t, frame.x("left"), frame.x("right"), frame.v("left"), frame.v("right"), shown["left"], shown["right"]))
        reason = self._check(frame, self._run_envelope)
        if reason:
            return self._finish("aborted", reason)
        if frame.t - self._t0 > self._max_s:
            return self._finish("failed", "превышено время процедуры")
        try:
            command = self._procedure.send(frame)
        except StopIteration as stop:
            self._procedure = None
            self._result.data = stop.value or {}
            return self._result
        except ProcedureError as error:
            self._procedure = None
            return self._finish("failed", str(error))
        return self._send(command)

    def cancel(self, reason: str, *, support: bool = True) -> RunResult:
        """Operator abort or an external latch; ``support=False`` when the host writes its own safe output."""

        return self._finish("aborted", reason, support=support)

    def run(self, procedure: Procedure, max_s: float = 600.0, envelope: ProcedureEnvelope | None = None) -> RunResult:
        assert self.tick is not None
        result = self.begin(procedure, max_s, envelope)
        while result is None:
            t = self.tick()
            result = self.feed(Frame(t, {side: self.drives[side].read() for side in SIDES}))
        return result


class ProcedureError(RuntimeError):
    pass
