from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import pytest

from app.core.config import Settings, get_settings
from app.models.enums import SafetyState
from app.schemas.hardware import HardwareSnapshotSchema
from app.services.hardware_runtime import HardwareRuntime
from app.services.motion.controller import ControlMode
from app.services.panel.bridge import PanelBridge, PanelBridgeConfig
from app.services.panel.protocol import PanelCommandEncoder, PanelProtocolError, parse_event
from app.services.panel.transport import PanelTransportError, PySerialTransport


def _status_line(sequence: int, **overrides: object) -> bytes:
    payload: dict[str, object] = {
        "v": 1,
        "seq": sequence,
        "type": "status",
        "firmware": "egym-panel-controller",
        "version": "1.0.0",
        "protocol": 1,
        "machine_state": "ready",
        "fault": "none",
        "stop_latched": False,
        "input_healthy": True,
        "buttons": {
            "power": False,
            "up": False,
            "down": False,
            "load_plus": False,
            "load_minus": False,
            "start_pause": False,
            "camera": False,
            "ok": False,
            "fail": False,
            "stop": False,
        },
        "sensors": {
            "left_bottom": False,
            "right_bottom": False,
            "left_top": False,
            "right_top": False,
        },
        "bottom_pair": False,
        "top_pair": False,
        "position_mm": 812.5,
    }
    payload.update(overrides)
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


class FakeSerialTransport:
    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.writes: list[bytes] = []
        self.reads: asyncio.Queue[bytes | Exception] = asyncio.Queue()

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def readline(self) -> bytes:
        try:
            value = await asyncio.wait_for(self.reads.get(), timeout=0.01)
        except TimeoutError:
            return b""
        if isinstance(value, Exception):
            raise value
        return value

    async def write(self, data: bytes) -> None:
        self.writes.append(data)


async def _wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def test_panel_parser_and_encoder_are_strict_and_monotonic() -> None:
    encoder = PanelCommandEncoder("backend-test")
    first = json.loads(encoder.encode("ping"))
    second = json.loads(encoder.encode("set_load", kg=42.5))

    assert first == {"v": 1, "cmd": "ping", "session": "backend-test", "seq": 1}
    assert second == {"v": 1, "cmd": "set_load", "session": "backend-test", "kg": 42.5, "seq": 2}
    assert PanelCommandEncoder().session_id
    event = parse_event(b'{"v":1,"seq":7,"type":"button","id":"stop","event":"pressed","value":0.0,"active":true}\n')
    assert event.sequence == 7
    assert event.event_type == "button"
    assert parse_event('{"v":1,"seq":8,"type":"state","id":"homing","event":"bottom_coarse","value":850.0,"active":true}').event_type == "state"
    assert parse_event('{"v":1,"seq":9,"type":"fault","id":"homing_timeout","event":"homing_aborted","value":850.0,"active":true}').event_type == "fault"

    with pytest.raises(PanelProtocolError):
        parse_event('{"v":2,"seq":1,"type":"machine_state","state":"ready"}')
    with pytest.raises(PanelProtocolError):
        parse_event('{"v":1,"seq":1,"type":"button","id":"stop","event":"pressed","value":0,"active":true,"extra":1}')
    with pytest.raises(PanelProtocolError):
        parse_event("x" * 769)
    status = parse_event(_status_line(10))
    assert status.event_type == "status"
    with pytest.raises(PanelProtocolError):
        parse_event(_status_line(11, buttons={"stop": False}))


def test_panel_led_commands_validate_feedback_and_brightness() -> None:
    encoder = PanelCommandEncoder("host")
    assert json.loads(encoder.encode("button_feedback", id="up", request_seq=21, accepted=False))["request_seq"] == 21
    assert json.loads(encoder.encode("set_activity", direction="down"))["direction"] == "down"
    assert json.loads(encoder.encode("play_effect", effect="homing_complete"))["effect"] == "homing_complete"
    assert json.loads(encoder.encode("set_brightness", brightness=0.4))["brightness"] == 0.4
    with pytest.raises(PanelProtocolError):
        encoder.encode("button_feedback", id="up", request_seq=0, accepted=True)
    with pytest.raises(PanelProtocolError):
        encoder.encode("set_brightness", brightness=0.0)


