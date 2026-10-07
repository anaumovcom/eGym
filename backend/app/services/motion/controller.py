"""Motion controller: turns telemetry + parameters + intent into drive commands.

Runs every control tick (10–20 ms) on top of a :class:`DriveAdapter`.  Every
rule from the mechanics backlog that can be expressed in software lives here:
compensations, load modes, synchronisation, rep detection, spotter, limits,
start/park/fixed-position logic and safety reactions.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from app.services.motion.adapter import SIDES, AdapterTelemetry, DriveCommand, SelfTestResult, Side, SideCommand
from app.services.motion.parameters import MotionParameters

G_MM_S2 = 9810.0

LoadMode = Literal[
    "normal_weight",
    "assist_up",
    "negative_phase",
    "light_mode",
    "isokinetic",
    "bodyweight",
    "no_machine",
    "fixed_position",
    "isometric",
]
StartPoint = Literal["lower", "upper", "custom"]
RepCountSource = Literal["motion", "load", "manual", "timer"]


class ControlMode(StrEnum):
    idle = "idle"
    post = "post"
    homing = "homing"
    moving = "moving"
    weightless = "weightless"
    start_hold = "start_hold"
    training = "training"
    fixed_hold = "fixed_hold"
    isometric = "isometric"
    paused = "paused"
    parked = "parked"
    estop = "estop"
    fault = "fault"


class HomingPhase(StrEnum):
    idle = "idle"
    bottom_coarse = "bottom_coarse"
    bottom_creep = "bottom_creep"
    bottom_stop = "bottom_stop"
    bottom_backoff = "bottom_backoff"
    bottom_fine = "bottom_fine"
    bottom_fine_creep = "bottom_fine_creep"
    bottom_reference = "bottom_reference"
    top_coarse = "top_coarse"
    top_creep = "top_creep"
    top_stop = "top_stop"
    top_backoff = "top_backoff"
    top_fine = "top_fine"
    top_fine_creep = "top_fine_creep"
    move_safe_top = "move_safe_top"
    complete = "complete"
    fault = "fault"


@dataclass
class TrainingConfig:
    lower_mm: float = 640.0
    upper_mm: float = 1320.0
    start_point: StartPoint = "lower"
    start_custom_mm: float | None = None
    load_kg: float = 20.0
    load_mode: LoadMode = "normal_weight"
    target_reps: int = 10
    target_set: int = 1
    warmup: bool = False
    guest: bool = False
    asymmetric_allowed: bool = False
    rep_count_source: RepCountSource = "motion"
    fixed_position_mm: float | None = None
    isometric_position_mm: float | None = None
    isometric_duration_s: float = 20.0
    motion_profile: str = "training"
    calibration_id: int | None = None

    @property
    def start_mm(self) -> float:
        if self.start_point == "upper":
            return self.upper_mm
        if self.start_point == "custom" and self.start_custom_mm is not None:
            return self.start_custom_mm
        return self.lower_mm

    @property
    def far_mm(self) -> float:
        return self.lower_mm if self.start_point == "upper" else self.upper_mm

    @property
    def range_mm(self) -> float:
        return max(1.0, self.upper_mm - self.lower_mm)


@dataclass
class MoveRequest:
    target_mm: float
    profile: str
    then: ControlMode
    label: str
    obstacle_check: bool = True


@dataclass
class ControllerEvent:
    time: float
    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {"time": round(self.time, 3), "kind": self.kind, "message": self.message, **self.payload}


@dataclass
class ControllerState:
    mode: ControlMode = ControlMode.post
    mode_since: float = 0.0
    label: str = "Самотест"
    message: str = ""
    time: float = 0.0
    # kinematics
    position_mm: float = 860.0
    velocity_mm_s: float = 0.0
    acceleration_mm_s2: float = 0.0
    direction: str = "up"
    moving: bool = False
    amplitude_percent: int = 0
    # user / load
    user_force_kg: float = 0.0
    user_force_left_kg: float = 0.0
    user_force_right_kg: float = 0.0
    drive_force_kg: float = 0.0  # total force produced by both motors (kg-equivalent)
    drive_torque_percent: float = 0.0  # total motor torque, % of rated (sum of both drives)
    load_target_kg: float = 0.0
    load_effective_kg: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    # reps
    repetition_count: int = 0
    partial_reps: int = 0
    concentric_s: float = 0.0
    eccentric_s: float = 0.0
    tempo_label: str = "—"
    target_reached: bool = False
    rep_quality: float = 0.0
    # sync
    sync_delta_mm: float = 0.0
    sync_status: str = "norm"
    asymmetry_percent: float = 0.0
    # detection
    grip_detected: bool = False
    released: bool = False
    stall_s: float = 0.0
    spotter_active: bool = False
    levitating: bool = False
    failure_detected: bool = False
    still_ms: float = 0.0
    # readiness
    post_status: str = "pending"
    post_results: list[dict[str, Any]] = field(default_factory=list)
    homed: bool = False
    position_known: bool = False
    heartbeat_ok: bool = True
    comm_ok: bool = True
    power_ok: bool = True
    brake_engaged: bool = True
    fixed_hold_test_passed: bool = False
    fixed_drift_mm: float = 0.0
    isometric_elapsed_s: float = 0.0
    move_target_mm: float | None = None
    move_progress_percent: int = 0
    alerts: list[str] = field(default_factory=list)
    fault_code: str | None = None
    tick_latency_ms: float = 0.0
    missed_ticks: int = 0
    idle_s: float = 0.0
    homing_phase: str = HomingPhase.idle.value
    physical_bottom_mm: float | None = None
    physical_top_mm: float | None = None
    working_bottom_mm: float | None = None
    working_top_mm: float | None = None
    full_travel_mm: float | None = None
    # counters
    travel_mm_total: float = 0.0
    cycles_total: int = 0
    loaded_seconds_total: float = 0.0


class MotionController:
    def __init__(self, parameters: MotionParameters, *, limit_switches_enabled: bool = True) -> None:
        self.params = parameters
        self.limit_switches_enabled = limit_switches_enabled
        self.state = ControllerState()
        self.config = TrainingConfig()
        self.events: deque[ControllerEvent] = deque(maxlen=400)
        self._move: MoveRequest | None = None
        self._prev_velocity = 0.0
        self._filtered_force = 0.0
        self._filtered_force_left = 0.0
        self._filtered_force_right = 0.0
        self._filtered_velocity = 0.0
        self._load_ramp_kg = 0.0
        self._rep_armed = False
        self._excursion_min = 0.0
        self._excursion_max = 0.0
        self._phase_started = 0.0
        self._last_direction_sign = 0
        self._release_s = 0.0
        self._obstacle_s = 0.0
        self._hold_position_mm: float | None = None
        self._isokinetic_load = 0.0
        self._levitation_factor = 1.0
        self._prev_torque: dict[Side, float] = {"left": 0.0, "right": 0.0}
        self._prev_mode: dict[Side, str] = {"left": "brake", "right": "brake"}
        self._load_peak_state = 0
        self._rep_started_at = 0.0
        self._estop_requested = False
        self._pending_self_test: list[SelfTestResult] | None = None
        self._homing_phase = HomingPhase.idle
        self._homing_started_at = 0.0
        self._homing_phase_started_at = 0.0
        self._homing_phase_start_mm = 0.0
        self._homing_first_edge_at: float | None = None
        self._homing_first_edge_mm: float | None = None
        self._homing_reference_pending = False
        self._homing_initial_validation_pending = False
        self._reference_verified = False
        self._last_alert_time = 0.0
        self._loaded_active = False
        self._move_start_mm = 0.0
        self._drift_s = 0.0
        self._jog_direction: str | None = None
        self._last_sync_correction: dict[Side, float] = {"left": 0.0, "right": 0.0}

    # ------------------------------------------------------------------ intents
    def set_jog(self, direction: str | None) -> None:
        """Hold-to-jog in weightless mode: a fixed torque offset relative to the weightless reference."""

        if direction not in {None, "up", "down"}:
            raise ValueError("direction must be 'up', 'down' or None")
        self._jog_direction = direction

    @property
    def jog_direction(self) -> str | None:
        return self._jog_direction

    def _jog_offset_kg(self) -> float:
        """Per-side force offset (kg-equivalent) of the held Up / Down button; 0 at the soft limits."""

        direction = self._jog_direction
        if direction is None:
            return 0.0
        margin = 1.5
        position = self.state.position_mm
        per_kg = max(float(self.params.get("torque.perKgRaw")), 1e-6)
        if direction == "up":
            if position >= float(self.params.get("limits.softMaxMm")) - margin:
                return 0.0
            return float(self.params.get("torque.jogUpRaw")) / per_kg
        if position <= float(self.params.get("limits.softMinMm")) + margin:
            return 0.0
        return -float(self.params.get("torque.jogDownRaw")) / per_kg

    def request_post(self, results: list[SelfTestResult]) -> None:
        self._pending_self_test = results
        self._enter(ControlMode.post, "Самотест", "Проверка связи, тормозов, концевиков и температуры.")

    def request_homing(self) -> None:
        self._homing_started_at = self.state.time
        self._homing_reference_pending = False
        self._reference_verified = False
        self._homing_initial_validation_pending = self.limit_switches_enabled
        self.state.homed = False
        self.state.position_known = False
        self.state.physical_bottom_mm = None
        self.state.physical_top_mm = None
        self.state.working_bottom_mm = None
        self.state.working_top_mm = None
        self.state.full_travel_mm = None
        if self.limit_switches_enabled:
            self._enter(ControlMode.homing, "Homing", "Поиск нулевой позиции на низкой скорости.")
            self._set_homing_phase(HomingPhase.bottom_coarse)
        else:
            self._enter(ControlMode.homing, "Homing", "Гриф должен находиться в крайнем нижнем положении; обнуление энкодеров без перемещения.")
            self._set_homing_phase(HomingPhase.bottom_reference)
            self._homing_reference_pending = True

    def request_move(self, target_mm: float, *, profile: str, then: ControlMode, label: str, obstacle_check: bool = True) -> None:
        target = self._clamp_soft(target_mm)
        self._move = MoveRequest(target, profile, then, label, obstacle_check)
        self.state.move_target_mm = target
        self._enter(ControlMode.moving, label, f"Перемещение к {target:.0f} мм, профиль {profile}.")

    def request_weightless(self) -> None:
        self.state.still_ms = 0.0
        self._enter(ControlMode.weightless, "Невесомый гриф", "Гриф скомпенсирован — переместите его рукой в нужную точку.")

    def request_start_hold(self, config: TrainingConfig) -> None:
        self.config = config
        self._reset_set_counters()
        self.state.grip_detected = False
        self._hold_position_mm = config.start_mm
        self._enter(ControlMode.start_hold, "Ожидание захвата", "Возьмитесь за гриф — движение начнётся автоматически.")

    def request_training(self, config: TrainingConfig) -> None:
        self.config = config
        self._reset_set_counters()
        self.state.grip_detected = True
        if config.load_mode == "fixed_position":
            self._hold_position_mm = config.fixed_position_mm if config.fixed_position_mm is not None else self.state.position_mm
            self.state.fixed_hold_test_passed = False
            self._enter(ControlMode.fixed_hold, "Фиксированная позиция", "Гриф жёстко удерживается на заданной высоте.")
            return
        if config.load_mode == "isometric":
            self._hold_position_mm = config.isometric_position_mm if config.isometric_position_mm is not None else self.state.position_mm
            self.state.isometric_elapsed_s = 0.0
            self._enter(ControlMode.isometric, "Изометрия", "Удерживайте гриф — нагрузка приложена.")
            return
        self._enter(ControlMode.training, "Движение выполняется", "Безопасный профиль движения активен.")

    def request_pause(self) -> None:
        self._hold_position_mm = self.state.position_mm
        self._enter(ControlMode.paused, "Пауза", "Гриф удерживается на месте.")

    def request_resume(self) -> None:
        if self.config.load_mode == "fixed_position":
            self._enter(ControlMode.fixed_hold, "Фиксированная позиция", "Удержание продолжается.")
        elif self.config.load_mode == "isometric":
            self._enter(ControlMode.isometric, "Изометрия", "Удержание продолжается.")
        else:
            self.state.spotter_active = False
            self.state.failure_detected = False
            self._enter(ControlMode.training, "Движение выполняется", "Продолжайте подход.")

    def request_hold(self, label: str = "Удержание", message: str = "Гриф удерживается на месте.") -> None:
        self._hold_position_mm = self.state.position_mm
        self._enter(ControlMode.paused, label, message)

    def request_park(self) -> None:
        park = float(self.params.get("start.parkPositionMm"))
        self.request_move(park, profile="return", then=ControlMode.parked, label="Парковка")

    def request_idle(self) -> None:
        self._enter(ControlMode.idle, "Тренажёр готов", "Приводы в удержании.")

    def skip_homing(self) -> None:
        """Without limit switches homing is not required: the bar position is taken as it is."""

        self._homing_phase = HomingPhase.complete
        self.state.homing_phase = HomingPhase.complete.value
        self.request_idle()

    def request_emergency_stop(self) -> None:
        self._estop_requested = True
        if self.state.mode == ControlMode.homing:
            self._homing_reference_pending = False
            self._homing_phase = HomingPhase.fault
            self.state.homing_phase = HomingPhase.fault.value
        self._enter(ControlMode.estop, "СТОП активирован", "Аварийная остановка активна. Любое движение заблокировано.")

    def clear_emergency_stop(self) -> None:
        self._estop_requested = False
        self._hold_position_mm = self.state.position_mm
        self._enter(ControlMode.paused, "СТОП снят", "Приводы в удержании. Проверьте синхронность и продолжайте.")

    def set_load(self, load_kg: float) -> None:
        self.config.load_kg = self._clamp_load(load_kg)
        self._emit("load_change", f"Нагрузка изменена: {self.config.load_kg:.1f} кг")

    def manual_rep(self) -> None:
        self.state.repetition_count += 1
        self._emit("rep", f"Повтор {self.state.repetition_count} (вручную)")
        self._check_target()

    def complete_set(self) -> None:
        self.state.cycles_total += 1
        self._hold_position_mm = self.state.position_mm
        self._enter(ControlMode.paused, "Подход завершён", "Нагрузка снята, гриф удерживается.")

    def mark_position_captured(self, which: str) -> float:
        self._emit("capture", f"Зафиксирована точка: {which} = {self.state.position_mm:.1f} мм", {"which": which, "positionMm": self.state.position_mm})
        return self.state.position_mm

    # -------------------------------------------------------------------- tick
    def tick(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        state.time += dt
        self._update_kinematics(telemetry, dt)
        self._update_safety(telemetry, dt)
        self._update_sync(telemetry)
        self._estimate_user_force(telemetry, dt)

        if self._estop_requested or telemetry.physical_estop:
            if state.mode != ControlMode.estop:
                self._enter(ControlMode.estop, "СТОП активирован", "Аварийная остановка активна.")
            return self._brake_command()

        if state.mode == ControlMode.fault:
            return self._brake_command()

        handler = {
            ControlMode.idle: self._tick_idle,
            ControlMode.post: self._tick_post,
            ControlMode.homing: self._tick_homing,
            ControlMode.moving: self._tick_moving,
            ControlMode.weightless: self._tick_weightless,
            ControlMode.start_hold: self._tick_start_hold,
            ControlMode.training: self._tick_training,
            ControlMode.fixed_hold: self._tick_fixed_hold,
            ControlMode.isometric: self._tick_isometric,
            ControlMode.paused: self._tick_paused,
            ControlMode.parked: self._tick_idle,
            ControlMode.estop: lambda _t, _d: self._brake_command(),
        }[state.mode]
        command = handler(telemetry, dt)
        self._apply_torque_rate_limit(command, dt)
        state.brake_engaged = command.left.mode == "brake" and command.right.mode == "brake"
        state.moving = abs(state.velocity_mm_s) > float(self.params.get("detection.stallSpeedMmPerSec"))
        self._update_counters(dt)
        return command

    # ------------------------------------------------------------- estimators
    def _update_kinematics(self, telemetry: AdapterTelemetry, dt: float) -> None:
        state = self.state
        alpha = self._alpha(float(self.params.get("regulator.velocityFilterHz")), dt)
        raw_velocity = telemetry.bar_velocity_mm_s
        self._filtered_velocity += alpha * (raw_velocity - self._filtered_velocity)
        acceleration = (self._filtered_velocity - self._prev_velocity) / dt if dt > 0 else 0.0
        self._prev_velocity = self._filtered_velocity
        state.acceleration_mm_s2 += 0.5 * (acceleration - state.acceleration_mm_s2)
        state.velocity_mm_s = round(self._filtered_velocity, 2)
        previous_position = state.position_mm
        state.position_mm = round(telemetry.bar_position_mm, 2)
        state.travel_mm_total += abs(state.position_mm - previous_position)
        stall_speed = float(self.params.get("detection.stallSpeedMmPerSec"))
        if state.velocity_mm_s > stall_speed:
            state.direction = "up"
        elif state.velocity_mm_s < -stall_speed:
            state.direction = "down"
        if abs(state.velocity_mm_s) < stall_speed:
            state.still_ms += dt * 1000
        else:
            state.still_ms = 0.0
        lower, upper = self.config.lower_mm, self.config.upper_mm
        state.amplitude_percent = int(max(0, min(100, round((state.position_mm - lower) / max(1.0, upper - lower) * 100))))

    def _update_safety(self, telemetry: AdapterTelemetry, dt: float) -> None:
        state = self.state
        alerts: list[str] = []
        state.heartbeat_ok = telemetry.heartbeat_ok
        state.power_ok = telemetry.power_ok
        state.comm_ok = telemetry.left.connected and telemetry.right.connected
        adapter_homed = telemetry.left.homed and telemetry.right.homed
        encoder_incremental = self.params.get("screw.encoderType") == "incremental"
        if not self.limit_switches_enabled and (not state.power_ok or not state.comm_ok):
            self._reference_verified = False
        if state.mode == ControlMode.homing and self._homing_phase != HomingPhase.complete:
            state.homed = False
            state.position_known = False
        elif not self.limit_switches_enabled:
            # no limit switches: homing is not required, the position is valid whenever the drives are powered
            state.homed = adapter_homed
            state.position_known = state.power_ok
        else:
            state.homed = adapter_homed
            state.position_known = state.homed or (not encoder_incremental and state.power_ok)
        current_warn = float(self.params.get("safety.currentWarnA"))
        current_max = float(self.params.get("safety.currentMaxA"))
        temp_warn = float(self.params.get("safety.tempWarnC"))
        temp_max = float(self.params.get("safety.tempMaxC"))
        fault: str | None = None
        for side in SIDES:
            side_t = telemetry.side(side)
            name = "Левый" if side == "left" else "Правый"
            if not side_t.connected:
                fault = fault or f"{name} привод: {side_t.error_message or 'нет связи'} ({side_t.error_code or 'E-COMM'})"
            if side_t.current_a >= current_max:
                fault = fault or f"{name} привод: ток {side_t.current_a:.1f} А выше предела"
            elif side_t.current_a >= current_warn:
                alerts.append(f"{name} привод: высокий ток {side_t.current_a:.1f} А")
            if side_t.temperature_c >= temp_max:
                fault = fault or f"{name} привод: перегрев {side_t.temperature_c:.0f} °C"
            elif side_t.temperature_c >= temp_warn:
                alerts.append(f"{name} привод: температура {side_t.temperature_c:.0f} °C")
        if not telemetry.power_ok:
            fault = fault or "Питание или управление приводами недоступно — удержание грифа не подтверждено"
        if not telemetry.heartbeat_ok:
            alerts.append("Heartbeat потерян — приводы в удержании")
        if not state.position_known and state.mode not in {ControlMode.post, ControlMode.homing, ControlMode.fault, ControlMode.estop}:
            alerts.append("Позиция не определена — требуется homing")
        if fault and state.mode not in {ControlMode.estop, ControlMode.fault}:
            if bool(self.params.get("safety.faultLockoutEnabled")):
                self._fault(fault)
            else:
                alerts.append(fault)
        elif state.mode == ControlMode.fault and not fault and state.comm_ok and state.power_ok:
            pass  # cleared explicitly via reset_fault
        state.alerts = alerts

    def _update_sync(self, telemetry: AdapterTelemetry) -> None:
        state = self.state
        delta = telemetry.sync_delta_mm
        state.sync_delta_mm = round(abs(delta), 2)
        norm = float(self.params.get("sync.normMm"))
        warn = float(self.params.get("sync.warningMm"))
        crit = float(self.params.get("sync.criticalMm"))
        if state.sync_delta_mm <= norm:
            state.sync_status = "norm"
        elif state.sync_delta_mm <= warn:
            state.sync_status = "ok"
        elif state.sync_delta_mm <= crit:
            state.sync_status = "warning"
        else:
            state.sync_status = "critical"
        if state.sync_status == "warning":
            state.alerts.append(f"Рассинхрон сторон {state.sync_delta_mm:.1f} мм")
        if state.sync_status == "critical" and self._jog_direction is None and state.mode in {ControlMode.training, ControlMode.moving, ControlMode.weightless, ControlMode.start_hold, ControlMode.homing}:
            action = str(self.params.get("sync.desyncAction"))
            self._emit("desync", f"Критический рассинхрон {state.sync_delta_mm:.1f} мм → {action}")
            if action == "estop":
                self.request_emergency_stop()
            elif action == "hold":
                self.request_hold("Перекос грифа", f"Рассинхрон {state.sync_delta_mm:.1f} мм. Гриф удержан, выровняйте стороны.")
            # 'slow' handled in load/velocity scaling via _slow_factor()

    def _estimate_user_force(self, telemetry: AdapterTelemetry, dt: float) -> None:
        """F_user = m_eff·a/g + m·g_comp − F_drives + friction·sign(v)  (all in kg-equivalent)."""

        state = self.state
        mass = self._bar_mass()
        inertial = float(self.params.get("compensation.equivalentMassKg"))
        friction = float(self.params.get("compensation.frictionUpKg")) if state.velocity_mm_s > 0 else float(self.params.get("compensation.frictionDownKg"))
        sign = 0.0 if abs(state.velocity_mm_s) < 1 else math.copysign(1.0, state.velocity_mm_s)
        drives = telemetry.total_force_kg
        state.drive_force_kg = round(drives, 2)
        state.drive_torque_percent = round(drives * float(self.params.get("torque.perKgRaw")) / 10.0, 1)
        raw = (mass + inertial) * state.acceleration_mm_s2 / G_MM_S2 + mass - drives + friction * sign
        if sign == 0.0:
            # at rest static friction hides up to ±friction of user force: apply a dead-zone
            static = (float(self.params.get("compensation.frictionUpKg")) + float(self.params.get("compensation.frictionDownKg"))) / 2
            raw = math.copysign(max(0.0, abs(raw) - static), raw)
        alpha = self._alpha(float(self.params.get("load.forceFilterHz")), dt)
        self._filtered_force += alpha * (raw - self._filtered_force)
        state.user_force_kg = round(self._filtered_force, 2)
        for side, attr in (("left", "_filtered_force_left"), ("right", "_filtered_force_right")):
            side_t = telemetry.side(side)
            raw_side = (mass + inertial) / 2 * state.acceleration_mm_s2 / G_MM_S2 + mass / 2 - side_t.force_kg + friction / 2 * sign
            setattr(self, attr, getattr(self, attr) + alpha * (raw_side - getattr(self, attr)))
        state.user_force_left_kg = round(self._filtered_force_left, 2)
        state.user_force_right_kg = round(self._filtered_force_right, 2)
        total = abs(state.user_force_left_kg) + abs(state.user_force_right_kg)
        state.asymmetry_percent = round(abs(state.user_force_left_kg - state.user_force_right_kg) / total * 100, 1) if total > 2 else 0.0
        if (
            state.mode == ControlMode.training
            and not self.config.asymmetric_allowed
            and state.asymmetry_percent > float(self.params.get("sync.asymmetryTolerancePercent"))
        ):
            state.alerts.append(f"Асимметрия усилий {state.asymmetry_percent:.0f} %")

    # ---------------------------------------------------------------- modes
    def _tick_idle(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        self.state.idle_s += dt
        return self._brake_command()

    def _tick_post(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        if self._pending_self_test is not None:
            results = self._pending_self_test
            self._pending_self_test = None
            state.post_results = [
                {"id": item.id, "label": item.label, "passed": item.passed, "detail": item.detail, "severity": item.severity}
                for item in results
            ]
            failed_critical = [item for item in results if not item.passed and item.severity == "critical"]
            state.post_status = "failed" if failed_critical else "passed"
            self._emit("post", "Самотест пройден" if not failed_critical else f"Самотест не пройден: {failed_critical[0].label}")
            if failed_critical:
                self._fault(f"POST: {failed_critical[0].label} — {failed_critical[0].detail}")
            elif not self.limit_switches_enabled:
                self.skip_homing()
            elif not state.homed and bool(self.params.get("safety.homingRequiredAfterPowerLoss")):
                self.request_homing()
            else:
                self.request_idle()
        return self._brake_command()

    def _tick_homing(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        del dt
        state = self.state
        phase = self._homing_phase
        position = state.position_mm
        now = state.time
        limit = self._torque_percent_to_kg(float(self.params.get("profile.calibration.torqueLimitPercent")))

        if not self.limit_switches_enabled:
            if abs(telemetry.left.velocity_mm_s) > 1 or abs(telemetry.right.velocity_mm_s) > 1:
                return self._homing_fault("zero_reference_requires_stationary_bar")
            return self._brake_command()

        if now - self._homing_started_at >= float(self.params.get("homing.totalTimeoutSec")):
            return self._homing_fault("homing_global_timeout")
        if self._homing_phase_expired(position):
            return self._homing_fault("homing_phase_timeout_or_distance")
        if (telemetry.left.limit_switch_low and telemetry.left.limit_switch_high) or (
            telemetry.right.limit_switch_low and telemetry.right.limit_switch_high
        ):
            return self._homing_fault("invalid_sensor_combination")

        if self._homing_initial_validation_pending:
            self._homing_initial_validation_pending = False
            if telemetry.left.limit_switch_low != telemetry.right.limit_switch_low:
                return self._homing_fault("bottom_sensor_mismatch")
            if telemetry.left.limit_switch_high != telemetry.right.limit_switch_high:
                return self._homing_fault("top_sensor_mismatch")

        if phase in {
            HomingPhase.bottom_coarse,
            HomingPhase.bottom_creep,
            HomingPhase.bottom_fine,
            HomingPhase.bottom_fine_creep,
        }:
            accepted = self._homing_search_pair(telemetry, top=False)
            if self.state.mode == ControlMode.fault:
                return self._brake_command()
            if accepted:
                if phase in {HomingPhase.bottom_fine, HomingPhase.bottom_fine_creep}:
                    state.physical_bottom_mm = position
                    state.working_bottom_mm = position + float(self.params.get("homing.bottomOffsetMm"))
                    self._homing_reference_pending = True
                    self._set_homing_phase(HomingPhase.bottom_reference)
                    self._emit("home", "Нижняя физическая граница подтверждена двумя датчиками")
                else:
                    self._set_homing_phase(HomingPhase.bottom_stop)
                return self._brake_command()
            speed_key = "homing.coarseSpeedMmPerSec" if self._homing_phase == HomingPhase.bottom_coarse else (
                "homing.creepSpeedMmPerSec" if self._homing_phase == HomingPhase.bottom_creep else "homing.fineSpeedMmPerSec"
            )
            return self._velocity_command(-float(self.params.get(speed_key)), limit, feedforward=self._gravity_comp_per_side())

        if phase == HomingPhase.bottom_stop:
            if self._homing_stop_settled():
                self._set_homing_phase(HomingPhase.bottom_backoff)
            return self._brake_command()
        if phase == HomingPhase.bottom_backoff:
            if self._homing_backoff_ready(telemetry, top=False):
                self._set_homing_phase(HomingPhase.bottom_fine)
                return self._brake_command()
            if self.state.mode == ControlMode.fault:
                return self._brake_command()
            return self._velocity_command(float(self.params.get("homing.backoffSpeedMmPerSec")), limit, feedforward=self._gravity_comp_per_side())
        if phase == HomingPhase.bottom_reference:
            return self._brake_command()

        if phase in {
            HomingPhase.top_coarse,
            HomingPhase.top_creep,
            HomingPhase.top_fine,
            HomingPhase.top_fine_creep,
        }:
            accepted = self._homing_search_pair(telemetry, top=True)
            if self.state.mode == ControlMode.fault:
                return self._brake_command()
            if accepted:
                if phase in {HomingPhase.top_fine, HomingPhase.top_fine_creep}:
                    state.physical_top_mm = position
                    state.working_top_mm = position - float(self.params.get("homing.topOffsetMm"))
                    if state.physical_bottom_mm is None or state.working_bottom_mm is None:
                        return self._homing_fault("bottom_reference_missing")
                    state.full_travel_mm = state.physical_top_mm - state.physical_bottom_mm
                    if state.full_travel_mm <= 0 or state.working_top_mm <= state.working_bottom_mm:
                        return self._homing_fault("invalid_calibrated_travel")
                    self._set_homing_phase(HomingPhase.move_safe_top)
                    self._emit("home", "Верхняя физическая граница подтверждена двумя датчиками")
                else:
                    self._set_homing_phase(HomingPhase.top_stop)
                return self._brake_command()
            speed_key = "homing.coarseSpeedMmPerSec" if self._homing_phase == HomingPhase.top_coarse else (
                "homing.creepSpeedMmPerSec" if self._homing_phase == HomingPhase.top_creep else "homing.fineSpeedMmPerSec"
            )
            return self._velocity_command(float(self.params.get(speed_key)), limit, feedforward=self._gravity_comp_per_side())

        if phase == HomingPhase.top_stop:
            if self._homing_stop_settled():
                self._set_homing_phase(HomingPhase.top_backoff)
            return self._brake_command()
        if phase == HomingPhase.top_backoff:
            if self._homing_backoff_ready(telemetry, top=True):
                self._set_homing_phase(HomingPhase.top_fine)
                return self._brake_command()
            if self.state.mode == ControlMode.fault:
                return self._brake_command()
            return self._velocity_command(-float(self.params.get("homing.backoffSpeedMmPerSec")), limit, feedforward=self._gravity_comp_per_side())
        if phase == HomingPhase.move_safe_top:
            target = state.working_top_mm
            if target is None:
                return self._homing_fault("top_reference_missing")
            if abs(position - target) <= float(self.params.get("homing.targetToleranceMm")):
                state.homed = True
                state.position_known = True
                self._set_homing_phase(HomingPhase.complete)
                self._emit("home", "Homing завершён; физические и рабочие границы установлены")
                self.request_idle()
                return self._brake_command()
            return self._position_command(target, limit)
        return self._brake_command()

    @property
    def homing_ready_to_zero(self) -> bool:
        return self.state.mode == ControlMode.homing and self._homing_phase == HomingPhase.bottom_reference and self._homing_reference_pending

    def mark_homing_reference_applied(self) -> None:
        if not self.homing_ready_to_zero:
            return
        self._homing_reference_pending = False
        # DriveAdapter.home() establishes the lower physical edge as coordinate 0.
        self.state.physical_bottom_mm = 0.0
        if not self.limit_switches_enabled:
            self._reference_verified = True
            self.state.working_bottom_mm = float(self.params.get("limits.softMinMm"))
            self.state.working_top_mm = float(self.params.get("limits.softMaxMm"))
            self.state.homed = True
            self.state.position_known = True
            self._set_homing_phase(HomingPhase.complete)
            self._emit("home", "Энкодеры обнулены в нижнем положении; действуют программные границы хода")
            self.request_idle()
        else:
            self.state.working_bottom_mm = float(self.params.get("homing.bottomOffsetMm"))
            self._set_homing_phase(HomingPhase.top_coarse)

    def _set_homing_phase(self, phase: HomingPhase) -> None:
        self._homing_phase = phase
        self.state.homing_phase = phase.value
        self._homing_phase_started_at = self.state.time
        self._homing_phase_start_mm = self.state.position_mm
        self._homing_first_edge_at = None
        self._homing_first_edge_mm = None
        self._emit("homing_phase", phase.value, {"phase": phase.value, "positionMm": self.state.position_mm})

    def _homing_phase_expired(self, position_mm: float) -> bool:
        elapsed = self.state.time - self._homing_phase_started_at
        distance = abs(position_mm - self._homing_phase_start_mm)
        return elapsed >= float(self.params.get("homing.phaseTimeoutSec")) or distance > float(
            self.params.get("homing.maximumSearchDistanceMm")
        )

    def _homing_fault(self, code: str) -> DriveCommand:
        self._homing_reference_pending = False
        self._homing_phase = HomingPhase.fault
        self.state.homing_phase = HomingPhase.fault.value
        self._fault(code)
        return self._brake_command()

    def _homing_search_pair(self, telemetry: AdapterTelemetry, *, top: bool) -> bool:
        left = telemetry.left.limit_switch_high if top else telemetry.left.limit_switch_low
        right = telemetry.right.limit_switch_high if top else telemetry.right.limit_switch_low
        pair = left and right
        single = left != right
        now = self.state.time
        position = self.state.position_mm
        if single and self._homing_first_edge_at is None:
            self._homing_first_edge_at = now
            self._homing_first_edge_mm = position
            coarse = HomingPhase.top_coarse if top else HomingPhase.bottom_coarse
            creep = HomingPhase.top_creep if top else HomingPhase.bottom_creep
            fine = HomingPhase.top_fine if top else HomingPhase.bottom_fine
            fine_creep = HomingPhase.top_fine_creep if top else HomingPhase.bottom_fine_creep
            if self._homing_phase == coarse:
                self._homing_phase = creep
                self.state.homing_phase = creep.value
                self._emit("homing_phase", creep.value, {"phase": creep.value, "positionMm": position})
            elif self._homing_phase == fine:
                self._homing_phase = fine_creep
                self.state.homing_phase = fine_creep.value
                self._emit("homing_phase", fine_creep.value, {"phase": fine_creep.value, "positionMm": position})
        if self._homing_first_edge_at is not None and (single or pair):
            edge_position = self._homing_first_edge_mm if self._homing_first_edge_mm is not None else position
            time_exceeded = (now - self._homing_first_edge_at) * 1000 >= float(self.params.get("homing.pairTimeWindowMs"))
            distance_exceeded = abs(position - edge_position) > float(self.params.get("homing.pairDistanceWindowMm"))
            if time_exceeded or distance_exceeded:
                side = "right" if left else "left"
                boundary = "top" if top else "bottom"
                self._homing_fault(f"{side}_{boundary}_sensor_pair_timeout")
                return False
        return pair

    def _homing_stop_settled(self) -> bool:
        return (self.state.time - self._homing_phase_started_at) * 1000 >= float(self.params.get("homing.stopSettleMs"))

    def _homing_backoff_ready(self, telemetry: AdapterTelemetry, *, top: bool) -> bool:
        left = telemetry.left.limit_switch_high if top else telemetry.left.limit_switch_low
        right = telemetry.right.limit_switch_high if top else telemetry.right.limit_switch_low
        elapsed_ms = (self.state.time - self._homing_phase_started_at) * 1000
        distance = abs(self.state.position_mm - self._homing_phase_start_mm)
        if (left or right) and (
            elapsed_ms >= float(self.params.get("homing.releaseTimeoutMs"))
            or distance > float(self.params.get("homing.releaseDistanceMm"))
        ):
            self._homing_fault(f"{'top' if top else 'bottom'}_sensor_release_stuck")
            return False
        return not left and not right and distance >= float(self.params.get("homing.backoffDistanceMm"))

    def _tick_moving(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        move = self._move
        if move is None:
            return self._brake_command()
        speed_max = float(self.params.get(f"profile.{move.profile}.speedMmPerSec")) * self._slow_factor()
        accel = float(self.params.get(f"profile.{move.profile}.accelMmPerSec2"))
        limit = self._torque_percent_to_kg(float(self.params.get(f"profile.{move.profile}.torqueLimitPercent")))
        remaining = move.target_mm - state.position_mm
        distance = abs(remaining)
        total = max(1.0, abs(move.target_mm - self._move_start_mm))
        state.move_progress_percent = int(max(0, min(100, 100 - distance / total * 100)))
        if distance <= 1.5 and abs(state.velocity_mm_s) < 15:
            state.move_target_mm = None
            self._emit("arrived", f"{move.label}: позиция {state.position_mm:.0f} мм достигнута")
            next_mode = move.then
            self._move = None
            if next_mode == ControlMode.start_hold:
                self._hold_position_mm = self.config.start_mm
                self._enter(ControlMode.start_hold, "Ожидание захвата", "Возьмитесь за гриф — движение начнётся автоматически.")
            elif next_mode == ControlMode.fixed_hold:
                self._hold_position_mm = move.target_mm
                state.fixed_hold_test_passed = False
                self._enter(ControlMode.fixed_hold, "Фиксированная позиция", "Проверка удержания перед стартом.")
            elif next_mode == ControlMode.parked:
                self._enter(ControlMode.parked, "Гриф запаркован", "Приводы в удержании, тренажёр готов к следующему упражнению.")
            elif next_mode == ControlMode.weightless:
                self.request_weightless()
            elif next_mode == ControlMode.paused:
                self._hold_position_mm = move.target_mm
                self._enter(ControlMode.paused, "Показ диапазона завершён", "Диапазон подтверждён, гриф удерживается.")
            else:
                self.request_idle()
            return self._position_command(move.target_mm, limit)
        # trapezoidal profile: v = min(vmax, sqrt(2·a·d))
        v_target = math.copysign(min(speed_max, math.sqrt(2 * accel * distance)), remaining)
        v_cmd = self._ramp_velocity(v_target, accel, dt)
        if move.obstacle_check:
            self._check_obstacle(telemetry, dt, limit)
        return self._velocity_command(v_cmd, limit, feedforward=self._gravity_comp_per_side())

    def _tick_weightless(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        damping = float(self.params.get("regulator.calibrationDampingKgPerMmPerSec"))
        max_speed = float(self.params.get("regulator.calibrationMaxSpeedMmPerSec"))
        if abs(state.velocity_mm_s) > max_speed:
            damping *= 3
        drift_limit = float(self.params.get("regulator.weightlessMaxDriftMmPerSec"))
        release_force = float(self.params.get("detection.releaseForceKg"))
        settled = (state.time - state.mode_since) > 0.4
        if settled and abs(state.velocity_mm_s) > drift_limit and abs(state.user_force_kg) < release_force and self._jog_direction is None:
            self._drift_s += dt
        else:
            self._drift_s = 0.0
        if self._drift_s >= 0.5:
            self._drift_s = 0.0
            self._emit("drift", f"Дрейф невесомого грифа {state.velocity_mm_s:.0f} мм/с → удержание")
            self.request_hold("Дрейф грифа", "Гриф уходил без усилия пользователя — переведён в удержание.")
            return self._position_command(state.position_mm, self._capacity_per_side())
        base = self._compensation_per_side(dt)
        viscous = -damping * state.velocity_mm_s / 2
        bumper = self._soft_bumper_per_side()
        jog = self._jog_offset_kg()
        components = {"gravity": base["gravity"] * 2, "friction": base["friction"] * 2, "inertia": base["inertia"] * 2, "damping": viscous * 2, "bumper": bumper * 2, "load": 0.0, "sync": 0.0, "spotter": 0.0, "jog": jog * 2}
        force = base["total"] + viscous + bumper + jog
        state.components = {key: round(value, 2) for key, value in components.items()}
        limit = self._torque_percent_to_kg(float(self.params.get("profile.calibration.torqueLimitPercent"))) + self._gravity_comp_per_side()
        return self._torque_command(force, limit, sync=True)

    def _tick_start_hold(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        hold_at = self._hold_position_mm if self._hold_position_mm is not None else self.config.start_mm
        tolerance = float(self.params.get("start.holdToleranceMm"))
        grip_delta = float(self.params.get("start.gripDetectDeltaMm"))
        grip_force = float(self.params.get("start.gripDetectForceKg"))
        pretension = float(self.params.get("start.holdTorquePercent"))
        if abs(state.position_mm - hold_at) > grip_delta or abs(state.user_force_kg) > grip_force:
            state.grip_detected = True
            self._emit("grip", f"Захват грифа обнаружен (усилие {state.user_force_kg:.1f} кг)")
            self._phase_started = state.time
            self._rep_armed = True
            self._excursion_min = self._excursion_max = state.position_mm
            self._enter(ControlMode.training, "Движение выполняется", "Безопасный профиль движения активен.")
            return self._tick_training(telemetry, dt)
        elapsed = state.time - state.mode_since
        if elapsed > float(self.params.get("start.holdTimeoutSec")):
            self._emit("timeout", "Захват не обнаружен — гриф паркуется")
            self.request_park()
            return self._brake_command()
        limit = max(self._gravity_comp_per_side() + 1.0, self._torque_percent_to_kg(pretension))
        state.components = {"gravity": self._gravity_comp_per_side() * 2, "pretension": pretension}
        if abs(state.position_mm - hold_at) > tolerance:
            state.alerts.append("Гриф вне стартовой точки")
        return self._position_command(hold_at, limit)

    def _tick_training(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        config = self.config
        if config.load_mode in {"bodyweight", "no_machine"}:
            return self._position_command(state.position_mm, self._capacity_per_side())

        target_load = self._target_load_kg()
        state.load_target_kg = round(target_load, 2)
        rate = float(self.params.get("load.changeRateKgPerSec"))
        ramp_in = float(self.params.get("load.rampInSec"))
        since = state.time - state.mode_since
        ramp_cap = target_load if ramp_in <= 0 else target_load * min(1.0, since / ramp_in)
        step = rate * dt
        desired = min(target_load, ramp_cap)
        if self._load_ramp_kg < desired:
            self._load_ramp_kg = min(desired, self._load_ramp_kg + step)
        else:
            self._load_ramp_kg = max(desired, self._load_ramp_kg - step)

        direction_factor = self._direction_factor()
        curve_factor = self._curve_factor()
        load = self._load_ramp_kg * direction_factor * curve_factor * self._slow_factor()

        # isokinetic: adapt load to keep concentric speed constant
        if config.load_mode == "isokinetic":
            v_target = float(self.params.get("load.isokineticSpeedMmPerSec"))
            if state.velocity_mm_s > 0:
                self._isokinetic_load += 0.05 * (state.velocity_mm_s - v_target) * dt * 10
            self._isokinetic_load = max(0.0, min(self._clamp_load(float(self.params.get("load.maxKg"))), self._isokinetic_load))
            load = self._isokinetic_load

        levitation = self._update_levitation(dt)
        load *= levitation

        self._detect_stall_and_failure(dt)
        spotter = 0.0
        if state.spotter_active:
            spotter = load * float(self.params.get("detection.spotterAssistPercent")) / 100
            load -= spotter
        if state.failure_detected:
            return self._position_command(state.position_mm, self._capacity_per_side())

        self._update_reps()
        self._update_release(dt)

        base = self._compensation_per_side(dt)
        descent_brake = self._descent_brake_per_side() * levitation
        bumper = self._soft_bumper_per_side()
        force_per_side = base["total"] - load / 2 + descent_brake + bumper
        state.load_effective_kg = round(load, 2)
        state.components = {
            "gravity": round(base["gravity"] * 2, 2),
            "friction": round(base["friction"] * 2, 2),
            "inertia": round(base["inertia"] * 2, 2),
            "load": round(-load, 2),
            "descentBrake": round(descent_brake * 2, 2),
            "bumper": round(bumper * 2, 2),
            "spotter": round(spotter, 2),
        }
        self._loaded_active = load > 1
        limit = self._capacity_per_side() * float(self.params.get(f"profile.{config.motion_profile if config.motion_profile in self._profiles() else 'training'}.torqueLimitPercent")) / 100
        if config.guest:
            limit = min(limit, self._capacity_per_side() * float(self.params.get("profile.guest.torqueLimitPercent")) / 100)
        return self._torque_command(force_per_side, max(limit, self._gravity_comp_per_side() + 1.0), sync=True)

    def _tick_fixed_hold(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        hold_at = self._hold_position_mm if self._hold_position_mm is not None else state.position_mm
        tolerance = float(self.params.get("fixed.driftToleranceMm"))
        state.fixed_drift_mm = round(abs(state.position_mm - hold_at), 2)
        since = state.time - state.mode_since
        if not state.fixed_hold_test_passed and since >= float(self.params.get("fixed.holdTestSec")):
            if state.fixed_drift_mm <= tolerance and state.sync_status in {"norm", "ok"}:
                state.fixed_hold_test_passed = True
                self._emit("hold_test", "Тест удержания пройден — можно начинать")
                state.message = "Гриф зафиксирован. Можно начинать упражнение."
            else:
                state.alerts.append("Тест удержания: дрейф или рассинхрон")
        if state.fixed_drift_mm > tolerance:
            state.alerts.append(f"Дрейф удержания {state.fixed_drift_mm:.1f} мм")
        total_down = max(0.0, -telemetry.total_force_kg + self._bar_mass())
        if total_down > float(self.params.get("safety.holdOverloadKg")):
            state.alerts.append(f"Перегрузка удержания {total_down:.0f} кг")
        if self.config.rep_count_source == "load":
            self._count_reps_by_load()
        limit = self._capacity_per_side() * float(self.params.get("fixed.torquePercent")) / 100
        state.components = {"gravity": self._gravity_comp_per_side() * 2, "hold": limit * 2}
        self._loaded_active = abs(state.user_force_kg) > 5
        return self._position_command(hold_at, limit)

    def _tick_isometric(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        hold_at = self._hold_position_mm if self._hold_position_mm is not None else state.position_mm
        state.isometric_elapsed_s += dt
        load = self._clamp_load(self.config.load_kg)
        state.load_effective_kg = round(load, 2)
        drift = abs(state.position_mm - hold_at)
        if drift > float(self.params.get("fixed.driftToleranceMm")) * 5:
            state.alerts.append(f"Изометрия: смещение {drift:.0f} мм")
        if state.isometric_elapsed_s >= self.config.isometric_duration_s:
            state.target_reached = True
            self._emit("target", "Время изометрии выполнено")
            self.complete_set()
        # drive pulls down with the load; position servo only prevents runaway beyond tolerance band
        base = self._compensation_per_side(dt)
        force = base["total"] - load / 2 + self._descent_brake_per_side() + self._soft_bumper_per_side()
        self._loaded_active = True
        state.components = {"gravity": base["gravity"] * 2, "load": -load}
        return self._torque_command(force, self._capacity_per_side(), sync=True)

    def _tick_paused(self, telemetry: AdapterTelemetry, dt: float) -> DriveCommand:
        state = self.state
        hold_at = self._hold_position_mm if self._hold_position_mm is not None else state.position_mm
        self._update_release(dt)
        if state.released and (state.time - state.mode_since) > float(self.params.get("start.holdTimeoutSec")):
            self._emit("timeout", "Гриф без пользователя — парковка")
            self.request_park()
            return self._brake_command()
        state.components = {"gravity": self._gravity_comp_per_side() * 2}
        return self._position_command(hold_at, self._capacity_per_side())

    # ------------------------------------------------------------- physics
    def _bar_mass(self) -> float:
        return float(self.params.get("compensation.barMassKg")) + float(self.params.get("compensation.movingPartsMassKg"))

    def _gravity_comp_per_side(self) -> float:
        if not bool(self.params.get("compensation.gravityEnabled")):
            return 0.0
        return self._bar_mass() * float(self.params.get("compensation.gravityGain")) / 100 / 2

    def _compensation_per_side(self, dt: float) -> dict[str, float]:
        state = self.state
        gravity = self._gravity_comp_per_side()
        friction = 0.0
        if bool(self.params.get("compensation.frictionEnabled")):
            stall = float(self.params.get("detection.stallSpeedMmPerSec"))
            blend = max(-1.0, min(1.0, state.velocity_mm_s / max(stall, 1.0)))
            coefficient = float(self.params.get("compensation.frictionUpKg")) if blend > 0 else float(self.params.get("compensation.frictionDownKg"))
            friction = coefficient * blend / 2
        inertia = 0.0
        if bool(self.params.get("compensation.inertiaEnabled")):
            equivalent = float(self.params.get("compensation.equivalentMassKg"))
            gain = float(self.params.get("compensation.inertiaGain")) / 100
            cap = float(self.params.get("compensation.inertiaMaxKg"))
            inertia = max(-cap, min(cap, equivalent * state.acceleration_mm_s2 / G_MM_S2 * gain)) / 2
        return {"gravity": gravity, "friction": friction, "inertia": inertia, "total": gravity + friction + inertia}

    def _direction_factor(self) -> float:
        """Load multiplier by phase with an S-curve blend across the reversal (velocity → 0)."""

        config = self.config
        up_factor = 1.0
        down_factor = 1.0
        if config.load_mode == "assist_up":
            up_factor = float(self.params.get("load.assistUpFactor"))
        elif config.load_mode == "negative_phase":
            down_factor = float(self.params.get("load.negativePhaseFactor"))
        if config.start_point == "upper":  # pull: concentric is downward
            up_factor, down_factor = down_factor, up_factor
        if up_factor == down_factor:
            return up_factor
        zone = max(1.0, float(self.params.get("compensation.reversalZoneMm")))
        v_ref = zone * 4  # mm/s at which the blend saturates
        w = max(0.0, min(1.0, (self.state.velocity_mm_s / v_ref + 1) / 2))
        w = w * w * (3 - 2 * w)
        return down_factor + (up_factor - down_factor) * w

    def _curve_factor(self) -> float:
        curve = str(self.params.get("load.curve"))
        depth = float(self.params.get("load.curveDepthPercent")) / 100
        amp = self.state.amplitude_percent / 100
        if curve == "band":
            return 1 - depth / 2 + depth * amp
        if curve == "chain":
            return 1 - depth / 2 + depth * (math.floor(amp * 4) / 4)
        if curve == "descending":
            return 1 + depth / 2 - depth * amp
        return 1.0

    def _target_load_kg(self) -> float:
        config = self.config
        load = self._clamp_load(config.load_kg)
        if config.load_mode == "light_mode":
            load *= float(self.params.get("load.lightModeFactor"))
        if config.warmup:
            load *= float(self.params.get("load.warmupFactor"))
        return load * float(self.params.get("load.kgToTorqueFactor"))

    def _clamp_load(self, load_kg: float) -> float:
        cap = float(self.params.get("load.maxKg"))
        if self.config.guest:
            cap = min(cap, float(self.params.get("load.guestMaxKg")))
        return max(0.0, min(cap, load_kg))

    def _update_levitation(self, dt: float) -> float:
        """Load multiplier: below the exercise lower bound only the bar weight is compensated (0 = levitation).

        Hysteresis: levitation starts below ``lower_mm`` and ends above ``lower_mm + levitationHysteresisMm``.
        The factor is ramped so the torque does not step.
        """

        state = self.state
        lower = self.config.lower_mm
        hysteresis = float(self.params.get("load.levitationHysteresisMm"))
        if state.position_mm < lower:
            if not state.levitating:
                state.levitating = True
                self._emit("levitate", f"Гриф ниже нижней границы {lower:.0f} мм — только компенсация веса", {"positionMm": round(state.position_mm, 1)})
        elif state.levitating and state.position_mm > lower + hysteresis:
            state.levitating = False
            self._emit("levitate_off", "Гриф выше нижней границы — нагрузка возвращена", {"positionMm": round(state.position_mm, 1)})
        ramp = max(0.05, float(self.params.get("load.levitationRampSec")))
        step = dt / ramp
        target = 0.0 if state.levitating else 1.0
        if self._levitation_factor < target:
            self._levitation_factor = min(target, self._levitation_factor + step)
        else:
            self._levitation_factor = max(target, self._levitation_factor - step)
        return self._levitation_factor

    def _descent_brake_per_side(self) -> float:
        state = self.state
        max_descent = float(self.params.get("limits.maxDescentSpeedMmPerSec"))
        max_user = float(self.params.get("limits.maxUserSpeedMmPerSec"))
        force = 0.0
        if state.velocity_mm_s < -max_descent:
            excess = -state.velocity_mm_s - max_descent
            force += 0.05 * excess * self._bar_mass() / 10
        if abs(state.velocity_mm_s) > max_user:
            excess = abs(state.velocity_mm_s) - max_user
            force += -math.copysign(0.02 * excess, state.velocity_mm_s)
            if state.time - self._last_alert_time > 1.0:
                self._emit("speed", f"Скорость {abs(state.velocity_mm_s):.0f} мм/с выше допустимой")
                self._last_alert_time = state.time
        return force / 2

    def _soft_bumper_per_side(self) -> float:
        """Virtual bumpers: decelerate near exercise bounds, hard stop at soft limits."""

        state = self.state
        kp = float(self.params.get("regulator.positionKp"))
        kd = float(self.params.get("regulator.positionKd"))
        zone = float(self.params.get("limits.decelZoneMm"))
        soft_min = float(self.params.get("limits.softMinMm"))
        soft_max = float(self.params.get("limits.softMaxMm"))
        force = 0.0
        if state.position_mm < soft_min:
            force += kp * (soft_min - state.position_mm) - kd * state.velocity_mm_s
        elif state.position_mm > soft_max:
            force += kp * (soft_max - state.position_mm) - kd * state.velocity_mm_s
        if self.state.mode in {ControlMode.training, ControlMode.isometric} and zone > 0:
            lower, upper = self.config.lower_mm, self.config.upper_mm
            margin = 5.0
            if state.position_mm < lower - margin and state.velocity_mm_s < 0:
                force += -kd * 4 * state.velocity_mm_s * min(1.0, (lower - margin - state.position_mm) / zone)
            if state.position_mm > upper + margin and state.velocity_mm_s > 0:
                force += -kd * 4 * state.velocity_mm_s * min(1.0, (state.position_mm - upper - margin) / zone)
        return force / 2

    def _sync_correction(self, telemetry: AdapterTelemetry) -> dict[Side, float]:
        mode = str(self.params.get("sync.mode"))
        gain = float(self.params.get("sync.correctionGain"))
        cap = float(self.params.get("sync.correctionMaxMmPerSec")) * 0.1  # kg-equivalent cap
        delta = telemetry.left.position_mm - telemetry.right.position_mm  # >0: left higher
        correction = max(-cap, min(cap, gain * delta))
        if mode == "master_slave":  # left is master, right follows
            return {"left": 0.0, "right": correction}
        return {"left": -correction / 2, "right": correction / 2}

    # ------------------------------------------------------------ detection
    def _detect_stall_and_failure(self, dt: float) -> None:
        state = self.state
        config = self.config
        stall_speed = float(self.params.get("detection.stallSpeedMmPerSec"))
        release_force = float(self.params.get("detection.releaseForceKg"))
        hysteresis = float(self.params.get("detection.repHysteresisMm"))
        in_far_zone = abs(state.position_mm - config.far_mm) <= hysteresis
        in_start_zone = abs(state.position_mm - config.start_mm) <= hysteresis
        under_load = abs(state.user_force_kg) > release_force
        if under_load and abs(state.velocity_mm_s) < stall_speed and not in_far_zone and not in_start_zone:
            state.stall_s += dt
        else:
            state.stall_s = 0.0
            if state.spotter_active and in_far_zone:
                state.spotter_active = False
                self._emit("spotter_off", "Страховка снята — верхняя точка достигнута")
        timeout = float(self.params.get("detection.stallTimeoutSec"))
        delay = float(self.params.get("detection.spotterDelaySec"))
        if state.stall_s >= delay and bool(self.params.get("detection.spotterEnabled")) and not state.spotter_active:
            state.spotter_active = True
            self._emit("spotter", f"Застревание {state.stall_s:.1f} с → страховка {self.params.get('detection.spotterAssistPercent')} %")
        elif state.stall_s >= timeout and not bool(self.params.get("detection.spotterEnabled")):
            if "Гриф остановился — снизьте нагрузку или завершите подход" not in state.alerts:
                state.alerts.append("Гриф остановился — снизьте нагрузку или завершите подход")
        failure_speed = float(self.params.get("detection.failureDescentSpeedMmPerSec"))
        concentric_down = config.start_point == "upper"
        pushing_up = state.user_force_kg > release_force
        cannot_hold = state.user_force_kg < 0.6 * state.load_effective_kg + 1.0
        if state.velocity_mm_s < -failure_speed and pushing_up and cannot_hold and not concentric_down and not state.failure_detected:
            state.failure_detected = True
            self._hold_position_mm = state.position_mm
            self._emit("failure", f"Потеря контроля: опускание {abs(state.velocity_mm_s):.0f} мм/с → удержание")
            self._enter(ControlMode.paused, "Спасение", "Гриф удержан. Нажмите «Продолжить», когда будете готовы.")

    def _update_release(self, dt: float) -> None:
        state = self.state
        release_force = float(self.params.get("detection.releaseForceKg"))
        if abs(state.user_force_kg) < release_force:
            self._release_s += dt
        else:
            self._release_s = 0.0
            state.released = False
        if self._release_s >= float(self.params.get("detection.releaseTimeoutSec")) and not state.released:
            state.released = True
            if state.mode == ControlMode.training and (state.time - state.mode_since) > 1.0:
                self._emit("release", "Гриф отпущен — удержание")
                self.request_hold("Гриф отпущен", "Нет усилия на грифе. Гриф удерживается.")

    def _update_reps(self) -> None:
        state = self.state
        config = self.config
        hysteresis = float(self.params.get("detection.repHysteresisMm"))
        full = float(self.params.get("detection.fullRepPercent")) / 100
        partial = float(self.params.get("detection.partialRepPercent")) / 100
        pos = state.position_mm
        self._excursion_min = min(self._excursion_min, pos)
        self._excursion_max = max(self._excursion_max, pos)
        in_start = abs(pos - config.start_mm) <= hysteresis
        in_far = abs(pos - config.far_mm) <= hysteresis
        stall = float(self.params.get("detection.stallSpeedMmPerSec")) * 3
        sign = 1 if state.velocity_mm_s > stall else (-1 if state.velocity_mm_s < -stall else 0)
        if sign != 0 and sign != self._last_direction_sign:
            if self._last_direction_sign != 0:
                phase_time = state.time - self._phase_started
                if self._last_direction_sign > 0:
                    state.concentric_s = round(phase_time, 2) if config.start_point != "upper" else state.concentric_s
                    state.eccentric_s = round(phase_time, 2) if config.start_point == "upper" else state.eccentric_s
                else:
                    state.eccentric_s = round(phase_time, 2) if config.start_point != "upper" else state.eccentric_s
                    state.concentric_s = round(phase_time, 2) if config.start_point == "upper" else state.concentric_s
                self._emit("reversal", f"Смена направления на {pos:.0f} мм", {"positionMm": pos})
            self._phase_started = state.time
            self._last_direction_sign = sign
        if config.rep_count_source != "motion":
            return
        if in_start and not self._rep_armed:
            excursion = (self._excursion_max - self._excursion_min) / config.range_mm
            if partial <= excursion < full:
                state.partial_reps += 1
                self._emit("partial_rep", f"Частичный повтор ({excursion * 100:.0f} %)")
            self._rep_armed = True
            self._excursion_min = self._excursion_max = pos
            self._rep_started_at = state.time
        elif in_far and self._rep_armed:
            excursion = (self._excursion_max - self._excursion_min) / config.range_mm
            if excursion >= full:
                state.repetition_count += 1
                duration = state.time - self._rep_started_at
                state.rep_quality = round(min(1.0, excursion) * (1.0 if 1.0 <= duration <= 6.0 else 0.8), 2)
                state.tempo_label = "быстро" if duration < 1.2 else ("медленно" if duration > 5 else "хорошо")
                self._emit("rep", f"Повтор {state.repetition_count} · {duration:.1f} с", {"repetition": state.repetition_count, "durationS": round(duration, 2)})
                self._check_target()
            self._rep_armed = False
            self._excursion_min = self._excursion_max = pos

    def _count_reps_by_load(self) -> None:
        """Count reps for fixed-position exercises by user force oscillations."""

        state = self.state
        force = abs(state.user_force_kg)
        high = 15.0
        low = 5.0
        if self._load_peak_state == 0 and force > high:
            self._load_peak_state = 1
        elif self._load_peak_state == 1 and force < low:
            self._load_peak_state = 0
            state.repetition_count += 1
            self._emit("rep", f"Повтор {state.repetition_count} (по усилию)")
            self._check_target()

    def _check_target(self) -> None:
        state = self.state
        if state.repetition_count >= self.config.target_reps and not state.target_reached:
            state.target_reached = True
            state.label = "Цель подхода достигнута"
            self._emit("target", "Цель подхода выполнена")
            action = str(self.params.get("detection.onTargetReached"))
            if action == "hold":
                self.request_hold("Цель подхода достигнута", "Гриф удерживается. Завершите подход.")
            elif action == "unload":
                self.config.load_kg = 0.0
                state.message = "Нагрузка снята — цель подхода выполнена."

    def _check_obstacle(self, telemetry: AdapterTelemetry, dt: float, limit: float) -> None:
        state = self.state
        threshold = float(self.params.get("safety.obstacleForceKg"))
        stall_speed = float(self.params.get("detection.stallSpeedMmPerSec"))
        near_limit = abs(telemetry.total_force_kg - self._gravity_comp_per_side() * 2) >= min(threshold, limit * 2 * 0.9)
        if near_limit and abs(state.velocity_mm_s) < stall_speed:
            self._obstacle_s += dt
        else:
            self._obstacle_s = 0.0
        if self._obstacle_s >= 0.3:
            self._obstacle_s = 0.0
            self._emit("obstacle", f"Препятствие на {state.position_mm:.0f} мм — остановка")
            self.request_hold("Препятствие", "Обнаружено сопротивление движению. Освободите зону и повторите.")

    # ------------------------------------------------------------- commands
    def _capacity_per_side(self) -> float:
        return (float(self.params.get("load.maxKg")) + self._bar_mass()) / 2

    def _torque_percent_to_kg(self, percent: float) -> float:
        return self._capacity_per_side() * percent / 100

    def _profiles(self) -> set[str]:
        return {"training", "calibration", "rangePreview", "service", "return", "guest"}

    def _slow_factor(self) -> float:
        if self.state.sync_status == "critical" and str(self.params.get("sync.desyncAction")) == "slow":
            return 0.5
        return 1.0

    def _brake_command(self) -> DriveCommand:
        return DriveCommand(SideCommand(mode="brake"), SideCommand(mode="brake"))

    def _position_command(self, target_mm: float, limit_kg: float) -> DriveCommand:
        feedforward = self._gravity_comp_per_side()
        target = self._clamp_soft(target_mm)
        return DriveCommand(
            SideCommand(mode="position", target_position_mm=target, force_limit_kg=limit_kg, feedforward_kg=feedforward, weight_comp_kg=feedforward),
            SideCommand(mode="position", target_position_mm=target, force_limit_kg=limit_kg, feedforward_kg=feedforward, weight_comp_kg=feedforward),
        )

    def _velocity_command(self, velocity_mm_s: float, limit_kg: float, *, feedforward: float) -> DriveCommand:
        velocity = max(-float(self.params.get("limits.maxSpeedMmPerSec")), min(float(self.params.get("limits.maxSpeedMmPerSec")), velocity_mm_s))
        weight = self._gravity_comp_per_side()
        return DriveCommand(
            SideCommand(mode="velocity", target_velocity_mm_s=velocity, force_limit_kg=limit_kg, feedforward_kg=feedforward, weight_comp_kg=weight),
            SideCommand(mode="velocity", target_velocity_mm_s=velocity, force_limit_kg=limit_kg, feedforward_kg=feedforward, weight_comp_kg=weight),
        )

    def _torque_command(self, force_per_side: float, limit_kg: float, *, sync: bool) -> DriveCommand:
        corrections = self._last_sync_correction if sync else {"left": 0.0, "right": 0.0}
        left = force_per_side + corrections["left"]
        right = force_per_side + corrections["right"]
        self.state.components["sync"] = round(corrections["right"] - corrections["left"], 2)
        weight = self._gravity_comp_per_side()
        return DriveCommand(
            SideCommand(mode="torque", force_kg=left, force_limit_kg=limit_kg, weight_comp_kg=weight),
            SideCommand(mode="torque", force_kg=right, force_limit_kg=limit_kg, weight_comp_kg=weight),
        )

    def _apply_torque_rate_limit(self, command: DriveCommand, dt: float) -> None:
        rate = float(self.params.get("safety.torqueRateLimitPercentPerSec")) / 100 * self._capacity_per_side() * dt
        gravity = self._gravity_comp_per_side()
        for side in SIDES:
            side_command = command.side(side)
            if side_command.mode == "torque":
                if self._prev_mode[side] != "torque":
                    # brake release / servo hand-over: pre-load the gravity share so the bar does not sag
                    self._prev_torque[side] = gravity
                previous = self._prev_torque[side]
                side_command.force_kg = max(previous - rate, min(previous + rate, side_command.force_kg))
                self._prev_torque[side] = side_command.force_kg
            elif side_command.mode != "brake":
                self._prev_torque[side] = side_command.feedforward_kg
            self._prev_mode[side] = side_command.mode

    def _ramp_velocity(self, target: float, accel: float, dt: float) -> float:
        current = self._filtered_velocity
        step = accel * dt
        return max(current - step, min(current + step, target))

    def _clamp_soft(self, position_mm: float) -> float:
        lower = self.state.working_bottom_mm
        upper = self.state.working_top_mm
        if lower is None or upper is None:
            lower = float(self.params.get("limits.softMinMm"))
            upper = float(self.params.get("limits.softMaxMm"))
        return max(lower, min(upper, position_mm))

    # --------------------------------------------------------------- misc
    def prepare_sync(self, telemetry: AdapterTelemetry) -> None:
        self._last_sync_correction = self._sync_correction(telemetry)

    def refresh_position(self, telemetry: AdapterTelemetry) -> None:
        """Publish the freshest position after the adapter step (removes one-tick lag in snapshots)."""

        self.state.position_mm = round(telemetry.bar_position_mm, 2)
        self.state.sync_delta_mm = round(abs(telemetry.sync_delta_mm), 2)

    def _update_counters(self, dt: float) -> None:
        if self._loaded_active:
            self.state.loaded_seconds_total += dt
        if self.state.mode not in {ControlMode.idle, ControlMode.parked}:
            self.state.idle_s = 0.0

    def _reset_set_counters(self) -> None:
        state = self.state
        state.repetition_count = 0
        state.partial_reps = 0
        state.target_reached = False
        state.spotter_active = False
        state.levitating = False
        self._levitation_factor = 1.0
        state.failure_detected = False
        state.released = False
        state.stall_s = 0.0
        state.concentric_s = 0.0
        state.eccentric_s = 0.0
        state.tempo_label = "—"
        self._load_ramp_kg = 0.0
        self._isokinetic_load = self._clamp_load(self.config.load_kg)
        self._release_s = 0.0
        self._rep_armed = abs(state.position_mm - self.config.start_mm) <= float(self.params.get("detection.repHysteresisMm"))
        self._excursion_min = self._excursion_max = state.position_mm
        self._phase_started = state.time
        self._last_direction_sign = 0
        self._rep_started_at = state.time

    def _fault(self, message: str) -> None:
        if self.state.mode == ControlMode.homing:
            self._homing_reference_pending = False
            self._homing_phase = HomingPhase.fault
            self.state.homing_phase = HomingPhase.fault.value
        self.state.fault_code = message
        self._enter(ControlMode.fault, "Тренажёр заблокирован", message)
        self._emit("fault", message)

    def reset_fault(self) -> None:
        self.state.fault_code = None
        self._hold_position_mm = self.state.position_mm
        self._enter(ControlMode.paused, "Ошибка сброшена", "Приводы в удержании.")

    def _enter(self, mode: ControlMode, label: str, message: str) -> None:
        state = self.state
        if state.mode != mode:
            self._emit("mode", f"{state.mode.value} → {mode.value}: {label}", {"from": state.mode.value, "to": mode.value})
        state.mode = mode
        state.mode_since = state.time
        state.label = label
        state.message = message
        if mode != ControlMode.weightless:
            self._jog_direction = None
        if mode in {ControlMode.moving}:
            self._move_start_mm = state.position_mm
        if mode not in {ControlMode.training}:
            self._loaded_active = False

    def _emit(self, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append(ControllerEvent(self.state.time, kind, message, payload or {}))

    @staticmethod
    def _alpha(cutoff_hz: float, dt: float) -> float:
        if cutoff_hz <= 0:
            return 1.0
        rc = 1 / (2 * math.pi * cutoff_hz)
        return dt / (rc + dt)
