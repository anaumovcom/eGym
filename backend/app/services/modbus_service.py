"""
Modbus RTU service for Lichuan A6 servo driver.

In development / emulator mode this service maintains a simulated register
bank that behaves like a real A6 driver. When a real serial port is available
and pyserial / minimalmodbus is installed it delegates to the real bus.
"""
from __future__ import annotations

import time
import threading
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
    # PA_002 – control mode: 0=Position, 1=Speed, 2=Torque, 3=CANopen
    0x002: 0,
    # PA_003 – rotation direction
    0x003: 0,
    # PA_00D – RS485 baud rate code: 0=2400, 1=4800, 2=9600, 3=19200, 4=38400, 5=57600, 6=115200
    0x00D: 3,
    # PA_090 – extended/communication mode: 0=standard, 1=extended
    0x090: 1,
    # PA_091 – active position segment index (0–15)
    0x091: 0,
    # PA_092 – active speed segment index (0–31)
    0x092: 0,
    # PA_093 – active torque segment index (0–31)
    0x093: 0,
    # PA_05E – first torque limit (%)
    0x05E: 2500,
    # PA_05F – second torque limit (%)
    0x05F: 2500,
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
}

# Position segments PA_168–PA_187 (low) and PA_188–PA_1A7-range (high)
# Each segment has 2 registers: low word and high word
for _i in range(16):
    _DEFAULT_REGISTERS[0x168 + _i * 2] = 0       # low
    _DEFAULT_REGISTERS[0x168 + _i * 2 + 1] = 0   # high

# Speed registers for internal position segments PA_190–PA_19F
for _i in range(16):
    _DEFAULT_REGISTERS[0x190 + _i] = 500  # default 500 rpm

# Speed segments PA_150–PA_16F
for _i in range(32):
    _DEFAULT_REGISTERS[0x150 + _i] = 0

# Torque segments PA_12C–PA_14B
for _i in range(32):
    _DEFAULT_REGISTERS[0x12C + _i] = 0

_MAX_LOG_ENTRIES = 500


