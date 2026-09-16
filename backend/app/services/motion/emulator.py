"""Physics-based emulator of two synchronised ball-screw drives carrying a bar.

The emulator is the "reality" the controller is tuned against, therefore it has
its own physical constants (true bar mass, friction, inertia) that are
independent from the controller parameters.  It also hosts the *virtual hand*
(user force) and fault injection used by tests and the tuning page.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.motion.adapter import (
    SIDES,
    AdapterTelemetry,
    DriveCommand,
    SelfTestResult,
    Side,
    SideCommand,
    SideTelemetry,
)

G_MM_S2 = 9810.0
KT_KG_PER_A = 5.0  # kg-equivalent of force per ampere (per side)
SUBSTEP_SECONDS = 0.001

ScenarioName = Literal["none", "steady_set", "failure", "jerk", "release", "tilt", "hold_still"]


@dataclass
class EmulatorPhysics:
    bar_mass_kg: float = 20.0
    moving_parts_kg: float = 6.0
    friction_kg: float = 1.4
    equivalent_mass_kg: float = 4.0
    backlash_mm: float = 0.3
    coupling_kg_per_mm: float = 6.0  # bar stiffness between sides
    coupling_damping: float = 0.15
    working_min_mm: float = 0.0
    working_max_mm: float = 1850.0
    # drive internal loops (velocity/position modes are executed by the drive)
    drive_kp_kg_per_mm: float = 3.0
    drive_kd: float = 0.12
    drive_kv: float = 0.2

    @property
    def total_mass_kg(self) -> float:
        return self.bar_mass_kg + self.moving_parts_kg


@dataclass
class UserScenario:
    name: ScenarioName = "none"
    strength_kg: float = 60.0  # maximum force the virtual user can apply
    period_s: float = 3.0  # duration of a full repetition
    lower_mm: float = 640.0
    upper_mm: float = 1320.0
    fail_after_reps: int = 3
    tilt_bias: float = 0.0  # -1 all force on left … +1 all on right
    jerk_kg: float = 40.0
    release_after_s: float = 2.0
    started_at: float = 0.0
    reps_done: int = 0
    manual_force_kg: float = 0.0
    manual_bias: float = 0.0
    phase_offset: float = 0.0


@dataclass
class SideState:
    side: Side
    position_mm: float
    velocity_mm_s: float = 0.0
    force_kg: float = 0.0
    current_a: float = 0.0
    temperature_c: float = 31.0
    brake_engaged: bool = True
    enabled: bool = True
    connected: bool = True
    homed: bool = True
    encoder_offset_mm: float = 0.0
    encoder_drift_mm_s: float = 0.0
    comm_lost: bool = False
    overheat: bool = False
    error_code: str | None = None
    error_message: str | None = None
    last_direction: int = 0
    backlash_slack_mm: float = 0.0


@dataclass
class EmulatorFaults:
    power_loss: bool = False
    physical_estop: bool = False
    comm_lost: set[str] = field(default_factory=set)
    encoder_drift: dict[str, float] = field(default_factory=dict)
    overheat: set[str] = field(default_factory=set)


class PhysicsEmulatorAdapter:
    name = "physics-emulator"

    def __init__(self, physics: EmulatorPhysics | None = None, *, initial_position_mm: float = 860.0) -> None:
        self.physics = physics or EmulatorPhysics()
        self.scenario = UserScenario()
        self.faults = EmulatorFaults()
        self.heartbeat_timeout_s = 0.5
        self._time = 0.0
        self._last_heartbeat = 0.0
        self._estop_latched = False
        self._sides: dict[Side, SideState] = {
            "left": SideState("left", initial_position_mm, brake_engaged=True),
            "right": SideState("right", initial_position_mm + 0.4, brake_engaged=True),
        }
        self._last_command = DriveCommand()
        self._power_ok = True
        self.events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ config
    def reset(self, *, position_mm: float = 860.0) -> None:
        self.__init__(self.physics, initial_position_mm=position_mm)  # type: ignore[misc]

    def set_physics(self, **values: float) -> None:
        for key, value in values.items():
            if hasattr(self.physics, key):
                setattr(self.physics, key, float(value))

    def set_user_force(self, force_kg: float, bias: float = 0.0) -> None:
        self.scenario.manual_force_kg = float(force_kg)
        self.scenario.manual_bias = max(-1.0, min(1.0, float(bias)))

    def set_scenario(self, name: ScenarioName, **kwargs: Any) -> None:
        scenario = UserScenario(name=name, started_at=self._time)
        for key, value in kwargs.items():
            if hasattr(scenario, key) and value is not None:
                setattr(scenario, key, value)
        scenario.manual_force_kg = self.scenario.manual_force_kg if name == "none" else 0.0
        bar = (self._sides["left"].position_mm + self._sides["right"].position_mm) / 2
        mid = (scenario.lower_mm + scenario.upper_mm) / 2
        amp = max(1.0, (scenario.upper_mm - scenario.lower_mm) / 2)
        scenario.phase_offset = math.acos(max(-1.0, min(1.0, (mid - bar) / amp)))
        self.scenario = scenario

    def inject_fault(self, fault: str, side: Side | None = None, value: float | None = None) -> None:
        if fault == "power_loss":
            self.faults.power_loss = True
            self._power_ok = False
            for state in self._sides.values():
                state.brake_engaged = True
                state.velocity_mm_s = 0.0
                state.connected = False
                state.enabled = False
                state.homed = False
            self._log("fault", "Пропадание питания: тормоза сработали, позиция потеряна")
        elif fault == "power_restore":
            self.faults.power_loss = False
            self._power_ok = True
            for state in self._sides.values():
                state.connected = True
                state.enabled = True
                state.brake_engaged = True
            self._log("fault", "Питание восстановлено, требуется homing")
        elif fault == "comm_lost" and side:
            self.faults.comm_lost.add(side)
            self._sides[side].comm_lost = True
            self._log("fault", f"Потеря связи: {side}")
        elif fault == "encoder_drift" and side:
            self.faults.encoder_drift[side] = float(value if value is not None else 2.0)
            self._sides[side].encoder_drift_mm_s = self.faults.encoder_drift[side]
            self._log("fault", f"Дрейф энкодера {side}: {self.faults.encoder_drift[side]} мм/с")
        elif fault == "overheat" and side:
            self.faults.overheat.add(side)
            self._sides[side].overheat = True
            self._log("fault", f"Перегрев {side}")
        elif fault == "physical_estop":
            self.faults.physical_estop = True
            self.emergency_stop()
            self._log("fault", "Нажата физическая кнопка СТОП")
        elif fault == "physical_estop_release":
            self.faults.physical_estop = False
        else:
            raise ValueError(f"Неизвестный сбой: {fault}")

    def clear_faults(self) -> None:
        self.faults = EmulatorFaults()
        self._power_ok = True
        for state in self._sides.values():
            state.comm_lost = False
            state.encoder_drift_mm_s = 0.0
            state.overheat = False
            state.connected = True
            state.enabled = True
            state.error_code = None
            state.error_message = None

    # --------------------------------------------------------------- adapter
    def emergency_stop(self) -> None:
        self._estop_latched = True
        for state in self._sides.values():
            state.brake_engaged = True
            state.velocity_mm_s = 0.0

    def release_emergency_stop(self) -> None:
        if self.faults.physical_estop:
            return
        self._estop_latched = False

    def set_brake(self, engaged: bool) -> None:
        for state in self._sides.values():
            state.brake_engaged = engaged
            if engaged:
                state.velocity_mm_s = 0.0

    def home(self) -> None:
        for state in self._sides.values():
            state.encoder_offset_mm = 0.0
            state.homed = True
        self._log("home", "Нулевая позиция установлена")

    def reset_errors(self) -> None:
        for state in self._sides.values():
            state.error_code = None
            state.error_message = None

    def self_test(self) -> list[SelfTestResult]:
        results: list[SelfTestResult] = []
        results.append(SelfTestResult("power", "Питание приводов", self._power_ok, "Питание в норме" if self._power_ok else "Нет питания приводов"))
        for side in SIDES:
            state = self._sides[side]
            ok = state.connected and not state.comm_lost
            results.append(SelfTestResult(f"comm-{side}", f"Связь: {side}", ok, "Ответ получен" if ok else "Нет ответа от драйвера", "critical"))
            results.append(SelfTestResult(f"brake-{side}", f"Тормоз: {side}", ok, "Тормоз отвечает" if ok else "Тормоз не проверен"))
            temp_ok = state.temperature_c < 75
            results.append(SelfTestResult(f"temp-{side}", f"Температура: {side}", temp_ok, f"{state.temperature_c:.1f} °C", "warning"))
        firmware_same = True
        results.append(SelfTestResult("firmware", "Версии прошивок совпадают", firmware_same, "emu-1.0 / emu-1.0", "warning"))
        results.append(SelfTestResult("estop", "Физический СТОП не нажат", not self.faults.physical_estop, "Кнопка отпущена" if not self.faults.physical_estop else "Кнопка СТОП нажата"))
        low_switch = any(self._true_position(side) <= self.physics.working_min_mm + 2 for side in SIDES)
        results.append(SelfTestResult("limits", "Концевики", True, "Нижний концевик активен" if low_switch else "Концевики свободны", "info"))
        return results

    def read(self) -> AdapterTelemetry:
        return self._telemetry()

    def step(self, command: DriveCommand, dt: float) -> AdapterTelemetry:
        self._time += dt
        if command.heartbeat:
            self._last_heartbeat = self._time
        heartbeat_ok = (self._time - self._last_heartbeat) <= self.heartbeat_timeout_s
        self._last_command = command

        user_total = self._user_force(dt)
        bias = self.scenario.manual_bias if self.scenario.name == "none" else self.scenario.tilt_bias
        user_forces = {"left": user_total * (1 - bias) / 2, "right": user_total * (1 + bias) / 2}

        substeps = max(1, int(round(dt / SUBSTEP_SECONDS)))
        sub_dt = dt / substeps
        for _ in range(substeps):
            self._integrate(command, user_forces, heartbeat_ok, sub_dt)

        for side in SIDES:
            state = self._sides[side]
            locked = state.brake_engaged
            state.current_a = abs(state.force_kg) / KT_KG_PER_A if not locked else abs(state.force_kg) / (KT_KG_PER_A * 4)
            heating = state.current_a**2 * 0.03
            cooling = (state.temperature_c - 28.0) * 0.02
            state.temperature_c += (heating - cooling) * dt
            if state.overheat:
                state.temperature_c = max(state.temperature_c, 85.0)
            state.encoder_offset_mm += state.encoder_drift_mm_s * dt

        return self._telemetry(heartbeat_ok=heartbeat_ok)

    def _integrate(self, command: DriveCommand, user_forces: dict[str, float], heartbeat_ok: bool, dt: float) -> None:
        half_mass = self.physics.total_mass_kg / 2
        half_inertia = self.physics.equivalent_mass_kg / 2
        # evaluate coupling with positions from the start of the substep for symmetry
        positions = {side: self._sides[side].position_mm for side in SIDES}
        velocities = {side: self._sides[side].velocity_mm_s for side in SIDES}
        for side in SIDES:
            state = self._sides[side]
            other_side = "right" if side == "left" else "left"
            side_command = command.side(side)
            forced_lock = (
                self._estop_latched
                or not self._power_ok
                or not heartbeat_ok
                or state.comm_lost
                or not state.enabled
            )
            state.brake_engaged = side_command.mode == "brake" or forced_lock
            locked = state.brake_engaged

            drive_force = 0.0 if locked else self._resolve_drive_force(state, side_command)
            coupling = self.physics.coupling_kg_per_mm * (positions[other_side] - positions[side]) + self.physics.coupling_damping * (velocities[other_side] - velocities[side])
            gravity = half_mass
            net_no_friction = drive_force + user_forces[side] + coupling - gravity

            if locked:
                state.velocity_mm_s = 0.0
                state.force_kg = max(0.0, gravity - user_forces[side] - coupling)  # brake carries the load
            else:
                friction = self.physics.friction_kg / 2
                if abs(state.velocity_mm_s) < 0.5 and abs(net_no_friction) <= friction:
                    net = 0.0
                    state.velocity_mm_s = 0.0
                else:
                    direction = math.copysign(1.0, state.velocity_mm_s if abs(state.velocity_mm_s) >= 0.5 else net_no_friction)
                    net = net_no_friction - friction * direction
                accel = net * G_MM_S2 / (half_mass + half_inertia)
                state.velocity_mm_s += accel * dt
                new_direction = 0 if abs(state.velocity_mm_s) < 0.5 else (1 if state.velocity_mm_s > 0 else -1)
                if new_direction != 0 and state.last_direction != 0 and new_direction != state.last_direction:
                    state.backlash_slack_mm = self.physics.backlash_mm
                if new_direction != 0:
                    state.last_direction = new_direction
                travel = state.velocity_mm_s * dt
                if state.backlash_slack_mm > 0:
                    absorbed = min(abs(travel), state.backlash_slack_mm)
                    state.backlash_slack_mm -= absorbed
                    travel -= math.copysign(absorbed, travel)
                state.position_mm += travel
                state.force_kg = drive_force

            if state.position_mm <= self.physics.working_min_mm:
                state.position_mm = self.physics.working_min_mm
                state.velocity_mm_s = max(0.0, state.velocity_mm_s)
            if state.position_mm >= self.physics.working_max_mm:
                state.position_mm = self.physics.working_max_mm
                state.velocity_mm_s = min(0.0, state.velocity_mm_s)

    # --------------------------------------------------------------- helpers
    def _resolve_drive_force(self, state: SideState, cmd: SideCommand) -> float:
        limit = abs(cmd.force_limit_kg)
        if cmd.mode == "disabled":
            return 0.0
        if cmd.mode == "torque":
            return max(-limit, min(limit, cmd.force_kg))
        if cmd.mode == "velocity":
            force = cmd.feedforward_kg + self.physics.drive_kv * (cmd.target_velocity_mm_s - state.velocity_mm_s) * (self.physics.total_mass_kg / 2)
            return max(-limit, min(limit, force))
        if cmd.mode == "position":
            target = cmd.target_position_mm if cmd.target_position_mm is not None else state.position_mm
            force = cmd.feedforward_kg + self.physics.drive_kp_kg_per_mm * (target - state.position_mm) - self.physics.drive_kd * state.velocity_mm_s
            return max(-limit, min(limit, force))
        return 0.0

    def _user_force(self, dt: float) -> float:
        scenario = self.scenario
        if scenario.name == "none":
            return scenario.manual_force_kg
        elapsed = self._time - scenario.started_at
        bar = (self._sides["left"].position_mm + self._sides["right"].position_mm) / 2
        velocity = (self._sides["left"].velocity_mm_s + self._sides["right"].velocity_mm_s) / 2
        # the virtual user follows a sinusoidal target between bounds
        theta = 2 * math.pi * (elapsed / scenario.period_s) + scenario.phase_offset
        mid = (scenario.lower_mm + scenario.upper_mm) / 2
        amp = (scenario.upper_mm - scenario.lower_mm) / 2
        target = mid - amp * math.cos(theta)
        target_velocity = amp * 2 * math.pi / scenario.period_s * math.sin(theta)
        reps = int((elapsed + scenario.phase_offset / (2 * math.pi) * scenario.period_s) // scenario.period_s)
        scenario.reps_done = reps
        holding = self._held_load_kg()
        strength = scenario.strength_kg
        if scenario.name == "failure" and reps >= scenario.fail_after_reps:
            strength *= 0.35
        if scenario.name == "release" and elapsed >= scenario.release_after_s:
            return 0.0
        if scenario.name == "hold_still":
            target = mid
            target_velocity = 0.0
        force = holding + 0.15 * (target - bar) + 0.05 * (target_velocity - velocity)
        if scenario.name == "jerk" and 0.3 <= (elapsed % scenario.period_s) <= 0.45:
            force += scenario.jerk_kg
        return max(-strength, min(strength, force))

    def _held_load_kg(self) -> float:
        """Estimate the load the user has to overcome (drive resistance minus gravity)."""

        total_drive = sum(self._sides[side].force_kg for side in SIDES)
        return max(0.0, self.physics.total_mass_kg - total_drive)

    def _true_position(self, side: Side) -> float:
        return self._sides[side].position_mm

    def _telemetry(self, heartbeat_ok: bool = True) -> AdapterTelemetry:
        sides: dict[Side, SideTelemetry] = {}
        for side in SIDES:
            state = self._sides[side]
            reported_position = state.position_mm + state.encoder_offset_mm
            connected = state.connected and not state.comm_lost
            error_code = state.error_code
            error_message = state.error_message
            if not connected:
                error_code = "E-COMM-02"
                error_message = "нет ответа от драйвера"
            elif state.overheat or state.temperature_c >= 85:
                error_code = "E-TEMP-01"
                error_message = "перегрев привода"
            sides[side] = SideTelemetry(
                side=side,
                connected=connected,
                enabled=state.enabled and not self._estop_latched,
                brake_engaged=state.brake_engaged,
                homed=state.homed,
                position_mm=round(reported_position, 3) if connected else round(reported_position, 3),
                velocity_mm_s=round(state.velocity_mm_s, 3),
                force_kg=round(state.force_kg, 3),
                current_a=round(state.current_a, 3),
                temperature_c=round(state.temperature_c, 2),
                torque_limit_percent=int(min(100, max(0, round(abs(self._last_command.side(side).force_limit_kg) / 2)))),
                error_code=error_code,
                error_message=error_message,
                limit_switch_low=state.position_mm <= self.physics.working_min_mm + 2,
                limit_switch_high=state.position_mm >= self.physics.working_max_mm - 2,
                latency_ms=12.0 if side == "left" else 13.0,
            )
        return AdapterTelemetry(
            timestamp=self._time,
            left=sides["left"],
            right=sides["right"],
            power_ok=self._power_ok,
            heartbeat_ok=heartbeat_ok,
            physical_estop=self.faults.physical_estop,
        )

    def _log(self, kind: str, message: str) -> None:
        self.events.append({"time": self._time, "kind": kind, "message": message, "wall": time.time()})
        if len(self.events) > 200:
            del self.events[: len(self.events) - 200]
