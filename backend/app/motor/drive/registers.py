"""Lichuan A6 register map: only what v2 uses (plan 15 §0) + write whitelist."""

from __future__ import annotations

PA_TORQUE_COMMAND = 0x12C  # PA_12C, signed, 0.1 % of rated torque
PA_TORQUE_LIMIT = 0x05E  # PA_05E
PA_SPEED_LIMIT = 0x056  # PA_056, rpm in Torque Mode
PA_VIRTUAL_DI = 0x1A4  # PA_1A4, virtual DI state (SRV-ON bit0 when PA_1A0 bit0 = 1)

MONITOR_BLOCK = 0x1BC  # PA_1BC..PA_1C9, 14 words
MONITOR_SLOW = 0x1D9  # PA_1D9..PA_1DE: DC bus V, module temp, torque load, regen load, overload, reason

# Commissioning parameters, address → (label, mask, expected): set by hand on the
# drive panel, saved to EEPROM; software only reads and compares them.
COMMISSIONING_EXPECTED: dict[int, tuple[str, int, int]] = {
    0x002: ("PA_002 режим управления (нужно 2 = Torque)", 0xFFFF, 2),
    0x00B: ("PA_00B энкодер (нужно 0 = абсолютный)", 0xFFFF, 0),
    0x08F: ("PA_08F автовключение (нужно 0 = по команде)", 0xFFFF, 0),
    0x090: ("PA_090 управление по связи (нужно 1)", 0xFFFF, 1),
    0x080: ("PA_080 функция DI0 (нужно 0 = SRV-ON)", 0xFFFF, 0),
    0x1A0: ("PA_1A0 bit0 (нужно 1 = SRV-ON из PA_1A4)", 0x0001, 1),
}

FORBIDDEN_WRITES = frozenset({0x000, 0x002, 0x00B, 0x08F, 0x090, 0x1A0, 0x1A7})
WRITABLE = frozenset({PA_TORQUE_COMMAND, PA_TORQUE_LIMIT, PA_SPEED_LIMIT, PA_VIRTUAL_DI})

ALARMS: dict[int, str] = {
    3: "Err 3: ошибка связи (мастер перестал опрашивать привод)",
    16: "Err 16: перегрузка",
    18: "Err 18: перегрузка тормозного резистора",
    40: "Err 40: батарея абсолютного энкодера разряжена или отключена",
}


class ForbiddenRegisterWriteError(PermissionError):
    pass


def assert_writable(address: int) -> None:
    if address in FORBIDDEN_WRITES or address not in WRITABLE:
        raise ForbiddenRegisterWriteError(f"Запись PA_{address:03X} запрещена в рантайме")


def alarm_text(code: int) -> str:
    return ALARMS.get(code, f"Авария привода {code}")
