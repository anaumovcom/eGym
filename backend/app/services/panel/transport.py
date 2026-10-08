"""Serial transport boundary for the optional panel sidecar."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any, Protocol

from app.services.panel.protocol import MAX_LINE_BYTES


class PanelTransportError(RuntimeError):
    pass


class PanelSerialTransport(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def readline(self) -> bytes: ...

    async def write(self, data: bytes) -> None: ...


class PySerialTransport:
    """Blocking pyserial calls isolated from the asyncio event-loop thread."""

    def __init__(self, port: str, baud: int, *, read_timeout_seconds: float = 0.1) -> None:
        self._port = port
        self._baud = baud
        self._read_timeout_seconds = read_timeout_seconds
        self._serial: Any | None = None
        self._receive_buffer = bytearray()
        self._discard_until_newline = False

    async def open(self) -> None:
        if self._serial is not None:
            return

        def open_serial() -> Any:
            try:
                serial = importlib.import_module("serial")
            except ImportError as error:
                raise PanelTransportError("pyserial is required; install the 'panel' optional dependency") from error
            try:
                return serial.Serial(
                    port=self._port,
                    baudrate=self._baud,
                    timeout=self._read_timeout_seconds,
                    write_timeout=1.0,
                    exclusive=True,
                )
            except Exception as error:  # pyserial exception classes are unavailable without the optional dependency
                raise PanelTransportError(f"cannot open panel serial port {self._port}: {error}") from error

        self._serial = await asyncio.to_thread(open_serial)
        self._receive_buffer.clear()
        self._discard_until_newline = False

    async def close(self) -> None:
        serial_port, self._serial = self._serial, None
        if serial_port is not None:
            await asyncio.to_thread(serial_port.close)

    async def readline(self) -> bytes:
        serial_port = self._serial
        if serial_port is None:
            raise PanelTransportError("panel serial port is not open")
        try:
            chunk = await asyncio.to_thread(serial_port.readline, MAX_LINE_BYTES + 2)
        except Exception as error:
            raise PanelTransportError(f"panel serial read failed: {error}") from error
        if not chunk:
            return b""

        if self._discard_until_newline:
            if b"\n" in chunk:
                self._discard_until_newline = False
                raise PanelTransportError("panel protocol line exceeded maximum length")
            return b""

        self._receive_buffer.extend(chunk)
        newline = self._receive_buffer.find(b"\n")
        if newline >= 0:
            line = bytes(self._receive_buffer[: newline + 1])
            self._receive_buffer.clear()
            if len(line.rstrip(b"\r\n")) > MAX_LINE_BYTES:
                raise PanelTransportError("panel protocol line exceeded maximum length")
            return line
        if len(self._receive_buffer) > MAX_LINE_BYTES:
            self._receive_buffer.clear()
            self._discard_until_newline = True
        return b""

    async def write(self, data: bytes) -> None:
        serial_port = self._serial
        if serial_port is None:
            raise PanelTransportError("panel serial port is not open")

        def write_all() -> None:
            written = serial_port.write(data)
            if written != len(data):
                raise PanelTransportError(f"short panel serial write: {written}/{len(data)} bytes")
            serial_port.flush()

        try:
            await asyncio.to_thread(write_all)
        except PanelTransportError:
            raise
        except Exception as error:
            raise PanelTransportError(f"panel serial write failed: {error}") from error
