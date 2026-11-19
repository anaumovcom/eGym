"""One synchronous CANopen master for the two A6 drives. All bus access is owned by HardwareRuntime's lock."""

from __future__ import annotations

import struct
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from app.motor.calibration.fit import percentile
from app.motor.drive.can_bus import CanBus, CanChannelError, open_can_bus
from app.motor.drive.canopen_diagnostics import CanMonitor
from app.motor.drive.protocol import DriveSample
from app.motor.profile import SideProfile
from app.motor.units import Side, clamp, force_to_raw, raw_to_force, rpm_to_mm_s
from app.schemas.drive_transport import CanopenSettings, CanopenTiming

MASTER = 127
COMMAND = (0x60400010, 0x60710010)
MOTION = (0x60640020, 0x606C0020)
STATUS = (0x60770010, 0x60410010)
SIGNED = {0x6071, 0x6077, 0x6064, 0x606C}
SDO_WIDTHS = {0x6040: 2, 0x6041: 2, 0x6071: 2, 0x6072: 2, 0x6077: 2, 0x603F: 2, 0x1017: 2,
              0x1001: 1, 0x6060: 1, 0x6061: 1, 0x1019: 1}
READ_ONLY = "Включена диагностика CANopen. Для управления выберите «Управление приводами»."


def encoder_delta(counts: int, zero: int) -> int:
    """Shortest signed distance across the 32-bit position counter's rollover."""
    return (counts - zero + 0x80000000) % 0x100000000 - 0x80000000


class SdoAbortError(OSError):
    def __init__(self, node: int, index: int, sub: int, code: int):
        super().__init__(f"CANopen ID {node}, {index:04X}:{sub:02X}, отказ SDO 0x{code:08X}")
        self.code = code


class DriveFaultError(OSError):
    """An actual drive alarm requires an operator reset."""


class SdoTimeoutError(TimeoutError):
    """No matching reply. Other nodes and the adapter may still be online."""


class SdoResponseError(OSError):
    """The node replied, but its response could not be decoded for this numeric object."""


