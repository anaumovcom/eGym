"""
Modbus RTU service for Lichuan A6 servo driver.

In development / emulator mode this service maintains a simulated register
bank that behaves like a real A6 driver. When a real serial port is available
and pyserial / minimalmodbus is installed it delegates to the real bus.
"""
from __future__ import annotations

import time
import threading
import math
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
    ModbusPositionsSchema,
    PositionCalibrationCaptureSchema,
    PositionCalibrationSchema,
    PositionExerciseSchema,
    PositionMotionStatusSchema,
    WeightlessPositionSchema,
    ModbusPositionSideSchema,
    ModbusReadinessSchema,
    ModbusReadRequestSchema,
    ModbusReadResultSchema,
    SoftwareStopResultSchema,
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
    # PA_002 – control mode: 0=Position, 1=Speed, 2=Torque
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
    # PA_1BC / PA_1BD – actual position feedback, low/high words
    0x1BC: 0,
    0x1BD: 0,
    # Simulation-only feedback/status (real mapping must be verified before use).
    0x1BE: 0, 0x1BF: 0, 0x1C0: 0, 0x1C1: 0,
    0x1C3: 0, 0x1C4: 0, 0x1C5: 0, 0x1C8: 0,
    0x1C9: 0, 0x1CE: 0, 0x1D0: 0, 0x1D1: 0,
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
MM_PER_PULSE = 0.0032  # SFE 32-32: 32 mm / 10000 encoder counts
PULSES_PER_MM = 312.5
STOP_TARGET_MM = 2000
STOP_TORQUE_LIMIT = 300
STOP_SPEED_RPM = 30  # commissioning value; verify on unloaded simulator before hardware use
MAX_SKEW_MM = 3
MAX_POSITION_ERROR_MM = 10
MODBUS_TIMEOUT_SECONDS = 0.3


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
        self._profiles: list[ParameterProfileSchema] = []
        self._profile_id_counter = 0
        self._motion_state = "idle"
        self._motion_target_type: str | None = None
        self._motion_target_mm: float | None = None
        self._motion_torque_limit: int | None = None
        self._motion_speed_rpm: int | None = None
        self._motion_min_mm = 0.0
        self._motion_max_mm = 2000.0
        self._motion_error: str | None = None
        self._weightless_threshold: int | None = None
        self._zero_generation = 0
        self._position_calibrations: dict[str, PositionCalibrationSchema] = {}
        self._stall_since: float | None = None
        self._previous_positions: tuple[float, float] | None = None

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
        if 0x168 <= address <= 0x187:
            return False  # 32-bit position is split into unsigned 16-bit words
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
            self._instr.address = slave_id

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
        return ports

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, params: ModbusConnectionParamsSchema) -> ModbusConnectionStatusSchema:
        with self._lock:
            if self is modbus_service:
                from app.services.hardware_runtime import hardware_runtime
                if hardware_runtime.controller.state.mode.value not in {"idle", "parked"}:
                    return ModbusConnectionStatusSchema(
                        connected=self._connected,
                        error_message="Нельзя подключать Modbus Position mode во время работы другого контроллера",
                    )
            if self._motion_state in {"exercise", "raising", "weightless", "holding"}:
                return ModbusConnectionStatusSchema(connected=self._connected, error_message="Сначала завершите движение; отсоединение при нагрузке опасно")
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
            self._position_calibrations.clear()
            self._reset_motion()
            self._connection_error = None
            is_sim = params.port == "SIM://"

            if is_sim:
                self._connected = True
                self._ok_count = 0
                self._error_count = 0
                self._last_success_at = self._now()
                self._log_info("CONNECT", f"Connected to {params.port} (simulation mode)")
                self._positions_locked(capture_zero=True)
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
                # A failed read of either encoder leaves the origin unset.
                self._positions_locked(capture_zero=True)
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

    def disconnect(self) -> ModbusConnectionStatusSchema:
        with self._lock:
            if self._motion_state in {"exercise", "raising", "weightless", "holding"}:
                raise ValueError("Нельзя отключать Modbus во время движения без аппаратной защиты")
            self._connected = False
            self._reset_motion()
            self.left_zero_pulses = None
            self.right_zero_pulses = None
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
            left_direction=self._params.left_direction if self._params else 1,
            right_direction=self._params.right_direction if self._params else 1,
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
        return self._do_read(ModbusReadRequestSchema(address=0x000, count=1))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_registers(self, req: ModbusReadRequestSchema) -> ModbusReadResultSchema:
        return self._do_read(req)

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
        # This read proves two responses, not the readiness of brakes, STO or
        # servo disable. Never infer torque/motion safety from register access.
        encoder_ready = left is not None and right is not None
        communication_ready = encoder_ready
        if self._connected and not encoder_ready:
            # An encoder read can fail while both slaves still answer a basic
            # status request. Do not conflate link readiness with encoder data.
            communication_ready = all(
                self._do_read(ModbusReadRequestSchema(address=0, slave_id=slave_id)).success
                for slave_id in (left_id, right_id)
            )
        readiness = ModbusReadinessSchema(
            communication_ready=communication_ready,
            encoder_ready=encoder_ready,
            allow_encoder_read=self._connected,
            allow_status_read=self._connected,
            allow_zero_offset=encoder_ready,
        )
        if capture_zero and self._motion_state in {"exercise", "raising", "weightless", "holding"}:
            raise ValueError("Нельзя менять программный ноль во время движения")
        if capture_zero and left is not None and right is not None:
            self.left_zero_pulses, self.right_zero_pulses = left, right
            self._zero_generation += 1
            self._position_calibrations.clear()
            self._log_info("ZERO", f"Software encoder zero captured for slaves {left_id} and {right_id}")
        zeroed = self.left_zero_pulses is not None and self.right_zero_pulses is not None
        left_dir = self._params.left_direction if self._params else 1
        right_dir = self._params.right_direction if self._params else 1
        left_mm = (left - self.left_zero_pulses) * MM_PER_PULSE * left_dir if left is not None and zeroed else None
        right_mm = (right - self.right_zero_pulses) * MM_PER_PULSE * right_dir if right is not None and zeroed else None
        return ModbusPositionsSchema(
            connected=self._connected, simulation_mode=self._params is not None and self._params.port == "SIM://", zeroed=zeroed,
            zero_generation=self._zero_generation,
            readiness=readiness,
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

    def get_position_calibration(self, exercise_key: str) -> PositionCalibrationSchema | None:
        with self._lock:
            calibration = self._position_calibrations.get(exercise_key)
            return calibration if calibration and calibration.zero_generation == self._zero_generation else None

    def capture_position_point(self, req: PositionCalibrationCaptureSchema) -> PositionCalibrationSchema:
        with self._lock:
            self._assert_simulated_motion()
            if self._motion_state not in {"idle", "weightless", "holding"}:
                raise ValueError("Фиксация точки недоступна во время движения или после ошибки")
            positions = self._positions_locked()
            left, right = positions.left.position_mm, positions.right.position_mm
            if left is None or right is None or not 0 <= left <= STOP_TARGET_MM or not 0 <= right <= STOP_TARGET_MM:
                raise ValueError("Нет позиций обоих приводов внутри программных границ")
            if abs(left - right) > MAX_SKEW_MM:
                raise ValueError("Перекос превышает 3 мм")
            value = round((left + right) / 2, 3)
            previous = self.get_position_calibration(req.exercise_key)
            data = previous.model_dump() if previous else {"exercise_key": req.exercise_key, "zero_generation": self._zero_generation}
            data[f"{req.point}_mm"] = value
            calibration = PositionCalibrationSchema(**data)
            self._position_calibrations[req.exercise_key] = calibration
            return calibration

    def _reset_motion(self) -> None:
        self._motion_state = "idle"
        self._motion_target_type = None
        self._motion_target_mm = None
        self._motion_torque_limit = None
        self._motion_speed_rpm = None
        self._motion_error = None
        self._weightless_threshold = None
        self._stall_since = None
        self._previous_positions = None

    @property
    def motion_active(self) -> bool:
        with self._lock:
            return self._motion_state in {"exercise", "raising", "weightless", "holding"}

    def _motion_fault(self, reason: str) -> None:
        self._motion_state = "fault"
        self._motion_error = reason
        self._log_info("POSITION_FAULT", reason)
        # Simulator only: hold each drive's present position without releasing
        # Servo-ON. A Modbus failure makes even this best-effort; real motion is
        # blocked until a drive-side watchdog and physical safety path exist.
        if not self._connected or self._params is None or self._params.port != "SIM://":
            return
        for sid in (self._left_slave_id, self._right_slave_id):
            pulses, error = self._read_position(sid)
            if error or pulses is None:
                self._log_info("POSITION_HOLD_FAILED", f"ID {sid}: {error}")
                continue
            raw = pulses & 0xFFFFFFFF
            self._select_slave(sid)
            self._simulate_write(0x168, raw & 0xFFFF)
            self._simulate_write(0x169, raw >> 16)
            self._set_di_bit(5, False)
            self._set_di_bit(5, True)
            self._set_di_bit(5, False)
            self._log_info("POSITION_HOLD", f"ID {sid}: simulated hold at {pulses} pulses")

    def _read_motion_register(self, address: int, slave_id: int) -> int:
        result = self._do_read(ModbusReadRequestSchema(address=address, slave_id=slave_id))
        if not result.success or len(result.registers) != 1 or result.registers[0].error:
            raise ValueError(f"Modbus ID {slave_id}, 0x{address:03X}: {result.error or 'нет данных'}")
        if (result.elapsed_ms or 0) > MODBUS_TIMEOUT_SECONDS * 1000:
            raise ValueError(f"Таймаут Modbus ID {slave_id}")
        return result.registers[0].value

    def _verified_motion_write(self, address: int, value: int, slave_id: int) -> None:
        result = self.write_register(ModbusWriteRequestSchema(address=address, value=value, slave_id=slave_id))
        if not result.success or (self._read_motion_register(address, slave_id) & 0xFFFF) != (value & 0xFFFF):
            raise ValueError(f"Не подтверждена запись ID {slave_id}, 0x{address:03X}")

    def _assert_simulated_motion(self) -> None:
        if not self._connected or self._params is None:
            raise ValueError("Modbus не подключён")
        if self._params.port != "SIM://" or hasattr(self, "_instr"):
            raise PermissionError("E-CTRL-UNAVAILABLE: POS_LOAD, DI и аппаратный контур защиты Lichuan A6 не проверены; реальное движение заблокировано")

    def _start_position(self, target_mm: float, torque_limit: int, speed_rpm: int,
                        target_type: str, min_mm: float, max_mm: float) -> PositionMotionStatusSchema:
        self._assert_simulated_motion()
        if self._motion_state == "fault":
            raise ValueError("Сначала устраните ошибку и переподключите симулятор")
        if not all(math.isfinite(v) for v in (target_mm, min_mm, max_mm)) or min_mm >= max_mm:
            raise ValueError("Недопустимые программные границы")
        if not min_mm <= target_mm <= max_mm:
            raise ValueError("Цель вне программных min/max")
        if not 1 <= torque_limit <= 3000 or not 1 <= speed_rpm <= 3000:
            raise ValueError("Недопустимый лимит момента или скорость")
        if (self._motion_state in {"exercise", "raising", "weightless", "holding"} and self._motion_target_mm == target_mm
                and self._motion_target_type == target_type and self._motion_speed_rpm == speed_rpm
                and self._motion_min_mm == min_mm and self._motion_max_mm == max_mm):
            status = self.position_motion_status()
            if status.state == "fault":
                raise ValueError(status.error or "Ошибка мониторинга")
            return self.update_position_limit(torque_limit) if self._motion_torque_limit != torque_limit else status
        positions = self._positions_locked()
        if not positions.zeroed or positions.left.position_mm is None or positions.right.position_mm is None:
            raise ValueError("Нет программного нуля обоих приводов")
        if positions.skew_mm is None or abs(positions.skew_mm) > MAX_SKEW_MM:
            raise ValueError("Перекос между приводами превышает 3 мм")
        if any(not min_mm <= p <= max_mm for p in (positions.left.position_mm, positions.right.position_mm)):
            raise ValueError("Текущая позиция вне программных min/max")
        ids = (self._left_slave_id, self._right_slave_id)
        for sid in ids:
            if self._read_motion_register(0x200, sid) or self._read_motion_register(0x1C9, sid):
                raise ValueError(f"Ошибка драйвера ID {sid}")
            if self._read_motion_register(0x002, sid) != 0 or self._read_motion_register(0x090, sid) != 1:
                raise ValueError(f"ID {sid}: требуются Position mode (PA_002=0) и extended control (PA_090=1)")

        # Prepare BOTH sides before POS_LOAD; never send torque command (PA_20A).
        try:
            for side, sid in (("left", ids[0]), ("right", ids[1])):
                self._verified_motion_write(0x05E, torque_limit, sid)
                self._verified_motion_write(0x05F, torque_limit, sid)
                origin = getattr(positions, side).zero_pulses
                direction = self._params.left_direction if side == "left" else self._params.right_direction
                assert origin is not None
                target_pulses = origin + direction * round(target_mm * PULSES_PER_MM)
                if not -(2**31) <= target_pulses < 2**31:
                    raise ValueError("Цель не помещается в 32-битный счётчик")
                raw = target_pulses & 0xFFFFFFFF
                self._verified_motion_write(0x168, raw & 0xFFFF, sid)
                self._verified_motion_write(0x169, raw >> 16, sid)
                self._verified_motion_write(0x190, speed_rpm, sid)
                self._verified_motion_write(0x091, 0, sid)
            for sid in ids:
                cmd = self.execute_command(ModbusCommandRequestSchema(command="servo_on", confirmed=True, slave_id=sid))
                if not cmd.success or not self._read_motion_register(0x201, sid) & 1:
                    raise ValueError(f"Servo-ON ID {sid} не подтверждён")
            for sid in ids:
                # Edge, not a permanently high bit; subsequent goals must trigger again.
                self._select_slave(sid)
                self._set_di_bit(5, False)
                cmd = self.execute_command(ModbusCommandRequestSchema(command="pos_load", confirmed=True, slave_id=sid))
                if not cmd.success:
                    raise ValueError(f"POS_LOAD ID {sid} не подтверждён")
                self._set_di_bit(5, False)
        except (ValueError, PermissionError) as exc:
            self._motion_fault(str(exc))
            raise
        self._motion_state = {"stop_raise": "raising", "weightless": "weightless", "hold": "holding"}.get(target_type, "exercise")
        self._motion_target_type = target_type
        self._motion_target_mm = target_mm
        self._motion_torque_limit = torque_limit
        self._motion_speed_rpm = speed_rpm
        self._motion_min_mm, self._motion_max_mm = min_mm, max_mm
        self._stall_since = None
        self._previous_positions = None
        return self.position_motion_status()

    def start_position_exercise(self, request: PositionExerciseSchema) -> PositionMotionStatusSchema:
        with self._lock:
            if self._motion_state == "weightless":
                raise ValueError("Сначала удержите гриф и завершите калибровку")
            target = request.lower_boundary_mm if request.target_type == "lower_boundary" else request.fixed_position_mm
            if target is None:
                raise ValueError("Целевая позиция упражнения не задана")
            if request.exercise_key:
                calibration = self.get_position_calibration(request.exercise_key)
                if calibration is None:
                    raise ValueError("Нет калибровки упражнения для текущего программного нуля")
                if request.target_type == "lower_boundary":
                    if calibration.lower_mm is None or calibration.upper_mm is None or calibration.upper_mm <= calibration.lower_mm:
                        raise ValueError("Зафиксируйте нижнюю и верхнюю точки амплитуды")
                    if target != calibration.lower_mm or calibration.upper_mm > request.max_mm:
                        raise ValueError("Цель/границы не совпадают с калибровкой")
                elif calibration.fixed_mm is None or target != calibration.fixed_mm:
                    raise ValueError("Фиксированная цель не совпадает с калибровкой")
            return self._start_position(target, request.torque_limit, request.speed_rpm,
                                        request.target_type, request.min_mm, request.max_mm)

    def update_position_limit(self, torque_limit: int) -> PositionMotionStatusSchema:
        with self._lock:
            self._assert_simulated_motion()
            if not 1 <= torque_limit <= 3000 or self._motion_state not in {"exercise", "raising", "weightless", "holding"}:
                raise ValueError("Нет активного упражнения или недопустимый лимит")
            if self._motion_state == "weightless" and (self._weightless_threshold is None or torque_limit >= self._weightless_threshold):
                raise ValueError("Невесомый режим: лимит должен оставаться ниже измеренного порога движения")
            try:
                for sid in (self._left_slave_id, self._right_slave_id):
                    for address in (0x05E, 0x05F):
                        self._verified_motion_write(address, torque_limit, sid)
            except ValueError as exc:
                self._motion_fault(str(exc))
                raise
            self._motion_torque_limit = torque_limit
            return self.position_motion_status()

    def stop_raise(self) -> PositionMotionStatusSchema:
        with self._lock:
            # No Servo-OFF and no zero torque. Fail closed when no verified path exists.
            if self._motion_state in {"exercise", "weightless", "holding"} and not self._motion_min_mm <= STOP_TARGET_MM <= self._motion_max_mm:
                raise ValueError("STOP 2000 мм вне действующих программных границ; используйте аппаратную защиту")
            return self._start_position(STOP_TARGET_MM, STOP_TORQUE_LIMIT, STOP_SPEED_RPM,
                                        "stop_raise", 0, STOP_TARGET_MM)

    def enter_weightless(self, req: WeightlessPositionSchema) -> PositionMotionStatusSchema:
        with self._lock:
            if req.torque_limit >= req.no_motion_threshold:
                raise ValueError("Лимит невесомого грифа должен быть ниже измеренного порога движения")
            if self._motion_state in {"exercise", "raising", "fault"}:
                raise ValueError("Сначала завершите движение; нельзя переключаться на невесомый режим под нагрузкой")
            # Reaching 2m is NOT expected in weightless mode. The low limit
            # must be established with the actual load; this is simulation only.
            status = self._start_position(STOP_TARGET_MM, req.torque_limit, req.speed_rpm,
                                          "weightless", 0, STOP_TARGET_MM)
            if status.state == "weightless":
                self._weightless_threshold = req.no_motion_threshold
            return status

    def hold_position(self) -> PositionMotionStatusSchema:
        with self._lock:
            self._assert_simulated_motion()
            if self._motion_state not in {"weightless", "holding"}:
                raise ValueError("Удержание доступно после невесомого режима")
            status = self.position_motion_status()
            if status.state == "fault":
                raise ValueError(status.error or "Ошибка движения")
            left, right = status.positions.left.position_mm, status.positions.right.position_mm
            if left is None or right is None or abs(left - right) > MAX_SKEW_MM:
                raise ValueError("Позиция для удержания не подтверждена")
            return self._start_position(round((left + right) / 2, 3), STOP_TORQUE_LIMIT,
                                        STOP_SPEED_RPM, "hold", 0, STOP_TARGET_MM)

    def position_motion_status(self) -> PositionMotionStatusSchema:
        with self._lock:
            positions = self._positions_locked()
            drives: dict[str, dict[str, int | float | None]] = {}
            servo: dict[str, bool | None] = {}
            load: dict[str, bool | None] = {}
            warning = None
            try:
                if self._motion_state in {"exercise", "raising", "weightless", "holding"}:
                    if not positions.readiness.encoder_ready:
                        raise ValueError("Потеряна связь Modbus/энкодер")
                    if positions.skew_mm is None or abs(positions.skew_mm) > MAX_SKEW_MM:
                        raise ValueError("Перекос превышает 3 мм")
                for side, sid in (("left", self._left_slave_id), ("right", self._right_slave_id)):
                    if not self._connected:
                        servo[side], load[side] = None, None
                        continue
                    # These feedback addresses are simulator placeholders until the
                    # drive's physical monitoring map is independently confirmed.
                    values = {name: self._read_motion_register(addr, sid) for name, addr in (
                        ("speed_command", 0x1C0), ("speed_actual", 0x1C1),
                        ("torque_command", 0x1C3), ("torque_actual", 0x1C4),
                        ("torque_error", 0x1C5), ("system_status", 0x1C8),
                        ("error_code", 0x1C9), ("alarm", 0x200),
                    )}
                    deviation = self._combine_position(
                        self._read_motion_register(0x1BE, sid), self._read_motion_register(0x1BF, sid)
                    )
                    values["position_error_mm"] = deviation * MM_PER_PULSE
                    drives[side] = values
                    mask = self._read_motion_register(0x201, sid)
                    servo[side] = bool(mask & 1)
                    load[side] = bool(mask & (1 << 5))
                    if self._motion_state in {"exercise", "raising", "weightless", "holding"}:
                        if values["alarm"] or values["error_code"]:
                            raise ValueError(f"Ошибка драйвера {side}: {values['alarm']}/{values['error_code']}")
                        if not servo[side]:
                            raise ValueError(f"Servo-ON {side} отключён")
                        p = getattr(positions, side).position_mm
                        if p is None or not self._motion_min_mm <= p <= self._motion_max_mm:
                            raise ValueError(f"{side}: выход за программные границы")
                        if self._motion_state != "weightless" and (abs(values["position_error_mm"]) > MAX_POSITION_ERROR_MM or abs((self._motion_target_mm or 0) - p) > MAX_POSITION_ERROR_MM):
                            warning = "Позиционная ошибка более 10 мм (при движении допустимо; проверьте препятствие)"
                if self._motion_state in {"exercise", "raising", "weightless", "holding"}:
                    current = (positions.left.position_mm, positions.right.position_mm)
                    assert current[0] is not None and current[1] is not None
                    stalled = (self._motion_state != "weightless" and self._previous_positions is not None and
                               all(abs(a - b) < 0.1 for a, b in zip(current, self._previous_positions)) and
                               all(abs(drives[s]["torque_actual"] or 0) >= (self._motion_torque_limit or 0) * 0.9 for s in ("left", "right")) and
                               any(abs((self._motion_target_mm or 0) - p) > 1 for p in current))
                    if stalled:
                        self._stall_since = self._stall_since or time.monotonic()
                        if time.monotonic() - self._stall_since >= 2:
                            raise ValueError("Препятствие: нет движения, момент около лимита")
                    else:
                        self._stall_since = None
                    self._previous_positions = current
            except ValueError as exc:
                if self._motion_state in {"exercise", "raising", "weightless", "holding"}:
                    self._motion_fault(str(exc))
                else:
                    warning = str(exc)
            return PositionMotionStatusSchema(
                state=self._motion_state, target_type=self._motion_target_type,
                target_mm=self._motion_target_mm, torque_limit=self._motion_torque_limit,
                speed_rpm=self._motion_speed_rpm, positions=positions,
                servo_on=servo, pos_load=load, drives=drives, warning=warning,
                error=self._motion_error, simulation_only=True,
            )

    def software_stop(self) -> SoftwareStopResultSchema:
        """Deprecated: never release the bar by zeroing torque or disabling the servos."""
        result = SoftwareStopResultSchema()
        result.errors.append("Servo-OFF/нулевой момент не являются штатной остановкой; используйте stop_raise() в симуляции или аппаратный E-STOP")
        return result

    def _do_read(self, req: ModbusReadRequestSchema) -> ModbusReadResultSchema:
        with self._lock:
            if not self._connected:
                return ModbusReadResultSchema(
                    success=False,
                    registers=[],
                    error="Not connected",
                )

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
            self._select_slave(slave_id)
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

    def get_diagnostics(self, slave_id: int | None = None) -> DriverDiagnosticsSchema:
        with self._lock:
            if not self._connected:
                return DriverDiagnosticsSchema(responding=False, status_summary="Not connected")
            self._select_slave(slave_id or (self._params.slave_id if self._params else 1))

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
            # Register diagnostics cannot prove STO, brakes, limits or sync.
            motion_safe = False

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

            # DI status registers are simulated placeholders, not verified control
            # registers on the real A6. Never claim a real motor command succeeded.
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
