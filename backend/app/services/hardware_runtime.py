"""Hardware runtime: control loop on top of a drive adapter + realtime publishing.

The runtime owns the adapter (physics emulator or Modbus), the motion
controller, the parameter registry, the telemetry recorder and multi-tick
procedures.  It exposes a thread-safe command API for ``HardwareService`` and
publishes snapshots to realtime subscribers.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from collections.abc import Generator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from app.core.config import get_settings
from app.models.enums import DriveState, MachineState, SafetyState
from app.services.motion.adapter import SIDES, AdapterTelemetry, DriveAdapter, DriveCommand
from app.services.motion.controller import ControlMode, MotionController, TrainingConfig
from app.services.motion.emulator import PhysicsEmulatorAdapter
from app.services.motion.keyboard_monitor import KeyboardCombinationMonitor
from app.services.motion.modbus_adapter import ModbusDriveAdapter
from app.services.motion.parameters import MotionParameters
from app.services.motion.procedures import MEASUREMENTS, PROCEDURE_LABELS, SCENARIOS, ProcedureContext
from app.services.motion.recorder import SAMPLE_FIELDS, TelemetryRecorder

DEFAULT_MOTION_TICK_SECONDS = 0.02
BROADCAST_INTERVAL_SECONDS = 0.1
DEBUG_BROADCAST_INTERVAL_SECONDS = 0.1
KEYBOARD_FORCE_KG = 35.0

INCIDENT_EVENT_KINDS = {"fault", "desync", "failure", "obstacle"}
LOAD_MODES = {"normal_weight", "assist_up", "negative_phase", "light_mode", "isokinetic", "bodyweight", "no_machine", "fixed_position", "isometric"}


@dataclass
class DriveRuntimeState:
    side: str
    status: DriveState
    connected: bool
    position_mm: float
    speed_mm_per_sec: float
    acceleration_mm_per_sec2: float
    jerk_mm_per_sec3: float
    torque_limit_percent: int
    current_a: float
    temperature_c: float
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class MotionRuntimeState:
    moving: bool = False
    motion_profile: str = "normal"
    bar_position_mm: float = 860.0
    left_position_mm: float = 860.0
    right_position_mm: float = 860.0
    sync_delta_mm: float = 0.0
    amplitude_percent: int = 0
    tempo_label: str = "стабилен"
    repetition_count: int = 0
    current_set: int = 1
    target_set: int = 1
    target_reps: int = 10
    direction: str = "up"
    lower_bound_mm: float = 640.0
    upper_bound_mm: float = 1320.0
    # extended fields
    control_mode: str = "post"
    partial_reps: int = 0
    load_target_kg: float = 0.0
    load_effective_kg: float = 0.0
    load_mode: str = "normal_weight"
    user_force_kg: float = 0.0
    velocity_mm_per_sec: float = 0.0
    start_point: str = "lower"
    fixed_position_mm: float | None = None


@dataclass
class HardwareCommandRecord:
    id: int
    action: str
    status: str
    created_at: datetime
    payload: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "action": self.action,
            "status": self.status,
            "createdAt": self.created_at.astimezone(UTC).isoformat(),
            "payload": self.payload,
        }


@dataclass
class ProcedureStatus:
    name: str | None = None
    label: str = ""
    status: str = "idle"  # idle | running | done | failed
    step: str = ""
    progress_ticks: int = 0
    result: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "step": self.step,
            "progressTicks": self.progress_ticks,
            "result": self.result,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
        }


@dataclass
class HardwareRuntimeState:
    emulator_mode: bool = True
    machine_state: MachineState = MachineState.ready
    machine_label: str = "Тренажёр готов"
    safety_state: SafetyState = SafetyState.enabled
    safety_message: str = "Система безопасности готова к тренировке."
    selected_user_id: str | None = None
    service_mode: bool = False
    calibration_required: bool = False
    calibration_actual: bool = False
    active_calibration_id: int | None = None
    diagnostics_status: str = "ready"
    last_diagnostics_at: datetime | None = None
    alerts: list[str] = field(default_factory=list)
    drives: dict[str, DriveRuntimeState] = field(default_factory=dict)
    motion: MotionRuntimeState = field(default_factory=MotionRuntimeState)
    recent_commands: deque[HardwareCommandRecord] = field(default_factory=lambda: deque(maxlen=25))


class HardwareRuntime:
    def __init__(self) -> None:
        self._lock = RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._debug_subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._command_counter = 0
        self._keyboard_simulation_enabled = False
        self._keyboard_monitor = KeyboardCombinationMonitor()
        self.tick_seconds = DEFAULT_MOTION_TICK_SECONDS
        self.parameters = MotionParameters()
        self.parameters_dirty = False
        self.emulator: PhysicsEmulatorAdapter | None = None
        self.adapter: DriveAdapter = self._build_adapter()
        self.controller = MotionController(self.parameters)
        self.recorder = TelemetryRecorder(tick_seconds=self.tick_seconds)
        self.last_telemetry: AdapterTelemetry | None = None
        self.last_command: DriveCommand | None = None
        self.procedure = ProcedureStatus()
        self._procedure_generator: Generator[str, None, dict[str, Any]] | None = None
        self._events_seen = 0
        self._last_broadcast = 0.0
        self._last_debug_broadcast = 0.0
        self._debug_batch: list[list[Any]] = []
        self._last_tick_wall = 0.0
        self._last_digest: tuple[Any, ...] = ()
        self.state = self._build_default_state()
        self._refresh_runtime_options()
        self._bootstrap_controller()

    # ------------------------------------------------------------- lifecycle
    def _build_adapter(self) -> DriveAdapter:
        settings = get_settings()
        if getattr(settings, "hardware_adapter", "emulator") == "modbus":
            self.emulator = None
            return ModbusDriveAdapter()
        self.emulator = PhysicsEmulatorAdapter()
        self.emulator.heartbeat_timeout_s = float(self.parameters.get("safety.heartbeatTimeoutMs")) / 1000
        return self.emulator

    def _build_default_state(self) -> HardwareRuntimeState:
        return HardwareRuntimeState(
            emulator_mode=self.emulator is not None,
            drives={
                side: DriveRuntimeState(
                    side=side,
                    status=DriveState.connected,
                    connected=True,
                    position_mm=860.0 if side == "left" else 860.4,
                    speed_mm_per_sec=0.0,
                    acceleration_mm_per_sec2=0.0,
                    jerk_mm_per_sec3=0.0,
                    torque_limit_percent=100,
                    current_a=0.0,
                    temperature_c=31.0,
                )
                for side in SIDES
            },
        )

    def _bootstrap_controller(self) -> None:
        """Power-on sequence: POST → (homing) → idle. Runs inside the control loop."""

        if bool(self.parameters.get("safety.postRequired")):
            self.controller.request_post(self.adapter.self_test())
        else:
            self.controller.state.post_status = "skipped"
            self.controller.request_idle()

    def reset(self) -> None:
        self._refresh_runtime_options()
        with self._lock:
            subscribers = self._subscribers
            debug_subscribers = self._debug_subscribers
            self.parameters = MotionParameters()
            self.adapter = self._build_adapter()
            self.controller = MotionController(self.parameters)
            self.recorder = TelemetryRecorder(tick_seconds=self.tick_seconds)
            self.last_telemetry = None
            self.last_command = None
            self.procedure = ProcedureStatus()
            self._procedure_generator = None
            self._events_seen = 0
            self._last_digest = ()
            self.state = self._build_default_state()
            self._subscribers = subscribers
            self._debug_subscribers = debug_subscribers
            self._command_counter = 0
            self._bootstrap_controller()
            # settle POST/homing synchronously so the first snapshot is meaningful
            for _ in range(5):
                self._tick_motion()
        self._schedule_broadcast()

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._refresh_runtime_options()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._loop = None
        self._keyboard_monitor.stop()

    async def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        with self._lock:
            self._subscribers.add(queue)
        await queue.put(self.snapshot_payload())
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    async def subscribe_debug(self) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=50)
        with self._lock:
            self._debug_subscribers.add(queue)
            recent = self.recorder.recent(250)
        await queue.put({"eventType": "telemetry.batch", "fields": list(SAMPLE_FIELDS), "samples": recent, "events": self.events_payload(40)})
        return queue

    def unsubscribe_debug(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        with self._lock:
            self._debug_subscribers.discard(queue)

    # ----------------------------------------------------------- parameters
    def load_parameters(self, values: dict[str, Any]) -> None:
        with self._lock:
            self.parameters.load_persisted(values)
            self._apply_parameter_side_effects()

    def update_parameters(self, values: dict[str, Any], *, temporary: bool) -> dict[str, tuple[Any, Any]]:
        with self._lock:
            changes = self.parameters.set_many(values, temporary=temporary)
            self._apply_parameter_side_effects()
            for key, (old, new) in changes.items():
                self.controller._emit("param", f"{key}: {old} → {new}", {"key": key, "old": old, "new": new, "temporary": temporary})
            if not temporary and changes:
                self.parameters_dirty = True
        self._schedule_broadcast()
        return changes

    def revert_temporary_parameters(self) -> list[str]:
        with self._lock:
            keys = self.parameters.revert_temporary()
            self._apply_parameter_side_effects()
            if keys:
                self.controller._emit("param", f"Временные параметры сброшены: {len(keys)}", {"keys": keys})
        self._schedule_broadcast()
        return keys

    def reset_parameters(self) -> None:
        with self._lock:
            self.parameters.reset_to_defaults()
            self._apply_parameter_side_effects()
            self.parameters_dirty = True
        self._schedule_broadcast()

    def _apply_parameter_side_effects(self) -> None:
        if self.emulator is not None:
            self.emulator.heartbeat_timeout_s = float(self.parameters.get("safety.heartbeatTimeoutMs")) / 1000
            self.emulator.physics.working_min_mm = float(self.parameters.get("limits.workingMinMm"))
            self.emulator.physics.working_max_mm = float(self.parameters.get("limits.workingMaxMm"))

    def parameters_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "values": self.parameters.effective(),
                "persisted": dict(self.parameters.persisted),
                "temporary": dict(self.parameters.temporary),
            }

    # ------------------------------------------------------------ selection
    def set_selected_user(self, user_id: str | None, *, broadcast: bool = True) -> None:
        with self._lock:
            self.state.selected_user_id = user_id
        if broadcast:
            self._schedule_broadcast()

    def set_calibration_state(self, calibration_id: int | None, required: bool, actual: bool) -> None:
        with self._lock:
            self.state.active_calibration_id = calibration_id
            self.state.calibration_required = required
            self.state.calibration_actual = actual
        self._schedule_broadcast()

    # -------------------------------------------------------------- commands
    def trigger_emergency_stop(self) -> HardwareCommandRecord:
        with self._lock:
            self.adapter.emergency_stop()
            self.controller.request_emergency_stop()
            self._abort_procedure("Аварийная остановка")
            self.state.safety_state = SafetyState.emergency_stop
            self.state.machine_state = MachineState.blocked
            self.state.machine_label = "СТОП активирован"
            self.state.safety_message = "Аварийная остановка активна. Любое движение заблокировано."
            self.state.alerts = ["Аварийная остановка активна"]
            self.recorder.capture_incident("Аварийная остановка", self.parameters.effective(), self.events_payload(80), now=self.controller.state.time)
            command = self._record_command("trigger_emergency_stop", {})
        self._schedule_broadcast()
        return command

    def clear_emergency_stop(self) -> HardwareCommandRecord:
        with self._lock:
            self.adapter.release_emergency_stop()
            self.controller.clear_emergency_stop()
            self.state.safety_state = SafetyState.enabled
            self.state.machine_state = MachineState.ready
            self.state.machine_label = "СТОП снят"
            self.state.safety_message = "Приводы в удержании. Проверьте синхронность перед продолжением."
            self.state.alerts = []
            command = self._record_command("clear_emergency_stop", {})
        self._schedule_broadcast()
        return command

    def set_service_mode(self, enabled: bool) -> HardwareCommandRecord:
        with self._lock:
            self.state.service_mode = enabled
            if not enabled:
                reverted = self.parameters.revert_temporary()
                self._apply_parameter_side_effects()
                if reverted:
                    self.controller._emit("param", f"Выход из сервисного режима: сброшено {len(reverted)} временных параметров")
            command = self._record_command("toggle_service_mode", {"enabled": enabled})
        self._schedule_broadcast()
        return command

    def run_diagnostics(self) -> HardwareCommandRecord:
        with self._lock:
            results = self.adapter.self_test()
            self.controller.state.post_results = [
                {"id": item.id, "label": item.label, "passed": item.passed, "detail": item.detail, "severity": item.severity}
                for item in results
            ]
            failed = [item for item in results if not item.passed and item.severity == "critical"]
            self.state.diagnostics_status = "failed" if failed else "passed"
            self.state.last_diagnostics_at = datetime.now(UTC)
            command = self._record_command("run_diagnostics", {"checks": len(results), "failed": len(failed)})
        self._schedule_broadcast()
        return command

    def run_self_test(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.request_post(self.adapter.self_test())
            command = self._record_command("run_self_test", {})
        self._schedule_broadcast()
        return command

    def home(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.request_homing()
            command = self._record_command("home", {})
        self._schedule_broadcast()
        return command

    def reset_zero_position(self) -> HardwareCommandRecord:
        with self._lock:
            self.adapter.home()
            position = self.controller.state.position_mm
            self.controller._emit("zero", f"Нулевая позиция переустановлена на {position:.1f} мм")
            command = self._record_command("reset_zero_position", {"positionMm": position})
        self._schedule_broadcast()
        return command

    def manual_move(self, direction: str, distance_mm: float, profile: str) -> HardwareCommandRecord:
        with self._lock:
            delta = distance_mm if direction == "up" else -distance_mm
            target = self.controller.state.position_mm + delta
            self.controller.request_move(target, profile="service" if profile == "service" else "return", then=ControlMode.paused, label="Ручное перемещение")
            self.state.motion.motion_profile = profile
            command = self._record_command("manual_move", {"direction": direction, "distanceMm": distance_mm, "profile": profile})
        self._schedule_broadcast()
        return command

    def start_motion(
        self,
        *,
        calibration_id: int | None,
        lower_bound_mm: float,
        upper_bound_mm: float,
        target_set: int,
        target_reps: int,
        motion_profile: str,
        load_kg: float = 20.0,
        load_mode: str = "normal_weight",
        start_point: str = "lower",
        warmup: bool = False,
        guest: bool = False,
        asymmetric_allowed: bool = False,
        rep_count_source: str = "motion",
        fixed_position_mm: float | None = None,
        isometric_duration_s: float = 20.0,
        wait_for_grip: bool = False,
        auto_user: bool | None = None,
    ) -> HardwareCommandRecord:
        with self._lock:
            config = TrainingConfig(
                lower_mm=lower_bound_mm,
                upper_mm=upper_bound_mm,
                start_point=start_point if start_point in {"lower", "upper", "custom"} else "lower",  # type: ignore[arg-type]
                load_kg=load_kg,
                load_mode=load_mode if load_mode in LOAD_MODES else "normal_weight",  # type: ignore[arg-type]
                target_reps=min(max(target_reps, 1), 50),
                target_set=min(max(target_set, 1), 12),
                warmup=warmup,
                guest=guest,
                asymmetric_allowed=asymmetric_allowed,
                rep_count_source=rep_count_source if rep_count_source in {"motion", "load", "manual", "timer"} else "motion",  # type: ignore[arg-type]
                fixed_position_mm=fixed_position_mm,
                isometric_position_mm=fixed_position_mm,
                isometric_duration_s=isometric_duration_s,
                motion_profile="training" if motion_profile in {"machine", "normal", "training"} else motion_profile,
                calibration_id=calibration_id,
            )
            self.state.active_calibration_id = calibration_id
            self.state.calibration_required = True
            self.state.calibration_actual = calibration_id is not None
            self.state.motion.motion_profile = config.motion_profile
            self.state.motion.lower_bound_mm = lower_bound_mm
            self.state.motion.upper_bound_mm = upper_bound_mm
            self.state.motion.current_set = config.target_set
            self.state.motion.target_set = config.target_set
            self.state.motion.target_reps = config.target_reps
            self.state.motion.load_mode = config.load_mode
            self.state.motion.start_point = config.start_point
            self.state.motion.fixed_position_mm = fixed_position_mm
            if wait_for_grip:
                self.controller.request_start_hold(config)
            else:
                self.controller.request_training(config)
            use_auto_user = auto_user if auto_user is not None else (self.emulator is not None and not self._keyboard_simulation_enabled)
            if self.emulator is not None and use_auto_user and config.load_mode not in {"fixed_position", "isometric", "bodyweight", "no_machine"}:
                self.emulator.set_scenario(
                    "steady_set",
                    strength_kg=max(40.0, load_kg * 1.8),
                    lower_mm=lower_bound_mm,
                    upper_mm=upper_bound_mm,
                    period_s=3.0,
                )
            self.state.machine_state = MachineState.ready
            self.state.motion.moving = True
            self.state.alerts = []
            command = self._record_command(
                "start_motion",
                {
                    "calibrationId": calibration_id,
                    "lowerBoundMm": lower_bound_mm,
                    "upperBoundMm": upper_bound_mm,
                    "targetSet": target_set,
                    "targetReps": target_reps,
                    "motionProfile": config.motion_profile,
                    "loadKg": load_kg,
                    "loadMode": config.load_mode,
                    "startPoint": config.start_point,
                },
            )
        self._schedule_broadcast()
        return command

    def move_to_start(self, *, lower_bound_mm: float, upper_bound_mm: float, start_point: str = "lower", custom_mm: float | None = None, **training_kwargs: Any) -> HardwareCommandRecord:
        """Bring the bar to the exercise start point and wait for grip."""

        with self._lock:
            config = TrainingConfig(
                lower_mm=lower_bound_mm,
                upper_mm=upper_bound_mm,
                start_point=start_point if start_point in {"lower", "upper", "custom"} else "lower",  # type: ignore[arg-type]
                start_custom_mm=custom_mm,
                load_kg=float(training_kwargs.get("load_kg", 20.0)),
                load_mode=training_kwargs.get("load_mode", "normal_weight"),
                target_reps=int(training_kwargs.get("target_reps", 10)),
                target_set=int(training_kwargs.get("target_set", 1)),
                guest=bool(training_kwargs.get("guest", False)),
                warmup=bool(training_kwargs.get("warmup", False)),
                calibration_id=training_kwargs.get("calibration_id"),
            )
            self.controller.config = config
            self.controller._reset_set_counters()
            self.state.motion.lower_bound_mm = lower_bound_mm
            self.state.motion.upper_bound_mm = upper_bound_mm
            self.state.motion.start_point = config.start_point
            self.state.motion.load_mode = config.load_mode
            self.controller.request_move(config.start_mm, profile="return", then=ControlMode.start_hold, label="Подвод в стартовую точку")
            if self.emulator is not None:
                self.emulator.set_scenario("none")
            command = self._record_command("move_to_start", {"targetMm": config.start_mm, "startPoint": config.start_point})
        self._schedule_broadcast()
        return command

    def start_fixed_position(self, *, position_mm: float, target_reps: int = 10, rep_count_source: str = "load", body_weight_kg: float = 0.0) -> HardwareCommandRecord:
        with self._lock:
            config = TrainingConfig(
                lower_mm=position_mm - 1,
                upper_mm=position_mm + 1,
                load_mode="fixed_position",
                fixed_position_mm=position_mm,
                target_reps=target_reps,
                rep_count_source=rep_count_source if rep_count_source in {"motion", "load", "manual", "timer"} else "load",  # type: ignore[arg-type]
            )
            self.controller.config = config
            self.controller._reset_set_counters()
            self.state.motion.load_mode = "fixed_position"
            self.state.motion.fixed_position_mm = position_mm
            self.state.motion.target_reps = target_reps
            self.controller.request_move(position_mm, profile="return", then=ControlMode.fixed_hold, label="Выход на высоту фиксации")
            if self.emulator is not None:
                self.emulator.set_scenario("none")
            command = self._record_command("start_fixed_position", {"positionMm": position_mm, "bodyWeightKg": body_weight_kg})
        self._schedule_broadcast()
        return command

    def range_preview(self, lower_mm: float, upper_mm: float) -> HardwareCommandRecord:
        with self._lock:
            self.controller.config.lower_mm = lower_mm
            self.controller.config.upper_mm = upper_mm
            self.state.motion.lower_bound_mm = lower_mm
            self.state.motion.upper_bound_mm = upper_mm
            self._start_procedure("range_preview", self._range_preview_procedure(lower_mm, upper_mm))
            command = self._record_command("range_preview", {"lowerMm": lower_mm, "upperMm": upper_mm})
        self._schedule_broadcast()
        return command

    def _range_preview_procedure(self, lower_mm: float, upper_mm: float) -> Generator[str, None, dict[str, Any]]:
        ctx = ProcedureContext(self)
        self.controller.request_move(lower_mm, profile="rangePreview", then=ControlMode.paused, label="Показ диапазона: нижняя точка")
        yield from ctx.wait_until(lambda: self.controller.state.mode != ControlMode.moving, 90.0, "Нижняя точка")
        yield from ctx.wait(0.6, "Пауза в нижней точке")
        self.controller.request_move(upper_mm, profile="rangePreview", then=ControlMode.paused, label="Показ диапазона: верхняя точка")
        yield from ctx.wait_until(lambda: self.controller.state.mode != ControlMode.moving, 120.0, "Верхняя точка")
        return {"lowerMm": lower_mm, "upperMm": upper_mm, "confirmed": True}

    def enter_weightless(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.request_weightless()
            if self.emulator is not None:
                self.emulator.set_scenario("none")
            command = self._record_command("enter_weightless", {})
        self._schedule_broadcast()
        return command

    def capture_point(self, which: str) -> tuple[HardwareCommandRecord, float | None]:
        with self._lock:
            state = self.controller.state
            still_needed = float(self.parameters.get("regulator.stillnessMs"))
            if state.mode != ControlMode.weightless:
                raise PermissionError("Фиксация точки доступна только в режиме невесомого грифа")
            if state.still_ms < still_needed:
                raise PermissionError(f"Гриф должен быть неподвижен не менее {still_needed:.0f} мс")
            position = self.controller.mark_position_captured(which)
            if which == "lower":
                self.state.motion.lower_bound_mm = position
                self.controller.config.lower_mm = position
            elif which == "upper":
                self.state.motion.upper_bound_mm = position
                self.controller.config.upper_mm = position
            elif which == "fixed":
                self.state.motion.fixed_position_mm = position
                self.controller.config.fixed_position_mm = position
            command = self._record_command("capture_point", {"which": which, "positionMm": position})
        self._schedule_broadcast()
        return command, position

    def hold(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.request_hold()
            self._abort_procedure("Удержание по команде")
            if self.emulator is not None:
                self.emulator.set_scenario("none")
            command = self._record_command("hold", {})
        self._schedule_broadcast()
        return command

    def pause(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.request_pause()
            if self.emulator is not None:
                self.emulator.set_scenario("none")
            command = self._record_command("pause", {})
        self._schedule_broadcast()
        return command

    def resume(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.request_resume()
            if self.emulator is not None and self.controller.config.load_mode not in {"fixed_position", "isometric"} and not self._keyboard_simulation_enabled:
                config = self.controller.config
                self.emulator.set_scenario("steady_set", strength_kg=max(40.0, config.load_kg * 1.8), lower_mm=config.lower_mm, upper_mm=config.upper_mm, period_s=3.0)
            command = self._record_command("resume", {})
        self._schedule_broadcast()
        return command

    def park(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.request_park()
            if self.emulator is not None:
                self.emulator.set_scenario("none")
            command = self._record_command("park", {})
        self._schedule_broadcast()
        return command

    def set_load(self, load_kg: float) -> HardwareCommandRecord:
        with self._lock:
            self.controller.set_load(load_kg)
            self.state.motion.load_target_kg = self.controller.config.load_kg
            command = self._record_command("set_load", {"loadKg": self.controller.config.load_kg})
        self._schedule_broadcast()
        return command

    def manual_rep(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.manual_rep()
            command = self._record_command("manual_rep", {"repetitionCount": self.controller.state.repetition_count})
        self._schedule_broadcast()
        return command

    def complete_set(self) -> HardwareCommandRecord:
        with self._lock:
            self.controller.complete_set()
            if self.emulator is not None:
                self.emulator.set_scenario("none")
            self.state.machine_label = "Подход завершён"
            command = self._record_command("complete_set", {"repetitionCount": self.controller.state.repetition_count})
        self._schedule_broadcast()
        return command

    def reset_fault(self) -> HardwareCommandRecord:
        with self._lock:
            self.adapter.reset_errors()
            if self.emulator is not None:
                self.emulator.clear_faults()
            self.controller.reset_fault()
            command = self._record_command("reset_fault", {})
        self._schedule_broadcast()
        return command

    def align_sides(self) -> HardwareCommandRecord:
        with self._lock:
            if not self.state.service_mode:
                raise PermissionError("Выравнивание сторон доступно только в сервисном режиме")
            self.controller.request_move(self.controller.state.position_mm, profile="service", then=ControlMode.paused, label="Выравнивание сторон", obstacle_check=False)
            command = self._record_command("align_sides", {"syncDeltaMm": self.controller.state.sync_delta_mm})
        self._schedule_broadcast()
        return command

    # ---------------------------------------------------------- procedures
    def start_procedure(self, name: str, **kwargs: Any) -> ProcedureStatus:
        with self._lock:
            factory = MEASUREMENTS.get(name) or SCENARIOS.get(name)
            if factory is None:
                raise LookupError(f"Неизвестная процедура: {name}")
            if self.controller.state.mode in {ControlMode.estop, ControlMode.fault}:
                raise PermissionError("Процедуры недоступны при СТОП или ошибке")
            if self.procedure.status == "running":
                raise PermissionError(f"Уже выполняется: {self.procedure.label}")
            generator = factory(ProcedureContext(self), **kwargs) if kwargs else factory(ProcedureContext(self))
            self._start_procedure(name, generator)
            self._record_command("procedure", {"name": name, **kwargs})
        self._schedule_broadcast()
        return self.procedure

    def _start_procedure(self, name: str, generator: Generator[str, None, dict[str, Any]]) -> None:
        self._procedure_generator = generator
        self.procedure = ProcedureStatus(name=name, label=PROCEDURE_LABELS.get(name, name), status="running", started_at=datetime.now(UTC).isoformat())
        self.controller._emit("procedure", f"Запуск: {self.procedure.label}")

    def abort_procedure(self) -> ProcedureStatus:
        with self._lock:
            self._abort_procedure("Прервано пользователем")
            if self.controller.state.mode not in {ControlMode.estop, ControlMode.fault}:
                self.controller.request_hold("Процедура прервана", "Гриф удерживается.")
            if self.emulator is not None:
                self.emulator.set_scenario("none")
                self.emulator.set_user_force(0.0)
        self._schedule_broadcast()
        return self.procedure

    def _abort_procedure(self, reason: str) -> None:
        if self._procedure_generator is not None:
            self._procedure_generator.close()
            self._procedure_generator = None
            self.procedure.status = "failed"
            self.procedure.result = {"error": reason}
            self.procedure.finished_at = datetime.now(UTC).isoformat()

    def _step_procedure(self) -> None:
        generator = self._procedure_generator
        if generator is None:
            return
        try:
            step = next(generator)
            self.procedure.step = step
            self.procedure.progress_ticks += 1
        except StopIteration as stop:
            self._procedure_generator = None
            self.procedure.status = "done" if not (isinstance(stop.value, dict) and stop.value.get("error")) else "failed"
            self.procedure.result = stop.value if isinstance(stop.value, dict) else {}
            self.procedure.finished_at = datetime.now(UTC).isoformat()
            self.controller._emit("procedure", f"Завершено: {self.procedure.label}", {"result": self.procedure.result})
            if self.emulator is not None:
                self.emulator.set_scenario("none")
                self.emulator.set_user_force(0.0)
        except Exception as error:  # noqa: BLE001 - procedure failures must not kill the loop
            self._procedure_generator = None
            self.procedure.status = "failed"
            self.procedure.result = {"error": str(error)}
            self.procedure.finished_at = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------- emulator
    def emulator_control(self, action: str, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            if self.emulator is None:
                raise PermissionError("Эмулятор не активен — команда доступна только в режиме эмуляции")
            if action == "user_force":
                self.emulator.set_user_force(float(kwargs.get("force_kg", 0.0)), float(kwargs.get("bias", 0.0)))
            elif action == "scenario":
                self.emulator.set_scenario(kwargs.get("name", "none"), **{k: v for k, v in kwargs.items() if k != "name"})
            elif action == "fault":
                self.emulator.inject_fault(kwargs["fault"], kwargs.get("side"), kwargs.get("value"))
            elif action == "clear_faults":
                self.emulator.clear_faults()
            elif action == "physics":
                self.emulator.set_physics(**{k: v for k, v in kwargs.items() if v is not None})
            else:
                raise ValueError(f"Неизвестное действие эмулятора: {action}")
            self._record_command(f"emulator:{action}", {k: v for k, v in kwargs.items() if v is not None})
            payload = self.emulator_payload()
        self._schedule_broadcast()
        return payload

    def emulator_payload(self) -> dict[str, Any]:
        if self.emulator is None:
            return {"active": False}
        scenario = self.emulator.scenario
        return {
            "active": True,
            "physics": asdict(self.emulator.physics),
            "userForceKg": scenario.manual_force_kg,
            "userBias": scenario.manual_bias,
            "scenario": {"name": scenario.name, "strengthKg": scenario.strength_kg, "periodS": scenario.period_s, "repsDone": scenario.reps_done, "tiltBias": scenario.tilt_bias},
            "faults": {
                "powerLoss": self.emulator.faults.power_loss,
                "physicalEstop": self.emulator.faults.physical_estop,
                "commLost": sorted(self.emulator.faults.comm_lost),
                "encoderDrift": dict(self.emulator.faults.encoder_drift),
                "overheat": sorted(self.emulator.faults.overheat),
            },
            "events": self.emulator.events[-20:],
        }

    # ------------------------------------------------------------ recording
    def recording_control(self, action: str, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            if action == "start":
                self.recorder.start_manual(len(self.controller.events))
                return {"recording": True}
            if action == "stop":
                recording = self.recorder.stop_manual(kwargs.get("title") or "Запись", kwargs.get("comment") or "", self.parameters.effective(), self.events_payload(400))
                return recording.to_summary()
            if action == "snapshot":
                recording = self.recorder.save_snapshot(kwargs.get("title") or "Снимок", kwargs.get("comment") or "", self.parameters.effective(), self.events_payload(400), seconds=float(kwargs.get("seconds", 20)), tick=self.tick_seconds)
                return recording.to_summary()
            raise ValueError(f"Неизвестное действие записи: {action}")

    def events_payload(self, limit: int = 100) -> list[dict[str, Any]]:
        events = list(self.controller.events)[-limit:]
        return [event.to_payload() for event in events]

    # -------------------------------------------------------------- snapshot
    def snapshot_payload(self) -> dict[str, object]:
        with self._lock:
            control = self.controller.state
            drives = [asdict(item) for item in self.state.drives.values()]
            machine_state = self.state.machine_state
            payload = {
                "eventType": "hardware.snapshot",
                "emittedAt": datetime.now(UTC).isoformat(),
                "machine": {
                    "machineState": machine_state.value,
                    "machineLabel": self.state.machine_label,
                    "leftDrive": self.state.drives["left"].status.value,
                    "rightDrive": self.state.drives["right"].status.value,
                    "safety": self.state.safety_state.value,
                    "calibration": "Калибровка актуальна" if self.state.calibration_actual else ("Калибровка требуется" if self.state.calibration_required else "Калибровка не требуется"),
                },
                "safety": {
                    "state": self.state.safety_state.value,
                    "label": "Аварийная остановка" if self.state.safety_state == SafetyState.emergency_stop else ("Защита отключена" if self.state.safety_state == SafetyState.disabled else "Безопасность включена"),
                    "message": self.state.safety_message,
                    "requiresService": self.state.safety_state == SafetyState.emergency_stop or self.state.service_mode,
                    "activeEventId": None,
                },
                "emulatorMode": self.state.emulator_mode,
                "serviceMode": self.state.service_mode,
                "selectedUserId": self.state.selected_user_id,
                "userSelected": self.state.selected_user_id is not None,
                "drives": [
                    {
                        **drive,
                        "status": str(drive["status"].value if hasattr(drive["status"], "value") else drive["status"]),
                    }
                    for drive in drives
                ],
                "motion": asdict(self.state.motion),
                "control": self._control_payload(),
                "procedure": self.procedure.to_payload(),
                "calibrationRequired": self.state.calibration_required,
                "calibrationActual": self.state.calibration_actual,
                "activeCalibrationId": self.state.active_calibration_id,
                "commandQueueDepth": len(self.state.recent_commands),
                "lastCommand": self.state.recent_commands[-1].to_payload() if self.state.recent_commands else None,
                "diagnosticsStatus": self.state.diagnostics_status,
                "lastDiagnosticsAt": self.state.last_diagnostics_at.isoformat() if self.state.last_diagnostics_at else None,
                "alerts": list(dict.fromkeys([*self.state.alerts, *control.alerts])),
            }
        return payload

    def _control_payload(self) -> dict[str, Any]:
        control = self.controller.state
        telemetry = self.last_telemetry
        return {
            "mode": control.mode.value,
            "label": control.label,
            "message": control.message,
            "positionMm": control.position_mm,
            "velocityMmPerSec": control.velocity_mm_s,
            "accelerationMmPerSec2": round(control.acceleration_mm_s2, 1),
            "userForceKg": control.user_force_kg,
            "userForceLeftKg": control.user_force_left_kg,
            "userForceRightKg": control.user_force_right_kg,
            "loadTargetKg": control.load_target_kg,
            "loadEffectiveKg": control.load_effective_kg,
            "components": control.components,
            "repetitionCount": control.repetition_count,
            "partialReps": control.partial_reps,
            "concentricS": control.concentric_s,
            "eccentricS": control.eccentric_s,
            "tempoLabel": control.tempo_label,
            "repQuality": control.rep_quality,
            "targetReached": control.target_reached,
            "syncDeltaMm": control.sync_delta_mm,
            "syncStatus": control.sync_status,
            "asymmetryPercent": control.asymmetry_percent,
            "gripDetected": control.grip_detected,
            "released": control.released,
            "stallS": round(control.stall_s, 2),
            "spotterActive": control.spotter_active,
            "failureDetected": control.failure_detected,
            "stillMs": round(control.still_ms),
            "postStatus": control.post_status,
            "postResults": control.post_results,
            "homed": control.homed,
            "positionKnown": control.position_known,
            "heartbeatOk": control.heartbeat_ok,
            "commOk": control.comm_ok,
            "powerOk": control.power_ok,
            "brakeEngaged": control.brake_engaged,
            "fixedHoldTestPassed": control.fixed_hold_test_passed,
            "fixedDriftMm": control.fixed_drift_mm,
            "isometricElapsedS": round(control.isometric_elapsed_s, 1),
            "moveTargetMm": control.move_target_mm,
            "moveProgressPercent": control.move_progress_percent,
            "faultCode": control.fault_code,
            "tickLatencyMs": control.tick_latency_ms,
            "missedTicks": control.missed_ticks,
            "counters": {
                "travelMmTotal": round(control.travel_mm_total),
                "cyclesTotal": control.cycles_total,
                "loadedSecondsTotal": round(control.loaded_seconds_total),
            },
            "config": {
                "lowerMm": self.controller.config.lower_mm,
                "upperMm": self.controller.config.upper_mm,
                "startPoint": self.controller.config.start_point,
                "loadKg": self.controller.config.load_kg,
                "loadMode": self.controller.config.load_mode,
                "targetReps": self.controller.config.target_reps,
                "fixedPositionMm": self.controller.config.fixed_position_mm,
            },
            "brakes": {side: telemetry.side(side).brake_engaged for side in SIDES} if telemetry else {},
            "limitSwitches": {side: telemetry.side(side).limit_switch_low for side in SIDES} if telemetry else {},
            "adapter": self.adapter.name,
            "temporaryParameters": len(self.parameters.temporary),
        }

    # ------------------------------------------------------------- the loop
    async def _run(self) -> None:
        try:
            next_tick = time.monotonic()
            while True:
                next_tick += self.tick_seconds
                delay = next_tick - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    next_tick = time.monotonic()  # fell behind (e.g. blocked loop) — resync instead of bursting
                    await asyncio.sleep(0)
                changed = self._tick_motion()
                now = time.monotonic()
                if changed and now - self._last_broadcast >= BROADCAST_INTERVAL_SECONDS:
                    self._last_broadcast = now
                    await self._broadcast_snapshot()
                if self._debug_subscribers and now - self._last_debug_broadcast >= DEBUG_BROADCAST_INTERVAL_SECONDS:
                    self._last_debug_broadcast = now
                    await self._broadcast_debug()
        except asyncio.CancelledError:
            raise

    def _tick_motion(self) -> bool:
        """One control tick. Returns True when state changed (always true while running)."""

        with self._lock:
            wall = time.perf_counter()
            if self._last_tick_wall:
                latency = (wall - self._last_tick_wall) * 1000
                self.controller.state.tick_latency_ms = round(latency, 1)
                if latency > self.tick_seconds * 1000 * 2.5:
                    self.controller.state.missed_ticks += 1
            self._last_tick_wall = wall

            dt = self.tick_seconds
            self._apply_keyboard_virtual_hand()
            telemetry = self.last_telemetry or self.adapter.read()
            self.controller.prepare_sync(telemetry)
            command = self.controller.tick(telemetry, dt)
            if self.controller.homing_ready_to_zero:
                self.adapter.home()
            telemetry = self.adapter.step(command, dt)
            self.last_telemetry = telemetry
            self.last_command = command
            self.controller.refresh_position(telemetry)
            self._step_procedure()
            self._sync_runtime_state(telemetry, command)
            self._record_sample(telemetry, command)
            self._handle_new_events()
            digest = self._digest()
            changed = digest != self._last_digest
            self._last_digest = digest
            return changed

    def _digest(self) -> tuple[Any, ...]:
        control = self.controller.state
        return (
            control.mode,
            round(control.position_mm),
            control.repetition_count,
            control.partial_reps,
            control.sync_status,
            control.label,
            tuple(control.alerts),
            self.procedure.status,
            self.procedure.step,
            round(control.user_force_kg),
            round(control.load_effective_kg),
            self.state.machine_state,
            control.still_ms >= float(self.parameters.get("regulator.stillnessMs")),
        )

    def _apply_keyboard_virtual_hand(self) -> None:
        if not self._keyboard_simulation_enabled or self.emulator is None:
            return
        direction = self._get_keyboard_direction()
        if direction is not None and self.controller.state.mode == ControlMode.paused and self.controller.state.released:
            self.controller.request_resume()
        if direction == "up":
            self.emulator.set_user_force(KEYBOARD_FORCE_KG + self.controller.state.load_effective_kg)
        elif direction == "down":
            self.emulator.set_user_force(-KEYBOARD_FORCE_KG)
        elif self.emulator.scenario.name == "none" and self.emulator.scenario.manual_force_kg != 0.0 and getattr(self, "_keyboard_was_pressed", False):
            self.emulator.set_user_force(0.0)
        self._keyboard_was_pressed = direction is not None

    def _sync_runtime_state(self, telemetry: AdapterTelemetry, command: DriveCommand) -> None:
        control = self.controller.state
        motion = self.state.motion
        motion.moving = control.moving or control.mode in {ControlMode.training, ControlMode.moving, ControlMode.homing}
        motion.bar_position_mm = round(control.position_mm, 1)
        motion.left_position_mm = round(telemetry.left.position_mm, 1)
        motion.right_position_mm = round(telemetry.right.position_mm, 1)
        motion.sync_delta_mm = control.sync_delta_mm
        motion.amplitude_percent = control.amplitude_percent
        motion.tempo_label = control.tempo_label if control.mode == ControlMode.training else ("остановлен" if not control.moving else "движение")
        motion.repetition_count = control.repetition_count
        motion.partial_reps = control.partial_reps
        motion.direction = control.direction
        motion.control_mode = control.mode.value
        motion.load_target_kg = control.load_target_kg
        motion.load_effective_kg = control.load_effective_kg
        motion.user_force_kg = control.user_force_kg
        motion.velocity_mm_per_sec = control.velocity_mm_s
        motion.lower_bound_mm = self.controller.config.lower_mm
        motion.upper_bound_mm = self.controller.config.upper_mm
        if control.mode == ControlMode.training:
            motion.motion_profile = self.controller.config.motion_profile
        elif control.mode == ControlMode.weightless:
            motion.motion_profile = "weightless"
        elif control.mode in {ControlMode.moving, ControlMode.homing}:
            motion.motion_profile = "return" if control.mode == ControlMode.moving else "calibration"

        for side in SIDES:
            side_t = telemetry.side(side)
            drive = self.state.drives[side]
            drive.position_mm = round(side_t.position_mm, 1)
            drive.speed_mm_per_sec = round(abs(side_t.velocity_mm_s), 1)
            drive.acceleration_mm_per_sec2 = round(abs(control.acceleration_mm_s2), 1)
            drive.current_a = side_t.current_a
            drive.temperature_c = side_t.temperature_c
            drive.torque_limit_percent = int(min(100, round(command.side(side).force_limit_kg / max(1.0, self.controller._capacity_per_side()) * 100)))
            drive.connected = side_t.connected
            drive.error_code = side_t.error_code
            drive.error_message = side_t.error_message
            if not side_t.connected or side_t.error_code:
                drive.status = DriveState.error
            elif side_t.temperature_c >= float(self.parameters.get("safety.tempWarnC")) or side_t.current_a >= float(self.parameters.get("safety.currentWarnA")):
                drive.status = DriveState.warning
            else:
                drive.status = DriveState.connected

        if self.state.safety_state == SafetyState.emergency_stop:
            return
        if control.mode == ControlMode.fault:
            self.state.machine_state = MachineState.blocked
            self.state.machine_label = "Тренажёр заблокирован"
            self.state.safety_message = control.fault_code or control.message
        elif control.sync_status in {"warning", "critical"} or self.state.service_mode or control.mode == ControlMode.post or not control.position_known:
            self.state.machine_state = MachineState.warning
            self.state.machine_label = "Сервисный режим" if self.state.service_mode and control.mode in {ControlMode.idle, ControlMode.parked, ControlMode.paused} else control.label
            self.state.safety_message = control.message
        else:
            self.state.machine_state = MachineState.ready
            self.state.machine_label = control.label
            self.state.safety_message = control.message or "Система безопасности готова к тренировке."
        self.state.alerts = ["Сервисный режим активен"] if self.state.service_mode else []

    def _record_sample(self, telemetry: AdapterTelemetry, command: DriveCommand) -> None:
        control = self.controller.state
        sample = [
            round(control.time, 3),
            control.mode.value,
            round(telemetry.left.position_mm, 2),
            round(telemetry.right.position_mm, 2),
            round(telemetry.left.velocity_mm_s, 1),
            round(telemetry.right.velocity_mm_s, 1),
            control.velocity_mm_s,
            round(control.acceleration_mm_s2, 1),
            telemetry.left.force_kg,
            telemetry.right.force_kg,
            control.user_force_kg,
            control.load_target_kg,
            control.load_effective_kg,
            round(telemetry.sync_delta_mm, 2),
            telemetry.left.current_a,
            telemetry.right.current_a,
            telemetry.left.temperature_c,
            telemetry.right.temperature_c,
            control.repetition_count,
            control.amplitude_percent,
            round(command.left.force_kg if command.left.mode == "torque" else command.left.feedforward_kg, 2),
            round(command.right.force_kg if command.right.mode == "torque" else command.right.feedforward_kg, 2),
        ]
        self.recorder.append(sample)
        if self._debug_subscribers:
            self._debug_batch.append(sample)

    def _handle_new_events(self) -> None:
        events = list(self.controller.events)
        new_events = events[self._events_seen :] if self._events_seen <= len(events) else events
        self._events_seen = len(events)
        for event in new_events:
            if event.kind in INCIDENT_EVENT_KINDS:
                self.recorder.capture_incident(event.message, self.parameters.effective(), self.events_payload(80), now=self.controller.state.time)

    def _refresh_runtime_options(self) -> None:
        settings = get_settings()
        self._keyboard_simulation_enabled = bool(settings.hardware_keyboard_simulation_enabled and os.name == "nt")
        if self._keyboard_simulation_enabled:
            self._keyboard_monitor.start()
        else:
            self._keyboard_monitor.stop()

    def _get_keyboard_direction(self) -> str | None:
        if not self._keyboard_simulation_enabled:
            return None
        return self._keyboard_monitor.get_direction()

    def _record_command(self, action: str, payload: dict[str, object]) -> HardwareCommandRecord:
        self._command_counter += 1
        command = HardwareCommandRecord(
            id=self._command_counter,
            action=action,
            status="completed",
            created_at=datetime.now(UTC),
            payload=payload,
        )
        self.state.recent_commands.append(command)
        return command

    def _schedule_broadcast(self) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self._broadcast_snapshot(), self._loop)

    async def _broadcast_snapshot(self) -> None:
        payload = self.snapshot_payload()
        with self._lock:
            subscribers = list(self._subscribers)
        stale: list[asyncio.Queue[dict[str, object]]] = []
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except asyncio.QueueFull:
                stale.append(subscriber)
        if stale:
            with self._lock:
                for subscriber in stale:
                    self._subscribers.discard(subscriber)

    async def _broadcast_debug(self) -> None:
        with self._lock:
            batch = self._debug_batch
            self._debug_batch = []
            subscribers = list(self._debug_subscribers)
            events = self.events_payload(10)
            control = self._control_payload()
        payload = {"eventType": "telemetry.batch", "fields": list(SAMPLE_FIELDS), "samples": batch, "events": events, "control": control}
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except asyncio.QueueFull:
                with self._lock:
                    self._debug_subscribers.discard(subscriber)


hardware_runtime = HardwareRuntime()
