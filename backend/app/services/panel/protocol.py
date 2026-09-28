"""Strict codec for the ESP32 panel JSON Lines protocol v1."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any, Literal

from app.services.panel.state import BUTTON_IDS, SENSOR_IDS

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 768
MAX_SEQUENCE = 2**32 - 1

BUTTON_EVENTS = {"pressed", "released", "long_press", "repeat"}
MACHINE_STATES = {
    "off",
    "booting",
    "homing",
    "ready",
    "positioning",
    "exercise_active",
    "paused",
    "set_complete",
    "warning",
    "error",
    "emergency_stop",
    "maintenance",
    "calibration",
}
FAULT_CODES = {
    "none",
    "bottom_sensor_mismatch",
    "top_sensor_mismatch",
    "left_bottom_stuck",
    "right_bottom_stuck",
    "left_top_stuck",
    "right_top_stuck",
    "bottom_pair_timeout",
    "top_pair_timeout",
    "invalid_sensor_combination",
    "homing_timeout",
    "homing_distance",
    "backoff_release_failed",
    "drive_fault",
    "heartbeat_timeout",
    "mcp_unavailable",
    "pca_unavailable",
    "i2c_bus_fault",
    "protocol_error",
    "emergency_stop",
}


class PanelProtocolError(ValueError):
    """A line does not conform to the documented firmware protocol."""


@dataclass(frozen=True)
class PanelEventBase:
    sequence: int
    event_type: str


@dataclass(frozen=True)
class PanelVersionEvent(PanelEventBase):
    firmware: str
    firmware_version: str
    protocol_version: int


@dataclass(frozen=True)
class PanelPongEvent(PanelEventBase):
    request_sequence: int
    firmware_version: str


@dataclass(frozen=True)
class PanelButtonEvent(PanelEventBase):
    button_id: str
    action: Literal["pressed", "released", "long_press", "repeat"]
    active: bool


@dataclass(frozen=True)
class PanelSensorEvent(PanelEventBase):
    sensor_id: str
    active: bool


@dataclass(frozen=True)
class PanelPairEvent(PanelEventBase):
    pair_id: Literal["bottom", "top"]
    action: Literal["first_edge", "confirmed"]
    position_mm: float
    active: bool


@dataclass(frozen=True)
class PanelMotionRequestEvent(PanelEventBase):
    direction: Literal["up", "down", "stop"]
    action: Literal["move", "stop"]
    speed_mm_per_second: float
    active: bool


@dataclass(frozen=True)
class PanelFaultEvent(PanelEventBase):
    code: str
    latched: bool


@dataclass(frozen=True)
class PanelMachineStateEvent(PanelEventBase):
    state: str


@dataclass(frozen=True)
class PanelPositionEvent(PanelEventBase):
    known: bool
    mm: float
    physical_bottom_mm: float
    physical_top_mm: float
    working_bottom_mm: float
    working_top_mm: float
    travel_mm: float


@dataclass(frozen=True)
class PanelDiagnosticEvent(PanelEventBase):
    subsystem: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PanelStatusEvent(PanelEventBase):
    firmware: str
    firmware_version: str
    protocol_version: int
    machine_state: str
    fault_code: str
    stop_latched: bool
    input_healthy: bool
    buttons: dict[str, bool]
    sensors: dict[str, bool]
    bottom_pair: bool
    top_pair: bool
    position_mm: float


@dataclass(frozen=True)
class PanelGenericEvent(PanelEventBase):
    item_id: str
    action: str
    value: float
    active: bool


type PanelEvent = (
    PanelVersionEvent
    | PanelPongEvent
    | PanelButtonEvent
    | PanelSensorEvent
    | PanelPairEvent
    | PanelMotionRequestEvent
    | PanelFaultEvent
    | PanelMachineStateEvent
    | PanelPositionEvent
    | PanelDiagnosticEvent
    | PanelStatusEvent
    | PanelGenericEvent
)


def _reject_constant(value: str) -> None:
    raise PanelProtocolError(f"non-finite JSON number: {value}")


def _require_keys(value: dict[str, Any], required: set[str], allowed: set[str] | None = None) -> None:
    missing = required - value.keys()
    if missing:
        raise PanelProtocolError(f"missing fields: {', '.join(sorted(missing))}")
    unexpected = value.keys() - (allowed or required)
    if unexpected:
        raise PanelProtocolError(f"unexpected fields: {', '.join(sorted(unexpected))}")


def _integer(value: Any, field: str, *, minimum: int = 0, maximum: int = MAX_SEQUENCE) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PanelProtocolError(f"{field} must be an integer in [{minimum}, {maximum}]")
    return int(value)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise PanelProtocolError(f"{field} must be a finite number")
    return float(value)


def _string(value: Any, field: str, *, allowed: set[str] | tuple[str, ...] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise PanelProtocolError(f"{field} must be a non-empty string")
    if allowed is not None and value not in allowed:
        raise PanelProtocolError(f"unsupported {field}: {value}")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PanelProtocolError(f"{field} must be a boolean")
    return value


def _boolean_map(value: Any, field: str, expected_keys: tuple[str, ...]) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise PanelProtocolError(f"{field} must be an object")
    _require_keys(value, set(expected_keys))
    return {key: _boolean(value[key], f"{field}.{key}") for key in expected_keys}


def parse_event(line: bytes | str, *, maximum_bytes: int = MAX_LINE_BYTES) -> PanelEvent:
    """Parse one complete firmware line without coercing types or accepting extensions."""

    if isinstance(line, bytes):
        raw = line[:-1] if line.endswith(b"\n") else line
        raw = raw[:-1] if raw.endswith(b"\r") else raw
        if not raw or len(raw) > maximum_bytes:
            raise PanelProtocolError("line length is outside protocol bounds")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise PanelProtocolError("line is not UTF-8") from error
    else:
        text = line[:-1] if line.endswith("\n") else line
        text = text[:-1] if text.endswith("\r") else text
        try:
            size = len(text.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise PanelProtocolError("line is not UTF-8") from error
        if not text or size > maximum_bytes:
            raise PanelProtocolError("line length is outside protocol bounds")

    try:
        document = json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, PanelProtocolError) as error:
        raise PanelProtocolError(f"invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise PanelProtocolError("event must be a JSON object")

    version = _integer(document.get("v"), "v", minimum=1)
    if version != PROTOCOL_VERSION:
        raise PanelProtocolError(f"unsupported protocol version: {version}")
    sequence = _integer(document.get("seq"), "seq", minimum=1)
    event_type = _string(document.get("type"), "type")
    envelope = {"v", "seq", "type"}

    if event_type == "version":
        fields = {"firmware", "version", "protocol"}
        _require_keys(document, envelope | fields)
        protocol_version = _integer(document["protocol"], "protocol", minimum=1)
        if protocol_version != PROTOCOL_VERSION:
            raise PanelProtocolError(f"unsupported advertised protocol version: {protocol_version}")
        return PanelVersionEvent(
            sequence,
            event_type,
            _string(document["firmware"], "firmware"),
            _string(document["version"], "version"),
            protocol_version,
        )

    if event_type == "pong":
        _require_keys(document, envelope | {"request_seq", "firmware"})
        return PanelPongEvent(
            sequence,
            event_type,
            _integer(document["request_seq"], "request_seq", minimum=1),
            _string(document["firmware"], "firmware"),
        )

    if event_type == "fault":
        if "code" in document:
            _require_keys(document, envelope | {"code", "latched"})
            return PanelFaultEvent(
                sequence,
                event_type,
                _string(document["code"], "code", allowed=FAULT_CODES),
                _boolean(document["latched"], "latched"),
            )
        _require_keys(document, envelope | {"id", "event", "value", "active"})
        _number(document["value"], "value")
        _string(document["event"], "event", allowed={"latched", "homing_aborted"})
        return PanelFaultEvent(
            sequence,
            event_type,
            _string(document["id"], "id", allowed=FAULT_CODES),
            _boolean(document["active"], "active"),
        )

    if event_type == "machine_state":
        _require_keys(document, envelope | {"state"})
        return PanelMachineStateEvent(sequence, event_type, _string(document["state"], "state", allowed=MACHINE_STATES))

    if event_type == "position":
        fields = {
            "known",
            "mm",
            "physical_bottom_mm",
            "physical_top_mm",
            "working_bottom_mm",
            "working_top_mm",
            "travel_mm",
        }
        _require_keys(document, envelope | fields)
        return PanelPositionEvent(
            sequence,
            event_type,
            _boolean(document["known"], "known"),
            _number(document["mm"], "mm"),
            _number(document["physical_bottom_mm"], "physical_bottom_mm"),
            _number(document["physical_top_mm"], "physical_top_mm"),
            _number(document["working_bottom_mm"], "working_bottom_mm"),
            _number(document["working_top_mm"], "working_top_mm"),
            _number(document["travel_mm"], "travel_mm"),
        )

    if event_type == "diagnostic":
        _require_keys(document, envelope | {"subsystem", "ok", "detail"})
        return PanelDiagnosticEvent(
            sequence,
            event_type,
            _string(document["subsystem"], "subsystem"),
            _boolean(document["ok"], "ok"),
            _string(document["detail"], "detail"),
        )

    if event_type == "status":
        fields = {
            "firmware",
            "version",
            "protocol",
            "machine_state",
            "fault",
            "stop_latched",
            "input_healthy",
            "buttons",
            "sensors",
            "bottom_pair",
            "top_pair",
            "position_mm",
        }
        _require_keys(document, envelope | fields)
        protocol_version = _integer(document["protocol"], "protocol", minimum=1)
        if protocol_version != PROTOCOL_VERSION:
            raise PanelProtocolError(f"unsupported advertised protocol version: {protocol_version}")
        buttons = _boolean_map(document["buttons"], "buttons", BUTTON_IDS)
        sensors = _boolean_map(document["sensors"], "sensors", SENSOR_IDS)
        bottom_pair = _boolean(document["bottom_pair"], "bottom_pair")
        top_pair = _boolean(document["top_pair"], "top_pair")
        if bottom_pair != (sensors["left_bottom"] and sensors["right_bottom"]):
            raise PanelProtocolError("bottom_pair disagrees with sensor states")
        if top_pair != (sensors["left_top"] and sensors["right_top"]):
            raise PanelProtocolError("top_pair disagrees with sensor states")
        return PanelStatusEvent(
            sequence,
            event_type,
            _string(document["firmware"], "firmware"),
            _string(document["version"], "version"),
            protocol_version,
            _string(document["machine_state"], "machine_state", allowed=MACHINE_STATES),
            _string(document["fault"], "fault", allowed=FAULT_CODES),
            _boolean(document["stop_latched"], "stop_latched"),
            _boolean(document["input_healthy"], "input_healthy"),
            buttons,
            sensors,
            bottom_pair,
            top_pair,
            _number(document["position_mm"], "position_mm"),
        )

    core_fields = envelope | {"id", "event", "value", "active"}
    _require_keys(document, core_fields)
    item_id = _string(document["id"], "id")
    action = _string(document["event"], "event")
    value = _number(document["value"], "value")
    active = _boolean(document["active"], "active")

    if event_type == "button":
        return PanelButtonEvent(
            sequence,
            event_type,
            _string(item_id, "id", allowed=BUTTON_IDS),
            _string(action, "event", allowed=BUTTON_EVENTS),  # type: ignore[arg-type]
            active,
        )
    if event_type == "sensor":
        _string(item_id, "id", allowed=SENSOR_IDS)
        _string(action, "event", allowed={"active", "inactive"})
        if active != (action == "active"):
            raise PanelProtocolError("sensor event and active flag disagree")
        return PanelSensorEvent(sequence, event_type, item_id, active)
    if event_type == "pair":
        return PanelPairEvent(
            sequence,
            event_type,
            _string(item_id, "id", allowed={"bottom", "top"}),  # type: ignore[arg-type]
            _string(action, "event", allowed={"first_edge", "confirmed"}),  # type: ignore[arg-type]
            value,
            active,
        )
    if event_type == "motion_request":
        return PanelMotionRequestEvent(
            sequence,
            event_type,
            _string(item_id, "id", allowed={"up", "down", "stop"}),  # type: ignore[arg-type]
            _string(action, "event", allowed={"move", "stop"}),  # type: ignore[arg-type]
            value,
            active,
        )
    if event_type in {"diagnostic_input", "load_request", "move_target", "log", "state"}:
        return PanelGenericEvent(sequence, event_type, item_id, action, value, active)
    raise PanelProtocolError(f"unsupported event type: {event_type}")


class PanelCommandEncoder:
    """Encode host commands with a process-local monotonically increasing sequence."""

    _simple_commands = {"ping", "heartbeat", "status", "home", "start", "pause", "stop", "clear_stop", "led_test", "input_test", "i2c_test", "diagnostics", "firmware_info"}

    def __init__(self, session_id: str | None = None) -> None:
        self._session_id = session_id if session_id is not None else uuid.uuid4().hex
        if not isinstance(self._session_id, str) or not self._session_id or len(self._session_id) > 64:
            raise ValueError("panel session ID must be a non-empty string of at most 64 characters")
        self._sequence = 0
        self._lock = Lock()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence

    def encode(self, command: str, **payload: Any) -> bytes:
        document: dict[str, Any] = {"v": PROTOCOL_VERSION, "cmd": command, "session": self._session_id}
        if command in self._simple_commands:
            if payload:
                raise ValueError(f"{command} does not accept a payload")
        elif command in {"position", "move"}:
            document["position_mm"] = _number(payload.pop("position_mm", None), "position_mm")
        elif command == "set_load":
            document["kg"] = _number(payload.pop("kg", None), "kg")
        elif command == "set_machine_state":
            document["state"] = _string(payload.pop("state", None), "state", allowed=MACHINE_STATES)
        elif command in {"set_night_mode", "drive_fault"}:
            document["enabled"] = _boolean(payload.pop("enabled", None), "enabled")
        elif command == "button_feedback":
            document["id"] = _string(payload.pop("id", None), "id", allowed=BUTTON_IDS)
            document["request_seq"] = _integer(payload.pop("request_seq", None), "request_seq", minimum=1)
            document["accepted"] = _boolean(payload.pop("accepted", None), "accepted")
        elif command == "set_activity":
            document["direction"] = _string(payload.pop("direction", None), "direction", allowed={"up", "down", "stop"})
        elif command == "play_effect":
            document["effect"] = _string(payload.pop("effect", None), "effect", allowed={"home_detected", "homing_complete", "target_reached", "limit_triggered", "set_complete"})
        elif command == "set_brightness":
            brightness = _number(payload.pop("brightness", None), "brightness")
            if not 0.1 <= brightness <= 1.0:
                raise PanelProtocolError("brightness must be in [0.1, 1.0]")
            document["brightness"] = brightness
        else:
            raise ValueError(f"unsupported panel command: {command}")
        if payload:
            raise ValueError(f"unexpected command fields: {', '.join(sorted(payload))}")

        with self._lock:
            if self._sequence >= MAX_SEQUENCE:
                raise OverflowError("panel command sequence exhausted")
            self._sequence += 1
            document["seq"] = self._sequence
        encoded = (json.dumps(document, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        if len(encoded.rstrip(b"\n")) > MAX_LINE_BYTES:
            raise ValueError("encoded command exceeds protocol line limit")
        return encoded