class ModbusService:
    """Stateful singleton Modbus service."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connected = False
        self._params: ModbusConnectionParamsSchema | None = None
        self._ok_count = 0
        self._error_count = 0
        self._last_success_at: datetime | None = None
        self._log: deque[ExchangeLogEntrySchema] = deque(maxlen=_MAX_LOG_ENTRIES)
        self._log_id = 0
        self._registers: dict[int, int] = dict(_DEFAULT_REGISTERS)
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
        ports.append(SerialPortInfoSchema(device="SIM://", description="Simulation (no hardware)", hardware_id=None))
        return ports

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, params: ModbusConnectionParamsSchema) -> ModbusConnectionStatusSchema:
        with self._lock:
            if self._connected:
                self._log_info("CONNECT", f"Already connected to {self._params.port if self._params else '?'}, reconnecting")
                self._connected = False

            self._params = params
            is_sim = params.port == "SIM://" or not self._real_serial_available()

            if is_sim:
                self._connected = True
                self._ok_count = 0
                self._error_count = 0
                self._last_success_at = self._now()
                self._log_info("CONNECT", f"Connected to {params.port} (simulation mode)")
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
                return self._build_status(simulation_mode=False)
            except Exception as exc:  # noqa: BLE001
                self._connected = False
                self._error_count += 1
                self._log_info("CONNECT_ERR", str(exc))
                return ModbusConnectionStatusSchema(
                    connected=False,
                    error_message=str(exc),
                    error_count=self._error_count,
                )

    def disconnect(self) -> ModbusConnectionStatusSchema:
        with self._lock:
            self._connected = False
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
            last_success_at=self._last_success_at,
            ok_count=self._ok_count,
            error_count=self._error_count,
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
        return self._do_read(ModbusReadRequestSchema(address=0x000, count=1))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_registers(self, req: ModbusReadRequestSchema) -> ModbusReadResultSchema:
        return self._do_read(req)

    def _do_read(self, req: ModbusReadRequestSchema) -> ModbusReadResultSchema:
        with self._lock:
            if not self._connected:
                return ModbusReadResultSchema(
                    success=False,
                    registers=[],
                    error="Not connected",
                )

            slave_id = req.slave_id or (self._params.slave_id if self._params else 1)
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
                        address=addr,
                        address_hex=f"0x{addr:03X}",
                        value=val,
                        error=err,
                        read_at=self._now(),
                    ))
                raw_resp = "[SIM] " + " ".join(f"{(r.value & 0xFFFF):04X}" for r in results)
            else:
                try:
                    raw_values: list[int] = []
                    for i in range(req.count):
                        addr = req.address + i
                        val = self._instr.read_register(  # type: ignore[attr-defined]
                            addr,
                            signed=self._is_signed_register(addr),
                        )
                        raw_values.append(val)
                        self._registers[addr] = val
                        results.append(ModbusRegisterValueSchema(
                            address=addr,
                            address_hex=f"0x{addr:03X}",
                            value=val,
                            read_at=self._now(),
                        ))
                    raw_resp = " ".join(f"{(v & 0xFFFF):04X}" for v in raw_values)
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                    raw_resp = None

            elapsed = (time.monotonic() - t0) * 1000

            if error:
                self._error_count += 1
                success = False
            else:
                self._ok_count += 1
                self._last_success_at = self._now()
                success = True

            self._append_log(ExchangeLogEntrySchema(
                id=self._next_log_id(),
                ts=self._now(),
                direction="TX",
                slave_id=slave_id,
                action="READ",
                address=req.address,
                raw_request=raw_req,
                raw_response=raw_resp,
                error=error,
                elapsed_ms=elapsed,
            ))

            return ModbusReadResultSchema(
                success=success,
                registers=results,
                elapsed_ms=elapsed,
                error=error,
                raw_request=raw_req,
                raw_response=raw_resp,
            )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write_register(self, req: ModbusWriteRequestSchema) -> ModbusWriteResultSchema:
        with self._lock:
            if not self._connected:
                return ModbusWriteResultSchema(success=False, address=req.address, value=req.value, error="Not connected")

            slave_id = req.slave_id or (self._params.slave_id if self._params else 1)
            return self._write_register_locked(req.address, req.value, slave_id)

    def _write_register_locked(self, address: int, value: int, slave_id: int) -> ModbusWriteResultSchema:
        raw_req = f"[{slave_id:02X}] WRITE 0x{address:03X} = {value} (0x{(value & 0xFFFF):04X})"
        t0 = time.monotonic()
        error: str | None = None
        signed = self._is_signed_register(address)

        is_sim = not hasattr(self, "_instr")
        if is_sim:
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

        elapsed = (time.monotonic() - t0) * 1000

        if error:
            self._error_count += 1
        else:
            self._ok_count += 1
            self._last_success_at = self._now()

        self._append_log(ExchangeLogEntrySchema(
            id=self._next_log_id(),
            ts=self._now(),
            direction="TX",
            slave_id=slave_id,
            action="WRITE",
            address=address,
            value=value,
            raw_request=raw_req,
            raw_response=raw_resp,
            error=error,
            elapsed_ms=elapsed,
        ))

        return ModbusWriteResultSchema(
            success=error is None,
            address=address,
            value=value,
            elapsed_ms=elapsed,
            error=error,
            raw_request=raw_req,
            raw_response=raw_resp,
        )

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> DriverDiagnosticsSchema:
        with self._lock:
            if not self._connected:
                return DriverDiagnosticsSchema(responding=False, status_summary="Not connected")

            # Read key registers
            def _r(addr: int) -> int | None:
                val, err = (self._simulate_read(addr) if not hasattr(self, "_instr") else self._real_read(addr))
                return val if err is None else None

            slave_id_val = _r(0x000)
            baud_rate_val = _r(0x00D)
            control_mode_val = _r(0x002)
            extended_mode_val = _r(0x090)
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

            slave_id = self._params.slave_id if self._params else 1

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
                "servo_on":           lambda: self._set_di_bit(0, True),
                "servo_off":          lambda: self._set_di_bit(0, False),
                "alarm_reset":        lambda: self._set_di_bit(1, True),
                "emergency_stop":     lambda: self._set_di_bit(4, True),
                "pos_load":           lambda: self._set_di_bit(5, True),
                "jog_start":          lambda: self._set_di_bit(6, True),
                "jog_stop":           lambda: self._set_di_bit(6, False),
                "homing":             lambda: self._set_di_bit(7, True),
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

    # ------------------------------------------------------------------
    # Exchange log
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

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
