"""Classic 11-bit CAN for Lichuan A6. Native ABI from USB-CAN-FD-B-Linux/controlcanfd.h."""

from __future__ import annotations

import ctypes as ct
import json
import os
import platform
import select
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol

from app.schemas.drive_transport import CanAdapterInfo, CanopenSettings


class CanBus(Protocol):
    def send(self, identifier: int, data: bytes) -> None: ...
    def receive(self, timeout: float) -> tuple[int, bytes] | None: ...
    def close(self) -> None: ...


class CanChannelError(OSError):
    """The adapter answered, but its channel could not be configured or started."""

    def __init__(self, message: str, info: CanAdapterInfo | None):
        super().__init__(message)
        self.info = info


class SocketCan:
    _frame = struct.Struct("=IB3x8s")

    def __init__(self, config: CanopenSettings):
        if not hasattr(socket, "AF_CAN"):
            raise OSError("SocketCAN доступен на Linux")
        self.info = CanAdapterInfo(model=config.interface)
        try:
            result = subprocess.run(["ip", "-details", "-json", "link", "show", "dev", config.interface],
                                    capture_output=True, timeout=1, check=True)
            link = json.loads(result.stdout)[0]
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            link = {}
        details = link.get("linkinfo", {}).get("info_data", {})
        self.info.interface_bitrate = details.get("bittiming", {}).get("bitrate")
        self.info.link_state = details.get("state") or link.get("operstate")
        if self.info.interface_bitrate and self.info.interface_bitrate != config.bitrate:
            raise CanChannelError(f"{config.interface}: скорость Linux {self.info.interface_bitrate}, выбрана {config.bitrate} бит/с", self.info)
        if link and ("UP" not in link.get("flags", []) or self.info.link_state in ("BUS-OFF", "STOPPED")):
            raise CanChannelError(f"{config.interface}: интерфейс недоступен ({self.info.link_state})", self.info)
        self.sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        try:
            self.sock.bind((config.interface,))
            self.sock.setblocking(False)
        except OSError:
            self.sock.close()
            raise

    def send(self, identifier: int, data: bytes) -> None:
        if self.sock.send(self._frame.pack(identifier, len(data), data)) != self._frame.size:
            raise OSError("Неполная отправка SocketCAN")

    def receive(self, timeout: float) -> tuple[int, bytes] | None:
        if select.select([self.sock], [], [], max(timeout, 0))[0]:
            identifier, size, data = self._frame.unpack(self.sock.recv(self._frame.size))
            if identifier <= 0x7FF and size <= 8:
                return identifier, data[:size]
        return None

    def close(self) -> None:
        self.sock.close()


class _Frame(ct.Structure):
    _fields_ = [("identifier", ct.c_uint32), ("size", ct.c_uint8), ("padding", ct.c_uint8 * 3), ("data", ct.c_uint8 * 8)]


class _Transmit(ct.Structure):
    _fields_ = [("frame", _Frame), ("transmit_type", ct.c_uint32)]


class _Receive(ct.Structure):
    _fields_ = [("frame", _Frame), ("timestamp", ct.c_uint64)]


class _ChannelConfig(ct.Structure):
    # TYPE_CANFD selects the SDK union member for this adapter, including for classic frames.
    _fields_ = [(key, ct.c_uint32) for key in ("can_type", "acc_code", "acc_mask", "abit_timing", "dbit_timing", "brp")] + [
        ("filter", ct.c_uint8), ("mode", ct.c_uint8), ("pad", ct.c_uint16), ("reserved", ct.c_uint32)]


class _DeviceInfo(ct.Structure):
    _pack_ = 1
    _fields_ = [(key, ct.c_uint16) for key in ("hardware", "firmware", "driver", "interface", "irq")] + [
        ("channels", ct.c_uint8), ("serial", ct.c_char * 21), ("model", ct.c_char * 40), ("reserved", ct.c_uint16 * 5)]


