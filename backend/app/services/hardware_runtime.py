from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock

from app.models.enums import DriveState, MachineState, SafetyState


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
        self._command_counter = 0
        self.state = self._build_default_state()

    def _build_default_state(self) -> HardwareRuntimeState:
        return HardwareRuntimeState(
            drives={
                "left": DriveRuntimeState(
                    side="left",
                    status=DriveState.connected,
                    connected=True,
                    position_mm=860.0,
                    speed_mm_per_sec=42.0,
                    acceleration_mm_per_sec2=110.0,
                    jerk_mm_per_sec3=210.0,
                    torque_limit_percent=72,
                    current_a=1.2,
                    temperature_c=31.4,
                ),
                "right": DriveRuntimeState(
                    side="right",
                    status=DriveState.connected,
                    connected=True,
                    position_mm=860.4,
                    speed_mm_per_sec=42.0,
                    acceleration_mm_per_sec2=111.0,
                    jerk_mm_per_sec3=208.0,
                    torque_limit_percent=72,
                    current_a=1.1,
                    temperature_c=31.2,
                ),
            }
        )

    def reset(self) -> None:
        with self._lock:
            subscribers = self._subscribers
            self.state = self._build_default_state()
            self._subscribers = subscribers
            self._command_counter = 0
        self._schedule_broadcast()

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
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

    async def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        with self._lock:
            self._subscribers.add(queue)
        await queue.put(self.snapshot_payload())
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        with self._lock:
            self._subscribers.discard(queue)

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
            self.state.safety_state = SafetyState.emergency_stop
            self.state.machine_state = MachineState.blocked
            self.state.machine_label = "СТОП активирован"
            self.state.safety_message = "Аварийная остановка активна. Любое движение заблокировано."
            self.state.motion.moving = False
            self.state.alerts = ["Аварийная остановка активна"]
            command = self._record_command("trigger_emergency_stop", {})
        self._schedule_broadcast()
        return command

    def clear_emergency_stop(self) -> HardwareCommandRecord:
        with self._lock:
            self.state.safety_state = SafetyState.enabled
            self.state.machine_state = MachineState.ready
            self.state.machine_label = "Тренажёр готов"
            self.state.safety_message = "Система безопасности готова к тренировке."
            self.state.alerts = []
            command = self._record_command("clear_emergency_stop", {})
        self._schedule_broadcast()
        return command

    def set_service_mode(self, enabled: bool) -> HardwareCommandRecord:
        with self._lock:
            self.state.service_mode = enabled
            self.state.machine_state = MachineState.warning if enabled else MachineState.ready
            self.state.machine_label = "Сервисный режим" if enabled else "Тренажёр готов"
            self.state.alerts = ["Сервисный режим активен"] if enabled else []
            command = self._record_command("toggle_service_mode", {"enabled": enabled})
        self._schedule_broadcast()
        return command

    def run_diagnostics(self) -> HardwareCommandRecord:
        with self._lock:
            self.state.diagnostics_status = "passed"
            self.state.last_diagnostics_at = datetime.now(UTC)
            self.state.machine_label = "Диагностика пройдена"
            command = self._record_command("run_diagnostics", {})
        self._schedule_broadcast()
        return command

    def home(self) -> HardwareCommandRecord:
        with self._lock:
            self.state.motion.bar_position_mm = 0.0
            self.state.motion.left_position_mm = 0.0
            self.state.motion.right_position_mm = 0.0
            self.state.motion.amplitude_percent = 0
            for drive in self.state.drives.values():
                drive.position_mm = 0.0
            command = self._record_command("home", {})
        self._schedule_broadcast()
        return command

    def reset_zero_position(self) -> HardwareCommandRecord:
        with self._lock:
            midpoint = (self.state.motion.lower_bound_mm + self.state.motion.upper_bound_mm) / 2
            self.state.motion.bar_position_mm = midpoint
            self.state.motion.left_position_mm = midpoint
            self.state.motion.right_position_mm = midpoint + 0.4
            for drive in self.state.drives.values():
                drive.position_mm = midpoint if drive.side == "left" else midpoint + 0.4
            command = self._record_command("reset_zero_position", {"positionMm": midpoint})
        self._schedule_broadcast()
        return command

    def manual_move(self, direction: str, distance_mm: float, profile: str) -> HardwareCommandRecord:
        with self._lock:
            delta = distance_mm if direction == "up" else -distance_mm
            next_position = self._clamp_position(self.state.motion.bar_position_mm + delta)
            self.state.motion.motion_profile = profile
            self._set_position(next_position)
            self.state.motion.direction = direction
            self.state.machine_state = MachineState.warning if profile == "service" else self.state.machine_state
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
    ) -> HardwareCommandRecord:
        with self._lock:
            self.state.active_calibration_id = calibration_id
            self.state.calibration_required = True
            self.state.calibration_actual = calibration_id is not None
            self.state.motion.moving = True
            self.state.motion.motion_profile = motion_profile
            self.state.motion.lower_bound_mm = lower_bound_mm
            self.state.motion.upper_bound_mm = upper_bound_mm
            self.state.motion.current_set = min(max(target_set, 1), 12)
            self.state.motion.target_set = min(max(target_set, 1), 12)
            self.state.motion.target_reps = min(max(target_reps, 1), 50)
            self.state.motion.repetition_count = 0
            self.state.motion.direction = "up"
            self.state.machine_state = MachineState.ready
            self.state.machine_label = "Движение выполняется"
            self.state.safety_message = "Безопасный профиль движения активен."
            self.state.alerts = []
            command = self._record_command(
                "start_motion",
                {
                    "calibrationId": calibration_id,
                    "lowerBoundMm": lower_bound_mm,
                    "upperBoundMm": upper_bound_mm,
                    "targetSet": target_set,
                    "targetReps": target_reps,
                    "motionProfile": motion_profile,
                },
            )
        self._schedule_broadcast()
        return command

    def complete_set(self) -> HardwareCommandRecord:
        with self._lock:
            self.state.motion.moving = False
            self.state.machine_label = "Подход завершён"
            command = self._record_command("complete_set", {"repetitionCount": self.state.motion.repetition_count})
        self._schedule_broadcast()
        return command

    def snapshot_payload(self) -> dict[str, object]:
        with self._lock:
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
                "calibrationRequired": self.state.calibration_required,
                "calibrationActual": self.state.calibration_actual,
                "activeCalibrationId": self.state.active_calibration_id,
                "commandQueueDepth": len(self.state.recent_commands),
                "lastCommand": self.state.recent_commands[-1].to_payload() if self.state.recent_commands else None,
                "diagnosticsStatus": self.state.diagnostics_status,
                "lastDiagnosticsAt": self.state.last_diagnostics_at.isoformat() if self.state.last_diagnostics_at else None,
                "alerts": list(self.state.alerts),
            }
        return payload

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(0.5)
                if self._tick_motion():
                    await self._broadcast_snapshot()
        except asyncio.CancelledError:
            raise

    def _tick_motion(self) -> bool:
        with self._lock:
            if not self.state.motion.moving or self.state.safety_state == SafetyState.emergency_stop:
                return False

            step = max(self.state.drives["left"].speed_mm_per_sec, self.state.drives["right"].speed_mm_per_sec) * 0.5
            delta = step if self.state.motion.direction == "up" else -step
            next_position = self.state.motion.bar_position_mm + delta
            completed_rep = False

            if next_position >= self.state.motion.upper_bound_mm:
                next_position = self.state.motion.upper_bound_mm
                self.state.motion.direction = "down"
            elif next_position <= self.state.motion.lower_bound_mm:
                next_position = self.state.motion.lower_bound_mm
                if self.state.motion.direction == "down":
                    completed_rep = True
                self.state.motion.direction = "up"

            self._set_position(next_position)
            if completed_rep:
                self.state.motion.repetition_count += 1
                if self.state.motion.repetition_count >= self.state.motion.target_reps:
                    self.state.motion.moving = False
                    self.state.machine_label = "Цель подхода достигнута"
            amplitude = (next_position - self.state.motion.lower_bound_mm) / max(
                self.state.motion.upper_bound_mm - self.state.motion.lower_bound_mm,
                1.0,
            )
            self.state.motion.amplitude_percent = max(0, min(100, int(round(amplitude * 100))))
            self.state.motion.tempo_label = "стабилен" if self.state.motion.repetition_count % 2 == 0 else "ускорение"
            self.state.motion.sync_delta_mm = abs(self.state.motion.left_position_mm - self.state.motion.right_position_mm)
            self.state.machine_state = MachineState.warning if self.state.motion.sync_delta_mm > 5 else MachineState.ready
            return True

    def _set_position(self, position_mm: float) -> None:
        right_position = self._clamp_position(position_mm + 0.4)
        left_position = self._clamp_position(position_mm)
        self.state.motion.bar_position_mm = round(position_mm, 1)
        self.state.motion.left_position_mm = round(left_position, 1)
        self.state.motion.right_position_mm = round(right_position, 1)
        self.state.drives["left"].position_mm = round(left_position, 1)
        self.state.drives["right"].position_mm = round(right_position, 1)
        self.state.motion.sync_delta_mm = round(abs(right_position - left_position), 2)

    def _clamp_position(self, position_mm: float) -> float:
        return max(0.0, min(1400.0, position_mm))

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


hardware_runtime = HardwareRuntime()