@dataclass(frozen=True)
class Pdo:
    identifier: int
    fields: tuple[int, ...]

    def pack(self, values: dict[int, int]) -> bytes:
        return b"".join(values[field >> 16].to_bytes((field & 255) // 8, "little", signed=field >> 16 in SIGNED)
                        for field in self.fields)

    def unpack(self, data: bytes) -> dict[int, int]:
        if sum(field & 255 for field in self.fields) != len(data) * 8:
            raise OSError(f"PDO {self.identifier:03X}: неожиданная длина {len(data)}")
        offset = 0
        values = {}
        for field in self.fields:
            end = offset + (field & 255) // 8
            if field in (*MOTION, *STATUS):
                index = field >> 16
                values[index] = int.from_bytes(data[offset:end], "little", signed=index in SIGNED)
            offset = end
        return values


@dataclass(frozen=True)
class PdoParameters:
    comm: int
    cob: int
    kind: int
    fields: tuple[int, ...]


class CanopenPair:
    def __init__(self, config: CanopenSettings, opener: Callable[[CanopenSettings], CanBus] = open_can_bus):
        self.config = config
        self.period_s = config.cycle_ms / 1000
        # Host SYNC times for the last 200 complete two-drive exchanges.
        self._sync_times: deque[float] = deque(maxlen=201)
        self._feedback_ms: deque[float] = deque(maxlen=200)
        self.nodes = (config.left_id, config.right_id)
        self.read_only = config.operation == "diagnostics"
        self.monitor = CanMonitor(self.nodes, time.monotonic())
        self._probe_side = 0
        self._next_open = self._next_usb_check = 0.0
        self.sent_targets: dict[int, tuple[int, int]] = {}
        self.opener = opener
        self.bus: CanBus | None = None
        self.ready = False
        self.error: str | None = None
        self.tpdo: dict[int, tuple[int, Pdo]] = {}
        self.rpdo: dict[int, Pdo] = {}
        self.feedback: dict[int, dict[int, int]] = {}
        self.replies: dict[int, float] = {}
        self.commands: dict[int, int] = {}
        self.words: dict[int, int] = {}
        self.zero: dict[int, int] = {}
        self.mode: dict[int, int] = {}
        self.reports: dict[int, list[dict[str, Any]]] = {}
        self.max_raw = self.speed_limit = 0
        self.cycle_t = self.last_heartbeat = 0.0
        self.errors = 0

    def close(self) -> None:
        bus, self.bus = self.bus, None
        self.ready = False
        for node, fields in self.feedback.items():
            for index, value in fields.items():
                self.monitor.axes[node].objects[index, 0] = (self.replies[node], value, None)
        self.feedback.clear()
        self.rpdo.clear()
        self.tpdo.clear()
        self.reports.clear()
        self._sync_times.clear()
        self._feedback_ms.clear()
        if bus is not None:
            bus.close()

    def _open(self) -> None:
        self.monitor.stage = "Открытие адаптера"
        try:
            self.bus = self.opener(self.config)
        except CanChannelError as exc:
            self.monitor.adapter = exc.info
            self.monitor.stage = "Адаптер обнаружен · ошибка запуска канала"
            raise
        self.monitor.adapter = getattr(self.bus, "info", None)
        self.sent_targets.clear()
        for axis in self.monitor.axes.values():
            axis.new_session()
        self.error = None
        self.monitor.stage = "Чтение состояния узлов"

    def _send(self, identifier: int, data: bytes) -> None:
        if self.bus is None:
            raise OSError("CAN-адаптер закрыт")
        if self.read_only and not (identifier - 0x600 in self.nodes and len(data) == 8 and data[0] == 0x40):
            raise OSError(READ_ONLY)
        self.bus.send(identifier, data)
        self.monitor.frame("TX", identifier, data, time.monotonic())

    def _receive(self, timeout: float) -> tuple[int, bytes] | None:
        assert self.bus is not None
        frame = self.bus.receive(timeout)
        if frame is not None:
            self.monitor.frame("RX", *frame, time.monotonic())
            self._event(*frame)
        return frame

    def _heartbeat(self) -> None:
        now = time.monotonic()
        if now - self.last_heartbeat >= 0.1:
            self._send(0x700 + MASTER, b"\x05")
            self.last_heartbeat = now

    def _event(self, identifier: int, data: bytes) -> None:
        if (node := identifier - 0x80) in self.nodes and len(data) == 8:
            code = int.from_bytes(data[:2], "little")
            self.monitor.axes[node].emcy = time.monotonic(), code, data[2]
            if code and not self.read_only:
                self.words[node] = 6
                raise DriveFaultError(f"CANopen ID {node}, EMCY 0x{code:04X}")
        if (node := identifier - 0x700) in self.nodes and len(data) == 1:
            axis = self.monitor.axes[node]
            if data[0] == 0:
                axis.new_session()
                axis.bootups += 1
            axis.heartbeat = time.monotonic(), data[0]
            if self.ready and data[0] != 5:
                self.words[node] = 6
                raise OSError(f"CANopen ID {node} вышел из Operational")

    def _sdo(self, node: int, index: int, sub: int, value: bytes | None = None) -> int:
        address = struct.pack("<HB", index, sub)
        command = 0x40 if value is None else 0x23 | ((4 - len(value)) << 2)
        if not self.read_only:
            self._heartbeat()
        self._send(0x600 + node, bytes([command]) + address + (value or b"").ljust(4, b"\0"))
        deadline = time.monotonic() + 0.065
        axis = self.monitor.axes[node]
        while (remaining := deadline - time.monotonic()) > 0:
            frame = self._receive(remaining)
            if frame is None:
                continue
            identifier, data = frame
            if identifier != 0x580 + node or len(data) != 8 or data[1:4] != address:
                continue
            if axis.responding is False:
                axis.objects.clear()
                axis.issues.clear()
                axis.pending.clear()
                axis.next_live = axis.next_inventory = 0
            axis.responding, axis.last_seen = True, time.monotonic()
            axis.issues.pop((index, sub), None)
            if data[0] == 0x80:
                code = int.from_bytes(data[4:], "little")
                self.monitor.aborts += 1
                if value is None:
                    axis.objects[index, sub] = (axis.last_seen, None, code)
                raise SdoAbortError(node, index, sub, code)
            if value is not None and data[0] == 0x60:
                axis.objects.pop((index, sub), None)
                return 0
            if value is None and data[0] in (0x43, 0x47, 0x4B, 0x4F):
                size = 4 - ((data[0] >> 2) & 3)
            elif value is None and data[0] == 0x42:
                # Expedited upload without an encoded size. Use the requested object's CiA type.
                size = SDO_WIDTHS.get(index, 4)
                if sub == 0 and (index == 0x1016 or 0x1400 <= index <= 0x1BFF):
                    size = 1
                elif sub == 2 and index in (0x1400, 0x1800, 0x1801):
                    size = 1
            else:
                detail = (f"Сегментированный ответ SDO 0x{data[0]:02X}" if data[0] in (0x40, 0x41)
                          else f"Неожиданный ответ SDO 0x{data[0]:02X}")
                axis.objects[index, sub] = (axis.last_seen, None, None)
                axis.issues[index, sub] = detail
                raise SdoResponseError(f"CANopen ID {node}, {index:04X}:{sub:02X}: {detail}")
            result = int.from_bytes(data[4:4 + size], "little")
            axis.objects[index, sub] = (axis.last_seen, result, None)
            if index == 0x6041:
                axis.issue = None
            return result
        self.monitor.timeouts += 1
        axis.issues.pop((index, sub), None)
        reason = f"CANopen ID {node} не отвечает на {index:04X}:{sub:02X}"
        if index == 0x6041:
            axis.responding, axis.issue = False, reason
        else:
            axis.objects[index, sub] = (time.monotonic(), None, None)
        raise SdoTimeoutError(reason)

    def _optional(self, node: int, index: int, sub: int = 0) -> int | None:
        try:
            return self._sdo(node, index, sub)
        except SdoAbortError as exc:
            if exc.code not in (0x06020000, 0x06090011):
                raise
            return None

    def observe(self) -> None:
        """Poll each node independently. Only SDO uploads pass the read-only transmit guard."""
        if not self.read_only:
            raise RuntimeError("Диагностический опрос требует режима чтения")
        now = time.monotonic()
        try:
            if self.bus is None:
                if now < self._next_open:
                    return
                self._open()
            if now >= self._next_usb_check:
                self._next_usb_check = now + 2
                if check := getattr(self.bus, "check_online", None):
                    check()
            for _ in range(64):
                if self._receive(0) is None:
                    break
            node = self.nodes[self._probe_side]
            self._probe_side = 1 - self._probe_side
            axis = self.monitor.axes[node]
            if axis.responding is False and now < axis.next_live:
                return
            axis.schedule(now)
            # Yield to the runtime between small batches, including when only one axis has power.
            for _ in range(6):
                if not axis.pending:
                    break
                index, sub = axis.pending.popleft()
                try:
                    value = self._sdo(node, index, sub)
                except SdoTimeoutError:
                    if index == 0x6041:
                        axis.pending.clear()
                        axis.next_live = time.monotonic() + 1
                        axis.next_inventory = 0
                    break
                except (SdoAbortError, SdoResponseError) as exc:
                    if index == 0x6041:
                        axis.issue = str(exc)
                else:
                    if sub == 0 and index in (0x1016, 0x1600, 0x1A00, 0x1A01):
                        limit = 127 if index == 0x1016 else 64
                        if value <= limit:
                            for address in tuple(axis.objects):
                                if address[0] == index and address[1] > value:
                                    del axis.objects[address]
                                    axis.issues.pop(address, None)
                            axis.pending = deque(key for key in axis.pending if key[0] != index or key[1] <= value)
                            axis.pending.extend((index, slot) for slot in range(1, value + 1) if (index, slot) not in axis.pending)
                if time.monotonic() - now > 0.005:
                    break
            self.monitor.stage = "Диагностика · чтение SDO"
        except (OSError, AttributeError) as exc:
            self.error = str(exc)
            self.errors += 1
            self.close()
            self._next_open = time.monotonic() + 2

    def axes_disabled(self, *, from_diagnostics: bool = False) -> bool:
        """Read the actual CiA 402 states before releasing the controller's channel."""
        for node in self.nodes:
            try:
                word = self._sdo(node, 0x6041, 0)
            except SdoTimeoutError:
                if not from_diagnostics:
                    raise
                last = self.monitor.axes[node].objects.get((0x6041, 0))
                if last is None or last[1] is None:
                    continue  # Still waiting for first power-up. Startup requires fresh 6041 from both drives.
                word = last[1]
            if from_diagnostics and (word & 0x4F) in (0, 8):
                continue  # Not ready to switch on or Fault. Active control will verify or report it on startup.
            if word & 0x4F != 0x40 and word & 0x6F != 0x21:
                return False
        return True

    def _write(self, node: int, index: int, sub: int, value: int, size: int) -> None:
        self._sdo(node, index, sub, value.to_bytes(size, "little", signed=value < 0))

    def _wait_value(self, node: int, index: int, mask: int, expected: int) -> int:
        deadline = time.monotonic() + 0.15
        while True:
            value = self._sdo(node, index, 0)
            if value & mask == expected or time.monotonic() >= deadline:
                return value
            time.sleep(0.003)

    def _setting(self, node: int, index: int, value: int, size: int, *, sub: int = 0, change: bool = True) -> None:
        if self._sdo(node, index, sub) == value:
            return
        if change:
            self._write(node, index, sub, value, size)
        if not change or self._sdo(node, index, sub) != value:
            raise OSError(f"CANopen ID {node}: проверьте {index:04X}:{sub:02X}, ожидается {value}")

    def _monitor_master(self, node: int, enabled: bool) -> bool:
        count = self._optional(node, 0x1016)
        if not count:
            return False
        entries = {sub: self._sdo(node, 0x1016, sub) for sub in range(1, count + 1)}
        for value in entries.values():
            if (value >> 16) & 255 == MASTER and 100 < (value & 0xFFFF) <= 500:
                return True
        slot = next((sub for sub, value in entries.items() if value >> 16 == MASTER or value == 0), None)
        if slot is None:
            return False
        self._setting(node, 0x1016, (MASTER << 16) | 300, 4, sub=slot, change=not enabled)
        return True

    def _parameters(self, node: int, comm: int) -> PdoParameters:
        count = self._sdo(node, comm + 0x200, 0)
        if count > 64:
            raise OSError(f"CANopen ID {node}: неверная длина карты {comm + 0x200:04X}")
        return PdoParameters(comm, self._sdo(node, comm, 1), self._sdo(node, comm, 2),
                             tuple(self._sdo(node, comm + 0x200, sub) for sub in range(1, count + 1)))

    def _map(self, node: int, current: PdoParameters, fields: tuple[int, ...], enabled: bool) -> Pdo:
        comm, cob = current.comm, current.cob
        kind = current.kind if comm == 0x1400 and current.kind <= 240 else 1
        identifier = cob & 0x7FF
        if not identifier and cob & 0x80000000:
            identifier = {0x1400: 0x200, 0x1800: 0x180, 0x1801: 0x280}[comm] + node
        if cob & 0x3FFFF800 or not identifier:
            raise OSError(f"ID {node}: нужен 11-битный COB-ID для {comm:04X}")
        wanted = PdoParameters(comm, (cob & 0x40000000) | identifier, kind, fields)
        if wanted != current:
            if enabled:
                raise OSError(f"Для настройки PDO {comm:04X} опустите гриф на упоры и выключите Servo ON")
            def install(parameters: PdoParameters) -> None:
                self._write(node, comm, 1, cob | 0x80000000, 4)
                if current.fields != fields:
                    self._write(node, comm + 0x200, 0, 0, 1)
                    for sub, field in enumerate(parameters.fields, 1):
                        self._write(node, comm + 0x200, sub, field, 4)
                    self._write(node, comm + 0x200, 0, len(parameters.fields), 1)
                if current.kind != kind:
                    self._write(node, comm, 2, parameters.kind, 1)
                self._write(node, comm, 1, parameters.cob, 4)
            try:
                install(wanted)
                if self._parameters(node, comm) != wanted:
                    raise OSError(f"ID {node}: карта {comm:04X} не подтверждена")
            except OSError as exc:
                try:
                    install(current)
                except OSError as rollback:
                    raise OSError(f"{exc}. Не восстановлена карта {comm:04X}: {rollback}") from exc
                raise
        return Pdo(identifier, fields)

    def _select_pair_mode(self, enabled: set[int]) -> int:
        supported = {n: self._optional(n, 0x6502) for n in self.nodes}
        modes = {"auto": (10, 4), "cst": (10,), "profile_torque": (4,)}[self.config.torque_mode]
        for mode in modes:
            if any(mask is not None and not mask & (1 << (mode - 1)) for mask in supported.values()):
                continue
            for node in self.nodes:
                if self._sdo(node, 0x6061, 0) == mode:
                    continue
                if node in enabled:
                    break
                try:
                    self._write(node, 0x6060, 0, mode, 1)
                except SdoAbortError:
                    break
                if self._wait_value(node, 0x6061, 0xFF, mode) != mode:
                    break
            else:
                return mode
        wanted = " или ".join("CST (10)" if mode == 10 else "Profile Torque (4)" for mode in modes)
        raise OSError(f"Оба привода должны подтвердить режим {wanted} в 6061:00")

    def _configure(self, node: int, enabled: bool, support: int) -> None:
        vendor = self._sdo(node, 0x1018, 1)
        if self._sdo(node, 0x1005, 0) != 0x80 or self._optional(node, 0x1019) not in (None, 0):
            raise OSError(f"ID {node}: требуется внешний SYNC 080 без данных")
        cycle_us = self.config.cycle_ms * 1000
        period = self._optional(node, 0x1006)
        if period not in (None, 0, cycle_us):
            self._setting(node, 0x1006, cycle_us, 4, change=not enabled)
        self._setting(node, 0x6072, self.max_raw, 2, change=not enabled)
        self._setting(node, 0x6080, self.speed_limit, 4, change=not enabled)
        watchdog = self._monitor_master(node, enabled)
        rx, pos, status = (self._parameters(node, comm) for comm in (0x1400, 0x1800, 0x1801))
        rx_fields = rx.fields if sorted(rx.fields) == sorted(COMMAND) else COMMAND
        tx_fields = pos.fields + status.fields
        usable = (set(MOTION + STATUS) <= set(tx_fields)
                  and all(0 < (field & 255) <= 64 and (field & 7) == 0 for field in tx_fields)
                  and all(0 < sum(f & 255 for f in p.fields) <= 64 for p in (pos, status)))
        self.rpdo[node] = self._map(node, rx, rx_fields, enabled)
        for params, fields in ((pos, pos.fields if usable else MOTION), (status, status.fields if usable else STATUS)):
            pdo = self._map(node, params, fields, enabled)
            if pdo.identifier in self.tpdo:
                raise OSError("Совпадают CAN-ID передающих PDO")
            self.tpdo[pdo.identifier] = node, pdo
        self.commands[node] = support
        self.words[node] = 0x000F if enabled else 0x0006
        # Initial discovery must not switch on a late drive. Enable is a separate verified pair transition.
        self.reports[node] = [{"register": key, "label": label, "value": value, "ok": True, "detail": None}
                              for key, label, value in (("1018:01", "Производитель", vendor),
                                  ("6061:00", "Режим момента", self.mode[node]), ("6072:00", "Предел момента", self.max_raw),
                                  ("6080:00", "Предел скорости", self.speed_limit), ("1400/1800/1801", "Карта PDO", 3))]
        self.reports[node].append({"register": "1016", "label": "Контроль heartbeat мастера",
                                   "value": int(watchdog), "ok": watchdog,
                                   "detail": None if watchdog else "Проверьте защиту A6 по потере команд на стенде"})

    def connect(self, support: dict[int, int], limit: int, speed: int, *, reset_fault: bool = False) -> None:
        if self.read_only:
            raise OSError(READ_ONLY)
        self.close()
        self.max_raw, self.speed_limit = limit, speed
        if any(abs(support[n]) > limit for n in self.nodes):
            raise OSError("Поддержка превышает предел момента")
        self._open()
        self.last_heartbeat = 0.0
        try:
            states = {}
            missing = []
            for n in self.nodes:
                try:
                    states[n] = self._sdo(n, 0x6041, 0)
                except SdoTimeoutError as exc:
                    missing.append(str(exc))
            if missing:
                raise SdoTimeoutError(". ".join(missing))
            for n, word in states.items():
                if word & 8:
                    if not reset_fault:
                        raise DriveFaultError(f"CANopen ID {n}: Fault, код {self._optional(n, 0x603F)}")
                    self._write(n, 0x6040, 0, 0, 2)
                    self._write(n, 0x6040, 0, 0x80, 2)
                    states[n] = self._wait_value(n, 0x6041, 8, 0)
                    if states[n] & 8:
                        raise DriveFaultError(f"CANopen ID {n}: авария остаётся активной")
            enabled = {n for n, word in states.items() if word & 0x6F == 0x27}
            for n, word in states.items():
                if word & 0x6F == 0x07:
                    raise DriveFaultError(f"CANopen ID {n}: активен Quick Stop")
                if n not in enabled:
                    if word & 0x4F != 0x40 and word & 0x6F not in (0x21, 0x23):
                        raise OSError(f"CANopen ID {n}: ожидание готовности, 6041={word:04X}")
                    self._send(0, bytes((0x80, n)))
            self.monitor.stage = "Проверка общего режима момента"
            mode = self._select_pair_mode(enabled)
            for n in self.nodes:
                self.monitor.stage = f"Проверка SYNC, пределов и карт PDO · ID {n}"
                self.mode[n] = mode
                self._configure(n, n in enabled, support[n])
            identifiers = [*(p.identifier for p in self.rpdo.values()), *self.tpdo]
            reserved = {0, 0x80, 0x100, 0x700 + MASTER} | {base + n for n in self.nodes for base in (0x80, 0x580, 0x600, 0x700)}
            if reserved.intersection(identifiers) or len(set(identifiers)) != len(identifiers):
                raise OSError("Конфликт идентификаторов PDO и служебных кадров CANopen")
            for n in self.nodes:
                self._send(0, bytes((1, n)))
            self.monitor.stage = "Ожидание синхронных TPDO обеих осей"
            self.cycle(entering_operational=True)
            if self.config.cycle_ms < 20:
                # Both drives must return all four TPDOs on successive fast SYNCs before arming.
                for _ in range(3):
                    self.cycle(spaced=True)
            for n in self.nodes:
                self.zero.setdefault(n, self.feedback[n][0x6064])
            self.ready, self.error = True, None
            self.monitor.stage = "Циклический обмен PDO"
        except Exception:
            self.close()
            raise

    def send_targets(self) -> None:
        for n in self.nodes:
            pdo = self.rpdo[n]
            self._send(pdo.identifier, pdo.pack({0x6040: self.words[n], 0x6071: self.commands[n]}))
            self.sent_targets[n] = self.words[n], self.commands[n]

    def cycle(self, *, spaced: bool = False, entering_operational: bool = False) -> None:
        assert self.bus is not None
        # Discard earlier TPDOs before sending this SYNC. A boot-up or EMCY remains significant.
        for _ in range(128):
            frame = self._receive(0)
            if frame is None:
                break
        else:
            raise OSError("Переполнена очередь приёма CAN")
        self._heartbeat()
        self.send_targets()
        # Let both four-byte RPDOs leave the adapter before the higher-priority SYNC.
        spacing = self.cycle_t + self.period_s - time.monotonic() if spaced else 0
        time.sleep(max(0.0006, spacing))
        self.cycle_t = time.monotonic()
        self._send(0x80, b"")
        pending = set(self.tpdo)
        values: dict[int, dict[int, int]] = {n: {} for n in self.nodes}
        replies = {}
        # Allow the original startup window immediately after NMT Start. In normal operation
        # leave 30% of each period for computing the next targets, queuing RPDOs and scheduling.
        window = 0.014 if entering_operational else self.period_s * 0.7
        deadline = self.cycle_t + window
        while pending and (remaining := deadline - time.monotonic()) > 0:
            frame = self._receive(remaining)
            if frame is None:
                continue
            identifier, data = frame
            received_at = time.monotonic()
            if identifier in pending and received_at <= deadline:
                node, pdo = self.tpdo[identifier]
                values[node].update(pdo.unpack(data))
                replies[node] = self.monitor.axes[node].last_seen = received_at
                pending.remove(identifier)
        if pending:
            raise OSError(f"Нет свежих TPDO за {window * 1000:g} мс после SYNC: " + ", ".join(f"{i:03X}" for i in sorted(pending)))
        self.feedback, self.replies = values, replies
        for node, fields in values.items():
            self.monitor.axes[node].tpdo_latency_ms = (replies[node] - self.cycle_t) * 1000
            if fields[0x6041] & 8:
                self.words[node] = 6
                raise DriveFaultError(f"CANopen ID {node}: авария привода, 6041={fields[0x6041]:04X}")
        self._sync_times.append(self.cycle_t)
        self._feedback_ms.append((max(replies.values()) - self.cycle_t) * 1000)

    def timing(self) -> CanopenTiming | None:
        if len(self._sync_times) < 21:
            return None
        periods = [b - a for a, b in pairwise(self._sync_times)]
        return CanopenTiming(intervals=len(periods), mean_hz=len(periods) / sum(periods),
                             p99_ms=1000 * percentile(periods, 0.99), p99_feedback_ms=percentile(list(self._feedback_ms), 0.99))

    def failed(self, exc: Exception, support: dict[int, int]) -> None:
        self.error, self.errors = str(exc), self.errors + 1
        if self.ready:
            for n in self.nodes:
                self.commands[n] = int(clamp(support[n], -self.max_raw, self.max_raw))
                pdo = self.rpdo[n]
                try:
                    self._send(pdo.identifier, pdo.pack({0x6040: self.words[n], 0x6071: self.commands[n]}))
                    self.sent_targets[n] = self.words[n], self.commands[n]
                except OSError:
                    continue
            try:
                time.sleep(0.0006)
                self._send(0x80, b"")
            except OSError:
                pass
        self.close()

    def switch(self, nodes: tuple[int, ...], on: bool, guard: Callable[[], str | None] | None = None) -> None:
        if not self.ready:
            raise OSError(self.error or "CANopen не готов")
        original = {n for n in nodes if self.feedback[n][0x6041] & 0x6F == 0x27}
        changed = set(nodes) - original if on else set(nodes)
        if not changed:
            return
        try:
            for word, target in (((6, 0x21), (7, 0x23), (15, 0x27)) if on else ((6, 0x21),)):
                if word == 15:
                    for node in nodes:
                        if self._sdo(node, 0x6071, 0) != (self.commands[node] & 0xFFFF):
                            raise OSError(f"ID {node}: привод не подтвердил момент поддержки в 6071:00")
                if on and guard is not None and (reason := guard()):
                    raise OSError(reason)
                for n in changed:
                    self.words[n] = word
                # CiA 402 transitions may need the full 100 ms even on a 5 ms bus.
                deadline = time.monotonic() + 0.100
                while True:
                    self.cycle(spaced=True)
                    if all(self.feedback[n][0x6041] & 0x6F == target for n in changed):
                        break
                    if time.monotonic() >= deadline:
                        raise OSError(f"CANopen: не подтверждено состояние CiA 402 0x{target:02X}")
        except OSError:
            if changed and on:
                for n in changed:
                    self.words[n] = 6
                self.cycle(spaced=True)
            raise

    def update_limits(self, limit: int, speed: int) -> None:
        for n in self.nodes:
            self._setting(n, 0x6072, limit, 2)
            self._setting(n, 0x6080, speed, 4)
        self.max_raw, self.speed_limit = limit, speed

    def config_report(self, node: int) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self.reports.get(node, [])]
        if not self.ready or not rows:
            return [{"register": "CAN", "label": "Конфигурация CANopen", "value": None, "ok": False, "detail": self.error}]
        try:
            for row in rows:
                register = row["register"]
                if register == "1400/1800/1801":
                    expected = {self.rpdo[node].identifier: self.rpdo[node],
                                **{i: pdo for i, (n, pdo) in self.tpdo.items() if n == node}}
                    for comm in (0x1400, 0x1800, 0x1801):
                        params = self._parameters(node, comm)
                        pdo_id = params.cob & 0x7FF
                        synchronous = params.kind <= 240 if comm == 0x1400 else params.kind == 1
                        if params.cob & 0xBFFFFFFF != pdo_id or expected.get(pdo_id) != Pdo(pdo_id, params.fields) or not synchronous:
                            row.update(ok=False, detail=f"Изменилась карта или тип передачи {comm:04X}")
                elif register == "1016":
                    count = self._optional(node, 0x1016) or 0
                    entries = (self._sdo(node, 0x1016, sub) for sub in range(1, count + 1))
                    ok = any(v >> 16 == MASTER and 100 < (v & 0xFFFF) <= 500 for v in entries)
                    row.update(value=int(ok), ok=ok)
                else:
                    index, sub = (int(part, 16) for part in register.split(":"))
                    expected_value = {0x6072: self.max_raw, 0x6080: self.speed_limit}.get(index, row["value"])
                    value = self._sdo(node, index, sub)
                    row.update(value=value, ok=value == expected_value)
        except OSError as exc:
            rows.append({"register": "SDO", "label": "Чтение конфигурации", "value": None, "ok": False, "detail": str(exc)})
        return rows


