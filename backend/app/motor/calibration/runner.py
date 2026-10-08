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
    def __init__(
        self,
        drives: dict[Side, TorqueDrive],
        tick: Callable[[], float],
        envelope: ProcedureEnvelope | None = None,
        dead_man: Callable[[], bool] = lambda: True,
    ) -> None:
        self.drives = drives
        self.tick = tick
        self.envelope = envelope or ProcedureEnvelope()
        self.dead_man = dead_man

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

    def _write(self, command: Command) -> None:
        for side in SIDES:
            drive = self.drives[side]
            if command.raw is not None:
                drive.write_raw(command.raw[side])
            elif command.forces_n is None:
                drive.support()
            else:
                force = max(-self.envelope.max_force_n, min(self.envelope.max_force_n, command.forces_n[side]))
                drive.write_force(force)

    def _abort(self, result: RunResult, status: Literal["aborted", "failed"], reason: str) -> RunResult:
        for drive in self.drives.values():
            drive.support()
        result.status = status
        result.reason = reason
        return result

    def run(self, procedure: Procedure, max_s: float = 600.0, envelope: ProcedureEnvelope | None = None) -> RunResult:
        envelope = envelope or self.envelope
        result = RunResult("done")
        try:
            command = next(procedure)
        except StopIteration as stop:
            result.data = stop.value or {}
            return result
        t0: float | None = None
        while True:
            self._write(command)
            t = self.tick()
            t0 = t if t0 is None else t0
            frame = Frame(t, {side: self.drives[side].read() for side in SIDES})
            forces = command.forces_n or {side: 0.0 for side in SIDES}
            result.log.append((t, frame.x("left"), frame.x("right"), frame.v("left"), frame.v("right"), forces["left"], forces["right"]))
            reason = self._check(frame, envelope)
            if reason:
                procedure.close()
                return self._abort(result, "aborted", reason)
            if t - t0 > max_s:
                procedure.close()
                return self._abort(result, "failed", "превышено время процедуры")
            try:
                command = procedure.send(frame)
            except StopIteration as stop:
                result.data = stop.value or {}
                return result
            except ProcedureError as error:
                return self._abort(result, "failed", str(error))


class ProcedureError(RuntimeError):
    pass
