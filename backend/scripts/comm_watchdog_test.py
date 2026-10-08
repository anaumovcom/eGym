"""C-WD: does the Lichuan A6 react to a silent master (Err 3), after how long, and how.

The backend must be stopped (./stop-watch.sh): this script owns /dev/ttyUSB0 itself.
The bar rests on the bottom stops. The script:

1. connects and runs the normal torque init (commissioning check, support PA_12C written first);
2. asks for confirmation and turns SRV-ON on both drives;
3. polls at 20 Hz for 3 s, like the runtime;
4. goes silent for growing pauses (0.5 … 30 s), reading PA_1C9 once after each pause;
   every read restarts the drive's timer, so Err 3 lies between the previous and the
   current pause;
5. always turns SRV-ON off at the end, also on Ctrl+C or an error.

    ../.venv/bin/python scripts/comm_watchdog_test.py
"""

from __future__ import annotations

import sys
import time

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.motor.drive.registers import alarm_text
from app.motor.store import load_active
from app.schemas.modbus import ModbusConnectionParamsSchema, ModbusReadRequestSchema
from app.services.modbus_service import ModbusService

PAUSES_S = [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 20.0, 30.0]
REASONS = {0: "работает", 2: "SRV-ON выключен"}


def probe(service: ModbusService, slave: int) -> dict[str, object]:
    data = service.read_torque_telemetry(slave, extended=True, log=False)
    if data.get("error"):
        return {"error": data["error"]}
    di = service.read_registers(ModbusReadRequestSchema(address=0x1A4, count=1, slave_id=slave))
    return {
        "alarm": int(data["alarm"] or 0),
        "reason": data["reason_pa1de"],
        "torque": data["feedback_torque_raw"],
        "di": di.registers[0].value if di.success and di.registers else None,
    }


def describe(result: dict[str, object]) -> str:
    if result.get("error"):
        return f"нет ответа ({result['error']})"
    reason = result["reason"]
    return (
        f"PA_1C9={result['alarm']} ({alarm_text(result['alarm']) if result['alarm'] else 'нет аварии'}), "
        f"PA_1DE={reason} ({REASONS.get(reason, 'см. мануал')}), "
        f"момент={result['torque']}, PA_1A4={result['di']}"
    )


def main() -> int:
    settings = get_settings()
    left, right = settings.modbus_left_slave_id, settings.modbus_right_slave_id
    slaves = {left: "левый", right: "правый"}
    with SessionLocal() as session:
        machine = load_active(session).machine
    support = {
        left: int(machine.left.support_raw.value) * machine.left.sign,
        right: int(machine.right.support_raw.value) * machine.right.sign,
    }

    service = ModbusService()
    status = service.connect(
        ModbusConnectionParamsSchema(port=settings.modbus_port, baud_rate=settings.modbus_baud_rate, slave_id=left, right_slave_id=right),
        initial_commands=support,
    )
    if not status.connected:
        print(f"Нет связи с {settings.modbus_port}: {status.error_message}")
        print("Бэкенд остановлен? ./stop-watch.sh")
        return 2
    not_ready = [f"ID{slave}: {service._init_error.get(slave, 'не готов')}" for slave in slaves if not service.torque_ready(slave)]
    if status.simulation_mode or not_ready:
        print("Инициализация не прошла: " + "; ".join(not_ready))
        service.disconnect(preserve_torque=True)
        return 2

    first_alarm: dict[int, tuple[float, float, str]] = {}
    try:
        for slave, name in slaves.items():
            result = probe(service, slave)
            print(f"ID{slave} {name}: {describe(result)}")
            if result.get("error") or result["alarm"]:
                print("Перед тестом нужна связь и отсутствие аварии.")
                return 2
        print(f"\nПоддержка PA_12C: {support}. Гриф должен лежать на упорах.")
        if input("Включить SRV-ON на обоих приводах и начать тест? [y/N] ").strip().lower() != "y":
            return 1
        for slave in slaves:
            if error := service.set_servo(slave, True):
                print(f"ID{slave}: SRV-ON не включился: {error}")
                return 2
        print("SRV-ON включён. Обычный опрос 20 Гц, 3 с…")
        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            for slave in slaves:
                service.read_torque_telemetry(slave, log=False)
            time.sleep(0.05)
        for slave, name in slaves.items():
            print(f"  ID{slave} {name}: {describe(probe(service, slave))}")

        previous = 0.0
        for pause in PAUSES_S:
            print(f"\nТишина {pause:g} с… (смотрите на дисплеи драйверов)")
            time.sleep(pause)
            for slave, name in slaves.items():
                if slave in first_alarm:
                    continue
                result = probe(service, slave)
                print(f"  ID{slave} {name}: {describe(result)}")
                if result.get("error") or result["alarm"]:
                    first_alarm[slave] = (previous, pause, describe(result))
            if len(first_alarm) == len(slaves):
                break
            previous = pause
    except KeyboardInterrupt:
        print("\nПрервано.")
    finally:
        for slave in slaves:
            error = service.set_servo(slave, False)
            print(f"ID{slave}: SRV-ON выключен" if not error else f"ID{slave}: выключить SRV-ON не удалось: {error}")
        service.disconnect(preserve_torque=True)

    print("\nИтог:")
    for slave, name in slaves.items():
        if slave in first_alarm:
            low, high, text = first_alarm[slave]
            print(f"  ID{slave} {name}: реакция после {low:g}–{high:g} с тишины; {text}")
        else:
            print(f"  ID{slave} {name}: за {max(PAUSES_S):g} с тишины реакции нет — сторожевого таймера связи нет")
    if first_alarm:
        print("Аварию сбросить перезапуском питания драйверов, затем ./start-watch.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
