"""Thread-safe state exposed by the optional physical panel sidecar."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any

BUTTON_IDS = (
    "power",
    "up",
    "down",
    "load_plus",
    "load_minus",
    "start_pause",
    "camera",
    "ok",
    "fail",
    "stop",
)
SENSOR_IDS = ("left_bottom", "right_bottom", "left_top", "right_top")


@dataclass
class PanelState:
    """Latest panel observations; all mutation is protected by ``_lock``."""

    enabled: bool = False
    connected: bool = False
    handshake_complete: bool = False
    port: str | None = None
    firmware_version: str | None = None
    protocol_version: int | None = None
    last_seen_at: datetime | None = None
    buttons: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(BUTTON_IDS, False))
    sensors: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(SENSOR_IDS, False))
    bottom_pair: bool = False
    top_pair: bool = False
    fault_code: str | None = None
    diagnostics: dict[str, dict[str, Any]] = field(default_factory=dict)
    position: dict[str, Any] = field(default_factory=dict)
    machine_state: str | None = None
    input_healthy: bool = False
    stop_latched: bool = False
    freshness_timeout_seconds: float = 2.0
    last_rx_monotonic: float | None = field(default=None, repr=False)
    _identity_seen: bool = field(default=False, init=False, repr=False, compare=False)
    _status_seen: bool = field(default=False, init=False, repr=False, compare=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def mark_connected(self, connected: bool) -> None:
        with self._lock:
            self.connected = connected
            if not connected:
                self.handshake_complete = False

    def mark_seen(self, monotonic_now: float | None = None) -> None:
        with self._lock:
            self.last_seen_at = datetime.now(UTC)
            self.last_rx_monotonic = time.monotonic() if monotonic_now is None else monotonic_now

    def begin_connection(self) -> None:
        with self._lock:
            self.connected = False
            self.handshake_complete = False
            self._identity_seen = False
            self._status_seen = False
            self.last_rx_monotonic = None

    def mark_identity_seen(self) -> None:
        with self._lock:
            self.connected = True
            self._identity_seen = True
            self.handshake_complete = self._identity_seen and self._status_seen

    def mark_status_seen(self) -> None:
        with self._lock:
            self._status_seen = True
            self.handshake_complete = self._identity_seen and self._status_seen

    def is_fresh(self, monotonic_now: float | None = None) -> bool:
        with self._lock:
            if self.last_rx_monotonic is None:
                return False
            now = time.monotonic() if monotonic_now is None else monotonic_now
            return now - self.last_rx_monotonic <= self.freshness_timeout_seconds

    def is_ready(self, monotonic_now: float | None = None) -> bool:
        with self._lock:
            if not self.connected or not self.handshake_complete or self.last_rx_monotonic is None:
                return False
            now = time.monotonic() if monotonic_now is None else monotonic_now
            return now - self.last_rx_monotonic <= self.freshness_timeout_seconds

    def reset_observations(self) -> None:
        with self._lock:
            self.connected = False
            self.handshake_complete = False
            self.firmware_version = None
            self.protocol_version = None
            self.last_seen_at = None
            self.buttons = dict.fromkeys(BUTTON_IDS, False)
            self.sensors = dict.fromkeys(SENSOR_IDS, False)
            self.bottom_pair = False
            self.top_pair = False
            self.fault_code = None
            self.diagnostics = {}
            self.position = {}
            self.machine_state = None
            self.input_healthy = False
            self.stop_latched = False
            self.last_rx_monotonic = None
            self._identity_seen = False
            self._status_seen = False

    def to_payload(self) -> dict[str, Any]:
        with self._lock:
            rx_age_seconds = time.monotonic() - self.last_rx_monotonic if self.last_rx_monotonic is not None else None
            fresh = rx_age_seconds is not None and rx_age_seconds <= self.freshness_timeout_seconds
            ready = self.connected and self.handshake_complete and fresh
            return {
                "enabled": self.enabled,
                "connected": self.connected,
                "ready": ready,
                "handshakeComplete": self.handshake_complete,
                "fresh": fresh,
                "rxAgeMs": round(rx_age_seconds * 1000, 1) if rx_age_seconds is not None else None,
                "port": self.port,
                "firmwareVersion": self.firmware_version,
                "protocolVersion": self.protocol_version,
                "lastSeenAt": self.last_seen_at.isoformat() if self.last_seen_at else None,
                "buttons": dict(self.buttons),
                "sensors": dict(self.sensors),
                "bottomPair": self.bottom_pair,
                "topPair": self.top_pair,
                "faultCode": self.fault_code,
                "diagnostics": {key: dict(value) for key, value in self.diagnostics.items()},
                "position": dict(self.position),
                "machineState": self.machine_state,
                "inputHealthy": self.input_healthy,
                "stopLatched": self.stop_latched,
            }
