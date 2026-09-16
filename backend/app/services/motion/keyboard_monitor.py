"""Windows keyboard monitor used to drive the virtual hand (Ctrl + Up/Down) in the emulator."""

from __future__ import annotations

import os
from threading import RLock
from typing import Any

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

try:
    import keyboard as keyboard_module
except ImportError:  # pragma: no cover - optional runtime dependency before install
    keyboard_module = None

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