def _vendor_library() -> ct.CDLL:
    path = os.environ.get("CANOPEN_LIBRARY")
    if not path:
        if not sys.platform.startswith("linux"):
            raise OSError("Комплект USB-CAN-FD-B содержит драйвер Linux. Проверьте адаптер на управляющем компьютере.")
        machine = platform.machine().lower()
        arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
        if arch.startswith("armv") or (arch == "aarch64" and ct.sizeof(ct.c_void_p) == 4):
            arch = "armhf"
        path = str(Path(__file__).with_name("usbcanfd") / arch / "libcontrolcanfd.so")
    lib = ct.CDLL(path)
    handle, uint = ct.c_void_p, ct.c_uint32
    signatures = {
        "OpenDevice": (handle, [uint, uint, uint]), "CloseDevice": (uint, [handle]),
        "SetAbitBaud": (uint, [handle, uint, uint]), "SetDbitBaud": (uint, [handle, uint, uint]),
        "SetCANFDStandard": (uint, [handle, uint, uint]), "InitCAN": (handle, [handle, uint, ct.POINTER(_ChannelConfig)]),
        "StartCAN": (uint, [handle]), "ResetCAN": (uint, [handle]),
        "Transmit": (uint, [handle, ct.POINTER(_Transmit), uint]),
        "Receive": (uint, [handle, ct.POINTER(_Receive), uint, ct.c_int]),
        "GetReceiveNum": (uint, [handle, ct.c_uint8]),
        "GetDeviceInf": (uint, [handle, ct.POINTER(_DeviceInfo)]),
        "ClearFilter": (uint, [handle]), "AckFilter": (uint, [handle]),
        "IsDeviceOnLine": (uint, [handle]),
    }
    for name, (result, args) in signatures.items():
        function = getattr(lib, "ZCAN_" + name)
        function.restype, function.argtypes = result, args
    return lib


class UsbCanFd:
    def __init__(self, config: CanopenSettings):
        self.lib = _vendor_library()
        self.device = self.lib.ZCAN_OpenDevice(41, config.device, 0)
        self.channel = None
        self.info = None
        if not self.device:
            raise OSError(f"USB-CAN-FD-B №{config.device} недоступен. Проверьте USB и права доступа.")
        try:
            info = _DeviceInfo()
            if self.lib.ZCAN_GetDeviceInf(self.device, ct.byref(info)) == 1:
                self.info = CanAdapterInfo(model=info.model.decode("ascii", "replace") or None,
                                          serial=info.serial.decode("ascii", "replace") or None,
                                          channels=info.channels, hardware=info.hardware,
                                          firmware=info.firmware, driver=info.driver)
            channel = config.channel
            label = f"USB-CAN-FD-B CAN{channel + 1} (SDK {channel})"
            for name, value in (("SetAbitBaud", config.bitrate), ("SetDbitBaud", 5000000), ("SetCANFDStandard", 0)):
                if getattr(self.lib, "ZCAN_" + name)(self.device, channel, value) != 1:
                    raise OSError(f"{label}: {name}({value})")
            init = _ChannelConfig(can_type=1, acc_mask=0xFFFFFFFF, filter=1)
            self.channel = self.lib.ZCAN_InitCAN(self.device, channel, ct.byref(init))
            if not self.channel:
                raise OSError(f"{label}: InitCAN")
            for name in ("ClearFilter", "AckFilter", "StartCAN"):
                if getattr(self.lib, "ZCAN_" + name)(self.channel) != 1:
                    raise OSError(f"{label}: {name}")
        except OSError as exc:
            self.close()
            raise CanChannelError(str(exc), self.info) from exc
        except Exception:
            self.close()
            raise

    def send(self, identifier: int, data: bytes) -> None:
        obj = _Transmit()
        obj.frame.identifier, obj.frame.size = identifier, len(data)
        obj.frame.data[:len(data)] = data
        if self.lib.ZCAN_Transmit(self.channel, ct.byref(obj), 1) != 1:
            raise OSError(f"USB-CAN-FD-B: не отправлен кадр {identifier:03X}")

    def receive(self, timeout: float) -> tuple[int, bytes] | None:
        deadline = time.monotonic() + timeout
        while True:
            count = self.lib.ZCAN_GetReceiveNum(self.channel, 0)
            if count == 0xFFFFFFFF:
                raise OSError("USB-CAN-FD-B потерял канал")
            if count:
                obj = _Receive()
                if self.lib.ZCAN_Receive(self.channel, ct.byref(obj), 1, 0) != 1:
                    raise OSError("USB-CAN-FD-B: ошибка приёма")
                if obj.frame.identifier <= 0x7FF and obj.frame.size <= 8:
                    return obj.frame.identifier, bytes(obj.frame.data[:obj.frame.size])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(0.0003, remaining))

    def check_online(self) -> None:
        if self.lib.ZCAN_IsDeviceOnLine(self.device) == 3:  # STATUS_OFFLINE (STATUS_ONLINE is 2)
            raise OSError("USB-CAN-FD-B отключён от USB")

    def close(self) -> None:
        try:
            if self.channel:
                self.lib.ZCAN_ResetCAN(self.channel)
                self.channel = None
        finally:
            if self.device:
                self.lib.ZCAN_CloseDevice(self.device)
                self.device = None


def open_can_bus(config: CanopenSettings) -> CanBus:
    return UsbCanFd(config) if config.driver == "usbcanfd" else SocketCan(config)
