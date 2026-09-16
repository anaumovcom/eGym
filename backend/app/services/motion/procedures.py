"""Multi-tick procedures (measurement wizards and one-button test scenarios).

Procedures are generators driven by the runtime control loop: every ``yield``
means "wait for the next control tick".  The return value is the result
payload shown in the tuning page.
"""

from __future__ import annotations

import math
from collections.abc import Generator
from statistics import mean
from typing import TYPE_CHECKING, Any

from app.services.motion.controller import ControlMode, TrainingConfig

if TYPE_CHECKING:
    from app.services.hardware_runtime import HardwareRuntime

Procedure = Generator[str, None, dict[str, Any]]


class ProcedureContext:
    def __init__(self, runtime: HardwareRuntime) -> None:
        self.runtime = runtime

    @property
    def tick(self) -> float:
        return self.runtime.tick_seconds

    @property
    def controller(self):  # noqa: ANN201
        return self.runtime.controller

    @property
    def telemetry(self):  # noqa: ANN201
        return self.runtime.last_telemetry

    @property
    def params(self):  # noqa: ANN201
        return self.runtime.parameters

    @property
    def emulator(self):  # noqa: ANN201
        return self.runtime.emulator

    def wait(self, seconds: float, label: str = "") -> Generator[str, None, None]:
        ticks = max(1, int(round(seconds / self.tick)))
        for _ in range(ticks):
            yield label

    def wait_until(self, predicate, timeout_s: float, label: str = "") -> Generator[str, None, bool]:  # noqa: ANN001
        ticks = max(1, int(round(timeout_s / self.tick)))
        for _ in range(ticks):
            if predicate():
                return True
            yield label
        return predicate()

    def samples(self, seconds: float, label: str = "") -> Generator[str, None, list[Any]]:
        collected: list[Any] = []
        ticks = max(1, int(round(seconds / self.tick)))
        for _ in range(ticks):
            collected.append(self.telemetry)
            yield label
        return collected


# ---------------------------------------------------------------- measurements
def measure_bar_mass(ctx: ProcedureContext) -> Procedure:
    """Hold still; steady-state drive force equals bar + moving parts mass."""

    ctx.controller.request_hold("Измерение массы", "Гриф удерживается для измерения массы.")
    yield from ctx.wait(1.0, "Стабилизация удержания")
    samples = yield from ctx.samples(1.5, "Измерение силы удержания")
    total = mean(item.total_force_kg for item in samples if item is not None)
    moving = float(ctx.params.get("compensation.movingPartsMassKg"))
    return {
        "measuredTotalMassKg": round(total, 2),
        "suggested": {"compensation.barMassKg": round(max(0.0, total - moving), 2)},
        "note": "Масса подвижных частей взята из текущих параметров; при необходимости скорректируйте её отдельно.",
    }


def measure_friction(ctx: ProcedureContext) -> Procedure:
    """Slow constant-speed moves up and down; force deviation from mass gives friction."""

    start = ctx.controller.state.position_mm
    mass_samples = yield from _steady_mass(ctx)
    mass = mean(mass_samples)
    speed = float(ctx.params.get("profile.calibration.speedMmPerSec"))
    up_forces: list[float] = []
    down_forces: list[float] = []
    ctx.controller.request_move(start + 120, profile="calibration", then=ControlMode.paused, label="Трение: подъём")
    arrived = yield from ctx.wait_until(lambda: ctx.controller.state.mode != ControlMode.moving, 25.0, "Подъём на низкой скорости")
    if not arrived:
        return {"error": "Подъём не завершён"}
    ctx.controller.request_move(start, profile="calibration", then=ControlMode.paused, label="Трение: опускание")
    while ctx.controller.state.mode == ControlMode.moving:
        telemetry = ctx.telemetry
        if telemetry is not None and abs(telemetry.bar_velocity_mm_s) > speed * 0.6:
            down_forces.append(telemetry.total_force_kg)
        yield "Опускание на низкой скорости"
    ctx.controller.request_move(start + 120, profile="calibration", then=ControlMode.paused, label="Трение: подъём 2")
    while ctx.controller.state.mode == ControlMode.moving:
        telemetry = ctx.telemetry
        if telemetry is not None and abs(telemetry.bar_velocity_mm_s) > speed * 0.6:
            up_forces.append(telemetry.total_force_kg)
        yield "Повторный подъём"
    ctx.controller.request_move(start, profile="return", then=ControlMode.paused, label="Возврат")
    yield from ctx.wait_until(lambda: ctx.controller.state.mode != ControlMode.moving, 25.0, "Возврат")
    friction_up = max(0.0, mean(up_forces) - mass) if up_forces else 0.0
    friction_down = max(0.0, mass - mean(down_forces)) if down_forces else 0.0
    return {
        "massKg": round(mass, 2),
        "frictionUpKg": round(friction_up, 2),
        "frictionDownKg": round(friction_down, 2),
        "suggested": {"compensation.frictionUpKg": round(friction_up, 2), "compensation.frictionDownKg": round(friction_down, 2)},
    }