@pytest.mark.asyncio
async def test_panel_bridge_handshake_heartbeat_state_and_reconnect() -> None:
    first = FakeSerialTransport()
    second = FakeSerialTransport()
    transports = iter((first, second))
    events = []
    disconnects = []
    bridge = PanelBridge(
        PanelBridgeConfig(
            enabled=True,
            port="COM_TEST",
            heartbeat_interval_seconds=0.05,
            reconnect_delay_seconds=0.1,
            status_interval_seconds=0.05,
        ),
        position_callback=lambda: 812.5,
        machine_state_callback=lambda: "ready",
        event_callback=events.append,
        disconnect_callback=disconnects.append,
        transport_factory=lambda _config: next(transports),
    )

    await bridge.start()
    await _wait_until(lambda: len(first.writes) >= 4)
    commands = [json.loads(line) for line in first.writes]
    assert [item["cmd"] for item in commands[:3]] == ["ping", "firmware_info", "status"]
    assert "heartbeat" in [item["cmd"] for item in commands]
    assert [item["seq"] for item in commands] == sorted({item["seq"] for item in commands})
    assert len({item["session"] for item in commands}) == 1
    assert bridge.state.to_payload()["connected"] is False
    assert bridge.state.to_payload()["ready"] is False

    await first.reads.put(b'{"v":1,"seq":1,"type":"version","firmware":"egym-panel-controller","version":"1.0.0","protocol":1}\n')
    await first.reads.put(_status_line(2))
    await _wait_until(lambda: bridge.state.is_ready())
    assert bridge.state.firmware_version == "1.0.0"
    assert bridge.state.to_payload()["handshakeComplete"] is True
    assert bridge.state.to_payload()["fresh"] is True

    await first.reads.put(OSError("usb removed"))
    await _wait_until(lambda: second.opened)
    assert disconnects == ["serial connection lost"]
    assert first.closed is True
    assert bridge.state.connected is False
    await bridge.stop()
    assert second.closed is True


@pytest.mark.asyncio
async def test_panel_bridge_sends_lighting_and_activity_after_handshake_and_on_change() -> None:
    transport = FakeSerialTransport()
    direction = "stop"
    bridge = PanelBridge(
        PanelBridgeConfig(enabled=True, port="COM_TEST", night_mode=True, brightness=0.4),
        position_callback=lambda: 800.0,
        machine_state_callback=lambda: "ready",
        activity_callback=lambda: direction,
        event_callback=lambda _event: None,
        disconnect_callback=lambda _reason: None,
        transport_factory=lambda _config: transport,
    )
    await bridge.start()
    try:
        await transport.reads.put(_status_line(1))
        await transport.reads.put(b'{"v":1,"seq":2,"type":"version","firmware":"egym-panel-controller","version":"1.0.0","protocol":1}\n')
        await _wait_until(lambda: any(b'"cmd":"set_brightness"' in line for line in transport.writes))
        commands = [json.loads(line) for line in transport.writes]
        assert any(item["cmd"] == "set_night_mode" and item["enabled"] for item in commands)
        assert any(item["cmd"] == "set_activity" and item["direction"] == "stop" for item in commands)
        direction = "up"
        await _wait_until(lambda: any(b'"direction":"up"' in line for line in transport.writes))
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_panel_bridge_rx_watchdog_disconnects_silent_mcu() -> None:
    first = FakeSerialTransport()
    second = FakeSerialTransport()
    transports = iter((first, second))
    disconnects: list[str] = []
    bridge = PanelBridge(
        PanelBridgeConfig(
            enabled=True,
            port="COM_TEST",
            heartbeat_interval_seconds=0.05,
            rx_watchdog_seconds=0.12,
            reconnect_delay_seconds=0.1,
        ),
        position_callback=lambda: 0.0,
        machine_state_callback=lambda: "ready",
        event_callback=lambda _event: None,
        disconnect_callback=disconnects.append,
        transport_factory=lambda _config: next(transports),
    )
    await bridge.start()
    await _wait_until(lambda: second.opened)
    assert disconnects == ["serial connection lost"]
    assert first.closed is True
    await bridge.stop()


class ChunkSerial:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = iter(chunks)

    def readline(self, _size: int) -> bytes:
        return next(self.chunks)


@pytest.mark.asyncio
async def test_pyserial_overflow_discards_tail_through_newline() -> None:
    transport = PySerialTransport("COM_TEST", 115200)
    transport._serial = ChunkSerial([b"x" * 770, b'{"v":1,"type":"button"}\n', b"{}\n"])
    assert await transport.readline() == b""
    with pytest.raises(PanelTransportError, match="exceeded"):
        await transport.readline()
    assert await transport.readline() == b"{}\n"


