"""Twin loop: connects ``MotorCore`` (or a calibration runner) to a ``TwinBench`` tick by tick."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.motor.core import CoreOutput, MotorCore
from app.motor.twin.bench import TwinBench
from app.motor.units import SIDES, Side


@dataclass
class Trace:
    t: list[float] = field(default_factory=list)
    x: dict[Side, list[float]] = field(default_factory=lambda: {side: [] for side in SIDES})
    v: dict[Side, list[float]] = field(default_factory=lambda: {side: [] for side in SIDES})
    force: dict[Side, list[float]] = field(default_factory=lambda: {side: [] for side in SIDES})
    mode: list[str] = field(default_factory=list)
    kind: list[str] = field(default_factory=list)


def write_output(bench: TwinBench, output: CoreOutput) -> bool:
    ok = True
    for side in SIDES:
        drive = bench.drives[side]
        if output.kind == "support":
            error = drive.support()
        elif output.kind == "zero":
            error = drive.zero()
        else:
            error = drive.write_force(output.forces_n[side])
        ok = ok and error is None
    return ok


def run_core(
    core: MotorCore,
    bench: TwinBench,
    seconds: float,
    dt: float = 0.02,
    on_tick: Callable[[float, CoreOutput], None] | None = None,
    trace: Trace | None = None,
) -> Trace:
    trace = trace or Trace()
    write_ok = True
    for _ in range(round(seconds / dt)):
        bench.advance(dt)
        samples = {side: bench.drives[side].read() for side in SIDES}
        output = core.step(samples, bench.t, write_ok)
        write_ok = write_output(bench, output)
        trace.t.append(bench.t)
        for side in SIDES:
            x, v = bench.true_state(side)
            trace.x[side].append(x)
            trace.v[side].append(v)
            trace.force[side].append(output.forces_n[side])
        trace.mode.append(output.mode.value)
        trace.kind.append(output.kind)
        if on_tick:
            on_tick(bench.t, output)
    return trace
