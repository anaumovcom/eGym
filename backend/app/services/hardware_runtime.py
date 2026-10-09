"""Minimal safe hardware runtime (plan 16, stage 1 / M0).

The v1 motion stack is removed. Until the v2 ``motor-rt`` process takes over
(plan 16, stage 5) this runtime only:

* holds upward support ``support_raw`` (PA_12C ≈ +100) on both drives,
  refreshed every ``SUPPORT_REFRESH_S``; the first write is support, never 0;
* latches E-stop (support), drive/bus faults (support) and overspeed (0);
* leaves PA_12C to the debug panel while its manual torque is active;
* runs calibration sessions (service mode, dead-man, envelope) step by step
  inside the tick: the session writes PA_12C instead of support until it ends;
* publishes position/telemetry snapshots and serves the physical panel.

Every motion request is rejected with ``MOTION_DISABLED_MESSAGE``.
Safety requirements: ``app/motor/SAFETY_REQUIREMENTS.md``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from app.core.config import get_settings
from app.models.enums import DriveState, MachineState, SafetyState
from app.motor.calibration.graph import BY_CODE, RUNNABLE
from app.motor.calibration.graph import status as calibration_status
from app.motor.calibration.runner import Frame
from app.motor.calibration.session import ON_STOPS_MM, CalibrationSession
from app.motor.drive.lichuan import LichuanTorqueDrive
from app.motor.drive.protocol import DriveSample, TorqueDrive
from app.motor.profile import MachineProfile, SafetyEnvelope
from app.motor.twin.bench import TwinBench
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES, Side, rpm_to_mm_s
from app.services.modbus_service import modbus_service
from app.services.panel.bridge import PanelBridge, PanelBridgeConfig
from app.services.panel.protocol import (
    PanelButtonEvent,
    PanelEvent,
    PanelFaultEvent,
    PanelStatusEvent,
)

logger = logging.getLogger(__name__)

TICK_SECONDS = 0.05
SUPPORT_REFRESH_S = 0.2
ZERO_SYNC_MAX_MM = 50.0
BROADCAST_INTERVAL_SECONDS = 0.1
MOTION_DISABLED_MESSAGE = "Управление двигателями переводится на v2: движение и нагрузка временно отключены, приводы держат поддержку"
SERVO_OFF_MESSAGE = "Приводы выключены (Servo OFF): гриф не поддерживается. Включить — в сервисном режиме"


@dataclass
class DriveRuntimeState:
    side: str
    status: DriveState = DriveState.connected
    connected: bool = True
    position_mm: float = 0.0
    speed_mm_per_sec: float = 0.0
    acceleration_mm_per_sec2: float = 0.0
    jerk_mm_per_sec3: float = 0.0
    torque_limit_percent: int = 100
    current_a: float = 0.0
    temperature_c: float = 0.0
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class MotionRuntimeState:
    moving: bool = False
    motion_profile: str = "support"
    bar_position_mm: float = 0.0
    left_position_mm: float = 0.0
    right_position_mm: float = 0.0
    sync_delta_mm: float = 0.0
    amplitude_percent: int = 0
    tempo_label: str = "остановлен"
    repetition_count: int = 0
    current_set: int = 1
    target_set: int = 1
    target_reps: int = 10
    direction: str = "up"
    lower_bound_mm: float = 0.0
    upper_bound_mm: float = 0.0
    control_mode: str = "support"
    velocity_mm_per_sec: float = 0.0


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
class HardwareRuntimeState:
    emulator_mode: bool = True
    machine_state: MachineState = MachineState.warning
    machine_label: str = "Управление двигателями отключено"
    safety_state: SafetyState = SafetyState.enabled
    safety_message: str = MOTION_DISABLED_MESSAGE
    selected_user_id: str | None = None
    service_mode: bool = False
    calibration_required: bool = False
    calibration_actual: bool = False
    active_calibration_id: int | None = None
    diagnostics_status: str = "ready"
    last_diagnostics_at: datetime | None = None
    alerts: list[str] = field(default_factory=list)
    drives: dict[str, DriveRuntimeState] = field(default_factory=lambda: {side: DriveRuntimeState(side) for side in SIDES})
    motion: MotionRuntimeState = field(default_factory=MotionRuntimeState)
    recent_commands: deque[HardwareCommandRecord] = field(default_factory=lambda: deque(maxlen=25))


class HardwareRuntime:
    def __init__(self) -> None:
        self._lock = RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._command_counter = 0
        self.tick_seconds = TICK_SECONDS
        self.events: deque[dict[str, Any]] = deque(maxlen=400)
        self.panel = self._build_panel_bridge()
        self.reset()

    # ------------------------------------------------------------- lifecycle
    def reset(self, *, profile: MachineProfile | None = None, envelope: SafetyEnvelope | None = None) -> None:
        with self._lock:
            self.profile = profile or MachineProfile()
            self.envelope = envelope or SafetyEnvelope()
            settings = get_settings()
            self.modbus = settings.hardware_adapter == "modbus"
            self.bench: TwinBench | None = None
            if self.modbus:
                ids = {"left": settings.modbus_left_slave_id, "right": settings.modbus_right_slave_id}
                self.drives: dict[Side, TorqueDrive] = {
                    side: LichuanTorqueDrive(side, ids[side], self.profile.side(side), self.envelope.max_raw, modbus_service) for side in SIDES
                }
            else:
                self.bench = TwinBench(PlantParams(), {side: self.profile.side(side) for side in SIDES}, initial_raw=100)
                for drive in self.bench.drives.values():
                    drive.servo_on = False  # as the commissioned drives: PA_08F = 0
                self.drives = dict(self.bench.drives)
            self.latch: str | None = None  # None | estop | fault | overspeed
            self.fault_reason: str | None = None
            self.calibration: CalibrationSession | None = None
            self.samples: dict[Side, DriveSample] = {}
            self._last_write = 0.0
            self._force_write = True
            self._zero_seen: tuple[int, int] | None = None
            self._powered_on = True
            self._panel_clear_stop_pending = False
            self.write_errors: dict[Side, str] = {}
            self.state = HardwareRuntimeState(emulator_mode=not self.modbus)
            self.events.clear()
            self._command_counter = 0
            self.tick()

    def _panel_config(self) -> PanelBridgeConfig:
        settings = get_settings()
        return PanelBridgeConfig(
            enabled=settings.hardware_panel_enabled,
            port=settings.hardware_panel_port,
            baud=settings.hardware_panel_baud,
            heartbeat_interval_seconds=settings.hardware_panel_heartbeat_interval_seconds,
            reconnect_delay_seconds=settings.hardware_panel_reconnect_delay_seconds,
            status_interval_seconds=settings.hardware_panel_status_interval_seconds,
            rx_watchdog_seconds=settings.hardware_panel_rx_watchdog_seconds,
            night_mode=settings.hardware_panel_night_mode,
            brightness=settings.hardware_panel_brightness,
        )

    def _build_panel_bridge(self) -> PanelBridge:
        return PanelBridge(
            self._panel_config(),
            position_callback=self._panel_position,
            machine_state_callback=self._panel_machine_state,
            activity_callback=lambda: "stop",
            event_callback=self._handle_panel_event,
            disconnect_callback=self._handle_panel_disconnect,
        )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if not self.panel.running:
            self.panel.configure(self._panel_config())
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        await self.panel.start()

    async def stop(self) -> None:
        try:
            if self._task is not None:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        finally:
            self._task = None
            try:
                # the lock serializes this with an in-flight tick (R7)
                await asyncio.to_thread(self.apply_shutdown_support)
            finally:
                await self.panel.stop()
                self._loop = None

    def apply_shutdown_support(self) -> None:
        with self._lock:
            errors = self._write_safe_output()
            if errors:
                logger.error("Shutdown support delivery failed: %s", errors)

    async def _run(self) -> None:
        last_broadcast = 0.0
        try:
            next_tick = time.monotonic()
            while True:
                next_tick += self.tick_seconds
                delay = next_tick - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    next_tick = time.monotonic()
                    await asyncio.sleep(0)
                try:
                    await asyncio.to_thread(self.tick)
                except Exception as exc:  # keep support alive after a failed tick (R4)
                    logger.exception("Safe runtime tick failed")
                    await asyncio.to_thread(self._handle_failure, exc)
                now = time.monotonic()
                if now - last_broadcast >= BROADCAST_INTERVAL_SECONDS:
                    last_broadcast = now
                    await self._broadcast_snapshot()
        finally:
            await asyncio.to_thread(self.apply_shutdown_support)

    def _handle_failure(self, error: Exception) -> None:
        with self._lock:
            self._set_fault(f"Ошибка цикла: {error}")
            self._write_safe_output()

    # ------------------------------------------------------------------ tick
    def tick(self) -> None:
        with self._lock:
            if self.bench is not None:
                self.bench.advance(self.tick_seconds)
            if self.modbus and not modbus_service.get_status().connected:
                self.samples = {side: DriveSample(side, time.monotonic(), ok=False, error="Modbus не подключён") for side in SIDES}
            else:
                if self.modbus and not (self.calibration is not None and self.calibration.running):
                    self._sync_zero()
                self.samples = {side: self.drives[side].read() for side in SIDES}
            overspeed_mm_s = rpm_to_mm_s(self.envelope.overspeed_rpm_alarm)
            for side, sample in self.samples.items():
                if sample.ok and abs(sample.speed_mm_s) >= overspeed_mm_s:
                    self._set_latch("overspeed", f"Превышение скорости: {side} {sample.speed_mm_s:.0f} мм/с; PA_12C = 0")
            failed = [s for s in self.samples.values() if not s.ok]
            if failed and self.latch is None:
                self._set_fault("; ".join(f"{'левый' if s.side == 'left' else 'правый'}: {s.error}" for s in failed))
            now = time.monotonic()
            manual = self.modbus and modbus_service.manual_torque_active() and self.latch not in {"estop", "overspeed"}
            session = self.calibration
            if session is not None and session.running and manual:
                session.cancel("включён ручной момент debug-панели", support=False)
                self._emit("calibration_aborted", f"Калибровка {session.code} прервана: {session.reason}")
            if session is not None and session.running:
                if session.step(Frame(self._frame_t(), dict(self.samples))):
                    self._calibration_finished()
                else:
                    self._last_write = now
            elif not manual and (self._force_write or now - self._last_write >= SUPPORT_REFRESH_S):
                if self.modbus and not modbus_service.get_status().connected:
                    self._force_write = True
                else:
                    errors = self._write_safe_output()
                    self._last_write = now
                    self._force_write = bool(errors)
                    if errors and self.latch is None:
                        self._set_fault("Запись PA_12C: " + "; ".join(f"{side}: {error}" for side, error in errors.items()))
            self._sync_state(manual)

    def _sync_zero(self) -> None:
        """B7: replace the zero captured at drive init with the measured absolute zero of the profile.

        Applied once per captured zero; a jump beyond ``ZERO_SYNC_MAX_MM`` means the absolute
        position was lost (e.g. encoder battery), so the init zero is kept and a warning is logged.
        """

        current = (getattr(modbus_service, "left_zero_pulses", None), getattr(modbus_service, "right_zero_pulses", None))
        if current[0] is None or current[1] is None or current == self._zero_seen:
            return
        self._zero_seen = (int(current[0]), int(current[1]))
        stored = [self.profile.side(side).zero_counts for side in SIDES]
        if any(item.provenance != "measured" or item.value is None for item in stored):
            return
        target = (int(stored[0].value), int(stored[1].value))
        if target == self._zero_seen:
            return
        shift_mm = max(abs(t - c) * float(self.profile.side(side).mm_per_pulse.value) for side, t, c in zip(SIDES, target, self._zero_seen, strict=True))
        if shift_mm > ZERO_SYNC_MAX_MM:
            self._emit("zero", f"Абсолютный ноль профиля отличается на {shift_mm:.0f} мм — оставлен ноль инициализации; повторите B7")
            return
        modbus_service.set_session_zero(*target)
        self._zero_seen = target
        self._emit("zero", f"Применён абсолютный ноль B7 (сдвиг {shift_mm:.2f} мм)")

    def _write_safe_output(self) -> dict[Side, str]:
        """Support on both drives (zero on overspeed); each side attempted independently (R3)."""

        errors: dict[Side, str] = {}
        if self.modbus and self.latch in {"estop", "fault"}:
            modbus_service.end_manual_torque()
        for side in SIDES:
            try:
                error = self.drives[side].zero() if self.latch == "overspeed" else self.drives[side].support()
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            if error:
                errors[side] = error
        self.write_errors = errors
        return errors

    def _set_latch(self, kind: str, reason: str) -> None:
        if self.latch == kind or self.latch == "overspeed":  # R5: zero torque is never overridden
            return
        if self.latch == "estop" and kind != "overspeed":
            return
        self.latch = kind
        self.fault_reason = reason
        self._force_write = True
        self._emit(kind, reason)
        if self.calibration is not None and self.calibration.running:
            # the caller writes the safe output (support, or 0 on overspeed)
            self.calibration.cancel(reason, support=False)
            self._emit("calibration_aborted", f"Калибровка {self.calibration.code} прервана: {reason}")

    def _set_fault(self, reason: str) -> None:
        self._set_latch("fault", reason)

    def _sync_state(self, manual: bool) -> None:
        state = self.state
        for side in SIDES:
            sample = self.samples.get(side)
            drive = state.drives[side]
            if sample is None:
                continue
            drive.connected = sample.ok or sample.alarm != 0
            drive.position_mm = round(sample.position_mm, 1)
            drive.speed_mm_per_sec = round(abs(sample.speed_mm_s), 1)
            drive.error_code = (f"E-DRIVE-{sample.alarm}" if sample.alarm else "E-DRIVE-COMM") if not sample.ok else None
            drive.error_message = sample.error if not sample.ok else None
            drive.status = DriveState.connected if sample.ok else DriveState.error
        left, right = self.samples.get("left"), self.samples.get("right")
        if left and right:
            motion = state.motion
            motion.left_position_mm = round(left.position_mm, 1)
            motion.right_position_mm = round(right.position_mm, 1)
            motion.bar_position_mm = round((left.position_mm + right.position_mm) / 2, 1)
            motion.sync_delta_mm = round(left.position_mm - right.position_mm, 2)
            motion.velocity_mm_per_sec = round((left.speed_mm_s + right.speed_mm_s) / 2, 1)
            motion.moving = abs(motion.velocity_mm_per_sec) > 1.0
            motion.control_mode = self.mode
        if state.safety_state == SafetyState.emergency_stop:
            return
        if not self._powered_on:
            state.machine_state, state.machine_label = MachineState.blocked, "Тренажёр выключен"
            state.safety_message = "Приводы держат поддержку."
        elif self.latch in {"fault", "overspeed"}:
            state.machine_state, state.machine_label = MachineState.blocked, "Тренажёр заблокирован"
            state.safety_message = self.fault_reason or "Ошибка привода"
        else:
            state.machine_state, state.machine_label = MachineState.warning, "Управление двигателями отключено"
            calibration = self.calibration
            if calibration is not None and calibration.running:
                stage = calibration.current_stage
                state.machine_label = f"Калибровка {calibration.code}"
                state.safety_message = f"Калибровка {stage.code}: {stage.note or stage.title}"
            elif manual:
                state.safety_message = "Ручной момент из debug-панели"
            elif not all(self.servo_states().values()):
                state.safety_message = SERVO_OFF_MESSAGE
            else:
                state.safety_message = MOTION_DISABLED_MESSAGE
        state.alerts = ["Сервисный режим активен"] if state.service_mode else []

    @property
    def mode(self) -> str:
        if self.latch is None and self.calibration is not None and self.calibration.running:
            return "calibration"
        return self.latch or "support"

    @property
    def jog_active(self) -> bool:
        return False

    # -------------------------------------------------------------- commands
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

    def trigger_emergency_stop(self) -> HardwareCommandRecord:
        with self._lock:
            self._set_latch("estop", "Аварийная остановка")
            self._write_safe_output()
            self._last_write = time.monotonic()
            self.state.safety_state = SafetyState.emergency_stop
            self.state.machine_state = MachineState.blocked
            self.state.machine_label = "СТОП активирован"
            self.state.safety_message = "Аварийная остановка активна. Приводы держат поддержку."
            self.state.alerts = ["Аварийная остановка активна"]
            command = self._record_command("trigger_emergency_stop", {})
        self.panel.send_command("stop")
        self._schedule_broadcast()
        return command

    def clear_emergency_stop(self) -> HardwareCommandRecord:
        panel = self.panel.state.to_payload()
        if panel["enabled"]:
            if not panel["connected"]:
                raise PermissionError("Нельзя снять аварийную остановку: панель не подключена")
            if not panel["handshakeComplete"] or not panel["ready"]:
                raise PermissionError("Нельзя снять аварийную остановку: handshake панели не завершён")
            if not panel["fresh"]:
                raise PermissionError("Нельзя снять аварийную остановку: состояние панели устарело")
            if not panel["inputHealthy"]:
                raise PermissionError("Нельзя снять аварийную остановку: входы панели неисправны")
            if panel["buttons"].get("stop"):
                raise PermissionError("Нельзя снять аварийную остановку, пока физическая кнопка STOP нажата")
            if panel["stopLatched"]:
                if not self.panel.send_command("clear_stop"):
                    raise PermissionError("Нельзя снять аварийную остановку: команда не доставлена панели")
                with self._lock:
                    self._panel_clear_stop_pending = True
                    command = self._record_command("clear_emergency_stop", {"awaitingPanel": True})
                    command.status = "pending"
                self._schedule_broadcast()
                return command
        command = self._clear_emergency_stop_confirmed()
        self.panel.send_command("clear_stop")
        self._schedule_broadcast()
        return command

    def _clear_emergency_stop_confirmed(self) -> HardwareCommandRecord:
        with self._lock:
            if self.latch == "estop":  # only the E-stop latch itself (R6)
                self.latch = None
                self.fault_reason = None
            self._panel_clear_stop_pending = False
            self.state.safety_state = SafetyState.enabled
            self.state.alerts = []
            self._force_write = True
            self._emit("estop_clear", "СТОП снят")
            command = self._record_command("clear_emergency_stop", {})
            self._sync_state(False)
        return command

    def reset_fault(self) -> HardwareCommandRecord:
        with self._lock:
            if self.latch == "estop":
                raise PermissionError("Сначала снимите аварийную остановку")
            if self.modbus:
                errors = modbus_service.initialize_torque_mode(
                    torque_limit=self.envelope.max_raw,
                    speed_limit_rpm=self.envelope.speed_limit_rpm,
                    initial_commands={drive.slave_id: int(drive.profile.support_raw.value) * drive.profile.sign for drive in self.drives.values()},  # type: ignore[attr-defined]
                ) if modbus_service.get_status().connected else ["Modbus не подключён"]
                if errors:
                    raise PermissionError("Сброс не выполнен: " + "; ".join(errors))
            self.latch = None
            self.fault_reason = None
            self._force_write = True
            self._emit("reset", "Ошибка сброшена")
            command = self._record_command("reset_fault", {})
            self.tick()
        self._schedule_broadcast()
        return command

    def set_service_mode(self, enabled: bool) -> HardwareCommandRecord:
        with self._lock:
            if not enabled:
                self._abort_calibration_locked("сервисный режим выключен")
            self.state.service_mode = enabled
            command = self._record_command("toggle_service_mode", {"enabled": enabled})
        self._schedule_broadcast()
        return command

    def servo_states(self) -> dict[Side, bool | None]:
        return {side: self.drives[side].servo_state() for side in SIDES}

    def set_servo(self, on: bool) -> HardwareCommandRecord:
        """SRV-ON/OFF on both drives, service mode only. Servo OFF drops a raised bar (no DB)."""

        with self._lock:
            if not self.state.service_mode:
                raise PermissionError("Включение и выключение приводов — только в сервисном режиме")
            self._abort_calibration_locked("приводы включены/выключены оператором")
            if on:
                if self.latch is not None:
                    raise PermissionError("Сначала снимите СТОП и сбросьте ошибку")
                # support is in PA_12C before SRV-ON, so the first torque is never 0 (R1)
                errors = self._write_safe_output()
                self._last_write = time.monotonic()
                if errors:
                    raise PermissionError("Поддержка не записана: " + "; ".join(f"{side}: {error}" for side, error in errors.items()))
            errors = {side: error for side in SIDES if (error := self.drives[side].set_servo(on))}
            if on and errors:
                for side in SIDES:  # never one side alone: the bar couples them
                    self.drives[side].set_servo(False)
            label = "Приводы включены" if on else "Приводы выключены"
            details = "; ".join(f"{side}: {error}" for side, error in errors.items())
            self._emit("servo_on" if on else "servo_off", f"{label}: {details}" if errors else label)
            if errors:
                self._sync_state(False)
                raise PermissionError(f"{'Включение' if on else 'Выключение'} приводов не выполнено: {details}")
            command = self._record_command("servo_on" if on else "servo_off", {})
            self._sync_state(False)
        self._schedule_broadcast()
        return command

    def run_diagnostics(self) -> HardwareCommandRecord:
        with self._lock:
            failed = [side for side, sample in self.samples.items() if not sample.ok]
            self.state.diagnostics_status = "failed" if failed else "passed"
            self.state.last_diagnostics_at = datetime.now(UTC)
            command = self._record_command("run_diagnostics", {"checks": len(SIDES), "failed": len(failed)})
        self.panel.send_command("diagnostics")
        self._schedule_broadcast()
        return command

    def reject_motion(self, action: str) -> None:
        with self._lock:
            self._emit("motion_rejected", f"{action}: {MOTION_DISABLED_MESSAGE}")
        raise PermissionError(MOTION_DISABLED_MESSAGE)

    # ----------------------------------------------------------- calibration
    def _frame_t(self) -> float:
        return self.bench.t if self.bench is not None else time.monotonic()

    def calibration_preconditions(self, code: str) -> list[dict[str, Any]]:
        with self._lock:
            samples = self.samples
            servo = self.servo_states()
            positions = {side: sample.position_mm for side, sample in samples.items() if sample.ok}
            telemetry_ok = len(samples) == len(SIDES) and all(sample.ok for sample in samples.values())
            on_stops = telemetry_ok and all(abs(x) <= ON_STOPS_MM for x in positions.values())
            manual = self.modbus and modbus_service.manual_torque_active()
            stages = RUNNABLE.get(code, ())
            missing = sorted({
                required for stage in stages[:1] for required in BY_CODE[stage].requires
                if BY_CODE[required].implemented and BY_CODE[required].produces
                and calibration_status(self.profile, BY_CODE[required]) not in ("actual", "stale")
            })
            busy = self.calibration is not None and self.calibration.running
            estop = self.state.safety_state == SafetyState.emergency_stop
            return [
                {"id": "service", "label": "Сервисный режим включён", "ok": self.state.service_mode, "detail": None if self.state.service_mode else "Настройки → Сервис"},
                {"id": "safety", "label": "Нет СТОП и ошибок привода", "ok": self.latch is None and not estop, "detail": self.fault_reason if self.latch or estop else None},
                {"id": "servo", "label": "Приводы включены (Servo ON)", "ok": all(servo.values()), "detail": None if all(servo.values()) else "Включите приводы в настройках сервиса"},
                {"id": "telemetry", "label": "Телеметрия обеих сторон в норме", "ok": telemetry_ok, "detail": None if telemetry_ok else "; ".join(f"{s.side}: {s.error}" for s in samples.values() if not s.ok) or "нет данных"},
                {"id": "stops", "label": f"Гриф на нижних упорах (≤ {ON_STOPS_MM:.0f} мм)", "ok": on_stops, "detail": ", ".join(f"{'Л' if side == 'left' else 'П'} {x:.1f} мм" for side, x in positions.items()) or None},
                {"id": "manual", "label": "Ручной момент debug-панели не активен", "ok": not manual, "detail": None if not manual else "Остановите ручной момент на странице Modbus"},
                {"id": "requires", "label": "Выполнены предыдущие калибровки", "ok": not missing, "detail": ("Сначала: " + ", ".join(missing)) if missing else None},
                {"id": "idle", "label": "Другая калибровка не выполняется", "ok": not busy, "detail": None},
            ]

    def start_calibration(self, code: str, options: dict[str, Any] | None = None) -> CalibrationSession:
        """Service mode, no latch, servo on, bar on the stops; the operator holds the dead-man (keepalive)."""

        with self._lock:
            if code not in RUNNABLE:
                raise ValueError(f"Калибровка {code} не запускается из интерфейса")
            failed = [item for item in self.calibration_preconditions(code) if not item["ok"]]
            if failed:
                item = failed[0]
                raise PermissionError(f"Не выполнено условие «{item['label']}»" + (f": {item['detail']}" if item["detail"] else ""))
            session = CalibrationSession(code, self.drives, self.profile, options=options, safety=self.envelope)
            self.calibration = session
            self._emit("calibration_start", f"Калибровка {code} запущена", {"id": session.id})
            self._record_command("calibration_start", {"code": code, "id": session.id})
            session.begin()
            if not session.running:
                self._calibration_finished()
            self._sync_state(False)
        self._schedule_broadcast()
        return session

    def calibration_keepalive(self) -> bool:
        with self._lock:
            if self.calibration is None or not self.calibration.running:
                return False
            self.calibration.keepalive()
            return True

    def _abort_calibration_locked(self, reason: str) -> bool:
        session = self.calibration
        if session is None or not session.running:
            return False
        session.cancel(reason, support=False)
        self._calibration_finished()
        return True

    def abort_calibration(self, reason: str = "прервано оператором") -> bool:
        with self._lock:
            aborted = self._abort_calibration_locked(reason)
            self._sync_state(False)
        self._schedule_broadcast()
        return aborted

    def _calibration_finished(self) -> None:
        """Support right after the session releases the drives (with the active profile restored)."""

        errors = self._write_safe_output()
        self._last_write = time.monotonic()
        self._force_write = bool(errors)
        session = self.calibration
        if session is not None:
            labels = {"done": "завершена", "aborted": "прервана", "failed": "не удалась"}
            message = f"Калибровка {session.code} {labels.get(session.status, session.status)}" + (f": {session.reason}" if session.reason else "")
            self._emit(f"calibration_{session.status}", message, {"id": session.id})
        self._schedule_broadcast()

    def discard_calibration(self) -> None:
        with self._lock:
            if self.calibration is not None and self.calibration.running:
                raise PermissionError("Калибровка ещё выполняется — сначала прервите её")
            self.calibration = None

    def calibration_payload(self, code: str) -> dict[str, Any]:
        with self._lock:
            return {
                "session": self.calibration.to_payload() if self.calibration is not None else None,
                "preconditions": self.calibration_preconditions(code),
                "profileVersion": self.profile.version,
            }

    def apply_profile(self, profile: MachineProfile, envelope: SafetyEnvelope | None = None) -> None:
        """Make a saved profile active without a restart; support is rewritten with the new sign/raw."""

        with self._lock:
            if self.calibration is not None and self.calibration.running:
                raise PermissionError("Идёт калибровка — профиль нельзя менять")
            self.profile = profile
            self._zero_seen = None  # re-check the absolute zero against the new profile
            if envelope is not None:
                self.envelope = envelope
            for side in SIDES:
                drive = self.drives[side]
                drive.profile = profile.side(side)  # type: ignore[attr-defined]
                if envelope is not None and hasattr(drive, "max_raw"):
                    drive.max_raw = envelope.max_raw  # type: ignore[attr-defined]
            self._force_write = True
            self._emit("profile", f"Применён профиль v{profile.version}")
        self._schedule_broadcast()

    # -------------------------------------------------------------- snapshot
    def events_payload(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self.events)[-limit:]

    def snapshot_payload(self) -> dict[str, object]:
        with self._lock:
            state = self.state
            estop = state.safety_state == SafetyState.emergency_stop
            return {
                "eventType": "hardware.snapshot",
                "emittedAt": datetime.now(UTC).isoformat(),
                "machine": {
                    "machineState": state.machine_state.value,
                    "machineLabel": state.machine_label,
                    "leftDrive": state.drives["left"].status.value,
                    "rightDrive": state.drives["right"].status.value,
                    "safety": state.safety_state.value,
                    "calibration": "Калибровка актуальна" if state.calibration_actual else ("Калибровка требуется" if state.calibration_required else "Калибровка не требуется"),
                },
                "safety": {
                    "state": state.safety_state.value,
                    "label": "Аварийная остановка" if estop else ("Защита отключена" if state.safety_state == SafetyState.disabled else "Безопасность включена"),
                    "message": state.safety_message,
                    "requiresService": estop or state.service_mode,
                    "activeEventId": None,
                },
                "emulatorMode": state.emulator_mode,
                "serviceMode": state.service_mode,
                "selectedUserId": state.selected_user_id,
                "userSelected": state.selected_user_id is not None,
                "drives": [{**asdict(drive), "status": drive.status.value} for drive in state.drives.values()],
                "motion": asdict(state.motion),
                "control": self._control_payload(),
                "calibrationRequired": state.calibration_required,
                "calibrationActual": state.calibration_actual,
                "activeCalibrationId": state.active_calibration_id,
                "commandQueueDepth": len(state.recent_commands),
                "lastCommand": state.recent_commands[-1].to_payload() if state.recent_commands else None,
                "diagnosticsStatus": state.diagnostics_status,
                "lastDiagnosticsAt": state.last_diagnostics_at.isoformat() if state.last_diagnostics_at else None,
                "alerts": list(state.alerts),
                "panel": self.panel.state.to_payload(),
            }

    def _control_payload(self) -> dict[str, Any]:
        motion = self.state.motion
        return {
            "mode": self.mode,
            "label": self.state.machine_label,
            "message": self.state.safety_message,
            "motorControl": "disabled",
            "motorControlMessage": MOTION_DISABLED_MESSAGE,
            "positionMm": motion.bar_position_mm,
            "velocityMmPerSec": motion.velocity_mm_per_sec,
            "syncDeltaMm": motion.sync_delta_mm,
            "syncStatus": "critical" if abs(motion.sync_delta_mm) >= self.envelope.sync_critical_mm else ("warning" if abs(motion.sync_delta_mm) >= self.envelope.sync_warning_mm else "ok"),
            "postStatus": "skipped",
            "positionKnown": all(sample.ok for sample in self.samples.values()),
            "commOk": all(sample.ok for sample in self.samples.values()),
            "faultCode": self.fault_reason if self.latch in {"fault", "overspeed"} else None,
            "supportRaw": {side: drive.last_raw for side, drive in self.drives.items()},  # type: ignore[attr-defined]
            "servo": self.servo_states(),
            "writeErrors": dict(self.write_errors),
            "adapter": "modbus-torque" if self.modbus else "twin",
            "softMinMm": self.envelope.soft_min_mm,
            "softMaxMm": self.envelope.soft_max_mm,
        }

    # ----------------------------------------------------------------- panel
    def _panel_position(self) -> float:
        with self._lock:
            return self.state.motion.bar_position_mm

    def _panel_machine_state(self) -> str:
        with self._lock:
            if self.state.safety_state == SafetyState.emergency_stop:
                return "emergency_stop"
            if not self._powered_on:
                return "off"
            if self.latch in {"fault", "overspeed"}:
                return "error"
            return "maintenance" if self.state.service_mode else "ready"

    def _handle_panel_disconnect(self, reason: str) -> None:
        with self._lock:
            self._emit("panel_disconnect", f"Панель отключена: {reason}")
        self._schedule_broadcast()

    def _handle_panel_event(self, event: PanelEvent) -> None:
        if isinstance(event, PanelStatusEvent):
            if event.stop_latched or event.buttons["stop"] or event.fault_code != "none" or not event.input_healthy:
                if self.state.safety_state != SafetyState.emergency_stop:
                    self.trigger_emergency_stop()
                    return
            self._schedule_broadcast()
            return
        if isinstance(event, PanelFaultEvent):
            if event.latched:
                if self.state.safety_state != SafetyState.emergency_stop:
                    self.trigger_emergency_stop()
            elif event.code == "none" and self._panel_clear_stop_pending:
                self._clear_emergency_stop_confirmed()
                self._schedule_broadcast()
            return
        if not isinstance(event, PanelButtonEvent):
            self._schedule_broadcast()
            return
        if event.button_id == "stop" and event.action == "pressed":
            if self.state.safety_state != SafetyState.emergency_stop:
                self.trigger_emergency_stop()
            return
        accepted = False
        if event.button_id == "power" and event.action == "pressed" and self.state.safety_state != SafetyState.emergency_stop:
            with self._lock:
                self._powered_on = not self._powered_on
                self.state.safety_state = SafetyState.enabled if self._powered_on else SafetyState.disabled
                self._sync_state(False)
            self.panel.send_command("set_machine_state", state="ready" if self._powered_on else "off")
            accepted = True
        elif event.action in {"pressed", "repeat"}:
            with self._lock:
                self._emit("panel_button_rejected", MOTION_DISABLED_MESSAGE, {"button": event.button_id})
        if event.action in {"pressed", "repeat"}:
            self.panel.send_command("button_feedback", id=event.button_id, request_seq=event.sequence, accepted=accepted)
        self._schedule_broadcast()

    # ------------------------------------------------------------- plumbing
    def _emit(self, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append({"t": round(time.monotonic(), 3), "kind": kind, "message": message, "payload": payload or {}})

    def _record_command(self, action: str, payload: dict[str, object]) -> HardwareCommandRecord:
        self._command_counter += 1
        command = HardwareCommandRecord(self._command_counter, action, "completed", datetime.now(UTC), payload)
        self.state.recent_commands.append(command)
        return command

    async def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=50)
        with self._lock:
            self._subscribers.add(queue)
        await queue.put(self.snapshot_payload())
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def _schedule_broadcast(self) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self._broadcast_snapshot(), self._loop)

    async def _broadcast_snapshot(self) -> None:
        payload = self.snapshot_payload()
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except asyncio.QueueFull:
                with self._lock:
                    self._subscribers.discard(subscriber)


hardware_runtime = HardwareRuntime()
