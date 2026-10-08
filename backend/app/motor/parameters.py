"""Service-editable motor parameters with descriptions (profile, behaviour, safety limits).

One table drives both the parameters page and validation of manual edits.
Manual edits of identified values get provenance ``manual``; a new profile
version is stored for every change.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal

from app.motor.profile import Measured, SafetyEnvelope, Tunables
from app.motor.store import ProfileBundle
from app.motor.units import SIDES, Side

Scope = Literal["side", "machine", "tunables", "envelope"]
Kind = Literal["float", "int", "bool", "sign", "weight", "counts"]


@dataclass(frozen=True)
class ParamSpec:
    scope: Scope
    key: str
    group: str
    label: str
    description: str
    unit: str = ""
    kind: Kind = "float"
    editable: bool = True
    min: float | None = None
    max: float | None = None
    step: float | None = None
    produced_by: str | None = None
    restart: bool = False  # written to the drive at connection: applies after a backend restart / fault reset


GROUPS: tuple[tuple[str, str, str], ...] = (
    ("drive", "Привод и механика", "Свойства приводов и винтов. Направление и масштаб определяют, как команда момента превращается в силу на грифе."),
    ("statics", "Вес и трение", "Окно невесомости: сила, при которой гриф трогается вверх и вниз. Измеряется калибровкой S3."),
    ("dynamics", "Динамика и связь", "Инерция, вязкое трение, тайминг шины и запас устойчивости удержания."),
    ("behaviour", "Поведение тренажёра", "Коэффициенты режимов тренировки: компенсация трения, удержание, подсчёт повторений. Применяются сразу после сохранения."),
    ("safety", "Пределы безопасности", "Жёсткие ограничения — последний фильтр перед приводом. Меняйте только понимая последствия."),
)

PARAMS: tuple[ParamSpec, ...] = (
    # ---------------------------------------------------------------- drive
    ParamSpec("side", "direction_sign", "drive", "Направление момента", "Знак команды момента, который поднимает сторону. Неверный знак — поддержка давит гриф вниз. Меняется только калибровкой B5.", kind="sign", editable=False, produced_by="B5"),
    ParamSpec("side", "n_per_raw", "drive", "Масштаб силы", "Сколько ньютонов на грифе даёт одна единица команды PA_12C (0,1 % номинального момента). Паспортное значение ±15 %; точно — эталонным грузом (S9).", "Н/ед.", min=0.1, max=5.0, step=0.01, produced_by="S9"),
    ParamSpec("side", "mm_per_pulse", "drive", "Ход на импульс энкодера", "Шаг винта / импульсы на оборот. Сейчас в связи с приводом используется фиксированное значение.", "мм", editable=False),
    ParamSpec("side", "support_raw", "drive", "Момент поддержки", "Команда PA_12C, которую приводы держат вне тренировки и при СТОП: гриф должен медленно опускаться, а не падать.", "ед.", kind="int", min=0, max=400, step=1, produced_by="C3"),
    ParamSpec("side", "zero_counts", "drive", "Абсолютный ноль", "Показание энкодера на нижних упорах (B7).", "имп.", kind="counts", editable=False, produced_by="B7"),
    ParamSpec("machine", "travel_mm", "drive", "Рабочий ход", "Полный ход грифа от нижних упоров до верха.", "мм", min=100, max=2000, step=10),
    # -------------------------------------------------------------- statics
    ParamSpec("side", "gravity_map", "statics", "Вес (баланс)", "Сила, удерживающая сторону грифа в равновесии: середина окна невесомости. При нескольких точках по высоте редактируется только калибровкой.", "Н", kind="weight", min=0, max=1500, step=1, produced_by="S3"),
    ParamSpec("side", "coulomb_up_n", "statics", "Трение вверх", "Добавка к весу, нужная чтобы сдвинуть гриф вверх (сухое трение винта и направляющих).", "Н", min=0, max=500, step=1, produced_by="S3"),
    ParamSpec("side", "coulomb_down_n", "statics", "Трение вниз", "Сколько можно убрать от веса, прежде чем гриф поедет вниз.", "Н", min=0, max=500, step=1, produced_by="S3"),
    ParamSpec("side", "stribeck_extra_n", "statics", "Добавка трогания", "Дополнительное трение покоя сверх трения движения (эффект Штрибека).", "Н", min=0, max=200, step=1, produced_by="S3"),
    ParamSpec("side", "stribeck_v_mm_s", "statics", "Скорость Штрибека", "Скорость, на которой трение покоя переходит в трение движения.", "мм/с", min=0.1, max=50, step=0.1),
    # ------------------------------------------------------------- dynamics
    ParamSpec("side", "viscous_n_per_mm_s", "dynamics", "Вязкое трение", "Рост сопротивления со скоростью (D2).", "Н·с/мм", min=0, max=5, step=0.01, produced_by="D2"),
    ParamSpec("side", "moving_mass_kg", "dynamics", "Приведённая масса", "Инерция винта, ротора и грифа, приведённая к стороне (D4).", "кг", min=1, max=300, step=1, produced_by="D4"),
    ParamSpec("machine", "hold_ultimate_k_n_per_mm", "dynamics", "Предельная жёсткость удержания", "K_u из релейного теста C1: при такой жёсткости удержание начинает раскачиваться. Рабочая жёсткость — доля от неё.", "Н/мм", min=0.01, max=100, step=0.01, produced_by="C1"),
    ParamSpec("machine", "hold_ultimate_period_s", "dynamics", "Период предельного цикла", "Период колебаний в релейном тесте C1; определяет демпфирование удержания.", "с", min=0.01, max=10, step=0.01, produced_by="C1"),
    ParamSpec("machine", "loop_period_s", "dynamics", "Период цикла", "Среднее время одного цикла чтение/запись по RS-485 (B1).", "с", min=0.005, max=0.5, step=0.001, produced_by="B1"),
    ParamSpec("machine", "loop_delay_s", "dynamics", "Задержка цикла", "Задержка от чтения положения до применения новой команды.", "с", min=0.005, max=0.5, step=0.001, produced_by="B1"),
    ParamSpec("machine", "jitter_p95_s", "dynamics", "Разброс цикла (p95)", "95-й перцентиль отклонения периода цикла (B1).", "с", min=0, max=0.5, step=0.001, produced_by="B1"),
    ParamSpec("machine", "side_coupling_n_per_mm", "dynamics", "Связь сторон", "Жёсткость грифа между сторонами: сила при перекосе на 1 мм.", "Н/мм", min=0, max=1000, step=1),
    # ------------------------------------------------------------ behaviour
    ParamSpec("tunables", "friction_gain_up", "behaviour", "Компенсация трения вверх", "Доля измеренного трения вверх, которую компенсирует мотор. 1 — полная (риск самоподъёма), 0 — нет.", "×", min=0, max=1.2, step=0.05),
    ParamSpec("tunables", "friction_gain_down", "behaviour", "Компенсация трения вниз", "Доля трения вниз, которую компенсирует мотор.", "×", min=0, max=1.2, step=0.05),
    ParamSpec("tunables", "inertia_gain", "behaviour", "Компенсация инерции", "Доля приведённой массы, компенсируемая при ускорениях. 0 — без компенсации.", "×", min=0, max=1, step=0.05),
    ParamSpec("tunables", "friction_blend_mm_s", "behaviour", "Сглаживание трения", "Скорость, в пределах которой компенсация трения плавно меняет знак.", "мм/с", min=0.5, max=50, step=0.5),
    ParamSpec("tunables", "weightless_damping_n_per_mm_s", "behaviour", "Демпфирование невесомости", "Вязкость в режиме невесомости: гасит самопроизвольный дрейф.", "Н·с/мм", min=0, max=5, step=0.05),
    ParamSpec("tunables", "hold_k_fraction", "behaviour", "Жёсткость удержания, доля K_u", "Рабочая жёсткость удержания как доля предельной (C1). Больше — твёрже, но ближе к раскачке.", "×", min=0.05, max=0.6, step=0.01),
    ParamSpec("tunables", "hold_c_fraction", "behaviour", "Демпфирование удержания, доля", "Демпфирование удержания относительно K_u·T_u.", "×", min=0.05, max=1, step=0.01),
    ParamSpec("tunables", "hold_k_default_n_per_mm", "behaviour", "Жёсткость удержания без C1", "Используется, пока C1 не выполнена.", "Н/мм", min=0.05, max=10, step=0.05),
    ParamSpec("tunables", "hold_c_default_n_per_mm_s", "behaviour", "Демпфирование удержания без C1", "Используется, пока C1 не выполнена.", "Н·с/мм", min=0, max=10, step=0.05),
    ParamSpec("tunables", "load_ramp_n_per_s", "behaviour", "Скорость набора нагрузки", "Как быстро нагрузка нарастает до заданной.", "Н/с", min=20, max=2000, step=10),
    ParamSpec("tunables", "phase_blend_s", "behaviour", "Переход фаз", "Время плавного перехода между концентрической и эксцентрической фазой.", "с", min=0.01, max=1, step=0.01),
    ParamSpec("tunables", "phase_hysteresis_mm_s", "behaviour", "Гистерезис фазы", "Скорость, после которой фаза движения считается сменившейся.", "мм/с", min=1, max=100, step=1),
    ParamSpec("tunables", "assist_alpha", "behaviour", "Помощь при отказе", "Доля нагрузки, которая остаётся при срабатывании помощи.", "×", min=0, max=1, step=0.05),
    ParamSpec("tunables", "eccentric_beta", "behaviour", "Эксцентрический коэффициент", "Множитель нагрузки при опускании.", "×", min=0.5, max=2, step=0.05),
    ParamSpec("tunables", "levitation_margin_mm", "behaviour", "Запас левитации", "Отступ от упоров, на котором гриф зависает при старте.", "мм", min=5, max=200, step=1),
    ParamSpec("tunables", "reps_full_percent", "behaviour", "Полное повторение", "Доля амплитуды, после которой повторение засчитывается полным.", "%", min=50, max=100, step=1),
    ParamSpec("tunables", "reps_partial_percent", "behaviour", "Частичное повторение", "Доля амплитуды для частичного повторения.", "%", min=10, max=90, step=1),
    ParamSpec("tunables", "reps_hysteresis_mm", "behaviour", "Гистерезис повторений", "Защита от двойного счёта у точки разворота.", "мм", min=1, max=100, step=1),
    ParamSpec("tunables", "release_force_n", "behaviour", "Сила отпускания", "Если пользователь давит слабее этой силы — гриф считается отпущенным.", "Н", min=5, max=300, step=5),
    ParamSpec("tunables", "release_timeout_s", "behaviour", "Время отпускания", "Сколько гриф должен быть отпущен, чтобы тренажёр перешёл к удержанию.", "с", min=0.5, max=30, step=0.5),
    ParamSpec("tunables", "sync_k_n_per_mm", "behaviour", "Выравнивание сторон", "Сила выравнивания на 1 мм перекоса.", "Н/мм", min=0, max=50, step=0.5),
    ParamSpec("tunables", "sync_max_n", "behaviour", "Предел выравнивания", "Максимальная сила выравнивания сторон.", "Н", min=0, max=300, step=5),
    # --------------------------------------------------------------- safety
    ParamSpec("envelope", "max_force_n_per_side", "safety", "Максимальная сила на сторону", "Команда силы ограничивается этим значением.", "Н", min=50, max=1500, step=10),
    ParamSpec("envelope", "max_raw", "safety", "Предел момента привода (PA_05E)", "Ограничение команды PA_12C и предел момента в приводе.", "ед.", kind="int", min=100, max=3000, step=10, restart=True),
    ParamSpec("envelope", "speed_limit_rpm", "safety", "Предел скорости привода (PA_056)", "Ограничение скорости в режиме момента, записывается в привод.", "об/мин", kind="int", min=50, max=3000, step=10, restart=True),
    ParamSpec("envelope", "overspeed_rpm_alarm", "safety", "Аварийная скорость", "Выше этой скорости момент обнуляется и тренажёр блокируется (1 об/мин ≈ 0,53 мм/с).", "об/мин", min=50, max=3000, step=10),
    ParamSpec("envelope", "max_speed_mm_s", "safety", "Максимальная скорость грифа", "Предел скорости в тренировке.", "мм/с", min=50, max=1000, step=10),
    ParamSpec("envelope", "max_descent_mm_s", "safety", "Максимальная скорость опускания", "Предел скорости вниз.", "мм/с", min=20, max=1000, step=10),
    ParamSpec("envelope", "soft_min_mm", "safety", "Нижний программный предел", "Ниже этой высоты нагрузка снимается, гриф мягко садится на упоры.", "мм", min=0, max=500, step=1),
    ParamSpec("envelope", "soft_max_mm", "safety", "Верхний программный предел", "Выше этой высоты нагрузка не прикладывается.", "мм", min=100, max=2000, step=10),
    ParamSpec("envelope", "max_rate_n_per_s", "safety", "Скорость изменения силы", "Ограничение скачков команды силы.", "Н/с", min=100, max=10000, step=50),
    ParamSpec("envelope", "sync_warning_mm", "safety", "Перекос: предупреждение", "Разница высот сторон, при которой выдаётся предупреждение.", "мм", min=1, max=50, step=0.5),
    ParamSpec("envelope", "sync_critical_mm", "safety", "Перекос: остановка", "Разница высот сторон, при которой движение останавливается.", "мм", min=2, max=100, step=0.5),
    ParamSpec("envelope", "stale_frame_limit_s", "safety", "Устаревание телеметрии", "Кадр старше этого времени считается потерянным.", "с", min=0.05, max=2, step=0.01),
    ParamSpec("envelope", "comm_freeze_frames", "safety", "Потерь до заморозки", "Сколько подряд потерянных кадров замораживает команду.", "кадров", kind="int", min=1, max=20, step=1),
    ParamSpec("envelope", "comm_fault_frames", "safety", "Потерь до ошибки", "Сколько подряд потерянных кадров вызывает ошибку и поддержку.", "кадров", kind="int", min=2, max=50, step=1),
    ParamSpec("envelope", "temp_max_c", "safety", "Максимальная температура", "Температура привода, выше которой нагрузка запрещена.", "°C", min=40, max=100, step=1),
    ParamSpec("envelope", "fault_lockout", "safety", "Блокировка после ошибки", "После ошибки привода тренажёр остаётся заблокированным до ручного сброса.", kind="bool"),
)
BY_KEY: dict[tuple[Scope, str], ParamSpec] = {(spec.scope, spec.key): spec for spec in PARAMS}


def _measured_payload(measured: Measured, kind: Kind) -> dict[str, Any]:
    value = measured.value
    points = None
    if kind == "weight":
        points = len(value or [])
        value = float(value[0][1]) if points == 1 else None
    return {"value": value, "ci95": measured.ci95, "provenance": measured.provenance, "runId": measured.run_id, "measuredAt": measured.measured_at, "points": points}


def _plain_payload(value: Any, default: Any) -> dict[str, Any]:
    return {"value": value, "ci95": None, "provenance": "default" if value == default else "manual", "runId": None, "measuredAt": None, "points": None}


def describe(bundle: ProfileBundle) -> dict[str, Any]:
    tunables_default, envelope_default = Tunables(), SafetyEnvelope()
    groups = []
    for group_id, title, description in GROUPS:
        items = []
        for spec in (p for p in PARAMS if p.group == group_id):
            item: dict[str, Any] = {
                "scope": spec.scope, "key": spec.key, "label": spec.label, "description": spec.description, "unit": spec.unit, "kind": spec.kind,
                "editable": spec.editable, "min": spec.min, "max": spec.max, "step": spec.step, "producedBy": spec.produced_by, "restart": spec.restart,
            }
            if spec.scope == "side":
                item["values"] = {side: _measured_payload(getattr(bundle.machine.side(side), spec.key), spec.kind) for side in SIDES}
                if spec.kind == "weight" and any(v["points"] != 1 for v in item["values"].values()):
                    item["editable"] = False
            elif spec.scope == "machine":
                item["value"] = _measured_payload(getattr(bundle.machine, spec.key), spec.kind)
            elif spec.scope == "tunables":
                item["value"] = _plain_payload(getattr(bundle.tunables, spec.key), getattr(tunables_default, spec.key))
            else:
                item["value"] = _plain_payload(getattr(bundle.envelope, spec.key), getattr(envelope_default, spec.key))
            items.append(item)
        groups.append({"id": group_id, "title": title, "description": description, "items": items})
    return {"version": bundle.machine.version, "groups": groups}


def _coerce(spec: ParamSpec, value: Any) -> Any:
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{spec.label}: ожидается да/нет")
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{spec.label}: ожидается число")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{spec.label}: недопустимое число")
    if spec.min is not None and number < spec.min or spec.max is not None and number > spec.max:
        raise ValueError(f"{spec.label}: допустимо от {spec.min:g} до {spec.max:g} {spec.unit}".rstrip())
    if spec.kind == "int":
        if number != int(number):
            raise ValueError(f"{spec.label}: ожидается целое число")
        return int(number)
    return number


def _manual(value: Any) -> Measured:
    return Measured(value, None, "manual", None, datetime.now(UTC).isoformat())


def apply_changes(bundle: ProfileBundle, changes: list[dict[str, Any]]) -> ProfileBundle:
    """Validated manual edits → a new bundle. Raises ``ValueError`` with an operator-readable message."""

    if not changes:
        raise ValueError("Нет изменений")
    machine, tunables, envelope = bundle.machine, bundle.tunables, bundle.envelope
    for change in changes:
        spec = BY_KEY.get((change.get("scope"), change.get("key")))  # type: ignore[arg-type]
        if spec is None:
            raise ValueError(f"Неизвестный параметр: {change.get('scope')}.{change.get('key')}")
        if not spec.editable:
            raise ValueError(f"{spec.label}: меняется только калибровкой")
        value = _coerce(spec, change.get("value"))
        if spec.scope == "side":
            side: Side | None = change.get("side")  # type: ignore[assignment]
            if side not in SIDES:
                raise ValueError(f"{spec.label}: не указана сторона")
            current = machine.side(side)
            if spec.kind == "weight":
                points = current.gravity_map.value or []
                if len(points) != 1:
                    raise ValueError(f"{spec.label}: карта по высоте редактируется только калибровкой")
                value = [(float(points[0][0]), value)]
            machine = machine.with_side(side, replace(current, **{spec.key: _manual(value)}))
        elif spec.scope == "machine":
            machine = replace(machine, **{spec.key: _manual(value)})
        elif spec.scope == "tunables":
            tunables = replace(tunables, **{spec.key: value})
        else:
            envelope = replace(envelope, **{spec.key: value})
    if envelope.soft_min_mm >= envelope.soft_max_mm:
        raise ValueError("Нижний программный предел должен быть ниже верхнего")
    if envelope.sync_warning_mm >= envelope.sync_critical_mm:
        raise ValueError("Порог предупреждения о перекосе должен быть меньше порога остановки")
    if envelope.comm_freeze_frames >= envelope.comm_fault_frames:
        raise ValueError("Потерь до заморозки должно быть меньше, чем потерь до ошибки")
    return ProfileBundle(machine, tunables, envelope)


__all__ = ["GROUPS", "PARAMS", "ParamSpec", "apply_changes", "describe"]