def measure_inertia(ctx: ProcedureContext) -> Procedure:
    """Aggressive accelerations; regress net force against acceleration → equivalent mass."""

    start = ctx.controller.state.position_mm
    mass_samples = yield from _steady_mass(ctx)
    mass = mean(mass_samples)
    friction = (float(ctx.params.get("compensation.frictionUpKg")) + float(ctx.params.get("compensation.frictionDownKg"))) / 2
    pairs: list[tuple[float, float]] = []
    previous_velocity = 0.0
    for target in (start + 150, start, start + 150, start):
        ctx.controller.request_move(target, profile="training", then=ControlMode.paused, label="Инерция: разгон")
        while ctx.controller.state.mode == ControlMode.moving:
            telemetry = ctx.telemetry
            if telemetry is not None:
                velocity = telemetry.bar_velocity_mm_s
                accel = (velocity - previous_velocity) / ctx.tick
                previous_velocity = velocity
                sign = math.copysign(1.0, velocity) if abs(velocity) > 2 else 0.0
                net = telemetry.total_force_kg - mass - friction * sign
                if abs(accel) > 300:
                    pairs.append((accel / 9810.0, net))
            yield "Измерение ускорения"
    if len(pairs) < 5:
        return {"error": "Недостаточно данных разгона", "pairs": len(pairs)}
    mean_x = mean(x for x, _ in pairs)
    mean_y = mean(y for _, y in pairs)
    denominator = sum((x - mean_x) ** 2 for x, _ in pairs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / denominator if denominator else 0.0
    equivalent = max(0.0, slope - mass)
    return {
        "massKg": round(mass, 2),
        "totalInertialMassKg": round(slope, 2),
        "equivalentMassKg": round(equivalent, 2),
        "samples": len(pairs),
        "suggested": {"compensation.equivalentMassKg": round(equivalent, 2)},
    }


def measure_backlash(ctx: ProcedureContext) -> Procedure:
    """Reverse direction at constant commanded speed; lost travel is the backlash."""

    start = ctx.controller.state.position_mm
    ctx.controller.request_move(start + 40, profile="calibration", then=ControlMode.paused, label="Люфт: подъём")
    yield from ctx.wait_until(lambda: ctx.controller.state.mode != ControlMode.moving, 20.0, "Подъём")
    top = ctx.controller.state.position_mm
    ctx.controller.request_move(start, profile="calibration", then=ControlMode.paused, label="Люфт: реверс")
    speed = float(ctx.params.get("profile.calibration.speedMmPerSec"))
    commanded = 0.0
    while ctx.controller.state.mode == ControlMode.moving:
        telemetry = ctx.telemetry
        if telemetry is not None and abs(telemetry.bar_velocity_mm_s) > speed * 0.5:
            commanded += abs(telemetry.bar_velocity_mm_s) * ctx.tick
        yield "Реверс"
    actual = abs(top - ctx.controller.state.position_mm)
    backlash = max(0.0, min(5.0, commanded - actual)) if commanded else 0.0
    return {"commandedTravelMm": round(commanded, 2), "actualTravelMm": round(actual, 2), "backlashMm": round(backlash, 2), "suggested": {"compensation.backlashMm": round(backlash, 2)}}


def measure_kg_factor(ctx: ProcedureContext, reference_kg: float = 10.0) -> Procedure:
    """Hang a reference weight (emulator: virtual hand pulls down); compare with force delta."""

    mass_samples = yield from _steady_mass(ctx)
    mass = mean(mass_samples)
    if ctx.emulator is not None:
        ctx.emulator.set_user_force(-reference_kg)
    yield from ctx.wait(1.0, "Стабилизация с эталонным грузом")
    samples = yield from ctx.samples(1.5, "Измерение с эталонным грузом")
    loaded = mean(item.total_force_kg for item in samples if item is not None)
    if ctx.emulator is not None:
        ctx.emulator.set_user_force(0.0)
    delta = loaded - mass
    factor = reference_kg / delta if delta > 0.5 else None
    current = float(ctx.params.get("load.kgToTorqueFactor"))
    return {
        "referenceKg": reference_kg,
        "measuredDeltaKg": round(delta, 2),
        "factor": round(factor, 4) if factor else None,
        "suggested": {"load.kgToTorqueFactor": round(current * factor, 4)} if factor else {},
    }


def _steady_mass(ctx: ProcedureContext) -> Generator[str, None, list[float]]:
    ctx.controller.request_hold("Измерение", "Стабилизация удержания.")
    yield from ctx.wait(0.8, "Стабилизация")
    samples = yield from ctx.samples(1.0, "Измерение массы в покое")
    return [item.total_force_kg for item in samples if item is not None]


# -------------------------------------------------------------------- scenarios
def scenario_weightless_drift(ctx: ProcedureContext) -> Procedure:
    start = ctx.controller.state.position_mm
    ctx.controller.request_weightless()
    samples = yield from ctx.samples(5.0, "Невесомый гриф: контроль дрейфа")
    positions = [item.bar_position_mm for item in samples if item is not None]
    drift = positions[-1] - start if positions else 0.0
    max_speed = max((abs(item.bar_velocity_mm_s) for item in samples if item is not None), default=0.0)
    ctx.controller.request_hold("Тест завершён", "Дрейф измерен, гриф удерживается.")
    return {"driftMm": round(drift, 2), "maxDriftSpeedMmPerSec": round(max_speed, 2), "passed": abs(drift) < 10}


def scenario_hold_load(ctx: ProcedureContext, load_kg: float = 20.0) -> Procedure:
    start = ctx.controller.state.position_mm
    config = TrainingConfig(lower_mm=start - 200, upper_mm=start + 200, start_point="custom", start_custom_mm=start, load_kg=load_kg, target_reps=99)
    if ctx.emulator is not None:
        ctx.emulator.set_scenario("hold_still", strength_kg=load_kg * 3, lower_mm=start - 200, upper_mm=start + 200)
    ctx.controller.request_training(config)
    samples = yield from ctx.samples(4.0, f"Удержание {load_kg:.0f} кг")
    drift = max((abs(item.bar_position_mm - start) for item in samples if item is not None), default=0.0)
    loads = [ctx.controller.state.load_effective_kg]
    if ctx.emulator is not None:
        ctx.emulator.set_scenario("none")
    ctx.controller.complete_set()
    return {"loadKg": load_kg, "maxDriftMm": round(drift, 2), "effectiveLoadKg": round(loads[-1], 2), "passed": drift < 40}


def scenario_accel_reverse(ctx: ProcedureContext) -> Procedure:
    start = ctx.controller.state.position_mm
    peak_accel = 0.0
    peak_force = 0.0
    previous = 0.0
    for target in (start + 150, start, start + 150, start):
        ctx.controller.request_move(target, profile="training", then=ControlMode.paused, label="Разгон/реверс")
        while ctx.controller.state.mode == ControlMode.moving:
            telemetry = ctx.telemetry
            if telemetry is not None:
                accel = (telemetry.bar_velocity_mm_s - previous) / ctx.tick
                previous = telemetry.bar_velocity_mm_s
                peak_accel = max(peak_accel, abs(accel))
                peak_force = max(peak_force, abs(telemetry.total_force_kg))
            yield "Разгон и реверс без нагрузки"
    return {"peakAccelMmPerSec2": round(peak_accel, 0), "peakDriveForceKg": round(peak_force, 2), "maxSyncDeltaMm": round(ctx.controller.state.sync_delta_mm, 2)}


def scenario_sync_sweep(ctx: ProcedureContext) -> Procedure:
    start = ctx.controller.state.position_mm
    worst = 0.0
    for target in (start + 200, start - 100, start):
        ctx.controller.request_move(target, profile="return", then=ControlMode.paused, label="Синхронный ход")
        while ctx.controller.state.mode == ControlMode.moving:
            worst = max(worst, ctx.controller.state.sync_delta_mm)
            yield "Синхронный ход вверх-вниз"
    return {"maxSyncDeltaMm": round(worst, 2), "status": ctx.controller.state.sync_status, "passed": worst < float(ctx.params.get("sync.warningMm"))}


def scenario_failure(ctx: ProcedureContext, load_kg: float = 40.0) -> Procedure:
    if ctx.emulator is None:
        return {"error": "Сценарий доступен только на эмуляторе"}
    start = ctx.controller.state.position_mm
    lower, upper = start - 150, start + 150
    config = TrainingConfig(lower_mm=lower, upper_mm=upper, start_point="lower", load_kg=load_kg, target_reps=10)
    ctx.emulator.set_scenario("failure", strength_kg=load_kg + 15, lower_mm=lower, upper_mm=upper, period_s=2.5, fail_after_reps=2)
    ctx.controller.request_training(config)
    spotter_at = None
    for _ in range(int(14 / ctx.tick)):
        if ctx.controller.state.spotter_active and spotter_at is None:
            spotter_at = round(ctx.controller.state.time - ctx.controller.state.mode_since, 2)
        if ctx.controller.state.mode != ControlMode.training:
            break
        yield "Имитация отказа"
    ctx.emulator.set_scenario("none")
    reps = ctx.controller.state.repetition_count
    ctx.controller.complete_set()
    return {"repsBeforeFailure": reps, "spotterTriggeredAfterS": spotter_at, "finalMode": ctx.controller.state.mode.value, "passed": spotter_at is not None}


def scenario_jerk(ctx: ProcedureContext, load_kg: float = 30.0) -> Procedure:
    if ctx.emulator is None:
        return {"error": "Сценарий доступен только на эмуляторе"}
    start = ctx.controller.state.position_mm
    lower, upper = start - 150, start + 150
    config = TrainingConfig(lower_mm=lower, upper_mm=upper, load_kg=load_kg, target_reps=4)
    ctx.emulator.set_scenario("jerk", strength_kg=load_kg + 30, lower_mm=lower, upper_mm=upper, period_s=2.5, jerk_kg=45)
    ctx.controller.request_training(config)
    peak_speed = 0.0
    for _ in range(int(10 / ctx.tick)):
        peak_speed = max(peak_speed, abs(ctx.controller.state.velocity_mm_s))
        if ctx.controller.state.target_reached:
            break
        yield "Имитация рывка"
    ctx.emulator.set_scenario("none")
    ctx.controller.complete_set()
    return {"peakSpeedMmPerSec": round(peak_speed, 0), "reps": ctx.controller.state.repetition_count, "maxSyncDeltaMm": ctx.controller.state.sync_delta_mm}


def scenario_torque_step(ctx: ProcedureContext, step_kg: float = 5.0) -> Procedure:
    start = ctx.controller.state.position_mm
    ctx.controller.request_weightless()
    yield from ctx.wait(1.0, "Стабилизация невесомого грифа")
    if ctx.emulator is not None:
        ctx.emulator.set_user_force(step_kg)
    samples = yield from ctx.samples(1.5, "Шаг усилия")
    if ctx.emulator is not None:
        ctx.emulator.set_user_force(0.0)
    response_time = None
    for index, item in enumerate(samples):
        if item is not None and abs(item.bar_position_mm - start) > 5:
            response_time = round(index * ctx.tick, 3)
            break
    ctx.controller.request_hold("Тест завершён", "Отклик измерен.")
    return {"stepKg": step_kg, "responseTimeS": response_time, "travelMm": round(ctx.controller.state.position_mm - start, 2)}


MEASUREMENTS = {
    "bar_mass": measure_bar_mass,
    "friction": measure_friction,
    "inertia": measure_inertia,
    "backlash": measure_backlash,
    "kg_factor": measure_kg_factor,
}

SCENARIOS = {
    "weightless_drift": scenario_weightless_drift,
    "hold_load": scenario_hold_load,
    "accel_reverse": scenario_accel_reverse,
    "sync_sweep": scenario_sync_sweep,
    "failure": scenario_failure,
    "jerk": scenario_jerk,
    "torque_step": scenario_torque_step,
}

PROCEDURE_LABELS = {
    "bar_mass": "Масса грифа и подвижных частей",
    "friction": "Трение вверх/вниз",
    "inertia": "Приведённая инерция ШВП",
    "backlash": "Люфт",
    "kg_factor": "Коэффициент кг → момент (эталонный груз)",
    "weightless_drift": "Невесомый гриф: дрейф",
    "hold_load": "Удержание N кг",
    "accel_reverse": "Разгон / реверс без нагрузки",
    "sync_sweep": "Синхронный ход вверх-вниз",
    "failure": "Имитация отказа (эмулятор)",
    "jerk": "Имитация рывка (эмулятор)",
    "torque_step": "Шаг усилия — отклик регулятора",
}
