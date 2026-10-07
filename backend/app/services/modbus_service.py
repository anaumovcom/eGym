"""
Modbus RTU service for Lichuan A6 servo driver.

In development / emulator mode this service maintains a simulated register
bank that behaves like a real A6 driver. When a real serial port is available
and pyserial / minimalmodbus is installed it delegates to the real bus.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from app.schemas.modbus import (
    DriverDiagnosticsSchema,
    ExchangeLogEntrySchema,
    ExchangeLogResponseSchema,
    ModbusCommandRequestSchema,
    ModbusCommandResultSchema,
    ModbusConnectionParamsSchema,
    ModbusConnectionStatusSchema,
    ModbusPositionSideSchema,
    ModbusPositionsSchema,
    ModbusReadRequestSchema,
    ModbusReadResultSchema,
    ModbusRegisterValueSchema,
    ModbusWriteRequestSchema,
    ModbusWriteResultSchema,
    ParameterProfileSchema,
    ParameterValueSchema,
    ProfileCompareResultSchema,
    ProfileSaveRequestSchema,
    SerialPortInfoSchema,
)

# ---------------------------------------------------------------------------
# Lichuan A6 simulated register bank (decimal addresses)
# Addresses taken from the A6 user manual
# ---------------------------------------------------------------------------

_DEFAULT_REGISTERS: dict[int, int] = {
    # PA_000 – slave address
    0x000: 1,
    # PA_001 – reserved
    0x001: 0,
    # PA_002 – control mode: 0=Position, 1=Speed, 2=Torque, 3=CANopen (project runs in Torque Mode)
    0x002: 2,
    # PA_003 – rotation direction
    0x003: 0,
    # PA_00D – RS485 baud rate code: 0=2400, 1=4800, 2=9600, 3=19200, 4=38400, 5=57600, 6=115200
    0x00D: 6,
    # PA_090 – extended/communication mode: 0=standard, 1=extended
    0x090: 1,
    # PA_091 – active position segment index (0–15)
    0x091: 0,
    # PA_092 – active speed segment index (0–31)
    0x092: 0,
    # PA_093 – active torque segment index (0–31)
    0x093: 0,
    # PA_05E – torque limit, 0.1% of rated (400 = 40%)
    0x05E: 400,
    # PA_05F – CW torque limit when PA_003 = 2
    0x05F: 400,
    # PA_1A7 – service command register
    0x1A7: 0,
    # Status / monitoring registers (0x200 range – fictitious addresses for simulation)
    # Alarm code: 0 = no alarm
    0x200: 0,
    # Input status word (DI bitmap)
    0x201: 0b00000000,
    # Output status word (DO bitmap)
    0x202: 0b00000000,
    # Actual speed (rpm)
    0x203: 0,
    # Actual torque (0.1 % of rated)
    0x204: 0,
    # Position feedback low word
    0x205: 0,
    # Position feedback high word
    0x206: 0,
    # PA_1BC / PA_1BD – actual position feedback, low/high words
    0x1BC: 0,
    0x1BD: 0,
    # Position command low word
    0x207: 0,
    # Position command high word
    0x208: 0,
    # Speed command
    0x209: 0,
    # Torque command
    0x20A: 0,
    # Position error low word
    0x20B: 0,
    # Position error high word
    0x20C: 0,
    # PA_08F – automatic Servo ON after power-on
    0x08F: 1,
    # PA_094 – bit0 = 0 absolute position command
    0x094: 0,
    # PA_096 – 0 continuous position loading, no POS_LOAD pulse
    0x096: 0,
    # Monitoring block. LOW word is the even address.
    0x1B8: 0,
    0x1B9: 0,
    0x1BA: 0,
    0x1BB: 0,
    0x1BE: 0,
    0x1BF: 0,
    0x1C0: 0,
    0x1C1: 0,
    0x1C2: 0,
    0x1C3: 0,
    0x1C4: 0,
    0x1C5: 0,
    0x1C9: 0,
    0x1C6: 0,
    0x1C7: 0,
    0x1C8: 0,
    # PA_056 – speed limit in Torque Mode, rpm
    0x056: 50,
    # PA_1DB..PA_1DE – drive status / limit reason monitoring
    0x1DB: 0,
    0x1DC: 0,
    0x1DD: 0,
    0x1DE: 0,
}

# Position segments PA_168–PA_187 (low) and PA_188–PA_1A7-range (high)
# Each segment has 2 registers: low word and high word
for _i in range(16):
    _DEFAULT_REGISTERS[0x168 + _i * 2] = 0       # low
    _DEFAULT_REGISTERS[0x168 + _i * 2 + 1] = 0   # high

# Speed registers for internal position segments PA_190–PA_19F
for _i in range(16):
    _DEFAULT_REGISTERS[0x190 + _i] = 30  # safe default, rpm

# Speed segments PA_150–PA_16F
for _i in range(32):
    _DEFAULT_REGISTERS[0x150 + _i] = 0

# Torque segments PA_12C–PA_14B
for _i in range(32):
    _DEFAULT_REGISTERS[0x12C + _i] = 0

_MAX_LOG_ENTRIES = 500
# Travel from the session zero, not the absolute encoder count.
# Confirmed by tape and stored as screw.mmPerPulse: 1703 mm = 6980387 pulses.
_MM_PER_PULSE = 1703.0 / 6_980_387.0
_INT32_MIN = -0x8000_0000
_INT32_MAX = 0x7FFF_FFFF
# PA_05E is 0.1% of rated torque. 400 = 40%, the documented test ceiling.
DEFAULT_TORQUE_LIMIT = 400
# PA_056 speed limit in Torque Mode, rpm. Start low.
DEFAULT_SPEED_LIMIT_RPM = 300
_INTER_SLAVE_GAP_S = 0.010  # quiet time on the RS-485 bus when the next frame goes to another drive
_REG_CONTROL_MODE = 0x002
_REG_SPEED_LIMIT = 0x056
_REG_TORQUE_LIMIT = 0x05E
_REG_TORQUE_SEGMENT = 0x093
_REG_TORQUE_COMMAND = 0x12C
_REG_ALARM = 0x1C9


class ModbusService:
    """Stateful singleton Modbus service."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connected = False
        self._params: ModbusConnectionParamsSchema | None = None
        self._ok_count = 0
        self._error_count = 0
        self._last_success_at: datetime | None = None
        self._connection_error: str | None = None
        self._log: deque[ExchangeLogEntrySchema] = deque(maxlen=_MAX_LOG_ENTRIES)
        self._log_id = 0
        self._registers: dict[int, int] = dict(_DEFAULT_REGISTERS)
        self._registers_by_slave: dict[int, dict[int, int]] = {1: self._registers}
        self._left_slave_id = 1
        self._right_slave_id = 2
        self.left_zero_pulses: int | None = None
        self.right_zero_pulses: int | None = None
        self._torque_ready: dict[int, bool] = {}
        self._torque_command: dict[int, int] = {}
        self._manual_torque = False
        self._torque_limit: dict[int, int] = {}
        self._speed_limit_rpm: dict[int, int] = {}
        self._profiles: list[ParameterProfileSchema] = []
        self._profile_id_counter = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _next_log_id(self) -> int:
        self._log_id += 1
        return self._log_id

    def _append_log(self, entry: ExchangeLogEntrySchema) -> None:
        self._log.append(entry)

    def _log_info(self, action: str, message: str) -> None:
        self._append_log(ExchangeLogEntrySchema(
            id=self._next_log_id(),
            ts=self._now(),
            direction="INFO",
            action=action,
            result=message,
        ))

    def _is_signed_register(self, address: int) -> bool:
        signed_addresses = {
            0x015,  # rate feed-forward
            0x03F,  # manufacturer parameter with negative default
            0x052,  # zero drift correction
            0x0A5,  # mechanical origin offset
            0x1D4,  # analog input AI0
            0x203,
            0x204,
            0x209,
            0x20A,
        }
        signed_ranges = (
            (0x053, 0x056),
            (0x074, 0x077),
            (0x12C, 0x14B),
            (0x150, 0x16F),
            (0x1C0, 0x1C5),
        )

        if address in signed_addresses:
            return True

        return any(start <= address <= end for start, end in signed_ranges)

    def _normalize_register_value(self, address: int, value: int) -> int:
        if self._is_signed_register(address) and value >= 0x8000:
            return value - 0x10000
        return value

    def _select_slave(self, slave_id: int) -> None:
        """Select a separate simulated bank and the RTU address while holding the lock."""
        self._registers = self._registers_by_slave.setdefault(slave_id, {**_DEFAULT_REGISTERS, 0x000: slave_id})
        if hasattr(self, "_instr"):
            last_slave = getattr(self, "_bus_last_slave", None)
            if last_slave is not None and last_slave != slave_id:
                rest = _INTER_SLAVE_GAP_S - (time.monotonic() - getattr(self, "_bus_last_end", 0.0))
                if rest > 0:
                    time.sleep(rest)
            self._instr.address = slave_id

    def _bus_done(self, slave_id: int) -> None:
        self._bus_last_slave = slave_id
        self._bus_last_end = time.monotonic()

    def _simulate_read(self, address: int) -> tuple[int, str | None]:
        """Return (value, error_or_None) from the simulated register bank."""
        if address in self._registers:
            return self._normalize_register_value(address, self._registers[address]), None
        return 0, f"Unknown register 0x{address:03X}"

    def _simulate_write(self, address: int, value: int) -> str | None:
        """Write to simulated register bank, return error string or None."""
        if address == 0x1A7:
            # Service command – execute side effects
            if value == 0x0801:
                self._log_info("SAVE", "Parameters saved to EEPROM (simulated)")
            elif value == 0x0802:
                self._log_info("CLR_ALARM", "Alarm history cleared (simulated)")
            self._registers[address] = value
            return None
        self._registers[address] = value if self._is_signed_register(address) else value & 0xFFFF
        if address == _REG_TORQUE_COMMAND:
            # simulated drive follows the reference instantly
            self._registers[0x1C3] = value
            self._registers[0x1C4] = value
        return None

    # ------------------------------------------------------------------
    # Ports
    # ------------------------------------------------------------------

    def list_ports(self) -> list[SerialPortInfoSchema]:
        ports: list[SerialPortInfoSchema] = []
        try:
            import serial.tools.list_ports  # type: ignore[import-untyped]
            all_ports = list(serial.tools.list_ports.comports())
            # Prefer USB/ACM ports; omit bare ttyS* that have no real hardware ID
            usb_ports = [p for p in all_ports if p.hwid and p.hwid != "n/a"]
            fallback_ports = [
                p for p in all_ports
                if p not in usb_ports and not p.device.startswith("/dev/ttyS")
            ]
            for p in sorted(usb_ports + fallback_ports, key=lambda x: x.device):
                ports.append(SerialPortInfoSchema(
                    device=p.device,
                    description=p.description or "",
                    hardware_id=p.hwid or None,
                ))
        except ImportError:
            # pyserial not installed – fall back to scanning /dev on Linux
            import glob
            import sys
            if sys.platform.startswith("linux"):
                for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
                    for dev in sorted(glob.glob(pattern)):
                        ports.append(SerialPortInfoSchema(
                            device=dev,
                            description="USB Serial (install pyserial for details)",
                            hardware_id=None,
                        ))
        return ports

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(
        self, params: ModbusConnectionParamsSchema, *, initial_commands: dict[int, int] | None = None,
    ) -> ModbusConnectionStatusSchema:
        with self._lock:
            if params.slave_id == params.right_slave_id:
                return ModbusConnectionStatusSchema(connected=False, error_message="Адреса левого и правого приводов должны различаться")
            if self._connected:
                self._log_info("CONNECT", f"Already connected to {self._params.port if self._params else '?'}, reconnecting")
                self._connected = False
            if hasattr(self, "_instr"):
                try:
                    self._instr.serial.close()
                except Exception:  # noqa: BLE001
                    pass
                del self._instr

            self._params = params
            self._left_slave_id = params.slave_id
            self._right_slave_id = params.right_slave_id
            self.left_zero_pulses = None
            self.right_zero_pulses = None
            self._clear_torque_state()
            if hasattr(self, "_instr"):
                self._instr.address = self._left_slave_id

            self._connection_error = None
            is_sim = params.port == "SIM://"

            if is_sim:
                self._connected = True
                self._ok_count = 0
                self._error_count = 0
                self._last_success_at = self._now()
                self._log_info("CONNECT", f"Connected to {params.port} (simulation mode)")
                errors = self.initialize_torque_mode(initial_commands=initial_commands)
                if errors:
                    self._connection_error = "; ".join(errors)
                    self._log_info("SYNC_ERR", self._connection_error)
                return self._build_status(simulation_mode=True)

            try:
                import minimalmodbus  # type: ignore[import-untyped]
                instr = minimalmodbus.Instrument(params.port, params.slave_id)
                instr.serial.baudrate = params.baud_rate
                instr.serial.parity = params.parity
                instr.serial.stopbits = params.stop_bits
                instr.serial.bytesize = params.data_bits
                instr.serial.timeout = params.timeout_ms / 1000.0
                instr.read_register(0)
                self._instr = instr
                self._connected = True
                self._ok_count = 0
                self._error_count = 0
                self._last_success_at = self._now()
                self._log_info("CONNECT", f"Connected to {params.port} @ {params.baud_rate}")
                errors = self.initialize_torque_mode(initial_commands=initial_commands)
                if errors:
                    self._connection_error = "; ".join(errors)
                    self._log_info("SYNC_ERR", self._connection_error)
                return self._build_status(simulation_mode=False)
            except Exception as exc:  # noqa: BLE001
                self._connected = False
                self._connection_error = str(exc)
                self._error_count += 1
                self._log_info("CONNECT_ERR", str(exc))
                return ModbusConnectionStatusSchema(
                    connected=False,
                    port=params.port,
                    baud_rate=params.baud_rate,
                    slave_id=params.slave_id,
                    error_message=str(exc),
                    error_count=self._error_count,
                )

    def _clear_torque_state(self) -> None:
        self._bus_last_slave = None
        self._manual_torque = False
        self._torque_ready.clear()
        self._torque_command.clear()
        self._torque_limit.clear()
        self._speed_limit_rpm.clear()

    def disconnect(self, *, preserve_torque: bool = False) -> ModbusConnectionStatusSchema:
        with self._lock:
            if self._connected and not preserve_torque:
                # never leave a torque reference behind on the drives
                self.stop_all_torque()
            self._connected = False
            self.left_zero_pulses = None
            self.right_zero_pulses = None
            self._clear_torque_state()
            if hasattr(self, "_instr"):
                try:
                    self._instr.serial.close()
                except Exception:  # noqa: BLE001
                    pass
                del self._instr
            self._log_info("DISCONNECT", "Disconnected")
            return self._build_status()

    def get_status(self) -> ModbusConnectionStatusSchema:
        with self._lock:
            return self._build_status()

    def _build_status(self, simulation_mode: bool = False) -> ModbusConnectionStatusSchema:
        return ModbusConnectionStatusSchema(
            connected=self._connected,
            port=self._params.port if self._params else None,
            baud_rate=self._params.baud_rate if self._params else None,
            parity=self._params.parity if self._params else None,
            slave_id=self._params.slave_id if self._params else None,
            right_slave_id=self._right_slave_id if self._params else None,
            last_success_at=self._last_success_at,
            ok_count=self._ok_count,
            error_count=self._error_count,
            error_message=self._connection_error if not self._connected else None,
            simulation_mode=simulation_mode or (self._params is not None and self._params.port == "SIM://"),
        )

    def _real_serial_available(self) -> bool:
        try:
            import minimalmodbus  # type: ignore[import-untyped]  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            import serial  # type: ignore[import-untyped]  # noqa: F401
            return True
        except ImportError:
            pass
        return False

    # ------------------------------------------------------------------
    # Ping
    # ------------------------------------------------------------------

    def ping(self) -> ModbusReadResultSchema:
        with self._lock:
            return self._do_read(ModbusReadRequestSchema(address=0x000, count=1))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_registers(self, req: ModbusReadRequestSchema) -> ModbusReadResultSchema:
        # one RS-485 bus shared with the control loop: never interleave transactions
        with self._lock:
            return self._do_read(req)

    def _do_read(self, req: ModbusReadRequestSchema, *, log: bool = True) -> ModbusReadResultSchema:
        if not self._connected:
            return ModbusReadResultSchema(success=False, registers=[], error="Not connected")
        slave_id = req.slave_id or (self._params.slave_id if self._params else 1)
        self._select_slave(slave_id)
        raw_req = f"[{slave_id:02X}] READ 0x{req.address:03X} count={req.count}"
        t0 = time.monotonic()
        results: list[ModbusRegisterValueSchema] = []
        error: str | None = None
        is_sim = not hasattr(self, "_instr")
        if is_sim:
            for i in range(req.count):
                addr = req.address + i
                val, err = self._simulate_read(addr)
                results.append(ModbusRegisterValueSchema(
                    address=addr, address_hex=f"0x{addr:03X}", value=val, error=err, read_at=self._now(),
                ))
            raw_resp = "[SIM] " + " ".join(f"{(r.value & 0xFFFF):04X}" for r in results)
        else:
            try:
                raw_values: list[int] = []
                # A drive may miss the first frame after the bus was used by the other drive: retry once.
                attempts = 2 if getattr(self, "_bus_last_slave", slave_id) != slave_id else 1
                for attempt in range(1, attempts + 1):
                    try:
                        if req.count > 1:
                            raw_values = [int(v) & 0xFFFF for v in self._instr.read_registers(req.address, req.count)]  # type: ignore[attr-defined]
                        else:
                            val = self._instr.read_register(req.address, signed=self._is_signed_register(req.address))  # type: ignore[attr-defined]
                            raw_values = [val & 0xFFFF]
                        break
                    except Exception:  # noqa: BLE001
                        self._bus_done(slave_id)
                        if attempt == attempts:
                            raise
                for i, val in enumerate(raw_values):
                    addr = req.address + i
                    value = val if req.count > 1 else self._normalize_register_value(addr, val)
                    self._registers[addr] = val if req.count > 1 else value
                    results.append(ModbusRegisterValueSchema(
                        address=addr, address_hex=f"0x{addr:03X}", value=value, read_at=self._now(),
                    ))
                raw_resp = " ".join(f"{v:04X}" for v in raw_values)
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                raw_resp = None
            self._bus_done(slave_id)
        elapsed = (time.monotonic() - t0) * 1000
        if error:
            self._error_count += 1
            success = False
        else:
            self._ok_count += 1
            self._last_success_at = self._now()
            success = True
        if log or error:
            self._append_log(ExchangeLogEntrySchema(
                id=self._next_log_id(), ts=self._now(), direction="TX", slave_id=slave_id,
                action="READ", address=req.address, raw_request=raw_req, raw_response=raw_resp,
                error=error, elapsed_ms=elapsed,
            ))
        return ModbusReadResultSchema(
            success=success, registers=results, elapsed_ms=elapsed, error=error,
            raw_request=raw_req, raw_response=raw_resp,
        )

    def write_register(self, req: ModbusWriteRequestSchema) -> ModbusWriteResultSchema:
        with self._lock:
            if not self._connected:
                return ModbusWriteResultSchema(success=False, address=req.address, value=req.value, error="Not connected")
            slave_id = req.slave_id or (self._params.slave_id if self._params else 1)
            self._select_slave(slave_id)
            return self._write_register_locked(req.address, req.value, slave_id)

    def _write_register_locked(self, address: int, value: int, slave_id: int, *, log: bool = True) -> ModbusWriteResultSchema:
        self._select_slave(slave_id)
        raw_req = f"[{slave_id:02X}] WRITE 0x{address:03X} = {value} (0x{(value & 0xFFFF):04X})"
        t0 = time.monotonic()
        error: str | None = None
        signed = self._is_signed_register(address)
        if not hasattr(self, "_instr"):
            error = self._simulate_write(address, value)
            raw_resp = "[SIM] OK" if error is None else f"[SIM] ERR: {error}"
        else:
            try:
                self._instr.write_register(address, value, signed=signed)  # type: ignore[attr-defined]
                self._registers[address] = value if signed else value & 0xFFFF
                raw_resp = "ACK"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                raw_resp = f"ERR: {error}"
            self._bus_done(slave_id)
        elapsed = (time.monotonic() - t0) * 1000
        if error:
            self._error_count += 1
        else:
            self._ok_count += 1
            self._last_success_at = self._now()
        if log or error:
            self._append_log(ExchangeLogEntrySchema(
                id=self._next_log_id(), ts=self._now(), direction="TX", slave_id=slave_id,
                action="WRITE", address=address, value=value, raw_request=raw_req,
                raw_response=raw_resp, error=error, elapsed_ms=elapsed,
            ))
        return ModbusWriteResultSchema(
            success=error is None, address=address, value=value, elapsed_ms=elapsed,
            error=error, raw_request=raw_req, raw_response=raw_resp,
        )

    @staticmethod
    def _combine_position(low: int, high: int) -> int:
        combined = ((high & 0xFFFF) << 16) | (low & 0xFFFF)
        return combined - 0x1_0000_0000 if combined >= 0x8000_0000 else combined

    def _read_position(self, slave_id: int) -> tuple[int | None, str | None]:
        result = self._do_read(ModbusReadRequestSchema(address=0x1BC, count=2, slave_id=slave_id))
        if not result.success:
            return None, result.error or "Ошибка чтения"
        if len(result.registers) != 2 or any(reg.error for reg in result.registers):
            return None, next((reg.error for reg in result.registers if reg.error), "Неполный ответ")
        return self._combine_position(result.registers[0].value, result.registers[1].value), None

    def _positions_locked(self, capture_zero: bool = False) -> ModbusPositionsSchema:
        left_id, right_id = self._left_slave_id, self._right_slave_id
        left: int | None = None
        right: int | None = None
        left_error: str | None = None
        right_error: str | None = None
        if self._connected:
            left, left_error = self._read_position(left_id)
            right, right_error = self._read_position(right_id)
        if capture_zero and left is not None and right is not None:
            self.left_zero_pulses, self.right_zero_pulses = left, right
            self._log_info("ZERO", f"Software encoder zero captured for slaves {left_id} and {right_id}")
        zeroed = self.left_zero_pulses is not None and self.right_zero_pulses is not None
        left_mm = (left - self.left_zero_pulses) * _MM_PER_PULSE if left is not None and zeroed else None
        right_mm = (right - self.right_zero_pulses) * _MM_PER_PULSE if right is not None and zeroed else None
        return ModbusPositionsSchema(
            connected=self._connected, simulation_mode=self._params is not None and self._params.port == "SIM://", zeroed=zeroed,
            left_zero_pulses=self.left_zero_pulses, right_zero_pulses=self.right_zero_pulses,
            left_position_mm=left_mm, right_position_mm=right_mm,
            left=ModbusPositionSideSchema(slave_id=left_id, current_pulses=left, zero_pulses=self.left_zero_pulses, position_mm=left_mm),
            right=ModbusPositionSideSchema(slave_id=right_id, current_pulses=right, zero_pulses=self.right_zero_pulses, position_mm=right_mm),
            skew_mm=left_mm - right_mm if left_mm is not None and right_mm is not None else None,
            error="; ".join(part for part in (
                "Modbus не подключён" if not self._connected else None,
                f"Левый: {left_error}" if left_error else None,
                f"Правый: {right_error}" if right_error else None,
                "Нулевая позиция не задана" if not zeroed else None,
            ) if part) or None,
        )

    def get_positions(self) -> ModbusPositionsSchema:
        with self._lock:
            return self._positions_locked()

    def capture_zero(self) -> ModbusPositionsSchema:
        """Rebase both drives together, or leave the previous offsets untouched."""
        with self._lock:
            return self._positions_locked(capture_zero=True)

    def set_session_zero(self, left_pulses: int, right_pulses: int) -> ModbusPositionsSchema:
        """Restore a known software zero without moving the drives."""
        with self._lock:
            self.left_zero_pulses = left_pulses
            self.right_zero_pulses = right_pulses
            return self._positions_locked()

    def _read_single_locked(self, address: int, slave_id: int, *, log: bool = True) -> tuple[int | None, str | None]:
        result = self._do_read(ModbusReadRequestSchema(address=address, count=1, slave_id=slave_id), log=log)
        if not result.success or not result.registers or result.registers[0].error:
            return None, result.error or (result.registers[0].error if result.registers else "Нет ответа")
        return result.registers[0].value & 0xFFFF, None

    # ------------------------------------------------------------------
    # Torque mode (Lichuan A6, PA_002 = 2)
    #
    # Runtime control is a single signed register PA_12C (0.1 % of rated
    # torque, +-3000) with PA_093 = 0. PA_000, PA_002 and PA_090 are never
    # written, nothing is saved to EEPROM, and "stop" means PA_12C = 0
    # (the servo stays enabled).
    # ------------------------------------------------------------------

    @staticmethod
    def _s16(value: int) -> int:
        value &= 0xFFFF
        return value - 0x10000 if value >= 0x8000 else value

    def _torque_drive_ready(self, slave_id: int) -> str | None:
        if not self._connected:
            return "Modbus не подключён"
        if not self._torque_ready.get(slave_id):
            return "Привод не инициализирован в Torque Mode: сначала initialize_torque_mode()"
        return None

    def _read_init_register(self, address: int, slave_id: int, attempts: int = 3) -> tuple[int | None, str | None]:
        """Read during init; the first request to a drive after a bus switch may time out once."""
        value, error = self._read_single_locked(address, slave_id)
        for _ in range(attempts - 1):
            if value is not None:
                break
            value, error = self._read_single_locked(address, slave_id)
        return value, error

    def _init_torque_drive_locked(
        self, slave_id: int, *, torque_limit: int, speed_limit_rpm: int, initial_command: int = 0,
    ) -> str | None:
        """Verify Torque Mode without dropping restart support to zero."""
        self._torque_ready[slave_id] = False
        alarm, error = self._read_init_register(_REG_ALARM, slave_id)
        if alarm is None:
            return error or "Нет связи с приводом"
        if alarm:
            return f"Авария привода PA_1C9={alarm}"
        mode, error = self._read_init_register(_REG_CONTROL_MODE, slave_id)
        if mode is None:
            return error or "Нет ответа PA_002"
        if mode != 2:
            return f"PA_002={mode}, ожидается Torque Mode (2); параметр рантаймом не меняется"
        segment, error = self._read_init_register(_REG_TORQUE_SEGMENT, slave_id)
        if segment is None:
            return error or "Нет ответа PA_093"
        if segment != 0:
            written = self._write_register_locked(_REG_TORQUE_SEGMENT, 0, slave_id)
            if not written.success:
                return f"PA_093: {written.error}"
        for address, value, name in ((_REG_SPEED_LIMIT, speed_limit_rpm, "PA_056"), (_REG_TORQUE_LIMIT, torque_limit, "PA_05E")):
            written = self._write_register_locked(address, value, slave_id)
            if not written.success:
                return f"{name}: {written.error}"
        initial_command = max(-torque_limit, min(torque_limit, initial_command))
        referenced = self._write_register_locked(_REG_TORQUE_COMMAND, initial_command, slave_id)
        if not referenced.success:
            return f"PA_12C: {referenced.error}"
        telemetry = self._read_torque_telemetry_locked(slave_id)
        if telemetry.get("error"):
            return str(telemetry["error"])
        feedback = telemetry["feedback_position"]
        if slave_id == self._left_slave_id:
            self.left_zero_pulses = int(feedback)  # type: ignore[arg-type]
        elif slave_id == self._right_slave_id:
            self.right_zero_pulses = int(feedback)  # type: ignore[arg-type]
        self._torque_limit[slave_id] = torque_limit
        self._speed_limit_rpm[slave_id] = speed_limit_rpm
        self._torque_command[slave_id] = initial_command
        self._torque_ready[slave_id] = True
        self._log_info("TORQUE_INIT", f"slave {slave_id}: PA_002=2, PA_093=0, PA_12C={initial_command}, speed limit={speed_limit_rpm} rpm, torque limit={torque_limit}")
        return None

    def initialize_torque_mode(
        self,
        *,
        torque_limit: int = DEFAULT_TORQUE_LIMIT,
        speed_limit_rpm: int = DEFAULT_SPEED_LIMIT_RPM,
        initial_commands: dict[int, int] | None = None,
    ) -> list[str]:
        """Prepare both drives for PA_12C control. Returns per-drive error strings (empty = ready)."""
        if not 0 <= torque_limit <= 3000:
            raise ValueError("PA_05E должен быть в диапазоне 0..3000")
        if not 0 <= speed_limit_rpm <= 3000:
            raise ValueError("PA_056 должен быть в диапазоне 0..3000 rpm")
        with self._lock:
            if not self._connected:
                return ["Modbus не подключён"]
            return [
                f"ID{slave_id}: {error}"
                for slave_id in (self._left_slave_id, self._right_slave_id)
                if (error := self._init_torque_drive_locked(
                    slave_id, torque_limit=torque_limit, speed_limit_rpm=speed_limit_rpm,
                    initial_command=(initial_commands or {}).get(slave_id, 0),
                ))
            ]

    def torque_ready(self, slave_id: int) -> bool:
        with self._lock:
            return self._connected and bool(self._torque_ready.get(slave_id))

    def set_torque_command(self, slave_id: int, torque_raw: int, *, log: bool = True) -> str | None:
        """Write PA_12C (signed, 0.1 % of rated torque), clamped to the active torque limit. Runtime only."""
        with self._lock:
            error = self._torque_drive_ready(slave_id)
            if error:
                return error
            limit = self._torque_limit.get(slave_id, DEFAULT_TORQUE_LIMIT)
            value = max(-limit, min(limit, int(torque_raw)))
            result = self._write_register_locked(_REG_TORQUE_COMMAND, value, slave_id, log=log)
            if not result.success:
                return result.error
            self._torque_command[slave_id] = value
            return None

    def stop_torque(self, slave_id: int) -> str | None:
        """PA_12C = 0. Not Servo OFF. Allowed even when the drive was not initialised."""
        with self._lock:
            if not self._connected:
                return "Modbus не подключён"
            result = self._write_register_locked(_REG_TORQUE_COMMAND, 0, slave_id)
            if result.success:
                self._torque_command[slave_id] = 0
            return None if result.success else result.error

    def stop_all_torque(self) -> list[str]:
        with self._lock:
            return [
                f"ID{slave_id}: {error}"
                for slave_id in (self._left_slave_id, self._right_slave_id)
                if (error := self.stop_torque(slave_id))
            ]

    # Manual override: the debug panel owns PA_12C until it is stopped explicitly
    # (PA_12C = 0 button, re-initialisation, e-stop or disconnect); the motion adapter must not write it meanwhile.
    def begin_manual_torque(self) -> None:
        self._manual_torque = True

    def end_manual_torque(self) -> None:
        self._manual_torque = False

    def manual_torque_active(self) -> bool:
        return self._manual_torque

    def set_torque_limit(self, slave_id: int, limit: int, *, log: bool = True) -> str | None:
        """Runtime PA_05E write. Not saved to EEPROM."""
        if not 0 <= limit <= 3000:
            return "PA_05E должен быть в диапазоне 0..3000"
        with self._lock:
            result = self._write_register_locked(_REG_TORQUE_LIMIT, limit, slave_id, log=log)
            if result.success:
                self._torque_limit[slave_id] = limit
            return None if result.success else result.error

    def set_speed_limit_rpm(self, slave_id: int, rpm: int, *, log: bool = True) -> str | None:
        """Runtime PA_056 write (speed limit in Torque Mode). Not saved to EEPROM."""
        if not 0 <= rpm <= 3000:
            return "PA_056 должен быть в диапазоне 0..3000 rpm"
        with self._lock:
            result = self._write_register_locked(_REG_SPEED_LIMIT, rpm, slave_id, log=log)
            if result.success:
                self._speed_limit_rpm[slave_id] = rpm
            return None if result.success else result.error

    def _read_torque_telemetry_locked(self, slave_id: int, *, extended: bool = False, log: bool = True) -> dict[str, int | float | str | None]:
        # PA_1BC..PA_1C9 in one transaction: position, position error, speeds, torques, alarm
        block = self._do_read(ModbusReadRequestSchema(address=0x1BC, count=14, slave_id=slave_id), log=log)
        if not block.success or len(block.registers) != 14:
            return {"error": block.error or "Неполный мониторинг"}
        words = [reg.value & 0xFFFF for reg in block.registers]
        offset = self.left_zero_pulses if slave_id == self._left_slave_id else self.right_zero_pulses if slave_id == self._right_slave_id else None
        feedback = self._combine_position(words[0], words[1])
        data: dict[str, int | float | str | None] = {
            "feedback_position": feedback,
            "position_mm": None if offset is None else (feedback - offset) * _MM_PER_PULSE,
            "position_error": self._combine_position(words[2], words[3]),
            "command_speed_rpm": self._s16(words[4]),
            "feedback_speed_rpm": self._s16(words[5]),
            "command_torque_raw": self._s16(words[7]),
            "feedback_torque_raw": self._s16(words[8]),
            "alarm": words[13],
            "torque_written_raw": self._torque_command.get(slave_id),
            "torque_limit_raw": self._torque_limit.get(slave_id),
            "speed_limit_rpm": self._speed_limit_rpm.get(slave_id),
            "status_pa1db": None,
            "reason_pa1de": None,
            "error": None,
        }
        if extended:
            status = self._do_read(ModbusReadRequestSchema(address=0x1DB, count=4, slave_id=slave_id), log=log)
            if status.success and len(status.registers) == 4:
                data["status_pa1db"] = status.registers[0].value & 0xFFFF
                data["reason_pa1de"] = status.registers[3].value & 0xFFFF
        return data

    def read_torque_telemetry(self, slave_id: int, *, extended: bool = False, log: bool = True) -> dict[str, int | float | str | None]:
        """Monitoring in one read: PA_1BC/1BD position, PA_1C1 speed, PA_1C3/1C4 torque, alarm; PA_1DB/1DE optionally."""
        with self._lock:
            if not self._connected:
                return {"error": "Modbus не подключён"}
            return self._read_torque_telemetry_locked(slave_id, extended=extended, log=log)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self, slave_id: int | None = None) -> DriverDiagnosticsSchema:
        with self._lock:
            if not self._connected:
                return DriverDiagnosticsSchema(responding=False, status_summary="Not connected")
            self._select_slave(slave_id or (self._params.slave_id if self._params else 1))

            def _r(addr: int) -> int | None:
                val, err = (self._simulate_read(addr) if not hasattr(self, "_instr") else self._real_read(addr))
                return val if err is None else None

            slave_id_val = _r(0x000)
            baud_rate_val = _r(0x00D)
            control_mode_val = _r(0x002)
            extended_mode_val = _r(0x090)
            alarm_code_val = _r(0x1C9)
            if alarm_code_val is None:
                alarm_code_val = _r(0x200)

            responding = slave_id_val is not None
            has_alarm = bool(alarm_code_val)
            motion_safe = responding and not has_alarm and extended_mode_val == 1

            summary_parts: list[str] = []
            if not responding:
                summary_parts.append("Драйвер не отвечает")
            else:
                summary_parts.append("Связь есть")
                if has_alarm:
                    summary_parts.append(f"Активная ошибка: {alarm_code_val:#06x}")
                if extended_mode_val != 1:
                    summary_parts.append("Расширенный режим выключен")

            return DriverDiagnosticsSchema(
                responding=responding,
                slave_id=slave_id_val,
                baud_rate_code=baud_rate_val,
                control_mode=control_mode_val,
                extended_mode=extended_mode_val,
                alarm_code=alarm_code_val,
                has_alarm=has_alarm,
                motion_safe=motion_safe,
                status_summary="; ".join(summary_parts),
                checked_at=self._now(),
            )

    def _real_read(self, addr: int) -> tuple[int | None, str | None]:
        try:
            val = self._instr.read_register(addr, signed=self._is_signed_register(addr))  # type: ignore[attr-defined]
            return val, None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def execute_command(self, req: ModbusCommandRequestSchema) -> ModbusCommandResultSchema:
        dangerous = {"servo_on", "emergency_stop", "pos_load", "jog_start", "homing", "save_parameters", "clear_alarm_history"}
        if req.command in dangerous and not req.confirmed:
            return ModbusCommandResultSchema(
                success=False,
                command=req.command,
                error="Confirmation required for this operation",
            )

        with self._lock:
            if not self._connected:
                return ModbusCommandResultSchema(success=False, command=req.command, error="Not connected")

            if hasattr(self, "_instr") and req.command not in {"save_parameters", "clear_alarm_history"}:
                return ModbusCommandResultSchema(
                    success=False, command=req.command,
                    error="Команда для реального привода не реализована: управляющий регистр не подтверждён",
                )

            slave_id = self._params.slave_id if self._params else 1
            slave_id = req.slave_id or slave_id
            self._select_slave(slave_id)

            if req.command == "save_parameters":
                result = self._write_register_locked(0x1A7, 0x0801, slave_id)
                if not result.success:
                    return ModbusCommandResultSchema(success=False, command=req.command, error=result.error)
                self._log_info("CMD:save_parameters", "Parameters saved to EEPROM")
                return ModbusCommandResultSchema(success=True, command=req.command, message="OK")

            if req.command == "clear_alarm_history":
                result = self._write_register_locked(0x1A7, 0x0802, slave_id)
                if not result.success:
                    return ModbusCommandResultSchema(success=False, command=req.command, error=result.error)
                self._log_info("CMD:clear_alarm_history", "Alarm history cleared")
                return ModbusCommandResultSchema(success=True, command=req.command, message="OK")

            cmd_map: dict[str, Any] = {
                "servo_on": lambda: self._set_di_bit(0, True),
                "servo_off": lambda: self._set_di_bit(0, False),
                "alarm_reset": lambda: self._set_di_bit(1, True),
                "emergency_stop": lambda: self._set_di_bit(4, True),
                "pos_load": lambda: self._set_di_bit(5, True),
                "jog_start": lambda: self._set_di_bit(6, True),
                "jog_stop": lambda: self._set_di_bit(6, False),
                "homing": lambda: self._set_di_bit(7, True),
            }
            fn = cmd_map.get(req.command)
            if fn is None:
                return ModbusCommandResultSchema(success=False, command=req.command, error=f"Unknown command: {req.command}")
            fn()
            self._log_info(f"CMD:{req.command}", f"Command executed (params={req.params})")
            return ModbusCommandResultSchema(success=True, command=req.command, message="OK")

    def _set_di_bit(self, bit: int, value: bool) -> None:
        current = self._registers.get(0x201, 0)
        if value:
            self._registers[0x201] = current | (1 << bit)
        else:
            self._registers[0x201] = current & ~(1 << bit)

    def get_log(self, limit: int = 200, direction: str | None = None, action: str | None = None) -> ExchangeLogResponseSchema:
        with self._lock:
            entries = list(self._log)
        if direction:
            entries = [e for e in entries if e.direction == direction.upper()]
        if action:
            entries = [e for e in entries if action.upper() in e.action.upper()]
        total = len(entries)
        entries = entries[-limit:]
        return ExchangeLogResponseSchema(entries=list(reversed(entries)), total=total)

    def clear_log(self) -> None:
        with self._lock:
            self._log.clear()
            self._log_id = 0

    def save_profile(self, req: ProfileSaveRequestSchema) -> ParameterProfileSchema:
        with self._lock:
            self._profile_id_counter += 1
            addresses = req.addresses if req.addresses is not None else list(self._registers.keys())
            params = [
                ParameterValueSchema(address=addr, name=f"0x{addr:03X}", value=self._registers.get(addr, 0))
                for addr in addresses
                if addr in self._registers
            ]
            profile = ParameterProfileSchema(
                id=str(self._profile_id_counter),
                name=req.name,
                comment=req.comment,
                parameters=params,
                created_at=self._now(),
            )
            self._profiles.append(profile)
            return profile

    def list_profiles(self) -> list[ParameterProfileSchema]:
        with self._lock:
            return list(self._profiles)

    def compare_profile(self, profile_id: str) -> ProfileCompareResultSchema:
        with self._lock:
            profile = next((p for p in self._profiles if p.id == profile_id), None)
            if profile is None:
                return ProfileCompareResultSchema(differences=[], matching=0, differing=0)
            diffs: list[dict] = []
            matching = 0
            for pv in profile.parameters:
                driver_val = self._registers.get(pv.address)
                if driver_val is None:
                    continue
                if driver_val == pv.value:
                    matching += 1
                else:
                    diffs.append({
                        "address": pv.address,
                        "address_hex": f"0x{pv.address:03X}",
                        "name": pv.name,
                        "driver_value": driver_val,
                        "profile_value": pv.value,
                    })
            return ProfileCompareResultSchema(differences=diffs, matching=matching, differing=len(diffs))


modbus_service = ModbusService()
