"""Async lifecycle and state management for the firmware panel sidecar."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services.panel.protocol import (
    PanelButtonEvent,
    PanelCommandEncoder,
    PanelDiagnosticEvent,
    PanelEvent,
    PanelFaultEvent,
    PanelGenericEvent,
    PanelMachineStateEvent,
    PanelMotionRequestEvent,
    PanelPairEvent,
    PanelPongEvent,
    PanelPositionEvent,
    PanelProtocolError,
    PanelSensorEvent,
    PanelStatusEvent,
    PanelVersionEvent,
    parse_event,
)
from app.services.panel.state import PanelState
from app.services.panel.transport import PanelSerialTransport, PanelTransportError, PySerialTransport

logger = logging.getLogger(__name__)

EventCallback = Callable[[PanelEvent], None]
DisconnectCallback = Callable[[str], None]
TransportFactory = Callable[["PanelBridgeConfig"], PanelSerialTransport]


@dataclass(frozen=True)
class PanelBridgeConfig:
    enabled: bool = False
    port: str | None = None
    baud: int = 115200
    heartbeat_interval_seconds: float = 0.5
    reconnect_delay_seconds: float = 1.0
    status_interval_seconds: float = 0.25
    rx_watchdog_seconds: float = 2.0
    night_mode: bool = False
    brightness: float = 1.0

    def __post_init__(self) -> None:
        if not 1200 <= self.baud <= 3_000_000:
            raise ValueError("panel baud must be in [1200, 3000000]")
        if not 0.05 <= self.heartbeat_interval_seconds <= 1.0:
            raise ValueError("panel heartbeat interval must be in [0.05, 1.0] seconds")
        if not 0.1 <= self.reconnect_delay_seconds <= 60.0:
            raise ValueError("panel reconnect delay must be in [0.1, 60.0] seconds")
        if not 0.05 <= self.status_interval_seconds <= 10.0:
            raise ValueError("panel status interval must be in [0.05, 10.0] seconds")
        if not self.heartbeat_interval_seconds < self.rx_watchdog_seconds <= 30.0:
            raise ValueError("panel RX watchdog must be greater than heartbeat interval and at most 30 seconds")
        if not 0.1 <= self.brightness <= 1.0:
            raise ValueError("panel brightness must be in [0.1, 1.0]")


class PanelBridge:
    """Maintains a reconnecting JSONL session without participating in drive control."""

    def __init__(
        self,
        config: PanelBridgeConfig,
        *,
        position_callback: Callable[[], float],
        machine_state_callback: Callable[[], str],
        event_callback: EventCallback,
        disconnect_callback: DisconnectCallback,
        activity_callback: Callable[[], str] | None = None,
        transport_factory: TransportFactory | None = None,
    ) -> None:
        self.config = config
        self.state = PanelState(
            enabled=config.enabled,
            port=config.port,
            freshness_timeout_seconds=config.rx_watchdog_seconds,
        )
        self._position_callback = position_callback
        self._machine_state_callback = machine_state_callback
        self._activity_callback = activity_callback
        self._event_callback = event_callback
        self._disconnect_callback = disconnect_callback
        self._transport_factory = transport_factory or self._default_transport_factory
        self._encoder = PanelCommandEncoder()
        self._commands: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=100)
        self._task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping = False
        self._transport: PanelSerialTransport | None = None
        self._last_rx_sequence: int | None = None
        self._pending_ping_sequence: int | None = None

    @staticmethod
    def _default_transport_factory(config: PanelBridgeConfig) -> PanelSerialTransport:
        if config.port is None:
            raise ValueError("panel port is not configured")
        read_timeout = min(0.1, config.heartbeat_interval_seconds / 2, config.status_interval_seconds / 2)
        return PySerialTransport(config.port, config.baud, read_timeout_seconds=read_timeout)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def configure(self, config: PanelBridgeConfig) -> None:
        if self.running:
            if config != self.config:
                raise RuntimeError("cannot reconfigure a running panel bridge")
            return
        self.config = config
        self.state.enabled = config.enabled
        self.state.port = config.port
        self.state.freshness_timeout_seconds = config.rx_watchdog_seconds
        self.state.reset_observations()

    async def start(self) -> None:
        if self.running or not self.config.enabled or not self.config.port:
            return
        self._loop = asyncio.get_running_loop()
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="hardware-panel-bridge")

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        transport, self._transport = self._transport, None
        if transport is not None:
            await transport.close()
        self.state.mark_connected(False)
        self._loop = None
        self._clear_commands()

    def send_command(self, command: str, **payload: Any) -> bool:
        """Queue an outbound command from either the event-loop or a worker thread."""

        loop = self._loop
        allowed_before_ready = command == "stop"
        if loop is None or loop.is_closed() or (not allowed_before_ready and not self.state.is_ready()):
            return False

        def enqueue() -> None:
            if command != "stop" and not self.state.is_ready():
                return
            try:
                self._commands.put_nowait((command, payload))
            except asyncio.QueueFull:
                logger.error("Panel command queue is full; dropping %s", command)

        loop.call_soon_threadsafe(enqueue)
        return True

    async def _run(self) -> None:
        while not self._stopping:
            transport = self._transport_factory(self.config)
            self._transport = transport
            was_open = False
            try:
                await transport.open()
                was_open = True
                self._last_rx_sequence = None
                self._pending_ping_sequence = None
                self.state.begin_connection()
                await self._write_command(transport, "ping")
                await self._write_command(transport, "firmware_info")
                await self._write_command(transport, "status")
                await self._connected_loop(transport)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - serial failures must reconnect without killing the app
                logger.warning("Panel connection failed on %s: %s", self.config.port, error)
                self._record_transport_error(str(error))
            finally:
                self.state.mark_connected(False)
                self._clear_commands()
                try:
                    await transport.close()
                except Exception:  # noqa: BLE001 - best-effort cleanup after a failed serial session
                    logger.exception("Failed to close panel serial transport")
                if self._transport is transport:
                    self._transport = None
                if was_open and not self._stopping:
                    self._invoke_disconnect("serial connection lost")
            if not self._stopping:
                await asyncio.sleep(self.config.reconnect_delay_seconds)

    async def _connected_loop(self, transport: PanelSerialTransport) -> None:
        loop = asyncio.get_running_loop()
        next_heartbeat = loop.time()
        next_status = loop.time()
        previous_state: str | None = None
        previous_activity: str | None = None
        previous_lighting: tuple[bool, float] | None = None
        opened_at = loop.time()
        while not self._stopping:
            now = loop.time()
            last_rx = self.state.last_rx_monotonic
            if now - (last_rx if last_rx is not None else opened_at) > self.config.rx_watchdog_seconds:
                raise PanelTransportError("panel RX watchdog expired")
            if now >= next_heartbeat:
                await self._write_command(transport, "heartbeat")
                next_heartbeat = now + self.config.heartbeat_interval_seconds
            machine_state = self._machine_state_callback()
            if self.state.is_ready(now) and now >= next_status:
                await self._write_status(transport, include_state=machine_state != previous_state)
                previous_state = machine_state
                next_status = now + self.config.status_interval_seconds
            elif self.state.is_ready(now) and machine_state != previous_state:
                await self._write_machine_state(transport, machine_state)
                previous_state = machine_state
            if self.state.is_ready(now):
                lighting = (self.config.night_mode, self.config.brightness)
                if lighting != previous_lighting:
                    await self._write_command(transport, "set_night_mode", enabled=lighting[0])
                    await self._write_command(transport, "set_brightness", brightness=lighting[1])
                    previous_lighting = lighting
                if self._activity_callback is not None:
                    activity = self._activity_callback()
                    if activity != previous_activity:
                        await self._write_command(transport, "set_activity", direction=activity)
                        previous_activity = activity

            await self._drain_commands(transport)
            line = await transport.readline()
            if not line:
                continue
            try:
                event = parse_event(line)
            except PanelProtocolError as error:
                logger.warning("Ignoring invalid panel event: %s", error)
                self._record_protocol_error(str(error))
                continue
            firmware_restarted = (
                self._last_rx_sequence is not None
                and event.sequence <= self._last_rx_sequence
                and isinstance(event, PanelVersionEvent)
            )
            if firmware_restarted:
                self._invoke_disconnect("panel firmware restarted")
                self._last_rx_sequence = None
                self.state.begin_connection()
                previous_state = None
                previous_activity = None
                previous_lighting = None
            if self._last_rx_sequence is not None and event.sequence <= self._last_rx_sequence:
                logger.warning("Ignoring stale panel event sequence %s", event.sequence)
                continue
            self._last_rx_sequence = event.sequence
            self._apply_event(event, now=loop.time())
            if firmware_restarted:
                await self._write_command(transport, "ping")
                await self._write_command(transport, "firmware_info")
                await self._write_command(transport, "status")
            if isinstance(event, PanelButtonEvent) and event.button_id != "stop" and not self.state.is_ready():
                logger.warning("Ignoring panel button %s before handshake readiness", event.button_id)
                if event.action in {"pressed", "repeat"}:
                    await self._write_command(transport, "button_feedback", id=event.button_id, request_seq=event.sequence, accepted=False)
                continue
            try:
                self._event_callback(event)
            except Exception:  # noqa: BLE001 - application callback failure must not break heartbeat
                logger.exception("Panel event callback failed for %s", event.event_type)

    async def _drain_commands(self, transport: PanelSerialTransport) -> None:
        for _ in range(100):
            try:
                command, payload = self._commands.get_nowait()
            except asyncio.QueueEmpty:
                return
            await self._write_command(transport, command, **payload)

    async def _write_status(self, transport: PanelSerialTransport, *, include_state: bool) -> None:
        await self._write_command(transport, "position", position_mm=self._position_callback())
        if include_state:
            await self._write_machine_state(transport, self._machine_state_callback())

    async def _write_machine_state(self, transport: PanelSerialTransport, machine_state: str) -> None:
        if machine_state == "emergency_stop":
            await self._write_command(transport, "stop")
        else:
            await self._write_command(transport, "set_machine_state", state=machine_state)

    async def _write_command(self, transport: PanelSerialTransport, command: str, **payload: Any) -> None:
        encoded = self._encoder.encode(command, **payload)
        if command == "ping":
            self._pending_ping_sequence = self._encoder.sequence
        await transport.write(encoded)

    def _apply_event(self, event: PanelEvent, *, now: float | None = None) -> None:
        self.state.mark_seen(now)
        with self.state._lock:
            if isinstance(event, PanelVersionEvent):
                self.state.firmware_version = event.firmware_version
                self.state.protocol_version = event.protocol_version
                self.state.mark_identity_seen()
            elif isinstance(event, PanelPongEvent):
                if self._pending_ping_sequence is None or event.request_sequence != self._pending_ping_sequence:
                    self.state.diagnostics["handshake"] = {"ok": False, "detail": "pong request sequence mismatch"}
                    return
                self.state.firmware_version = event.firmware_version
                self.state.protocol_version = 1
                self.state.mark_identity_seen()
            elif isinstance(event, PanelStatusEvent):
                self.state.firmware_version = event.firmware_version
                self.state.protocol_version = event.protocol_version
                self.state.machine_state = event.machine_state
                self.state.fault_code = None if event.fault_code == "none" else event.fault_code
                self.state.stop_latched = event.stop_latched
                self.state.input_healthy = event.input_healthy
                self.state.buttons = dict(event.buttons)
                self.state.sensors = dict(event.sensors)
                self.state.bottom_pair = event.bottom_pair
                self.state.top_pair = event.top_pair
                self.state.position = {"mm": event.position_mm}
                self.state.mark_status_seen()
            elif isinstance(event, PanelButtonEvent):
                self.state.buttons[event.button_id] = event.active
                if event.button_id == "stop":
                    self.state.stop_latched = self.state.stop_latched or event.active
            elif isinstance(event, PanelSensorEvent):
                self.state.sensors[event.sensor_id] = event.active
                self.state.bottom_pair = self.state.sensors["left_bottom"] and self.state.sensors["right_bottom"]
                self.state.top_pair = self.state.sensors["left_top"] and self.state.sensors["right_top"]
            elif isinstance(event, PanelPairEvent):
                if event.pair_id == "bottom":
                    self.state.bottom_pair = event.active
                else:
                    self.state.top_pair = event.active
            elif isinstance(event, PanelFaultEvent):
                if event.latched:
                    self.state.fault_code = event.code
                elif event.code == "none":
                    self.state.fault_code = None
                    if self.state.input_healthy and not self.state.buttons["stop"]:
                        self.state.stop_latched = False
            elif isinstance(event, PanelMachineStateEvent):
                self.state.machine_state = event.state
            elif isinstance(event, PanelPositionEvent):
                self.state.position = {
                    "known": event.known,
                    "mm": event.mm,
                    "physicalBottomMm": event.physical_bottom_mm,
                    "physicalTopMm": event.physical_top_mm,
                    "workingBottomMm": event.working_bottom_mm,
                    "workingTopMm": event.working_top_mm,
                    "travelMm": event.travel_mm,
                }
            elif isinstance(event, PanelDiagnosticEvent):
                self.state.diagnostics[event.subsystem] = {"ok": event.ok, "detail": event.detail}
            elif isinstance(event, PanelMotionRequestEvent):
                self.state.diagnostics["lastMotionRequest"] = {
                    "direction": event.direction,
                    "action": event.action,
                    "speedMmPerSecond": event.speed_mm_per_second,
                    "active": event.active,
                }
            elif isinstance(event, PanelGenericEvent) and event.event_type == "diagnostic_input":
                self.state.diagnostics[f"input:{event.item_id}"] = {
                    "ok": True,
                    "detail": event.action,
                    "active": event.active,
                }
            elif isinstance(event, PanelGenericEvent) and event.event_type == "state":
                self.state.diagnostics["homing"] = {
                    "phase": event.action,
                    "positionMm": event.value,
                    "active": event.active,
                }

    def _record_protocol_error(self, detail: str) -> None:
        with self.state._lock:
            self.state.diagnostics["protocol"] = {"ok": False, "detail": detail}

    def _record_transport_error(self, detail: str) -> None:
        with self.state._lock:
            self.state.diagnostics["transport"] = {"ok": False, "detail": detail}

    def _invoke_disconnect(self, reason: str) -> None:
        try:
            self._disconnect_callback(reason)
        except Exception:  # noqa: BLE001 - safety callback failures are logged but reconnect continues
            logger.exception("Panel disconnect callback failed")

    def _clear_commands(self) -> None:
        while True:
            try:
                self._commands.get_nowait()
            except asyncio.QueueEmpty:
                return
