"""XMTZC05HM service-data decoder (UUID 181B, not a GATT characteristic).

Layout cross-checked against ESPHome xiaomi_miscale and BLE Monitor miscale.
The 13 bytes here EXCLUDE the AD header and the little-endian service UUID.
"""

from dataclasses import dataclass
from datetime import datetime
from struct import unpack

SERVICE_UUID = "0000181b-0000-1000-8000-00805f9b34fb"


@dataclass(frozen=True)
class ScalePacket:
    weight_kg: float
    stable: bool
    removed: bool
    impedance_ohm: int | None
    clock: str | None


def decode_service_data(data: bytes) -> ScalePacket | None:
    if len(data) != 13:
        return None
    unit, flags, year, month, day, hour, minute, second, impedance, raw = unpack("<BBHBBBBBHH", data)
    # BLE Monitor documents bit 6 of the SECOND control byte as Chinese catty.
    if unit not in (2, 3):
        return None
    if flags & 0x40:
        weight = raw / 100 * 0.5
    elif unit == 2:
        weight = raw / 200
    else:
        weight = raw / 100 * 0.45359237
    removed = bool(flags & 0x80)
    # Zero on unload is useful for rearming, but is never a body measurement.
    if not removed and not 2 <= weight <= 180:
        return None
    if removed and weight > 180:
        return None
    clock = None
    try:
        if 2020 <= year <= 2100:
            clock = datetime(year, month, day, hour, minute, second).isoformat()
    except ValueError:
        pass  # Scales without a synchronized clock still provide valid weight.
    return ScalePacket(
        weight_kg=round(weight, 3), stable=bool(flags & 0x20), removed=removed,
        impedance_ohm=impedance if flags & 2 and 0 < impedance < 3000 else None,
        clock=clock,
    )


class MeasurementGate:
    """One stable result per occupancy, including subsequent impedance packets.

    Re-arm on unload or a new unstable phase. A long silence permits a fresh
    occupancy even if the unload advertisement was missed. Continuous repeated
    stable packets never re-arm the gate.
    """

    def __init__(self) -> None:
        self.latched = False
        self.last_seen: float | None = None
        self.last_saved: float | None = None

    def accept(self, packet: ScalePacket, now: float) -> bool:
        if self.last_seen is not None and now - self.last_seen > 120:
            self.latched = False
        self.last_seen = now
        if packet.removed:
            self.latched = False
            return False
        if not packet.stable:
            if self.last_saved is None or now - self.last_saved > 10:
                self.latched = False
            return False
        if self.latched:
            return False
        self.latched = True
        self.last_saved = now
        return True