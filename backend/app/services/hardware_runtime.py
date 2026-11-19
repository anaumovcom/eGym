"""Minimal safe hardware runtime (plan 16, stage 1 / M0).

The v1 motion stack is removed. Until the v2 ``motor-rt`` process takes over
(plan 16, stage 5) this runtime only:

* holds upward support ``support_raw`` (PA_12C ≈ +100) on both drives,
  refreshed every ``SUPPORT_REFRESH_S``; the first write is support, never 0;
* discovers late-powered drives at rest and latches drive/bus faults during a workout or calibration;
* maintains support during E-stop, and applies ABORT_SUPPORT_RAW after overspeed;
* leaves PA_12C to the debug panel while its manual torque is active;
* runs calibration sessions (service mode, dead-man, envelope) step by step
  inside the tick: the session writes PA_12C instead of support until it ends;
* runs exercises (``WorkoutController``: weightless setup, jog, move to the start
  point, grip wait, load ramp, reps, pause, park) on a calibrated profile;
* publishes position/telemetry snapshots and serves the physical panel.

Safety requirements: ``app/motor/SAFETY_REQUIREMENTS.md``.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Literal

from app.core.config import BACKEND_ROOT, get_settings
from app.models.enums import DriveState, MachineState, SafetyState
from app.motor.calibration.graph import BY_CODE, EMPTY_SERIES, RUN_SPECS, RUNNABLE
from app.motor.calibration.graph import status as calibration_status
from app.motor.calibration.middle_zone import MIDDLE_CODES, REQUIRED_MIDDLE, confirmed_bounds, middle_window
from app.motor.calibration.runner import Frame
from app.motor.calibration.session import ON_STOPS_MM, CalibrationSession
from app.motor.drive.canopen import READ_ONLY, CanopenDrive, CanopenPair, DriveFaultError, encoder_delta
from app.motor.drive.lichuan import LichuanTorqueDrive
from app.motor.drive.protocol import CONTROL_PERIOD_S, DriveSample, TorqueDrive
from app.motor.exercise_observation import ExerciseObservation
from app.motor.profile import MachineProfile, SafetyEnvelope, Tunables
from app.motor.twin.bench import TwinBench
from app.motor.twin.plant import PlantParams
from app.motor.units import SIDES, G, Side, rpm_to_mm_s
from app.motor.workout import SetPlan, WorkoutController, WorkoutError, load_mode, per_side_n
from app.schemas.drive_transport import CanopenNodeStatus, DriveTransportSettings, DriveTransportStatus
from app.schemas.modbus import ModbusConnectionParamsSchema, ModbusConnectionStatusSchema
from app.services.modbus_service import control_bus_deadline, modbus_service
from app.services.panel.bridge import PanelBridge, PanelBridgeConfig
from app.services.panel.protocol import (
    PanelButtonEvent,
    PanelEvent,
    PanelFaultEvent,
    PanelStatusEvent,
)

logger = logging.getLogger(__name__)
# exercises on the real drives: one line per tick (positions, speeds, forces, guard state) for post-mortems
motion_trace = logging.getLogger("egym.motion.trace")
MOTION_LOG = BACKEND_ROOT / "logs" / "motion.log"


def _motion_trace_handler() -> None:
    if motion_trace.handlers:
        return
    MOTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(MOTION_LOG, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", "%Y-%m-%d %H:%M:%S"))
    motion_trace.addHandler(handler)
    motion_trace.setLevel(logging.INFO)
    motion_trace.propagate = False

TICK_SECONDS = CONTROL_PERIOD_S
SUPPORT_REFRESH_S = 0.2
DRIVE_RECONNECT_S = 2.0
# an interrupted calibration (abort, failure, latch) leaves PA_12C = 100 on both drives instead of the profile support:
# no jerk from a changed or wrong support_raw (C3 hold, a candidate profile); kept until the next calibration starts
ABORT_SUPPORT_RAW = 100
# the stored absolute zero is rejected only if it puts the bar outside the travel by more than this (encoder position lost)
ZERO_SYNC_MARGIN_MM = 50.0
BROADCAST_INTERVAL_SECONDS = 0.1
SLOW_TICK_S = 0.3  # logged: bus retries / timeouts stretch the control period
STALL_S = 0.5  # gap between ticks: the loop stood still, the screen heartbeat could not be served
MIN_TICK_GAP_S = 0.005  # idle time after every tick: a back-to-back slow loop must not starve API calls waiting for the lock
HEARTBEAT_GAP_S = 0.7  # logged: the screen heartbeat (every 0.25 s) came late
PANEL_MOTION_MESSAGE = "Кнопки панели не двигают гриф: управляйте с экрана"
SERVO_OFF_MESSAGE = "Приводы выключены (Servo OFF): гриф не поддерживается. Включить — в сервисном режиме"
# exercises drive the motors only on a calibrated profile: balance, support, motion, mass, stop distances
MOTION_REQUIRED_CALIBRATIONS = ("S3", "M1", "M3", "C3")


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
    sync_available: bool = False
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
    partial_reps: int = 0
    load_target_kg: float = 0.0
    load_effective_kg: float = 0.0
    load_mode: str = "normal_weight"
    user_force_kg: float = 0.0
    start_point: str = "lower"
    load_direction: Literal["down", "up"] = "down"
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
class HardwareRuntimeState:
    emulator_mode: bool = True
    machine_state: MachineState = MachineState.warning
    machine_label: str = "Готов к тренировке"
    safety_state: SafetyState = SafetyState.enabled
    safety_message: str = ""
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
        # the control loop owns a thread: a blocked event loop (sync DB/network in a handler) must not freeze the drives
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._manage_drives = False
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._command_counter = 0
        self.tick_seconds = TICK_SECONDS
        self._tick_started: float | None = None
        self.events: deque[dict[str, Any]] = deque(maxlen=400)
        self.observation: ExerciseObservation | None = None
        self._finished_observations: dict[str, ExerciseObservation] = {}
        self.panel = self._build_panel_bridge()
        self.reset()

    # ------------------------------------------------------------- lifecycle
    def _install_transport(self, config: DriveTransportSettings) -> None:
        settings = get_settings()
        self.transport = config
        self.modbus = config.adapter == "modbus"
        self.canopen = CanopenPair(config.canopen) if config.adapter == "canopen" else None
        self._drive_ids: dict[Side, int] = {"left": settings.modbus_left_slave_id, "right": settings.modbus_right_slave_id}
        self.bench: TwinBench | None = None
        self.tick_seconds = self.canopen.period_s if self.canopen and not self.canopen.read_only else TICK_SECONDS
        self.drives: dict[Side, TorqueDrive]
        if self.canopen:
            self._drive_ids = {"left": config.canopen.left_id, "right": config.canopen.right_id}
            self.drives = {s: CanopenDrive(s, self._drive_ids[s], self.profile.side(s), self.envelope.max_raw, self.canopen) for s in SIDES}
        elif self.modbus:
            self.drives = {s: LichuanTorqueDrive(s, self._drive_ids[s], self.profile.side(s), self.envelope.max_raw, modbus_service) for s in SIDES}
        else:
            self.bench = TwinBench(PlantParams(), {s: self.profile.side(s) for s in SIDES}, initial_raw=100)
            for drive in self.bench.drives.values():
                drive.servo_on = False
            self.drives = dict(self.bench.drives)
        if self.bench is None:
            _motion_trace_handler()
        self.workout = WorkoutController(self.drives, self.profile, self.tunables, self.envelope)

    def reset(self, *, profile: MachineProfile | None = None, envelope: SafetyEnvelope | None = None,
              tunables: Tunables | None = None, transport: DriveTransportSettings | None = None) -> None:
        with self._lock:
            self._finish_observation("interrupted", "Перезапуск контроллера")
            self.profile = profile or MachineProfile()
            self.envelope = envelope or SafetyEnvelope()
            self.tunables = tunables or Tunables()
            if getattr(self, "canopen", None):
                self.canopen.close()
            self._install_transport(transport or DriveTransportSettings.from_environment())
            self.latch: str | None = None  # None | drive_wait | estop | fault | overspeed
            self._auto_servo = True
            self._next_drive_recovery = 0.0
            self.fault_reason: str | None = None
            self.calibration: CalibrationSession | None = None
            self.samples: dict[Side, DriveSample] = {}
            self._last_write = 0.0
            self._force_write = True
            self._tick_started = None
            self._zero_seen: tuple[int, int] | None = None
            self._powered_on = True
            self._panel_clear_stop_pending = False
            self.write_errors: dict[Side, str] = {}
            self.abort_hold = False  # ABORT_SUPPORT_RAW instead of support after an interrupted calibration
            self.state = HardwareRuntimeState(emulator_mode=self.bench is not None)
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
        if self._thread is None or not self._thread.is_alive():
            self._stop_event = threading.Event()
            with self._lock:
                self._start_transport()
            self._thread = threading.Thread(target=self._control_loop, args=(self._stop_event,), name="hardware-control", daemon=True)
            self._thread.start()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._broadcast_loop())
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
            thread, self._thread = self._thread, None
            self._stop_event.set()
            self._manage_drives = False
            if thread is not None:
                await asyncio.to_thread(thread.join, 2.0)
            try:
                # the lock serializes this with an in-flight tick (R7)
                await asyncio.to_thread(self.apply_shutdown_support)
            finally:
                await self.panel.stop()
                self._loop = None

    def apply_shutdown_support(self) -> None:
        with self._lock:
            errors = self._write_safe_output()
            if self.canopen and self.canopen.ready:
                self._exchange_canopen()
            if errors:
                logger.error("Shutdown support delivery failed: %s", errors)

    def _control_loop(self, stop: threading.Event) -> None:
        try:
            next_tick = time.monotonic()
            while not stop.is_set():
                period = self.tick_seconds
                next_tick += period
                now = time.monotonic()
                # Leave time for other lock users on overruns without imposing a 5 ms floor on fast CAN.
                minimum_gap = min(MIN_TICK_GAP_S, period / 4)
                next_tick = max(next_tick, now + minimum_gap)
                delay = next_tick - now
                if self.canopen:
                    # Event.wait rounds short timeouts to a scheduler tick on some Windows hosts.
                    # Python's high-resolution sleep releases the GIL; check for shutdown before issuing any command.
                    time.sleep(delay)
                    if stop.is_set():
                        break
                elif stop.wait(delay):
                    break
                try:
                    self.tick()
                except Exception as exc:  # keep support alive after a failed tick (R4)
                    logger.exception("Safe runtime tick failed")
                    try:
                        self._handle_failure(exc)
                    except Exception:  # noqa: BLE001
                        logger.exception("Safe runtime failure handling failed")
        finally:
            self.apply_shutdown_support()

    async def _broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(BROADCAST_INTERVAL_SECONDS)
            try:
                await self._broadcast_snapshot()
            except Exception:  # noqa: BLE001
                logger.exception("Hardware snapshot broadcast failed")

    def _handle_failure(self, error: Exception) -> None:
        with self._lock:
            self._set_fault(f"Ошибка цикла: {error}")
            self._write_safe_output()

    # ------------------------------------------------------------------ tick
    def tick(self) -> None:
        started = time.monotonic()
        gap = started - self._tick_started if self._tick_started is not None else 0.0
        self._tick_started = started
        if gap >= STALL_S:
            logger.warning("Control loop stalled: %.0f ms between ticks", gap * 1000)
            session = self.calibration
            if session is not None and session.running:
                session.excuse_stall(gap - self.tick_seconds)
        try:
            self._tick()
        finally:
            elapsed = time.monotonic() - started
            if elapsed >= SLOW_TICK_S:
                logger.warning("Slow control tick: %.0f ms (calibration=%s)", elapsed * 1000, self.calibration.code if self.calibration is not None and self.calibration.running else None)

    def _tick(self) -> None:
        with self._lock:
            if self.canopen and self.canopen.read_only:
                if self._manage_drives:
                    if self.latch is None:
                        self._wait_for_drives(READ_ONLY)
                    self.canopen.observe()
                self._control_step(False)
                return
            verified = self._prepare_idle_drives() if self._manage_drives else False
            if self.canopen and self.canopen.ready and not verified:
                moving = self.workout.active or (self.calibration and self.calibration.running)
                if moving and time.monotonic() - self.canopen.cycle_t > self.envelope.stale_frame_limit_s:
                    self._set_fault("Истёк срок команд CANopen")
                    self._write_safe_output()
                self._exchange_canopen()
                if self.canopen.ready and self._manage_drives and self._idle_drive_control():
                    verified = self.latch == "drive_wait" or (
                        self._auto_servo and not self.state.service_mode and not all(self.servo_states().values()))
                if self.canopen.ready and (self.workout.active or (self.calibration and self.calibration.running)) and not all(self.servo_states().values()):
                    for node in self.canopen.nodes:
                        if self.canopen.feedback[node][0x6041] & 0x6F != 0x27:
                            self.canopen.words[node] = 6
                    self._set_fault("Привод CANopen вышел из Operation enabled")
            self._control_step(verified)

    def _exchange_canopen(self) -> None:
        assert self.canopen is not None
        try:
            self.canopen.cycle()
        except OSError as exc:
            self._canopen_failure(exc)

    def _canopen_failure(self, exc: Exception) -> None:
        assert self.canopen is not None
        if isinstance(exc, DriveFaultError) or self.workout.active or (self.calibration and self.calibration.running):
            self._set_fault(str(exc))
        self.canopen.failed(exc, self._support_commands())
        self._drive_error(str(exc))

    def _start_transport(self) -> None:
        self._manage_drives = self.bench is None
        if self.modbus:
            settings = get_settings()
            params = self.transport.modbus or ModbusConnectionParamsSchema(
                port=settings.modbus_port, baud_rate=settings.modbus_baud_rate,
                slave_id=self._drive_ids["left"], right_slave_id=self._drive_ids["right"])
            self._set_modbus_ids(params)
            modbus_service.request_connection(params)
        elif self.canopen and modbus_service.get_status().connected:
            modbus_service.disconnect(preserve_torque=True)
        if self._manage_drives and self.latch in (None, "drive_wait"):
            self._wait_for_drives(READ_ONLY if self.canopen and self.canopen.read_only else "Проверка готовности обоих приводов")
        self._next_drive_recovery = 0.0

    def transport_status(self) -> DriveTransportStatus:
        with self._lock:
            connected = self.canopen.ready if self.canopen else (modbus_service.get_status().connected if self.modbus else True)
            error = self.canopen.error if self.canopen else None
            nodes = []
            if self.canopen and self.canopen.ready:
                for node, fields in self.canopen.feedback.items():
                    nodes.append(CanopenNodeStatus(node=node, mode=self.canopen.mode[node], statusword=fields[0x6041],
                                                   position=fields[0x6064], velocity=fields[0x606C], torque=fields[0x6077]))
            pair = self.canopen
            diagnostics = (pair.monitor.snapshot(time.monotonic(), pair.bus is not None, pair.feedback, pair.replies, pair.sent_targets)
                           if pair else None)
            fault = None if pair and pair.read_only and self.latch == "drive_wait" else self.fault_reason
            return DriveTransportStatus(config=self.transport, connected=connected, error=error or fault, diagnostics=diagnostics,
                                        nodes=nodes, timing=pair.timing() if pair and connected else None)

    def change_transport(self, config: DriveTransportSettings, persist: Callable[[DriveTransportSettings], None]) -> DriveTransportStatus:
        with self._lock:
            if config.modbus is None and self.transport.modbus is not None:
                config = config.model_copy(update={"modbus": self.transport.modbus})
            if config == self.transport:
                persist(config)
                return self.transport_status()
            if self.workout.active or (self.calibration and self.calibration.running) or modbus_service.manual_torque_active():
                raise PermissionError("Смена канала недоступна во время упражнения, калибровки или ручного момента")
            serial = modbus_service.get_status()
            taking_control = (self.canopen is not None and self.canopen.read_only and self.canopen.bus is not None
                              and (config.adapter == "modbus" or (config.adapter == "canopen" and config.canopen.operation == "control")))
            if self.canopen and (self.canopen.ready or taking_control):
                try:
                    disabled = self.canopen.axes_disabled(from_diagnostics=taking_control)
                except OSError as exc:
                    if not taking_control:
                        self._canopen_failure(exc)
                    raise PermissionError(f"Не удалось подтвердить отключение приводов CANopen: {exc}") from exc
                if not disabled:
                    raise PermissionError("Опустите гриф на упоры и выключите оба привода перед сменой канала")
            if serial.connected:
                modbus_service.check_servo_pair()
                if any(modbus_service.servo_state(n) is not False for n in (serial.slave_id, serial.right_slave_id)):
                    raise PermissionError("Опустите гриф на упоры и выключите оба привода Modbus перед сменой канала")
            persist(config)
            if self.canopen:
                self.canopen.close()
            if self.modbus or serial.connected:
                modbus_service.disconnect(preserve_torque=True)
            self._install_transport(config)
            self.samples.clear()
            self.write_errors.clear()
            self._zero_seen = None
            self._force_write = True
            self.calibration = None
            self.state.emulator_mode = self.bench is not None
            if self.latch == "drive_wait":
                self.latch = self.fault_reason = None
            self._start_transport()
            self._control_step(False)
            self._emit("transport", f"Выбран канал приводов: {config.adapter}")
            return self.transport_status()

    def close_transport(self) -> None:
        with self._lock:
            if self.canopen:
                self.canopen.close()
            elif self.modbus:
                modbus_service.disconnect(preserve_torque=True)

    def _idle_drive_control(self) -> bool:
        return (self.bench is None and self.latch in (None, "drive_wait") and self._powered_on
                and self.state.safety_state == SafetyState.enabled
                and not self.workout.active and not (self.calibration and self.calibration.running)
                and not (self.modbus and modbus_service.manual_torque_active()))

    def _wait_for_drives(self, reason: str) -> None:
        if self.latch != "drive_wait":
            self._set_latch("drive_wait", reason)
        else:
            self.fault_reason = reason

    def _support_commands(self) -> dict[int, int]:
        return {
            slave: (ABORT_SUPPORT_RAW if self.abort_hold or self.latch == "overspeed" else int(self.profile.side(side).support_raw.value)) * self.profile.side(side).sign
            for side, slave in self._drive_ids.items()
        }

    def configure_modbus(self, params: ModbusConnectionParamsSchema | None) -> ModbusConnectionStatusSchema:
        """Serialize an explicit connection change with the controller that owns these axes."""
        with self._lock:
            if self.canopen:
                raise PermissionError("Активен CANopen. Выберите Modbus в настройках подключения приводов.")
            if self.workout.active or (self.calibration and self.calibration.running) or modbus_service.manual_torque_active():
                raise PermissionError("Остановите упражнение, калибровку или ручное управление перед сменой подключения")
            if params and params.slave_id == params.right_slave_id:
                return ModbusConnectionStatusSchema(connected=False, error_message="Адреса левого и правого приводов должны различаться")
            if modbus_service.get_status().connected:
                self._write_safe_output()
            if params is None:
                status = modbus_service.disconnect(preserve_torque=True)
            else:
                self.transport = self.transport.model_copy(update={"modbus": params})
                self._set_modbus_ids(params)
                status = modbus_service.connect(params, initial_commands=self._support_commands(), torque_limit=self.envelope.max_raw,
                                                speed_limit_rpm=self.envelope.speed_limit_rpm)
            self._zero_seen = None
            self._next_drive_recovery = 0.0
            if self.latch in (None, "drive_wait"):
                self._wait_for_drives(status.error_message or ("Проверка готовности обоих приводов" if params else "Соединение Modbus отключено оператором"))
            return status

    def _set_modbus_ids(self, params: ModbusConnectionParamsSchema) -> None:
        self._drive_ids = {"left": params.slave_id, "right": params.right_slave_id}
        for side, drive in self.drives.items():
            if isinstance(drive, LichuanTorqueDrive):
                drive.slave_id = self._drive_ids[side]
                drive.last_raw = drive.last_write_at = None

    def _prepare_idle_drives(self) -> bool:
        if time.monotonic() < self._next_drive_recovery or not self._idle_drive_control():
            return False
        if self.canopen:
            if self.canopen.ready:
                return False
            self._next_drive_recovery = time.monotonic() + DRIVE_RECONNECT_S
            try:
                self.canopen.connect(self._support_commands(), self.envelope.max_raw, self.envelope.speed_limit_rpm)
                return True
            except (OSError, AttributeError) as exc:
                self._canopen_failure(exc)
                return False
        if self.latch is None and modbus_service.get_status().connected:
            self._next_drive_recovery = time.monotonic() + DRIVE_RECONNECT_S
            if self.state.service_mode or not self._auto_servo or not modbus_service.auto_servo_allowed():
                return False
            if all(self.servo_states().values()) and modbus_service.check_servo_pair():
                return False
        errors = modbus_service.recover_pair(self._support_commands(), self.envelope.max_raw, self.envelope.speed_limit_rpm)
        self._next_drive_recovery = time.monotonic() + DRIVE_RECONNECT_S
        self._wait_for_drives("; ".join(errors) if errors else "Проверка готовности обоих приводов")
        return not errors

    def _auto_enable_block(self) -> str | None:
        if self._stop_event.is_set():
            return "Завершение работы контроллера"
        if self.modbus and (modbus_service.manual_torque_active() or not modbus_service.auto_servo_allowed()):
            return "Ручное управление приводами"
        now = time.monotonic()
        if any(not sample.ok or sample.age(now) > self.envelope.stale_frame_limit_s for sample in self.samples.values()) or len(self.samples) != len(SIDES):
            return "Ожидание свежих данных обоих приводов"
        panel = self.panel.state.to_payload()
        if panel["enabled"] and (not panel["ready"] or not panel["fresh"] or not panel["inputHealthy"]
                                 or panel["stopLatched"] or panel["buttons"]["stop"] or panel["faultCode"] != "none"):
            return "Ожидание готовности панели и кнопки СТОП"
        return None

    def _finish_idle_recovery(self) -> None:
        if self._stop_event.is_set() or not self._idle_drive_control():
            return
        if not self.state.service_mode and self._auto_servo and (not self.modbus or modbus_service.auto_servo_allowed()):
            if reason := self._auto_enable_block():
                self._wait_for_drives(reason)
                return
            if not all(self.servo_states().values()):
                try:
                    self._switch_servos(True, automatic=True)
                except PermissionError as exc:
                    if self.latch in (None, "drive_wait"):
                        self._wait_for_drives(str(exc))
                    return
        self.latch = self.fault_reason = None
        self._force_write = True
        self._emit("drives_ready", "Оба привода на связи, проверка завершена")

    def _drive_error(self, reason: str) -> None:
        if self._idle_drive_control():
            self._wait_for_drives(reason)
        elif self.latch is None:
            self._set_fault(reason)

    def _control_step(self, verified: bool) -> None:
        # B0 explicitly reads the full commissioning report on both drives at rest.
        commissioning = self.calibration and self.calibration.running and self.calibration.current_stage.code == "B0"
        with control_bus_deadline(None if commissioning else time.monotonic() + self.envelope.stale_frame_limit_s):
            if self.bench is not None:
                self.bench.advance(self.tick_seconds)
            if self.modbus and not modbus_service.get_status().connected:
                self.samples = {side: DriveSample(side, time.monotonic(), ok=False, error="Modbus не подключён") for side in SIDES}
            else:
                if self.bench is None and not (self.calibration is not None and self.calibration.running):
                    self._sync_zero()
                self.samples = {side: self.drives[side].read() for side in SIDES}
            frame = Frame(self._frame_t(), dict(self.samples))
            if self.observation is not None:
                self.observation.sample_approach(frame, self.workout, self.envelope.stale_frame_limit_s)
                self.observation.sample(frame, self.workout, self.envelope.stale_frame_limit_s)
            overspeed_mm_s = rpm_to_mm_s(self.envelope.overspeed_rpm_alarm)
            for side, sample in self.samples.items():
                if sample.ok and abs(sample.speed_mm_s) >= overspeed_mm_s:
                    self._set_latch("overspeed", f"Превышение скорости: {side} {sample.speed_mm_s:.0f} мм/с; PA_12C = {ABORT_SUPPORT_RAW}")
            failed = [s for s in self.samples.values() if not s.ok]
            if failed and self.latch is None:
                self._drive_error("; ".join(f"{'левый' if s.side == 'left' else 'правый'}: {s.error}" for s in failed))
            elif verified and not failed and all(s.age(time.monotonic()) <= self.envelope.stale_frame_limit_s for s in self.samples.values()):
                self._finish_idle_recovery()
            now = time.monotonic()
            manual = self.modbus and modbus_service.manual_torque_active() and self.latch not in {"estop", "overspeed"}
            session = self.calibration
            if session is not None and session.running and manual:
                session.cancel("включён ручной момент debug-панели", support=False)
                self._emit("calibration_aborted", f"Калибровка {session.code} прервана: {session.reason}")
            if manual and self.workout.active:
                self._abort_workout("включён ручной момент debug-панели")
            if session is not None and session.running:
                if session.step(frame):
                    self._calibration_finished()
                else:
                    self._last_write = now
            elif self.workout.active and self.latch is None and not manual:
                fault = self.workout.step(frame)
                if self.observation is not None:
                    self.observation.full, self.observation.partial = self.workout.repetitions()
                if self.bench is None:
                    self._trace_motion()
                if fault:
                    self._emit("workout_aborted", fault)
                    self._set_fault(fault)
                    self.abort_hold = True
                    self._write_safe_output()
                self._last_write = now
                self._force_write = not self.workout.active  # parked / aborted: support at once
            else:
                self.workout.step(frame)  # inactive: only follows the bar (stillness for the next start)
                if not manual and (self._force_write or now - self._last_write >= SUPPORT_REFRESH_S):
                    if (self.modbus and not modbus_service.get_status().connected) or (self.canopen and not self.canopen.ready):
                        self._force_write = True
                    else:
                        errors = self._write_safe_output()
                        self._last_write = now
                        self._force_write = bool(errors)
                        if errors and self.latch is None:
                            self._drive_error("Запись PA_12C: " + "; ".join(f"{side}: {error}" for side, error in errors.items()))
            self._sync_state(manual)

    def _trace_motion(self) -> None:
        core, out = self.workout.core, self.workout.output
        if core is None or out is None or not motion_trace.isEnabledFor(logging.INFO):
            return
        left, right = out.states["left"], out.states["right"]
        motion_trace.info(
            "%s/%s xL=%.1f xR=%.1f d=%.1f vL=%.0f vR=%.0f aL=%.0f aR=%.0f FL=%.0f FR=%.0f load=%.0f relief=%.2f cut=%.2f range=%.0f sync=%.1f fall=%.0f/%.0f",
            self.workout.mode, out.mode,
            left.x_mm, right.x_mm, left.x_mm - right.x_mm, left.v_mm_s, right.v_mm_s, left.a_mm_s2, right.a_mm_s2,
            out.forces_n.get("left", 0.0), out.forces_n.get("right", 0.0), core.load.load_n, core.load_relief["left"],
            core.floor_cut, core.range_force_n, core.sync_left_n, core.fall_assist["left"], core.fall_assist["right"],
        )

    def _sync_zero(self) -> None:
        """Replace the zero captured at drive init with the absolute zero of the profile (B7 / «Сброс нуля»).

        Positions are counted from the absolute encoder, so a restart keeps the bar height wherever the bar is.
        Applied once per captured zero; a position outside the travel by more than ``ZERO_SYNC_MARGIN_MM``
        means the absolute position was lost (e.g. encoder battery): the init zero is kept and a warning is logged.
        """

        current = (self._encoder_zero("left"), self._encoder_zero("right"))
        if current[0] is None or current[1] is None or current == self._zero_seen:
            return
        self._zero_seen = (int(current[0]), int(current[1]))
        stored = [self.profile.side(side).zero_counts for side in SIDES]
        if any(item.provenance != "measured" or item.value is None for item in stored):
            return
        target = (int(stored[0].value), int(stored[1].value))
        if target == self._zero_seen:
            return
        # bar height at the init capture, counted from the stored zero
        heights = {
            side: (encoder_delta(c, t) if self.canopen else c - t) * float(self.profile.side(side).mm_per_pulse.value) * self.profile.side(side).sign
            for side, t, c in zip(SIDES, target, self._zero_seen, strict=True)
        }
        limit = float(self.profile.travel_mm.value) + ZERO_SYNC_MARGIN_MM
        if any(abs(height) > limit for height in heights.values()):
            text = ", ".join(f"{'левый' if side == 'left' else 'правый'} {height:.0f} мм" for side, height in heights.items())
            self._emit("zero", f"Абсолютный ноль профиля даёт высоту вне хода ({text}) — оставлен ноль инициализации; выполните «Сброс нуля» на упорах")
            logger.warning("Profile absolute zero %s rejected: init zero %s gives %s mm", target, self._zero_seen, heights)
            return
        if self.canopen:
            self.canopen.zero.update(zip(self.canopen.nodes, target, strict=True))
        else:
            modbus_service.set_session_zero(*target)
        self._zero_seen = target
        logger.info("Profile absolute zero %s applied: bar at %s mm", target, heights)
        self._emit("zero", f"Применён абсолютный ноль: левый {heights['left']:.1f} мм, правый {heights['right']:.1f} мм")

    def _encoder_zero(self, side: Side) -> int | None:
        return (self.canopen.zero.get(self._drive_ids[side]) if self.canopen
                else getattr(modbus_service, f"{side}_zero_pulses", None))

    def _write_safe_output(self) -> dict[Side, str]:
        """Apply support on each side independently, including the overspeed support setting (R3, R5)."""

        errors: dict[Side, str] = {}
        if self.canopen and self.canopen.read_only:
            return errors
        if self.modbus and self.latch in {"estop", "fault"}:
            modbus_service.end_manual_torque()
        for side in SIDES:
            try:
                drive = self.drives[side]
                # Support is a new, independent command even if the preceding workout frame expired.
                with control_bus_deadline(time.monotonic() + self.envelope.stale_frame_limit_s):
                    if self.latch == "overspeed" or self.abort_hold:
                        error = drive.write_raw(ABORT_SUPPORT_RAW * self.profile.side(side).sign)
                    else:
                        error = drive.support()
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            if error:
                errors[side] = error
        self.write_errors = errors
        return errors

    def _set_latch(self, kind: str, reason: str) -> None:
        if self.latch == kind or self.latch == "overspeed":  # R5: the overspeed output is never overridden
            return
        if (self.latch == "estop" and kind != "overspeed") or (self.latch == "fault" and kind == "estop"):
            return
        self.latch = kind
        self.fault_reason = reason
        self._force_write = True
        logger.log(logging.INFO if kind == "drive_wait" else logging.WARNING, "Hardware latch %s: %s", kind, reason)
        self._emit(kind, reason)
        self._finish_observation("interrupted", reason)
        if self.workout.active:
            self._abort_workout(reason)
        if self.calibration is not None and self.calibration.running:
            # the caller writes the safe output (support, or 0 on overspeed)
            self.abort_hold = True
            self.calibration.cancel(reason, support=False, fault_code=kind)
            self._emit("calibration_aborted", f"Калибровка {self.calibration.code} прервана: {reason}")

    def _set_fault(self, reason: str) -> None:
        self._set_latch("fault", reason)

    def _sync_state(self, manual: bool) -> None:
        state = self.state
        observing = self.canopen is not None and self.canopen.read_only
        for side in SIDES:
            sample = self.samples.get(side)
            drive = state.drives[side]
            if sample is None:
                continue
            drive.position_mm = round(sample.position_mm, 1)
            drive.speed_mm_per_sec = round(abs(sample.speed_mm_s), 1)
            if observing:
                axis = self.canopen.monitor.axes[self._drive_ids[side]]
                drive.connected = self.canopen.bus is not None and axis.responding is True
                status = axis.objects.get((0x6041, 0))
                fault = drive.connected and status is not None and status[1] is not None and status[1] & 8
                drive.status = DriveState.error if fault else DriveState.connected if drive.connected else DriveState.warning
                drive.error_code = "CANopen Fault" if fault else None
                drive.error_message = "Авария привода по 6041" if fault else self.canopen.error or axis.issue
                continue
            drive.connected = sample.ok or sample.alarm != 0
            waiting = self.latch == "drive_wait" and not sample.alarm
            drive.error_code = (f"E-DRIVE-{sample.alarm}" if sample.alarm else "E-DRIVE-COMM") if not sample.ok and not waiting else None
            drive.error_message = sample.error if not sample.ok else None
            drive.status = DriveState.connected if sample.ok else DriveState.warning if waiting else DriveState.error
        left, right = self.samples.get("left"), self.samples.get("right")
        motion = state.motion
        motion.sync_available = False
        if left and right:
            motion.left_position_mm = round(left.position_mm, 1)
            motion.right_position_mm = round(right.position_mm, 1)
            motion.bar_position_mm = round((left.position_mm + right.position_mm) / 2, 1)
            session = self.calibration
            monitor = session.runner.pair if session and session.running else self.workout.pair
            if monitor.delta_mm is not None and all(self.samples[s].ok and monitor.previous.get(s) is self.samples[s] for s in SIDES):
                motion.sync_delta_mm = round(monitor.delta_mm, 2)
                motion.sync_available = True
            motion.velocity_mm_per_sec = round((left.speed_mm_s + right.speed_mm_s) / 2, 1)
            motion.moving = max(abs(left.speed_mm_s), abs(right.speed_mm_s)) > 1.0
            motion.control_mode = self.control_mode
            motion.direction = "up" if motion.velocity_mm_per_sec > 1.0 else "down" if motion.velocity_mm_per_sec < -1.0 else motion.direction
            self._sync_workout(motion)
        if state.safety_state == SafetyState.emergency_stop:
            return
        if not self._powered_on:
            state.machine_state, state.machine_label = MachineState.blocked, "Тренажёр выключен"
            state.safety_message = READ_ONLY if observing else "Приводы держат поддержку."
        elif observing and self.latch == "drive_wait":
            state.machine_state, state.machine_label = MachineState.warning, "Диагностика CANopen"
            state.safety_message = READ_ONLY
        elif self.latch == "drive_wait":
            alarms = [f"{'Левый' if sample.side == 'left' else 'Правый'}: {sample.error}" for sample in self.samples.values() if sample.alarm]
            state.machine_state, state.machine_label = (MachineState.blocked, "Авария привода") if alarms else (MachineState.warning, "Ожидание приводов")
            state.safety_message = "; ".join(alarms) or self.fault_reason or "Ожидание связи с приводами"
        elif self.latch in {"fault", "overspeed"}:
            state.machine_state, state.machine_label = MachineState.blocked, "Тренажёр заблокирован"
            state.safety_message = self.fault_reason or "Ошибка привода"
        else:
            blocked = self.motion_block_reason()
            state.machine_state = MachineState.warning if blocked else MachineState.ready
            state.machine_label = "Упражнения недоступны" if blocked else "Готов к тренировке"
            calibration = self.calibration
            if calibration is not None and calibration.running:
                stage = calibration.current_stage
                state.machine_label = f"Калибровка {calibration.code}"
                state.safety_message = f"Калибровка {stage.code}: {stage.note or stage.title}"
            elif manual:
                state.safety_message = "Ручной момент из debug-панели"
            elif self.workout.active or self.workout.reason:
                state.machine_label = "Упражнение" if self.workout.active else state.machine_label
                state.safety_message = self.workout.message() or ""
            else:
                state.safety_message = blocked or "Приводы держат поддержку: гриф на месте"
        state.alerts = ["Сервисный режим активен"] if state.service_mode else []

    def _sync_workout(self, motion: MotionRuntimeState) -> None:
        workout = self.workout
        plan = workout.plan
        full, partial = workout.repetitions()
        motion.repetition_count, motion.partial_reps = full, partial
        motion.amplitude_percent = workout.amplitude_percent()
        kg_per_n = 2 / (G * workout.tunables.exercise_load_scale)
        motion.load_effective_kg = round(workout.load_n * kg_per_n, 1) if workout.active else 0.0
        motion.user_force_kg = round(workout.user_force_n() / G, 1) if workout.active else 0.0
        motion.motion_profile = workout.mode if workout.active else "support"
        if plan is not None:
            motion.load_target_kg = round(plan.load_n * kg_per_n, 1)
            motion.lower_bound_mm, motion.upper_bound_mm = plan.lower_mm, plan.upper_mm
            motion.target_reps, motion.target_set, motion.current_set = plan.target_reps, plan.target_set, plan.target_set
            motion.start_point = plan.start_point
            motion.load_direction = plan.load_direction
            motion.fixed_position_mm = plan.fixed_mm
            motion.load_mode = plan.load_mode

    @property
    def mode(self) -> str:
        if self.latch is None and self.calibration is not None and self.calibration.running:
            return "calibration"
        if self.latch is None and self.workout.active:
            return self.workout.mode
        return self.latch or "support"

    @property
    def control_mode(self) -> str:
        """The mode for the screens: the resting support is ``idle`` (or ``parked`` after a set)."""

        mode = self.mode
        return self.workout.mode if mode == "support" else mode

    def motion_block_reason(self) -> str | None:
        """Why exercises cannot drive the motors now, ``None`` if they can."""

        if self.latch is not None or self.state.safety_state == SafetyState.emergency_stop:
            return self.fault_reason or "Аварийная остановка активна"
        if self.canopen and self.canopen.read_only:
            return READ_ONLY
        if not self._powered_on:
            return "Тренажёр выключен"
        if self.calibration is not None and self.calibration.running:
            return "Идёт калибровка привода"
        if not all(self.servo_states().values()):
            if self._manage_drives and self._auto_servo and (not self.modbus or modbus_service.auto_servo_allowed()) and not self.state.service_mode:
                return "Ожидание автоматического включения приводов"
            return SERVO_OFF_MESSAGE
        if not all(sample.ok for sample in self.samples.values()) or len(self.samples) != len(SIDES):
            return "Нет телеметрии приводов"
        if self.modbus and modbus_service.manual_torque_active():
            return "Активен ручной момент debug-панели"
        missing = [code for code in MOTION_REQUIRED_CALIBRATIONS if calibration_status(self.profile, BY_CODE[code]) not in ("actual", "stale")]
        if missing:
            return "Сначала выполните калибровки привода: " + ", ".join(missing)
        return None

    # ------------------------------------------------------------ exercises
    def _finish_observation(self, status: str, reason: str | None = None) -> None:
        current = self.observation
        if current is not None:
            current.finish(status, reason, self._frame_t())
            self._finished_observations[current.id] = current
            self.observation = None

    def observation_checkpoints(self, *, shutdown: bool = False) -> list[ExerciseObservation]:
        with self._lock:
            if shutdown:
                self._finish_observation("interrupted", "Завершение работы контроллера")
            batch = list(self._finished_observations.values())
            if self.observation is not None:
                batch.append(self.observation.snapshot())
            return batch

    def observations_saved(self, ids: list[str]) -> None:
        with self._lock:
            for record_id in ids:
                self._finished_observations.pop(record_id, None)

    def _abort_workout(self, reason: str) -> None:
        self._finish_observation("interrupted", reason)
        self.workout.abort(reason)
        self.abort_hold = True  # interrupted: the bar is lowered slowly (R5)
        self._force_write = True
        self._emit("workout_aborted", f"Упражнение прервано: {reason}")

    def workout_command(self, action: str, payload: dict[str, Any], calibration: dict[str, Any] | None = None) -> HardwareCommandRecord:
        """Exercise commands from the screens; ``WorkoutError`` / ``PermissionError`` with the reason for the user."""

        extra: dict[str, object] = {}
        with self._lock:
            stopping = action in {"pause", "jog_stop", "jog_keepalive", "complete_set", "park", "hold"}
            blocked = self.motion_block_reason()
            if blocked and not (stopping and self.workout.active and self.latch is None):
                if action in {"jog_stop", "complete_set"} and not self.workout.active:
                    return self._record_command(action, {"skipped": blocked})
                raise WorkoutError(blocked)
            workout = self.workout
            direction = payload.get("load_direction")
            if (action in {"start_motion", "start_fixed_position", "resume", "set_load", "move_to_start"}
                    and direction is not None and direction not in {"down", "up"}):
                raise WorkoutError("Направление нагрузки должно быть down или up")
            if (workout.active and workout.plan is not None
                    and not (workout.load_n <= 1.0 and (
                        workout.mode == "weightless" or (
                            action in {"start_motion", "start_fixed_position"} and workout.completed_rest
                        )
                    ))
                    and action in {"start_motion", "start_fixed_position", "resume", "set_load", "move_to_start"}):
                requested = direction
                if action in {"start_motion", "start_fixed_position"}:
                    requested = requested or (calibration or {}).get("load_direction", "down")
                if requested is not None and requested != workout.plan.load_direction:
                    raise WorkoutError("Направление нагрузки меняется только после завершения подхода")
            if not workout.active:
                self.abort_hold = False
            if action == "enter_weightless":
                workout.enter_weightless()
            elif action == "hold":
                workout.hold()
            elif action == "capture_point":
                extra["capturedPositionMm"] = workout.capture_point()
            elif action == "jog_start":
                workout.jog_start(str(payload.get("jog_id") or ""), 1 if payload.get("direction") == "up" else -1)
            elif action == "jog_keepalive":
                workout.jog_keepalive(str(payload.get("jog_id") or ""))
            elif action == "jog_stop":
                workout.jog_stop(payload.get("jog_id"))
            elif action in {"start_motion", "start_fixed_position"}:
                plan = self._set_plan(action, payload, calibration)
                workout.start_set(plan)
                observation = ExerciseObservation(plan, payload.get("exercise_slug"), self.transport.adapter,
                                                  self.profile.version, self._frame_t(), self.tunables.exercise_load_scale, self.envelope)
                observation.context.update(workoutRunId=payload.get("workout_run_id"), exerciseId=payload.get("workout_exercise_id"),
                                           warmup=bool(payload.get("warmup")))
                if self.observation is not None and self.observation.same_preparation(observation):
                    # The exercise screen may reposition the same unloaded set while waiting for grip.
                    self.observation.context = observation.context
                else:
                    self._finish_observation("interrupted", "Начат следующий подход")
                    self.observation = observation
            elif action == "pause":
                workout.pause()
            elif action == "resume":
                weight = payload.get("weight_kg")
                workout.resume(float(weight) if weight else None)
            elif action == "set_load":
                workout.set_load(float(payload.get("weight_kg") or 0.0))
            elif action == "complete_set":
                if workout.active:
                    workout.complete_set()
            elif action in {"park", "home"}:
                workout.park()
            elif action == "move_to_start":
                if workout.plan is None:
                    raise WorkoutError("Подход не начат")
                workout.start_set(workout.plan)
            else:
                raise WorkoutError(f"Команда «{action}» пока не поддерживается")
            if action == "complete_set":
                self._finish_observation("completed")
            elif action in {"park", "home", "enter_weightless"}:
                self._finish_observation("interrupted", "Парковка грифа" if action != "enter_weightless" else "Включена невесомость")
            if workout.active:
                self._force_write = False
            if action in {"start_motion", "start_fixed_position", "resume", "set_load", "move_to_start"} and workout.plan is not None:
                # Capture the accepted plan under the command lock, not a later telemetry snapshot.
                extra["resolved_load_direction"] = workout.plan.load_direction
            command = self._record_command(action, {key: value for key, value in payload.items() if value is not None} | extra)
            self._sync_state(False)
        self._schedule_broadcast()
        return command

    def _set_plan(self, action: str, payload: dict[str, Any], calibration: dict[str, Any] | None) -> SetPlan:
        if calibration is None:
            raise WorkoutError("Настройка грифа для упражнения не найдена: выполните настройку упражнения")
        load = per_side_n(float(payload.get("weight_kg") or 0.0), self.workout.tunables.exercise_load_scale)
        direction = payload.get("load_direction") or calibration.get("load_direction", "down")
        if direction not in {"down", "up"}:
            raise WorkoutError("Направление нагрузки должно быть down или up")
        common = {
            "load_n": load,
            "load_direction": direction,
            "load_mode": load_mode(payload.get("load_mode")),
            "target_reps": int(payload.get("target_reps") or 10),
            "target_set": int(payload.get("target_set") or 1),
        }
        if action == "start_fixed_position" or calibration.get("setup_type") == "fixed_position":
            position = payload.get("position_mm") or calibration.get("fixed_position_mm")
            if position is None:
                raise WorkoutError("Не задана высота фиксации грифа")
            return SetPlan(lower_mm=float(position) - 1.0, upper_mm=float(position) + 1.0, fixed_mm=float(position), **common)
        lower, upper = calibration.get("lower_point_mm"), calibration.get("upper_point_mm")
        if lower is None or upper is None:
            raise WorkoutError("В настройке грифа нет нижней и верхней точки")
        start = "upper" if (payload.get("start_point") or calibration.get("start_point")) == "upper" else "lower"
        return SetPlan(lower_mm=float(lower), upper_mm=float(upper), start_point=start, **common)  # type: ignore[arg-type]

    @property
    def jog_active(self) -> bool:
        return self.workout.active and self.workout.mode == "moving"

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
            if self.canopen and self.canopen.ready:
                self._exchange_canopen()
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
            if self.canopen and self.canopen.read_only:
                raise PermissionError(READ_ONLY)
            if self.workout.active or (self.calibration and self.calibration.running):
                raise PermissionError("Сброс доступен после остановки упражнения или калибровки")
            if self.latch == "estop" or self.state.safety_state == SafetyState.emergency_stop:
                raise PermissionError("Сначала снимите аварийную остановку")
            if self.modbus:
                errors = self.initialize_modbus_torque(self.envelope.max_raw, self.envelope.speed_limit_rpm)
                if errors:
                    raise PermissionError("Сброс не выполнен: " + "; ".join(errors))
            elif self.canopen:
                try:
                    self.canopen.connect(self._support_commands(), self.envelope.max_raw, self.envelope.speed_limit_rpm, reset_fault=True)
                except (OSError, AttributeError) as exc:
                    self._canopen_failure(exc)
                    raise PermissionError(str(exc)) from exc
            self.latch = None
            self.fault_reason = None
            self._force_write = True
            self._emit("reset", "Ошибка сброшена")
            command = self._record_command("reset_fault", {})
            self.tick()
        self._schedule_broadcast()
        return command

    def initialize_modbus_torque(self, torque_limit: int, speed_limit_rpm: int) -> list[str]:
        with self._lock:
            if self.canopen:
                return ["Активен CANopen. Выберите Modbus в настройках подключения приводов."]
            if self.workout.active or (self.calibration and self.calibration.running):
                return ["Инициализация приводов доступна после остановки упражнения или калибровки"]
            modbus_service.end_manual_torque()
            support = self._support_commands()
            if not modbus_service.get_status().connected:
                return modbus_service.recover_pair(support, torque_limit, speed_limit_rpm)
            return modbus_service.initialize_torque_mode(initial_commands=support, torque_limit=torque_limit, speed_limit_rpm=speed_limit_rpm)

    def set_service_mode(self, enabled: bool) -> HardwareCommandRecord:
        with self._lock:
            if not enabled:
                self._abort_calibration_locked("сервисный режим выключен")
            self.state.service_mode = enabled
            command = self._record_command("toggle_service_mode", {"enabled": enabled})
        self._schedule_broadcast()
        return command

    def reset_zero(self) -> HardwareCommandRecord:
        """Software rebase of both encoders at the current bar position; drives do not move."""

        with self._lock:
            if self.canopen and self.canopen.read_only:
                raise PermissionError(READ_ONLY)
            if not self.state.service_mode:
                raise PermissionError("Сброс нуля — только в сервисном режиме")
            if self.bench is not None:
                raise PermissionError("Сброс нуля доступен только на реальных приводах")
            if (self.calibration is not None and self.calibration.running) or self.workout.active:
                raise PermissionError("Сброс нуля недоступен во время калибровки или упражнения")
            if self.canopen:
                if self.canopen.ready:
                    self._exchange_canopen()
                if not self.canopen.ready:
                    raise PermissionError(self.canopen.error or "Нет показаний CANopen")
                self.canopen.zero = {n: self.canopen.feedback[n][0x6064] for n in self.canopen.nodes}
                left, right = (self.canopen.zero[n] for n in self.canopen.nodes)
            else:
                positions = modbus_service.capture_zero()
                if positions.error:
                    raise PermissionError("Ноль не сброшен: " + positions.error)
                if positions.left_zero_pulses is None or positions.right_zero_pulses is None:
                    raise PermissionError("Ноль не сброшен: нет показаний обоих энкодеров")
                left, right = positions.left_zero_pulses, positions.right_zero_pulses
            # keep the operator's zero: do not let B7 sync replace it with the profile zero
            self._zero_seen = (left, right)
            self._emit("zero", "Нулевая позиция грифа обновлена оператором")
            command = self._record_command("reset_zero_position", {
                "leftZeroPulses": left, "rightZeroPulses": right,
            })
        self._schedule_broadcast()
        return command

    def servo_states(self) -> dict[Side, bool | None]:
        return {side: self.drives[side].servo_state() for side in SIDES}

    def _switch_servos(self, on: bool, *, automatic: bool = False) -> None:
        if on:
            errors = self._write_safe_output()
            self._last_write = time.monotonic()
            if errors:
                raise PermissionError("Поддержка не записана: " + "; ".join(f"{side}: {error}" for side, error in errors.items()))
        if self.canopen:
            def guard() -> str | None:
                self.samples = {s: self.drives[s].read() for s in SIDES}
                return self._auto_enable_block()

            try:
                self.canopen.switch(self.canopen.nodes, on, guard if on else None)
            except OSError as exc:
                self._canopen_failure(exc)
                raise PermissionError(str(exc)) from exc
            self._emit("servo_on" if on else "servo_off", "Оба привода CANopen включены" if on else "Оба привода CANopen выключены")
            return
        errors = {}
        rollback_sides = [] if automatic else list(SIDES)
        for side in SIDES:
            if automatic and (reason := self._auto_enable_block()):
                if side == SIDES[0]:
                    raise PermissionError(reason)
                errors[side] = reason
                break
            if automatic and self.drives[side].servo_state() is not True:
                rollback_sides.append(side)
            with control_bus_deadline(time.monotonic() + self.envelope.stale_frame_limit_s):
                error = self.drives[side].set_servo(on)
            if error:
                errors[side] = error
                if on:
                    break
        if on and errors:
            # A previously enabled axis may be holding a raised bar. Undo only our own automatic enable attempts.
            for side in rollback_sides:
                with control_bus_deadline(time.monotonic() + self.envelope.stale_frame_limit_s):
                    rollback = self.drives[side].set_servo(False)
                if rollback:
                    errors[side] = f"{errors.get(side, '')} Servo OFF: {rollback}".strip()
        label = "Приводы включены" if on else "Приводы выключены"
        details = "; ".join(f"{side}: {error}" for side, error in errors.items())
        if errors:
            raise PermissionError(f"{'Включение' if on else 'Выключение'} приводов не выполнено: {details}")
        self._emit("servo_on" if on else "servo_off", label)

    def set_servo(self, on: bool) -> HardwareCommandRecord:
        """SRV-ON/OFF on both drives, service mode only. Servo OFF drops a raised bar (no DB)."""

        with self._lock:
            if self.canopen and self.canopen.read_only:
                raise PermissionError(READ_ONLY)
            if not self.state.service_mode:
                raise PermissionError("Включение и выключение приводов — только в сервисном режиме")
            self._abort_calibration_locked("приводы включены/выключены оператором")
            if self.workout.active:
                self._abort_workout("приводы включены/выключены оператором")
            if on and (self.latch is not None or self.state.safety_state != SafetyState.enabled or not self._powered_on):
                raise PermissionError("Сначала включите тренажёр, снимите СТОП и сбросьте ошибку")
            self._auto_servo = False  # an explicit OFF or failed manual ON requires an explicit ON
            try:
                self._switch_servos(on)
            except PermissionError:
                self._sync_state(False)
                raise
            self._auto_servo = on
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

    # ----------------------------------------------------------- calibration
    def _frame_t(self) -> float:
        return self.bench.t if self.bench is not None else time.monotonic()

    def _zero_error_locked(self) -> str | None:
        if self.bench is None:
            problems = []
            for side in SIDES:
                stored = self.profile.side(side).zero_counts
                actual = self._encoder_zero(side)
                label = "левый" if side == "left" else "правый"
                if stored.provenance != "measured" or stored.value is None:
                    problems.append(f"{label}: нет сохранённого результата B7")
                elif actual is None:
                    problems.append(f"{label}: фактический ноль неизвестен")
                elif stored.value != actual:
                    problems.append(f"{label}: ноль инициализации не совпадает с принятым B7")
            if problems:
                return "; ".join(problems) + ". Проверьте и сохраните ноль B7 на нижних упорах"
        return None

    def _middle_zone_locked(self, code: str) -> tuple[dict[str, float] | None, dict[str, Any]]:
        """Resolve the guided window against the same absolute zero the live drives use."""
        error = self._zero_error_locked()
        zone: dict[str, float] | None = None
        if error is None:
            try:
                low_mm, high_mm = middle_window(code, self.profile, self.envelope)
                zone = {"lowMm": float(low_mm), "highMm": float(high_mm)}
            except ValueError as exc:
                error = f"Рабочая зона не вычислена: {exc}"
        return zone, {
            "id": "middleZone",
            "label": "Рабочая зона и абсолютный ноль подтверждены",
            "ok": error is None,
            "detail": error,
        }

    def _calibration_preconditions_locked(self, code: str, working_zone: str | None = None) -> tuple[list[dict[str, Any]], dict[str, float] | None]:
        samples = self.samples
        servo = self.servo_states()
        positions = {side: sample.position_mm for side, sample in samples.items() if sample.ok}
        telemetry_ok = len(samples) == len(SIDES) and all(sample.ok for sample in samples.values())
        on_stops = telemetry_ok and all(abs(x) <= ON_STOPS_MM for x in positions.values())
        stops_detail = ", ".join(f"{'Л' if side == 'left' else 'П'} {x:.1f} мм" for side, x in positions.items()) or None
        if not on_stops and telemetry_ok and self.profile.support_holds.value:
            stops_detail = f"{stops_detail}; поддержка держит гриф — опустите его рукой"
        manual = self.modbus and modbus_service.manual_torque_active()
        stages = RUNNABLE.get(code, ())
        missing = sorted({
            required for required in (RUN_SPECS[code].requires if stages else ())
            if BY_CODE[required].implemented and BY_CODE[required].produces
            and calibration_status(self.profile, BY_CODE[required]) not in ("actual", "stale")
        })
        busy = self.calibration is not None and self.calibration.running
        estop = self.state.safety_state == SafetyState.emergency_stop
        items = [
            {"id": "service", "label": "Сервисный режим включён", "ok": self.state.service_mode, "detail": None if self.state.service_mode else "Нажмите «Включить сервисный режим» в панели состояния"},
            {"id": "safety", "label": "Нет СТОП и ошибок привода", "ok": self.latch is None and not estop, "detail": self.fault_reason if self.latch or estop else None},
            {"id": "servo", "label": "Оба привода включены (Servo ON)", "ok": all(servo.values()), "detail": None if all(servo.values()) else "В сервисном режиме нажмите «Включить приводы» в панели состояния"},
            {"id": "telemetry", "label": "Телеметрия обеих сторон в норме", "ok": telemetry_ok, "detail": None if telemetry_ok else "; ".join(f"{s.side}: {s.error}" for s in samples.values() if not s.ok) or "нет данных"},
            {"id": "stops", "label": f"Гриф на нижних упорах (≤ {ON_STOPS_MM:.0f} мм)", "ok": on_stops, "detail": stops_detail},
            {"id": "manual", "label": "Ручной момент debug-панели не активен", "ok": not manual, "detail": None if not manual else "Остановите ручной момент на странице Modbus"},
            {"id": "requires", "label": "Выполнены предыдущие калибровки", "ok": not missing, "detail": ("Сначала: " + ", ".join(missing)) if missing else None},
            {"id": "idle", "label": "Другая калибровка не выполняется", "ok": not busy, "detail": None},
            {"id": "workout", "label": "Упражнение не выполняется", "ok": not self.workout.active, "detail": None if not self.workout.active else "Завершите подход или опустите гриф на упоры"},
        ]
        if code in EMPTY_SERIES:
            error = self._zero_error_locked()
            if error is None:
                try:
                    confirmed_bounds(self.profile, self.envelope)
                    for stage in stages:
                        if stage in MIDDLE_CODES:
                            middle_window(stage, self.profile, self.envelope)
                except ValueError as exc:
                    error = str(exc)
            items.append({"id": "seriesTravel", "label": "Проверены ноль, ход и границы измерений всей серии", "ok": error is None, "detail": error})
        if code == "N1" and self.bench is None:
            error = self._zero_error_locked()
            items.append({"id": "zero", "label": "Положение нижних упоров подтверждено B7", "ok": error is None, "detail": error})
        if code not in REQUIRED_MIDDLE and working_zone != "middle":
            return items, None
        zone, middle = self._middle_zone_locked(code)
        return [*items, middle], zone

    def calibration_preconditions(self, code: str, working_zone: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return self._calibration_preconditions_locked(code, working_zone)[0]

    def start_calibration(self, code: str, options: dict[str, Any] | None = None) -> CalibrationSession:
        """Service mode, no latch, servo on, bar on the stops; the operator holds the dead-man (keepalive)."""

        with self._lock:
            if self.canopen and self.canopen.read_only:
                raise PermissionError(READ_ONLY)
            if code not in RUNNABLE:
                raise ValueError(f"Калибровка {code} не запускается из интерфейса")
            options = dict(options or {})
            working_zone = options.get("workingZone")
            if working_zone not in (None, "middle"):
                raise ValueError("Рабочая зона должна быть middle")
            if self.workout.active:
                raise PermissionError("Упражнение выполняется: завершите подход, затем запускайте калибровку")
            preconditions, _ = self._calibration_preconditions_locked(code, working_zone)
            failed = [item for item in preconditions if not item["ok"]]
            if failed:
                item = failed[0]
                raise PermissionError(f"Не выполнено условие «{item['label']}»" + (f": {item['detail']}" if item["detail"] else ""))
            previous = self.calibration
            if previous is not None and previous.status == "done" and previous.saved_version is None and any(item["changed"] for item in previous.changes()):
                raise PermissionError("Сначала сохраните или отклоните несохранённые изменения предыдущей калибровки")
            session = CalibrationSession(code, self.drives, self.profile, options=options, safety=self.envelope,
                                         tunables=self.tunables, adapter=self.transport.adapter)
            self.abort_hold = False
            self.calibration = session
            self._emit("calibration_start", f"Калибровка {code} запущена", {"id": session.id})
            self._record_command("calibration_start", {"code": code, "id": session.id})
            session.begin()
            if not session.running:
                self._calibration_finished()
            self._sync_state(False)
        self._schedule_broadcast()
        return session

    def calibration_keepalive(self, client_interval_ms: float | None = None, session_id: str | None = None) -> bool:
        # no lock: the tick holds it for the whole bus exchange; act only on this one captured session
        session = self.calibration
        if session is None or not session.running or (session_id is not None and session.id != session_id):
            return False
        gap = time.monotonic() - session.keepalive_at
        if gap >= HEARTBEAT_GAP_S:
            # client interval ≈ gap: the browser sent late; client interval small: the request was held up on the way
            logger.warning(
                "Calibration %s: heartbeat after %.0f ms (screen sent it %s ms after the previous one)",
                session.code, gap * 1000, "?" if client_interval_ms is None else f"{client_interval_ms:.0f}",
            )
        session.keepalive()
        return self.calibration is session and session.running

    def calibration_reply(self, value: float | None, session_id: str | None = None, prompt_text: str | None = None) -> None:
        """Operator's answer to the prompt of the running calibration (``ValueError`` if nothing is asked or it does not fit)."""

        with self._lock:
            session = self.calibration
            if session_id is not None and (session is None or session.id != session_id):
                raise PermissionError("Ответ относится к другой сессии калибровки")
            if session is None or not session.running:
                raise ValueError("Калибровка не выполняется")
            prompt = session.prompt
            if prompt_text is not None and (prompt is None or prompt.text != prompt_text):
                raise ValueError("Ответ относится к другому вопросу калибровки")
            session.reply(value)
            self._record_command("calibration_reply", {"id": session.id, "value": value})

    def _abort_calibration_locked(self, reason: str) -> bool:
        session = self.calibration
        if session is None or not session.running:
            return False
        session.cancel(reason, support=False)
        self._calibration_finished()
        return True

    def abort_calibration(self, reason: str = "прервано оператором", session_id: str | None = None) -> bool:
        with self._lock:
            session = self.calibration
            if session_id is not None and (session is None or session.id != session_id):
                return False
            aborted = self._abort_calibration_locked(reason)
            self._sync_state(False)
        self._schedule_broadcast()
        return aborted

    def _calibration_finished(self) -> None:
        """Support right after the session releases the drives (with the active profile restored)."""

        session = self.calibration
        if session is not None and session.status != "done":
            self.abort_hold = True
            if session.runner.result.abort_code in ("skew", "telemetry", "drive"):
                self._set_fault(session.reason or "Ошибка парного измерения")
            elif session.runner.result.drive_write_failed:
                self._set_fault(session.reason or "Ошибка записи в привод во время калибровки")
        errors = self._write_safe_output()
        if errors:
            self._set_fault("Ошибка поддержки после калибровки: " + "; ".join(f"{side}: {error}" for side, error in errors.items()))
        self._last_write = time.monotonic()
        self._force_write = bool(errors)
        session = self.calibration
        if session is not None:
            labels = {"done": "завершена", "aborted": "прервана", "failed": "не удалась"}
            message = f"Калибровка {session.code} {labels.get(session.status, session.status)}" + (f": {session.reason}" if session.reason else "")
            self._emit(f"calibration_{session.status}", message, {"id": session.id})
        self._schedule_broadcast()

    def discard_calibration(self, session_id: str | None = None) -> None:
        with self._lock:
            session = self.calibration
            if session_id is not None and (session is None or session.id != session_id):
                raise PermissionError("Отклонение относится к другой сессии калибровки")
            if session is not None and session.running:
                raise PermissionError("Калибровка ещё выполняется — сначала прервите её")
            self.calibration = None

    def calibration_payload(
        self,
        code: str,
        working_zone: str | None = None,
        run: CalibrationSession | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            preconditions, zone = self._calibration_preconditions_locked(code, working_zone)
            session = self.calibration if run is None else run
            payload = {
                "session": session.to_payload() if session is not None else None,
                "preconditions": preconditions,
                "profileVersion": self.profile.version,
            }
            if working_zone == "middle" or code in REQUIRED_MIDDLE:
                payload["workingZone"] = zone
            return payload

    def apply_profile(self, profile: MachineProfile, envelope: SafetyEnvelope | None = None, tunables: Tunables | None = None) -> None:
        """Make a saved profile active without a restart; support is rewritten with the new sign/raw."""

        with self._lock:
            if self.calibration is not None and self.calibration.running:
                raise PermissionError("Идёт калибровка — профиль нельзя менять")
            if self.workout.active:
                raise PermissionError("Идёт упражнение — профиль нельзя менять")
            self.profile = profile
            self._zero_seen = None  # re-check the absolute zero against the new profile
            if envelope is not None:
                self.envelope = envelope
                if self.canopen and self.canopen.ready and (self.canopen.max_raw, self.canopen.speed_limit) != (envelope.max_raw, envelope.speed_limit_rpm):
                    try:
                        self.canopen.update_limits(envelope.max_raw, envelope.speed_limit_rpm)
                    except OSError as exc:
                        self._canopen_failure(exc)
            if tunables is not None:
                self.tunables = tunables
            self.workout.configure(self.profile, self.tunables, self.envelope)
            for side in SIDES:
                drive = self.drives[side]
                drive.profile = profile.side(side)  # type: ignore[attr-defined]
                if envelope is not None and hasattr(drive, "max_raw"):
                    drive.max_raw = envelope.max_raw
            self._force_write = True
            self._emit("profile", f"Применён профиль v{profile.version}")
        self._schedule_broadcast()

    # -------------------------------------------------------------- snapshot
    def scale_monitoring_block_reason(self) -> str | None:
        """Read-only guard for optional BLE; no commands, I/O or publications."""
        with self._lock:
            if self.calibration is not None and self.calibration.running:
                return "Калибровка тренажёра"
            if self.workout.active:
                return "Настройка или выполнение упражнения"
            return None

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
        blocked = self.motion_block_reason()
        return {
            "mode": self.control_mode,
            "label": self.state.machine_label,
            "message": self.state.safety_message,
            "motorControl": "disabled" if blocked else "enabled",
            "motorControlMessage": blocked,
            "stillMs": int(self.workout.still_s * 1000),
            "holdReason": self.workout.reason,
            "loadTargetKg": motion.load_target_kg,
            "loadDirection": motion.load_direction,
            "loadEffectiveKg": motion.load_effective_kg,
            "positionMm": motion.bar_position_mm,
            "velocityMmPerSec": motion.velocity_mm_per_sec,
            "syncDeltaMm": motion.sync_delta_mm,
            "syncStatus": "unavailable" if not motion.sync_available else "critical" if abs(motion.sync_delta_mm) >= self.envelope.sync_critical_mm else ("warning" if abs(motion.sync_delta_mm) >= self.envelope.sync_warning_mm else "ok"),
            "postStatus": "skipped",
            "positionKnown": len(self.samples) == len(SIDES) and all(sample.ok for sample in self.samples.values()),
            "commOk": len(self.samples) == len(SIDES) and all(sample.ok for sample in self.samples.values()),
            "faultCode": self.fault_reason if self.latch in {"fault", "overspeed"} else None,
            "supportRaw": {side: drive.last_raw for side, drive in self.drives.items()},  # type: ignore[attr-defined]
            "servo": self.servo_states(),
            "writeErrors": dict(self.write_errors),
            "adapter": f"{self.transport.adapter}-torque" if self.bench is None else "twin",
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
            if self.latch == "drive_wait":
                return "error" if any(sample.alarm for sample in self.samples.values()) else "warning"
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
                self._emit("panel_button_rejected", PANEL_MOTION_MESSAGE, {"button": event.button_id})
        if event.action in {"pressed", "repeat"}:
            self.panel.send_command("button_feedback", id=event.button_id, request_seq=event.sequence, accepted=accepted)
        self._schedule_broadcast()

    # ------------------------------------------------------------- plumbing
    def _emit(self, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append({"t": round(time.monotonic(), 3), "kind": kind, "message": message, "payload": payload or {}})
        if kind.endswith("_aborted"):
            logger.warning("Hardware event %s: %s", kind, message)

    def _record_command(self, action: str, payload: dict[str, object]) -> HardwareCommandRecord:
        self._command_counter += 1
        command = HardwareCommandRecord(self._command_counter, action, "completed", datetime.now(UTC), payload)
        self.state.recent_commands.append(command)
        return command

    async def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        # subscribers live on the event loop only: no runtime lock here, a tick may hold it for the whole RS-485 exchange
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)
        await queue.put(await asyncio.to_thread(self.snapshot_payload))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        self._subscribers.discard(queue)

    def _schedule_broadcast(self) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self._broadcast_snapshot(), self._loop)

    async def _broadcast_snapshot(self) -> None:
        payload = await asyncio.to_thread(self.snapshot_payload)  # never wait for the runtime lock on the event loop
        for subscriber in list(self._subscribers):
            try:
                subscriber.put_nowait(payload)
            except asyncio.QueueFull:
                self._subscribers.discard(subscriber)


hardware_runtime = HardwareRuntime()
