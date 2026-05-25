from __future__ import annotations

import asyncio
import os
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

try:
    import keyboard as keyboard_module
except ImportError:  # pragma: no cover - optional runtime dependency before install
    keyboard_module = None

from app.core.config import get_settings
from app.models.enums import DriveState, MachineState, SafetyState

DEFAULT_MOTION_TICK_SECONDS = 0.1
KEYBOARD_SIMULATION_TICK_SECONDS = 0.02
VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_UP = 0x26
VK_DOWN = 0x28

if os.name == "nt":
    WH_KEYBOARD_LL = 13
    HC_ACTION = 0
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    WM_QUIT = 0x0012


if os.name == "nt":
    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]


class KeyboardCombinationMonitor:
    def __init__(self) -> None:
        self._lock = RLock()
        self._pressed_keys: set[int] = set()
        self._pressed_names: set[str] = set()
        self._backend: str | None = None
        self._keyboard_hook: Any = None
        self._thread: Any = None
        self._thread_id: int | None = None
        self._hook_id: Any = None
        self._callback: Any = None
        self._ready_event: Any = None

    def start(self) -> None:
        if os.name != "nt":
            return

        if keyboard_module is not None:
            with self._lock:
                if self._backend == "keyboard":
                    return
                self._pressed_keys.clear()
                self._pressed_names.clear()
                self._keyboard_hook = keyboard_module.hook(self._handle_keyboard_event)
                self._backend = "keyboard"
            return

        import threading

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._pressed_keys.clear()
            self._pressed_names.clear()
            self._ready_event = threading.Event()
            self._thread = threading.Thread(target=self._run, name="hardware-keyboard-monitor", daemon=True)
            self._thread.start()
            ready_event = self._ready_event
            self._backend = "win32"

        if ready_event is not None:
            ready_event.wait(timeout=2.0)

    def stop(self) -> None:
        if os.name != "nt":
            return

        backend = None
        keyboard_hook = None

        thread = None
        thread_id = None
        with self._lock:
            backend = self._backend
            keyboard_hook = self._keyboard_hook
            thread = self._thread
            thread_id = self._thread_id
            self._backend = None
            self._keyboard_hook = None
            self._thread = None
            self._thread_id = None
            self._ready_event = None
            self._pressed_keys.clear()
            self._pressed_names.clear()

        if backend == "keyboard" and keyboard_module is not None and keyboard_hook is not None:
            keyboard_module.unhook(keyboard_hook)
            return

        if thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)

        if thread is not None:
            thread.join(timeout=2.0)

    def get_direction(self) -> str | None:
        with self._lock:
            if self._backend == "keyboard":
                ctrl_pressed = "ctrl" in self._pressed_names
                up_pressed = "up" in self._pressed_names
                down_pressed = "down" in self._pressed_names
            else:
                ctrl_pressed = any(key in self._pressed_keys for key in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL))
                up_pressed = VK_UP in self._pressed_keys
                down_pressed = VK_DOWN in self._pressed_keys

        if not ctrl_pressed or up_pressed == down_pressed:
            return None

        return "up" if up_pressed else "down"

    def _handle_keyboard_event(self, event: Any) -> None:
        normalized_name = self._normalize_key_name(getattr(event, "name", None))
        if normalized_name is None:
            return

        event_type = getattr(event, "event_type", "")
        with self._lock:
            if event_type == "down":
                self._pressed_names.add(normalized_name)
            elif event_type == "up":
                self._pressed_names.discard(normalized_name)

    @staticmethod
    def _normalize_key_name(name: str | None) -> str | None:
        if name is None:
            return None

        normalized = name.lower()
        if normalized in {"ctrl", "left ctrl", "right ctrl"}:
            return "ctrl"
        if normalized in {"up", "down"}:
            return normalized

        return None

    def _run(self) -> None:
        if os.name != "nt":
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        LowLevelKeyboardProc = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        def keyboard_proc(code: int, w_param: int, l_param: int) -> int:
            if code == HC_ACTION:
                keyboard_data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk_code = int(keyboard_data.vkCode)
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    with self._lock:
                        self._pressed_keys.add(vk_code)
                elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                    with self._lock:
                        self._pressed_keys.discard(vk_code)

            return int(user32.CallNextHookEx(self._hook_id, code, w_param, l_param))

        callback = LowLevelKeyboardProc(keyboard_proc)
        hook_id = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, kernel32.GetModuleHandleW(None), 0)

        with self._lock:
            self._callback = callback
            self._hook_id = hook_id
            self._thread_id = int(kernel32.GetCurrentThreadId())
            if self._ready_event is not None:
                self._ready_event.set()

        if not hook_id:
            return

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

        with self._lock:
            if self._hook_id:
                user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
            self._callback = None
            self._pressed_keys.clear()


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
        self._keyboard_simulation_enabled = False
        self._rep_armed = False
        self._tick_interval_seconds = DEFAULT_MOTION_TICK_SECONDS
        self._keyboard_monitor = KeyboardCombinationMonitor()
        self.state = self._build_default_state()
        self._refresh_runtime_options()

    def _build_default_state(self) -> HardwareRuntimeState:
        return HardwareRuntimeState(
            drives={
                "left": DriveRuntimeState(
                    side="left",
                    status=DriveState.connected,
                    connected=True,
                    position_mm=860.0,
                    speed_mm_per_sec=1000.0,
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
                    speed_mm_per_sec=1000.0,
                    acceleration_mm_per_sec2=111.0,
                    jerk_mm_per_sec3=208.0,
                    torque_limit_percent=72,
                    current_a=1.1,
                    temperature_c=31.2,
                ),
            }
        )

    def reset(self) -> None:
        self._refresh_runtime_options()
        with self._lock:
            subscribers = self._subscribers
            self.state = self._build_default_state()
            self._subscribers = subscribers
            self._command_counter = 0
            self._rep_armed = False
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
            self._update_motion_metrics(self.state.motion.bar_position_mm)
            self._rep_armed = self.state.motion.bar_position_mm <= lower_bound_mm or self.state.motion.amplitude_percent == 0
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
            self._rep_armed = False
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
                await asyncio.sleep(self._tick_interval_seconds)
                if self._tick_motion():
                    await self._broadcast_snapshot()
        except asyncio.CancelledError:
            raise

    def _tick_motion(self) -> bool:
        with self._lock:
            if self.state.safety_state == SafetyState.emergency_stop:
                return False

            if self._keyboard_simulation_enabled:
                return self._tick_keyboard_simulation()

            if not self.state.motion.moving:
                return False

            step = max(self.state.drives["left"].speed_mm_per_sec, self.state.drives["right"].speed_mm_per_sec) * DEFAULT_MOTION_TICK_SECONDS
            delta = step if self.state.motion.direction == "up" else -step
            next_position = self.state.motion.bar_position_mm + delta
            completed_rep = False

            if next_position >= self.state.motion.upper_bound_mm:
                next_position = self.state.motion.upper_bound_mm
                if self.state.motion.direction == "up" and self._rep_armed:
                    completed_rep = True
                    self._rep_armed = False
                self.state.motion.direction = "down"
            elif next_position <= self.state.motion.lower_bound_mm:
                next_position = self.state.motion.lower_bound_mm
                if self.state.motion.direction == "down":
                    self._rep_armed = True
                self.state.motion.direction = "up"

            self._set_position(next_position)
            if completed_rep:
                self.state.motion.repetition_count += 1
                if self.state.motion.repetition_count >= self.state.motion.target_reps:
                    self.state.motion.moving = False
                    self.state.machine_label = "Цель подхода достигнута"
            self._update_motion_metrics(next_position)
            return True

    def _tick_keyboard_simulation(self) -> bool:
        direction = self._get_keyboard_direction()
        if direction is None:
            if not self.state.motion.moving and self.state.motion.motion_profile != "keyboard-sim":
                return False
            self.state.motion.moving = False
            self.state.motion.motion_profile = "manual"
            self.state.motion.tempo_label = "остановлен"
            self.state.machine_label = "Тренажёр готов"
            self.state.safety_message = "Система безопасности готова к тренировке."
            return True

        step = max(self.state.drives["left"].speed_mm_per_sec, self.state.drives["right"].speed_mm_per_sec) * KEYBOARD_SIMULATION_TICK_SECONDS
        delta = step if direction == "up" else -step
        next_position = self._clamp_position(self.state.motion.bar_position_mm + delta)
        if abs(next_position - self.state.motion.bar_position_mm) < 0.05 and self.state.motion.moving and self.state.motion.direction == direction:
            return False

        reached_upper_bound = direction == "up" and next_position >= self.state.motion.upper_bound_mm
        reached_lower_bound = direction == "down" and next_position <= self.state.motion.lower_bound_mm
        completed_rep = reached_upper_bound and self._rep_armed

        self.state.motion.moving = True
        self.state.motion.motion_profile = "keyboard-sim"
        self.state.motion.direction = direction
        self.state.machine_state = MachineState.ready
        self.state.machine_label = "Симуляция движения грифа"
        self.state.safety_message = "Положение грифа управляется комбинацией Ctrl + стрелка вверх/вниз."
        self._set_position(next_position)

        if reached_lower_bound:
            self._rep_armed = True

        if completed_rep:
            self.state.motion.repetition_count += 1
            self._rep_armed = False
            if self.state.motion.repetition_count >= self.state.motion.target_reps:
                self.state.motion.moving = False
                self.state.machine_label = "Цель подхода достигнута"

        self._update_motion_metrics(next_position)
        return True

    def _update_motion_metrics(self, position_mm: float) -> None:
        amplitude = (position_mm - self.state.motion.lower_bound_mm) / max(
            self.state.motion.upper_bound_mm - self.state.motion.lower_bound_mm,
            1.0,
        )
        self.state.motion.amplitude_percent = max(0, min(100, int(round(amplitude * 100))))
        self.state.motion.tempo_label = "стабилен" if self.state.motion.repetition_count % 2 == 0 else "ускорение"
        self.state.motion.sync_delta_mm = abs(self.state.motion.left_position_mm - self.state.motion.right_position_mm)
        self.state.machine_state = MachineState.warning if self.state.motion.sync_delta_mm > 5 else MachineState.ready

    def _refresh_runtime_options(self) -> None:
        settings = get_settings()
        self._keyboard_simulation_enabled = bool(settings.hardware_keyboard_simulation_enabled and os.name == "nt")
        self._tick_interval_seconds = KEYBOARD_SIMULATION_TICK_SECONDS if self._keyboard_simulation_enabled else DEFAULT_MOTION_TICK_SECONDS
        if self._keyboard_simulation_enabled:
            self._keyboard_monitor.start()
        else:
            self._keyboard_monitor.stop()

    def _get_keyboard_direction(self) -> str | None:
        if not self._keyboard_simulation_enabled:
            return None

        return self._keyboard_monitor.get_direction()

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
        return max(0.0, min(2100.0, position_mm))

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