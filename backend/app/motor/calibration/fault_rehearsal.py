"""Read-only fault rehearsal. Only timestamped model samples enter the production pair monitor."""

from dataclasses import replace
from typing import Any

from app.motor.drive.protocol import DriveSample
from app.motor.profile import MachineProfile, SafetyEnvelope
from app.motor.supervisor.pair import PairMonitor
from app.motor.units import SIDES, Side

CASES = (
    ("level", "Ровный быстрый ход", "Стороны движутся вместе со скоростью 1,5 м/с. Энкодеры опрашиваются по очереди.", "ok"),
    ("left", "Отстаёт левая каретка", "Правая сторона продолжает подъём, разница высот последовательно растёт.", "skew"),
    ("right", "Отстаёт правая каретка", "Левая сторона продолжает подъём, разница высот последовательно растёт.", "skew"),
    ("spike", "Одиночный выброс энкодера", "Один кадр пересекает первый критический порог. Следующий подтверждает ровный гриф.", "warning"),
    ("frozen", "Застыл кадр привода", "Правый привод повторяет прошлый кадр с прежней меткой времени.", "telemetry"),
    ("missing", "Пропала связь", "В очередном цикле отсутствуют данные левой каретки.", "drive"),
    ("alarm", "Авария правого привода", "Приходит свежий кадр со статусом аварии привода.", "drive"),
)


def fault_rehearsal(profile: MachineProfile, safety: SafetyEnvelope) -> dict[str, Any]:
    dt = min(float(profile.loop_period_s.value), safety.stale_frame_limit_s * 0.6)
    cases = []
    for key, title, description, expected in CASES:
        monitor = PairMonitor()
        frames = []
        response, detail = "ok", ""
        for i in range(10):
            t = (i + 1) * dt
            samples = {s: DriveSample(s, t, True, position_mm=600.0) for s in SIDES}
            if key == "level":
                for side in SIDES:
                    ts = t - (0.3 * dt if side == "left" else 0.0)
                    samples[side] = replace(samples[side], t=ts, position_mm=600 + 1500 * ts, speed_mm_s=1500)
            elif key in ("left", "right"):
                other: Side = "right" if key == "left" else "left"
                samples[other] = replace(samples[other], position_mm=600 + max(0, i - 2) * 0.34 * safety.sync_critical_mm)
            elif i == 4:
                if key == "spike":
                    samples["left"] = replace(samples["left"], position_mm=600 + 1.2 * safety.sync_critical_mm)
                elif key == "frozen":
                    samples["right"] = monitor.previous["right"]
                elif key == "missing":
                    del samples["left"]
                elif key == "alarm":
                    samples["right"] = replace(samples["right"], alarm=1)
            fault = monitor.check(samples, t, safety.stale_frame_limit_s, safety.sync_critical_mm)
            delta = monitor.delta_mm
            state = "stop" if fault else "warning" if delta is not None and abs(delta) >= safety.sync_warning_mm else "ok"
            raw = samples["left"].position_mm - samples["right"].position_mm if len(samples) == 2 else None
            frames.append({"ms": round((t - dt) * 1000, 1), "rawMm": round(raw, 2) if raw is not None else None,
                           "deltaMm": round(delta, 2) if delta is not None else None, "state": state})
            if fault:
                response, detail = fault.code, fault.message
                break
            if state == "warning":
                response = "warning"
        cases.append({"id": key, "title": title, "description": description, "frames": frames,
                      "expected": expected, "actual": response, "matches": expected == response, "detail": detail})
    return {"version": profile.version, "warningMm": safety.sync_warning_mm, "criticalMm": safety.sync_critical_mm,
            "cycleMs": round(dt * 1000, 2), "cases": cases}
