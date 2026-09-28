"""Optional ESP32 panel sidecar transport."""

from app.services.panel.bridge import PanelBridge, PanelBridgeConfig
from app.services.panel.protocol import PanelCommandEncoder, PanelEvent, PanelProtocolError, parse_event
from app.services.panel.state import PanelState
from app.services.panel.transport import PanelSerialTransport, PanelTransportError, PySerialTransport

__all__ = [
    "PanelBridge",
    "PanelBridgeConfig",
    "PanelCommandEncoder",
    "PanelEvent",
    "PanelProtocolError",
    "PanelSerialTransport",
    "PanelState",
    "PanelTransportError",
    "PySerialTransport",
    "parse_event",
]