def _runtime(monkeypatch: pytest.MonkeyPatch) -> HardwareRuntime:
    monkeypatch.setenv("HARDWARE_PANEL_ENABLED", "false")
    monkeypatch.delenv("HARDWARE_PANEL_PORT", raising=False)
    get_settings.cache_clear()
    runtime = HardwareRuntime()
    for _ in range(25):
        runtime._tick_motion()
    return runtime


def test_panel_defaults_are_disabled_and_snapshot_schema_is_backward_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    assert Settings().hardware_panel_enabled is False
    assert Settings().hardware_panel_port is None

    snapshot = runtime.snapshot_payload()
    validated = HardwareSnapshotSchema.model_validate(snapshot)
    assert validated.panel.enabled is False
    assert validated.panel.connected is False
    assert validated.panel.port is None


def test_panel_stop_fault_and_release_keep_emergency_stop_latched(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":1,"type":"button","id":"stop","event":"pressed","value":0.0,"active":true}')
    )
    assert runtime.controller.state.mode == ControlMode.estop

    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":2,"type":"button","id":"stop","event":"released","value":0.0,"active":false}')
    )
    assert runtime.controller.state.mode == ControlMode.estop

    runtime.clear_emergency_stop()
    runtime._handle_panel_event(parse_event('{"v":1,"seq":3,"type":"fault","code":"top_sensor_mismatch","latched":true}'))
    assert runtime.controller.state.mode == ControlMode.estop

    runtime.panel.state.enabled = True
    runtime.panel.state.mark_seen()
    runtime.panel.state.mark_identity_seen()
    runtime.panel.state.input_healthy = True
    runtime.panel.state.mark_status_seen()
    runtime.panel.state.buttons["stop"] = True
    with pytest.raises(PermissionError, match="физическая кнопка STOP"):
        runtime.clear_emergency_stop()


def test_panel_enabled_disconnected_blocks_emergency_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    runtime.trigger_emergency_stop()
    runtime.panel.state.enabled = True
    with pytest.raises(PermissionError, match="не подключена"):
        runtime.clear_emergency_stop()


def test_panel_latched_stop_can_be_cleared_after_fresh_released_status(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    runtime.trigger_emergency_stop()
    monkeypatch.setattr(runtime.panel, "send_command", lambda _command, **_payload: True)
    runtime.panel.state.enabled = True
    runtime.panel.state.mark_seen()
    runtime.panel.state.mark_identity_seen()
    runtime.panel.state.input_healthy = True
    runtime.panel.state.stop_latched = True
    runtime.panel.state.buttons["stop"] = False
    runtime.panel.state.mark_status_seen()

    command = runtime.clear_emergency_stop()

    assert command.status == "pending"
    assert runtime.controller.state.mode == ControlMode.estop
    runtime._handle_panel_event(parse_event('{"v":1,"seq":1,"type":"fault","code":"none","latched":false}'))

    assert runtime.controller.state.mode == ControlMode.paused


def test_required_panel_blocks_direct_motion_intents_when_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    runtime.panel.configure(PanelBridgeConfig(enabled=True, port="COM_TEST"))

    with pytest.raises(PermissionError, match="панель не готова"):
        runtime.park()
    with pytest.raises(PermissionError, match="панель не готова"):
        runtime.enter_weightless()
    with pytest.raises(PermissionError, match="панель не готова"):
        runtime.start_procedure("bar_mass")


def test_motion_gate_blocks_power_off_and_disconnect_aborts_paused_procedure(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    runtime._panel_powered_on = False
    runtime.state.safety_state = SafetyState.disabled
    with pytest.raises(PermissionError, match="выключен"):
        runtime.start_procedure("weightless_drift")

    runtime._panel_powered_on = True
    runtime.state.safety_state = SafetyState.enabled
    runtime.start_procedure("weightless_drift")
    runtime.controller.request_pause()
    runtime._handle_panel_disconnect("usb removed")

    assert runtime.controller.state.mode == ControlMode.estop
    assert runtime.procedure.status == "failed"


def test_fresh_ready_panel_sensors_are_merged_without_mutating_adapter_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    runtime.panel.configure(PanelBridgeConfig(enabled=True, port="COM_TEST"))
    original = runtime.adapter.read()
    runtime.panel.state.mark_seen()
    runtime.panel.state.mark_identity_seen()
    runtime.panel.state.input_healthy = True
    runtime.panel.state.sensors.update(
        {"left_bottom": True, "right_bottom": False, "left_top": False, "right_top": True}
    )
    runtime.panel.state.mark_status_seen()

    merged = runtime._merge_panel_sensors(original)

    assert merged is not original
    assert merged.left is not original.left
    assert merged.left.limit_switch_low is True
    assert merged.right.limit_switch_high is True
    assert original.left.limit_switch_low is False


def test_panel_buttons_use_runtime_guards_and_controller_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    runtime.start_motion(
        calibration_id=None,
        lower_bound_mm=700,
        upper_bound_mm=1000,
        target_set=1,
        target_reps=8,
        motion_profile="training",
        load_kg=149,
    )
    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":1,"type":"button","id":"load_plus","event":"pressed","value":0.0,"active":true}')
    )
    assert runtime.controller.config.load_kg == 150

    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":2,"type":"button","id":"start_pause","event":"pressed","value":0.0,"active":true}')
    )
    assert runtime.controller.state.mode == ControlMode.paused
    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":3,"type":"button","id":"start_pause","event":"pressed","value":0.0,"active":true}')
    )
    assert runtime.controller.state.mode == ControlMode.training

    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":4,"type":"button","id":"ok","event":"pressed","value":0.0,"active":true}')
    )
    assert runtime.controller.state.mode == ControlMode.paused
    assert runtime.controller.state.cycles_total == 1

    runtime.set_service_mode(True)
    start = runtime.controller.state.position_mm
    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":5,"type":"button","id":"up","event":"pressed","value":0.0,"active":true}')
    )
    assert runtime.controller.state.mode == ControlMode.moving
    assert runtime.controller.state.move_target_mm == pytest.approx(start + 5.0)
    runtime._handle_panel_event(
        parse_event('{"v":1,"seq":6,"type":"button","id":"up","event":"released","value":0.0,"active":false}')
    )
    assert runtime.controller.state.mode == ControlMode.paused