class CanopenDrive:
    def __init__(self, side: Side, node: int, profile: SideProfile, max_raw: int, pair: CanopenPair):
        self.control_period_s = pair.period_s
        self.side, self.node, self.profile, self.max_raw, self.pair = side, node, profile, max_raw, pair

    def read(self) -> DriveSample:
        pair, node = self.pair, self.node
        fields = pair.feedback.get(node)
        if not pair.ready or fields is None:
            return DriveSample(self.side, time.monotonic(), False, error=pair.error or (READ_ONLY if pair.read_only else "Ожидание CANopen"))
        sign, scale = self.profile.sign, float(self.profile.mm_per_pulse.value)
        counts, speed = fields[0x6064], fields[0x606C]
        velocity = rpm_to_mm_s(speed) if pair.config.velocity_unit == "rpm" else speed * scale
        return DriveSample(self.side, pair.cycle_t, True, encoder_delta(counts, pair.zero[node]) * scale * sign, velocity * sign,
                           raw_to_force(fields[0x6077], self.profile.n_per_raw_value, sign), pair.commands[node],
                           counts=counts, reply_t=pair.replies[node], bus_errors=pair.errors)

    def write_raw(self, raw: int) -> str | None:
        if not self.pair.ready:
            return self.pair.error or "CANopen не готов"
        limit = min(self.max_raw, self.pair.max_raw)
        self.pair.commands[self.node] = int(clamp(raw, -limit, limit))
        return None

    def write_force(self, force_n: float) -> str | None:
        return self.write_raw(force_to_raw(force_n, self.profile.n_per_raw_value, self.profile.sign, self.profile.pull_scale_value))

    def support(self) -> str | None:
        return self.write_raw(int(self.profile.support_raw.value) * self.profile.sign)

    def zero(self) -> str | None:
        return self.write_raw(0)

    def limit_speed_rpm(self, rpm: int | None) -> str | None:
        if not self.pair.ready:
            return "CANopen не готов"
        try:
            self.pair._setting(self.node, 0x6080, self.pair.speed_limit if rpm is None else min(self.pair.speed_limit, max(1, rpm)), 4)
        except OSError as exc:
            return str(exc)
        return None

    def set_servo(self, on: bool) -> str | None:
        try:
            self.pair.switch((self.node,), on)
        except OSError as exc:
            return str(exc)
        return None

    def servo_state(self) -> bool | None:
        fields = self.pair.feedback.get(self.node)
        return fields[0x6041] & 0x6F == 0x27 if self.pair.ready and fields else None

    def config_report(self) -> list[dict[str, Any]]:
        return self.pair.config_report(self.node)
