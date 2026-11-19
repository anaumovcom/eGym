"""Last observations on the controller's own channel. A snapshot never accesses the bus."""

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from app.schemas.drive_transport import (
    CanAdapterInfo,
    CanAxisDiagnostics,
    CanObjectReading,
    CanopenDiagnostics,
    CanTraceFrame,
)

Address = tuple[int, int]
LIVE = (0x6041, 0x603F, 0x1001, 0x6061, 0x6040, 0x6071, 0x6077, 0x6064, 0x606C)
INVENTORY = (
    *((0x1018, sub) for sub in range(1, 5)),
    *((index, 0) for index in (0x6502, 0x6060, 0x6072, 0x6080, 0x6087, 0x1005, 0x1006, 0x1019, 0x1017, 0x1016)),
    *((comm, sub) for comm in (0x1400, 0x1800, 0x1801) for sub in (1, 2)),
    (0x1600, 0), (0x1A00, 0), (0x1A01, 0),
)
SIGNED_BITS = {0x6060: 8, 0x6061: 8, 0x6071: 16, 0x6077: 16, 0x6064: 32, 0x606C: 32}


@dataclass
class AxisObservation:
    responding: bool | None = None
    last_seen: float | None = None
    issue: str | None = None
    heartbeat: tuple[float, int] | None = None
    emcy: tuple[float, int, int] | None = None
    bootups: int = 0
    tpdo_latency_ms: float | None = None
    # Unsigned wire values from successful SDO uploads, or a received abort code.
    objects: dict[Address, tuple[float, int | None, int | None]] = field(default_factory=dict)
    issues: dict[Address, str] = field(default_factory=dict)
    pending: deque[Address] = field(default_factory=deque)
    next_live: float = 0
    next_inventory: float = 0

    def new_session(self) -> None:
        self.responding = self.last_seen = self.issue = self.heartbeat = self.emcy = self.tpdo_latency_ms = None
        self.objects.clear()
        self.issues.clear()
        self.pending.clear()
        self.next_live = self.next_inventory = 0

    def schedule(self, now: float) -> None:
        if now >= self.next_live:
            # Prioritise reachability, while allowing slow optional objects to finish their turn.
            status = (0x6041, 0)
            if status not in self.pending:
                self.pending.appendleft(status)
            self.pending.extend((index, 0) for index in LIVE[1:] if (index, 0) not in self.pending)
            self.next_live = now + 1
        if now >= self.next_inventory:
            self.pending.extend(key for key in INVENTORY if key not in self.pending)
            self.next_inventory = now + 30


class CanMonitor:
    def __init__(self, nodes: tuple[int, ...], now: float):
        self.start = now
        self.stage = "Ожидание адаптера"
        self.adapter: CanAdapterInfo | None = None
        self.axes = {node: AxisObservation() for node in nodes}
        self.tx = self.rx = self.timeouts = self.aborts = 0
        self.frames: deque[tuple[float, Literal["TX", "RX"], int, bytes]] = deque(maxlen=64)

    def frame(self, direction: Literal["TX", "RX"], identifier: int, data: bytes, now: float) -> None:
        if direction == "TX":
            self.tx += 1
        else:
            self.rx += 1
        self.frames.append((now, direction, identifier, data))

    def snapshot(self, now: float, opened: bool, feedback: dict[int, dict[int, int]],
                 replies: dict[int, float], sent: dict[int, tuple[int, int]]) -> CanopenDiagnostics:
        def age(stamp: float | None) -> int | None:
            return max(0, round((now - stamp) * 1000)) if stamp is not None else None

        axes = []
        for node, axis in self.axes.items():
            objects = {}
            for (index, sub), (stamp, value, abort) in axis.objects.items():
                if value is not None and (bits := SIGNED_BITS.get(index)):
                    value = (value + (1 << (bits - 1))) % (1 << bits) - (1 << (bits - 1))
                objects[f"{index:04X}:{sub:02X}"] = CanObjectReading(value=value, abort=abort, issue=axis.issues.get((index, sub)),
                                                                    age_ms=age(stamp))
            for index, value in feedback.get(node, {}).items():
                objects[f"{index:04X}:00"] = CanObjectReading(value=value, age_ms=age(replies[node]))
            hb, emcy = axis.heartbeat, axis.emcy
            word, target = sent.get(node, (None, None))
            axes.append(CanAxisDiagnostics(node=node, responding=axis.responding if opened else None,
                        last_seen_ms=age(axis.last_seen), issue=axis.issue, objects=objects,
                        heartbeat_state=hb[1] if hb else None, heartbeat_age_ms=age(hb[0]) if hb else None,
                        bootups=axis.bootups, emcy=emcy[1] if emcy else None, emcy_register=emcy[2] if emcy else None,
                        emcy_age_ms=age(emcy[0]) if emcy else None, sent_controlword=word, sent_target=target,
                        tpdo_latency_ms=axis.tpdo_latency_ms))
        frames = [CanTraceFrame(seq=seq, elapsed_ms=round((stamp - self.start) * 1000, 2), direction=d,
                                identifier=i, data=data.hex(" ").upper())
                  for seq, (stamp, d, i, data) in enumerate(self.frames, self.tx + self.rx - len(self.frames) + 1)]
        return CanopenDiagnostics(stage=self.stage, adapter_open=opened, adapter=self.adapter, axes=axes, frames=frames,
                                  tx=self.tx, rx=self.rx, sdo_timeouts=self.timeouts, sdo_aborts=self.aborts)