def test_panel_feedback_reflects_guards_and_events_drive_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    sent: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(runtime.panel, "send_command", lambda command, **payload: sent.append((command, payload)) or True)

    runtime._handle_panel_event(parse_event('{"v":1,"seq":41,"type":"button","id":"up","event":"pressed","value":0,"active":true}'))
    assert ("button_feedback", {"id": "up", "request_seq": 41, "accepted": False}) in sent
    runtime._handle_panel_event(parse_event('{"v":1,"seq":42,"type":"button","id":"camera","event":"pressed","value":0,"active":true}'))
    assert ("button_feedback", {"id": "camera", "request_seq": 42, "accepted": True}) in sent

    runtime.controller._emit("homing_phase", "complete", {"phase": "complete"})
    runtime.controller._emit("arrived", "position reached")
    runtime.controller._emit("target", "reps complete")
    runtime._handle_new_events()
    assert ("play_effect", {"effect": "homing_complete"}) in sent
    assert sent.count(("play_effect", {"effect": "target_reached"})) == 2

    runtime.controller.state.mode = ControlMode.moving
    runtime.controller.state.moving = True
    runtime.controller.state.velocity_mm_s = -10.0
    assert runtime._panel_activity() == "down"
    runtime.controller.state.velocity_mm_s = 0.0
    assert runtime._panel_activity() == "stop"

    runtime.controller.state.mode = ControlMode.training
    runtime.complete_set()
    assert ("play_effect", {"effect": "set_complete"}) in sent
    assert runtime._panel_machine_state() == "paused"


def test_panel_disconnect_during_exercise_latches_stop_and_home_is_observer_only(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(monkeypatch)
    sent: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(runtime.panel, "send_command", lambda command, **payload: sent.append((command, payload)) or True)

    runtime.home()
    assert ("set_machine_state", {"state": "homing"}) in sent
    assert all(command != "home" for command, _payload in sent)

    runtime.start_motion(
        calibration_id=None,
        lower_bound_mm=700,
        upper_bound_mm=1000,
        target_set=1,
        target_reps=8,
        motion_profile="training",
        load_kg=30,
    )
    runtime._handle_panel_disconnect("usb removed")
    assert runtime.controller.state.mode == ControlMode.estop
    assert sent[-1][0] == "stop"
