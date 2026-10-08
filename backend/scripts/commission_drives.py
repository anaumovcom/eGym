"""Commission both Lichuan A6 drives through the backend debug API and save to EEPROM.

Run with the bar resting on the bottom stops and the backend started with
HARDWARE_ADAPTER=emulator (so the runtime does not use the bus):

    ../.venv/bin/python scripts/commission_drives.py            # check, write, verify, save
    ../.venv/bin/python scripts/commission_drives.py --dry-run  # only show current vs target

PA_000, PA_002 and PA_090 are expected to be set already; they are checked, not written.
Nothing is saved unless every value on both drives reads back as expected.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Already set by hand: address → (label, expected)
PRESET = {
    0x002: ("режим Torque", 2),
    0x090: ("команда из внутренних регистров", 1),
}

# Written in this order: torque command and virtual DI are zeroed first.
TARGET = [
    (0x12C, 0, "команда момента 0"),
    (0x1A4, 0, "виртуальные входы сброшены (Servo OFF)"),
    (0x093, 0, "активный сегмент момента = PA_12C"),
    (0x003, 1, "лимит PA_05E в обе стороны"),
    (0x05E, 400, "лимит момента 40 %"),
    (0x05F, 400, "второй лимит момента"),
    (0x056, 300, "лимит скорости 300 об/мин"),
    (0x00B, 0, "абсолютный энкодер"),
    (0x08F, 0, "без автовключения"),
    (0x080, 0, "DI0 = SRV-ON"),
    (0x1A0, 1, "DI0 управляется из PA_1A4"),
    (0x06C, 0, "встроенный тормозной резистор (перемычка B2–B3)"),
]


class ApiError(RuntimeError):
    pass


def call(api: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{api}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise ApiError(f"{method} {path}: HTTP {exc.code} {exc.read().decode(errors='replace')}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"бэкенд недоступен ({api}): {exc.reason}") from exc


def read(api: str, address: int, slave: int) -> int:
    result = call(api, "POST", "/read", {"address": address, "count": 1, "slave_id": slave})
    if not result.get("success") or not result.get("registers"):
        raise ApiError(f"ID{slave} чтение PA_{address:03X}: {result.get('error')}")
    return int(result["registers"][0]["value"])


def write(api: str, address: int, value: int, slave: int) -> None:
    result = call(api, "POST", "/write", {"address": address, "value": value, "slave_id": slave})
    if not result.get("success"):
        raise ApiError(f"ID{slave} запись PA_{address:03X}={value}: {result.get('error')}")


def report_alarms(api: str, slaves: list[int], attempts: int) -> bool:
    """PA_1C9 per drive; retries because the drive does not answer while writing EEPROM."""
    clean = True
    for slave in slaves:
        for attempt in range(attempts):
            try:
                alarm = read(api, 0x1C9, slave)
                break
            except ApiError as exc:
                if attempt == attempts - 1:
                    print(f"ID{slave}: аварию PA_1C9 прочитать не удалось ({exc})")
                    clean = False
                    alarm = None
                else:
                    time.sleep(1.0)
        if alarm is not None:
            print(f"ID{slave}: авария PA_1C9 = {alarm}{'' if alarm == 0 else '  ← АВАРИЯ'}")
            clean = clean and alarm == 0
    return clean


def ensure_connected(api: str, port: str) -> None:
    status = call(api, "GET", "/status")
    if status.get("connected"):
        if status.get("simulation_mode"):
            raise ApiError("бэкенд подключён к симуляции SIM://, а не к драйверам")
        return
    status = call(api, "POST", "/connect", {"port": port, "baud_rate": 115200, "parity": "E", "slave_id": 1, "right_slave_id": 2})
    if not status.get("connected"):
        raise ApiError(f"нет связи с {port}: {status.get('error_message')}")
    print(f"Подключено к {port}")


def check_preset(api: str, slave: int) -> list[str]:
    problems = []
    address = read(api, 0x000, slave)
    if address != slave:
        problems.append(f"ID{slave}: PA_000={address}, отвечает не тот драйвер")
    for reg, (label, expected) in PRESET.items():
        value = read(api, reg, slave)
        mark = "ok" if value == expected else f"НУЖНО {expected}"
        print(f"  ID{slave} PA_{reg:03X} = {value:<5} {mark:<9} {label}")
        if value != expected:
            problems.append(f"ID{slave}: PA_{reg:03X}={value}, нужно {expected}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/modbus")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--slaves", type=int, nargs="+", default=[1, 2])
    parser.add_argument("--dry-run", action="store_true", help="только прочитать и показать")
    parser.add_argument("--no-save", action="store_true", help="записать и проверить, но не сохранять в EEPROM")
    args = parser.parse_args()

    try:
        ensure_connected(args.api, args.port)

        print("Проверка уже выставленных параметров:")
        problems = [problem for slave in args.slaves for problem in check_preset(args.api, slave)]
        if problems:
            print("\nОСТАНОВ: " + "; ".join(problems))
            return 1

        for slave in args.slaves:
            print(f"\nID{slave}:")
            for reg, value, label in TARGET:
                before = read(args.api, reg, slave)
                if not args.dry_run and before != value:
                    write(args.api, reg, value, slave)
                after = before if args.dry_run else read(args.api, reg, slave)
                mark = "ok" if after == value else f"НУЖНО {value}"
                change = f"{before} → {after}" if before != after else f"{after}"
                print(f"  PA_{reg:03X} = {change:<12} {mark:<9} {label}")
                if after != value:
                    problems.append(f"ID{slave}: PA_{reg:03X}={after}, нужно {value}")

        if args.dry_run:
            print()
            alarms_ok = report_alarms(args.api, args.slaves, attempts=2)
            print("Dry-run: ничего не записано.")
            return 1 if problems or not alarms_ok else 0
        if problems:
            print("\nОСТАНОВ, в EEPROM не сохранено: " + "; ".join(problems))
            return 1
        if args.no_save:
            print("\nВсё записано и проверено, в EEPROM НЕ сохранено (--no-save).")
            return 0

        for slave in args.slaves:
            result = call(args.api, "POST", "/commands", {"command": "save_parameters", "confirmed": True, "slave_id": slave})
            if not result.get("success"):
                raise ApiError(f"ID{slave} сохранение (PA_1A7=0x0801): {result.get('error')}")
            print(f"ID{slave}: сохранено в EEPROM")
        time.sleep(2.0)  # the drive is silent while it writes EEPROM
        report_alarms(args.api, args.slaves, attempts=5)
    except ApiError as exc:
        print(f"\nОШИБКА: {exc}")
        return 2

    print("\nГотово. Полностью обесточьте оба драйвера (PA_00B вступит в силу после перезапуска),")
    print("затем запустите скрипт с --dry-run: все строки должны быть ok, PA_1C9 = 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
