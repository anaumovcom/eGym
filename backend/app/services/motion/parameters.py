"""Unified registry of tunable mechanics parameters.

Every parameter that influences motion control lives here with its metadata
(group, unit, defaults, soft and hard limits).  The UI is generated from this
registry, values are validated against it and persisted as one JSON document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParameterType = Literal["number", "integer", "boolean", "enum"]


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    group: str
    label: str
    description: str
    type: ParameterType
    default: Any
    unit: str = ""
    min: float | None = None
    max: float | None = None
    hard_min: float | None = None
    hard_max: float | None = None
    step: float | None = None
    options: tuple[str, ...] = ()
    requires_restart: bool = False
    safety_critical: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "group": self.group,
            "label": self.label,
            "description": self.description,
            "type": self.type,
            "default": self.default,
            "unit": self.unit,
            "min": self.min,
            "max": self.max,
            "hardMin": self.hard_min,
            "hardMax": self.hard_max,
            "step": self.step,
            "options": list(self.options),
            "requiresRestart": self.requires_restart,
            "safetyCritical": self.safety_critical,
        }


@dataclass(frozen=True)
class ParameterGroup:
    id: str
    label: str
    description: str


PARAMETER_GROUPS: tuple[ParameterGroup, ...] = (
    ParameterGroup("limits", "Лимиты и скорость", "Физические и мягкие пределы хода, ограничения скорости."),
    ParameterGroup("homing", "Поиск границ", "Двухпроходный поиск парных нижних и верхних датчиков."),
    ParameterGroup("profiles", "Профили движения", "Скорость, ускорение, плавность и момент для сценариев движения."),
    ParameterGroup("compensation", "Компенсации", "Вес грифа, трение, инерция ШВП, люфт."),
    ParameterGroup("start", "Стартовое положение и удержание", "Подвод в стартовую точку, натяг, детекция захвата, парковка."),
    ParameterGroup("sync", "Синхронизация сторон", "Пороги рассинхрона, регулятор выравнивания, реакция на перекос."),
    ParameterGroup("load", "Нагрузка", "Пересчёт кг в момент, режимы нагрузки, ramp, кривые."),
    ParameterGroup("detection", "Детекция повторов и отказа", "Гистерезис повторов, застревание, отказ, страховка."),
    ParameterGroup("safety", "Безопасность", "Пороги тока и температуры, таймауты, heartbeat, препятствие."),
    ParameterGroup("regulator", "Регулятор", "Коэффициенты контура, фильтры, демпфирование."),
    ParameterGroup("screw", "ШВП и энкодер", "Шаг, передаточное отношение, инверсия сторон, тип энкодера."),
    ParameterGroup("fixed", "Фиксированная позиция", "Удержание грифа как турника или упора."),
)


def _num(
    key: str,
    group: str,
    label: str,
    description: str,
    default: float,
    unit: str = "",
    *,
    min: float | None = None,  # noqa: A002
    max: float | None = None,  # noqa: A002
    hard_min: float | None = None,
    hard_max: float | None = None,
    step: float | None = None,
    integer: bool = False,
    restart: bool = False,
    critical: bool = False,
) -> ParameterSpec:
    return ParameterSpec(
        key=key,
        group=group,
        label=label,
        description=description,
        type="integer" if integer else "number",
        default=default,
        unit=unit,
        min=min,
        max=max,
        hard_min=hard_min if hard_min is not None else min,
        hard_max=hard_max if hard_max is not None else max,
        step=step,
        requires_restart=restart,
        safety_critical=critical,
    )


def _bool(key: str, group: str, label: str, description: str, default: bool, *, critical: bool = False, restart: bool = False) -> ParameterSpec:
    return ParameterSpec(key=key, group=group, label=label, description=description, type="boolean", default=default, safety_critical=critical, requires_restart=restart)


def _enum(key: str, group: str, label: str, description: str, default: str, options: tuple[str, ...], *, critical: bool = False) -> ParameterSpec:
    return ParameterSpec(key=key, group=group, label=label, description=description, type="enum", default=default, options=options, safety_critical=critical)


def _profile(name: str, label: str, speed: float, accel: float, jerk: float, torque: int) -> tuple[ParameterSpec, ...]:
    return (
        _num(f"profile.{name}.speedMmPerSec", "profiles", f"{label}: скорость", "Максимальная скорость автоматического движения в этом профиле.", speed, "мм/с", min=1, max=1500, hard_max=1500, step=5),
        _num(f"profile.{name}.accelMmPerSec2", "profiles", f"{label}: ускорение", "Ускорение разгона и торможения.", accel, "мм/с²", min=10, max=5000, step=10),
        _num(f"profile.{name}.jerkMmPerSec3", "profiles", f"{label}: плавность", "Ограничение рывка (изменения ускорения).", jerk, "мм/с³", min=10, max=50000, step=50),
        _num(f"profile.{name}.torqueLimitPercent", "profiles", f"{label}: момент", "Ограничение момента приводов в процентах от номинала.", torque, "%", min=1, max=100, hard_max=100, step=1, integer=True, critical=True),
    )


PARAMETER_SPECS: tuple[ParameterSpec, ...] = (
    # --- limits -----------------------------------------------------------
    _num("limits.workingMinMm", "limits", "Физический минимум", "Абсолютно запрещённая зона снизу (концевик).", 0, "мм", min=0, max=500, critical=True),
    _num("limits.workingMaxMm", "limits", "Физический максимум", "Абсолютно запрещённая зона сверху.", 1850, "мм", min=500, max=2100, hard_max=2100, critical=True),
    _num("limits.softMinMm", "limits", "Мягкий нижний лимит", "Ниже система не заходит в обычном режиме.", 50, "мм", min=0, max=600, critical=True),
    _num("limits.softMaxMm", "limits", "Мягкий верхний лимит", "Выше система не заходит в обычном режиме.", 1800, "мм", min=500, max=2100, hard_max=2100, critical=True),
    _num("limits.decelZoneMm", "limits", "Зона замедления у границ", "Ширина зоны перед границей диапазона, где скорость плавно снижается.", 60, "мм", min=0, max=300, step=5),
    _num("limits.maxSpeedMmPerSec", "limits", "Макс. скорость грифа", "Абсолютное ограничение скорости в любом режиме.", 800, "мм/с", min=50, max=1500, hard_max=1500, step=10, critical=True),
    _num("limits.maxDescentSpeedMmPerSec", "limits", "Макс. скорость опускания", "Гриф под нагрузкой никогда не опускается быстрее этого значения.", 600, "мм/с", min=20, max=1500, hard_max=1500, step=10, critical=True),
    _num("limits.maxUserSpeedMmPerSec", "limits", "Порог скорости пользователя", "Превышение вызывает подтормаживание и предупреждение.", 1000, "мм/с", min=50, max=1500, step=10),
    # --- homing -----------------------------------------------------------
    _bool("homing.limitSwitchesEnabled", "homing", "Концевые датчики установлены", "ВЫКЛ — при следующем запуске гриф должен стоять в крайнем нижнем положении; энкодеры обнуляются без перемещения. Требуется перезапуск тренажёра.", True, critical=True, restart=True),
    _num("homing.coarseSpeedMmPerSec", "homing", "Грубый поиск", "Скорость первого подхода к границе.", 40, "мм/с", min=1, max=200, step=1, critical=True),
    _num("homing.creepSpeedMmPerSec", "homing", "Controlled creep", "Скорость после первого датчика пары.", 8, "мм/с", min=0.5, max=40, step=0.5, critical=True),
    _num("homing.fineSpeedMmPerSec", "homing", "Точный подход", "Скорость повторного подхода после отъезда.", 4, "мм/с", min=0.5, max=30, step=0.5, critical=True),
    _num("homing.backoffSpeedMmPerSec", "homing", "Скорость отъезда", "Скорость освобождения парных датчиков.", 12, "мм/с", min=0.5, max=60, step=0.5, critical=True),
    _num("homing.backoffDistanceMm", "homing", "Дистанция отъезда", "Минимальный отъезд перед точным подходом.", 8, "мм", min=1, max=50, step=0.5, critical=True),
    _num("homing.releaseDistanceMm", "homing", "Предел освобождения", "Максимальный отъезд для отпускания обоих датчиков.", 20, "мм", min=2, max=100, step=0.5, critical=True),
    _num("homing.stopSettleMs", "homing", "Пауза перед отъездом", "Время торможения после подтверждения пары.", 100, "мс", min=0, max=2000, step=10, integer=True, critical=True),
    _num("homing.pairTimeWindowMs", "homing", "Окно пары по времени", "Максимальная задержка второго датчика пары.", 250, "мс", min=10, max=2000, step=10, integer=True, critical=True),
    _num("homing.pairDistanceWindowMm", "homing", "Окно пары по пути", "Максимальный путь после первого датчика пары.", 4, "мм", min=0.1, max=30, step=0.1, critical=True),
    _num("homing.releaseTimeoutMs", "homing", "Таймаут отпускания", "Максимальное время освобождения обоих датчиков при отъезде.", 3000, "мс", min=100, max=15000, step=100, integer=True, critical=True),
    _num("homing.phaseTimeoutSec", "homing", "Таймаут фазы", "Максимальное время отдельной фазы поиска.", 60, "с", min=1, max=180, step=1, critical=True),
    _num("homing.totalTimeoutSec", "homing", "Общий таймаут", "Максимальное время полного поиска двух границ.", 150, "с", min=10, max=600, step=5, critical=True),
    _num("homing.maximumSearchDistanceMm", "homing", "Предел пути фазы", "Максимальный путь в одной фазе поиска.", 2200, "мм", min=100, max=4000, step=10, critical=True),
    _num("homing.bottomOffsetMm", "homing", "Нижний рабочий отступ", "Отступ рабочего минимума от физической нижней границы.", 5, "мм", min=0, max=200, step=0.5, critical=True),
    _num("homing.topOffsetMm", "homing", "Верхний рабочий отступ", "Отступ рабочего максимума от физической верхней границы.", 5, "мм", min=0, max=200, step=0.5, critical=True),
    _num("homing.targetToleranceMm", "homing", "Допуск безопасной позиции", "Допуск остановки у рабочего верхнего отступа.", 1.5, "мм", min=0.2, max=10, step=0.1, critical=True),
    # --- profiles ---------------------------------------------------------
    *_profile("training", "Тренировка", 800, 1500, 8000, 100),
    *_profile("calibration", "Калибровка", 20, 100, 500, 20),
    *_profile("rangePreview", "Показ диапазона", 15, 80, 400, 15),
    *_profile("service", "Сервис", 10, 60, 300, 15),
    *_profile("return", "Возврат / подвод", 60, 200, 1000, 30),
    *_profile("guest", "Гостевой режим", 300, 600, 3000, 50),
    # --- compensation -----------------------------------------------------
    _bool("compensation.gravityEnabled", "compensation", "Компенсация веса грифа", "Двигатели держат вес грифа и подвижных частей.", True),
    _num("compensation.barMassKg", "compensation", "Масса грифа", "Масса грифа, измеряется мастером.", 20.0, "кг", min=0, max=80, step=0.1),
    _num("compensation.movingPartsMassKg", "compensation", "Масса подвижных частей", "Каретки, гайки и крепёж на обеих сторонах.", 6.0, "кг", min=0, max=60, step=0.1),
    _num("compensation.gravityGain", "compensation", "Доля компенсации веса", "100 % — гриф невесомый; меньше — часть веса остаётся.", 100, "%", min=0, max=100, hard_max=100, step=1, integer=True),
    _bool("compensation.frictionEnabled", "compensation", "Компенсация трения", "Учитывать трение направляющих и ШВП.", True),
    _num("compensation.frictionUpKg", "compensation", "Трение при подъёме", "Эквивалент трения, добавляемый при движении вверх.", 1.5, "кг", min=0, max=20, step=0.1),
    _num("compensation.frictionDownKg", "compensation", "Трение при опускании", "Эквивалент трения при движении вниз.", 1.2, "кг", min=0, max=20, step=0.1),
    _bool("compensation.inertiaEnabled", "compensation", "Компенсация инерции ШВП", "Feed-forward по ускорению для винта и роторов.", True),
    _num("compensation.equivalentMassKg", "compensation", "Приведённая масса ШВП", "Инерция винт+ротор+гайка, приведённая к линейной массе (обе стороны).", 4.0, "кг", min=0, max=40, step=0.1),
    _num("compensation.inertiaGain", "compensation", "Доля компенсации инерции", "Часть расчётного инерционного усилия, которую компенсируем.", 100, "%", min=0, max=150, hard_max=150, step=1, integer=True),
    _num("compensation.inertiaMaxKg", "compensation", "Предел компенсации инерции", "Ограничение компенсирующего усилия.", 15.0, "кг", min=0, max=60, step=0.5, critical=True),
    _num("compensation.reversalZoneMm", "compensation", "Зона разворота", "Ширина зоны у границ, где момент переходит по S-кривой.", 30, "мм", min=0, max=200, step=1),
    _num("compensation.backlashMm", "compensation", "Люфт ШВП", "Мёртвый ход при реверсе, компенсируется в позиционировании.", 0.3, "мм", min=0, max=5, step=0.05),
    # --- start ------------------------------------------------------------
    _num("start.holdTorquePercent", "start", "Натяг в стартовой точке", "Момент удержания грифа до захвата пользователем.", 15, "%", min=0, max=60, step=1, integer=True),
    _num("start.holdToleranceMm", "start", "Допуск удержания", "Отклонение от стартовой точки, считающееся удержанием.", 5, "мм", min=1, max=50, step=1),
    _num("start.gripDetectDeltaMm", "start", "Захват: смещение", "Смещение грифа, по которому детектируется захват.", 4, "мм", min=1, max=50, step=0.5),
    _num("start.gripDetectForceKg", "start", "Захват: усилие", "Усилие пользователя, по которому детектируется захват.", 3.0, "кг", min=0.2, max=30, step=0.1),
    _num("start.confirmCountdownSec", "start", "Обратный отсчёт", "Задержка перед автоматическим подводом в стартовую точку.", 3, "с", min=0, max=10, step=0.5),
    _num("start.parkPositionMm", "start", "Парковочная позиция", "Куда уходит гриф после тренировки/простоя.", 300, "мм", min=0, max=2100, step=10),
    _num("start.holdTimeoutSec", "start", "Таймаут удержания без пользователя", "После этого времени без захвата гриф паркуется.", 30, "с", min=5, max=600, step=5),
    # --- sync -------------------------------------------------------------
    _enum("sync.mode", "sync", "Схема синхронизации", "Ведущий+ведомый или параллельное управление с коррекцией.", "master_slave", ("master_slave", "parallel")),
    _num("sync.normMm", "sync", "Норма", "До этого значения рассинхрон считается нормой.", 2, "мм", min=0.5, max=20, step=0.5),
    _num("sync.warningMm", "sync", "Предупреждение", "Выше — предупреждение и усиленная коррекция.", 5, "мм", min=1, max=30, step=0.5, critical=True),
    _num("sync.criticalMm", "sync", "Критично", "Выше — срабатывает desyncAction, запуск заблокирован.", 8, "мм", min=2, max=40, hard_max=40, step=0.5, critical=True),
    _num("sync.correctionGain", "sync", "Коэффициент коррекции", "Насколько сильно ведомая сторона подтягивается к ведущей.", 0.8, "", min=0, max=5, step=0.05),
    _num("sync.correctionMaxMmPerSec", "sync", "Предел скорости коррекции", "Максимальная скорость выравнивания сторон.", 20, "мм/с", min=1, max=200, step=1),
    _enum("sync.desyncAction", "sync", "Действие при критическом рассинхроне", "Замедлить, удержать позицию или аварийный стоп.", "hold", ("slow", "hold", "estop"), critical=True),
    _num("sync.asymmetryTolerancePercent", "sync", "Допуск асимметрии усилий", "Разница усилий сторон, выше которой показывается предупреждение.", 30, "%", min=5, max=100, step=1, integer=True),
    # --- load -------------------------------------------------------------
    _num("load.kgToTorqueFactor", "load", "Коэффициент кг → момент", "Калибровочный коэффициент пересчёта нагрузки в момент.", 1.0, "", min=0.2, max=5, step=0.01),
    _num("load.changeRateKgPerSec", "load", "Скорость изменения нагрузки", "Ограничение скорости изменения нагрузки во время подхода.", 10, "кг/с", min=0.5, max=100, step=0.5),
    _num("load.rampInSec", "load", "Нарастание нагрузки", "Время плавного выхода на заданную нагрузку в начале подхода.", 0.6, "с", min=0, max=5, step=0.1),
    _num("load.rampOutSec", "load", "Сброс нагрузки", "Время плавного снятия нагрузки в конце подхода.", 0.6, "с", min=0, max=5, step=0.1),
    _num("load.negativePhaseFactor", "load", "Коэффициент негативной фазы", "Множитель нагрузки на опускании в режиме negative_phase.", 1.3, "", min=1, max=2, hard_max=2, step=0.05, critical=True),
    _num("load.assistUpFactor", "load", "Доля нагрузки при помощи вверх", "Множитель нагрузки на подъёме в режиме assist_up.", 0.6, "", min=0, max=1, step=0.05),
    _num("load.lightModeFactor", "load", "Множитель лёгкого режима", "Снижение нагрузки в light_mode.", 0.5, "", min=0.1, max=1, step=0.05),
    _num("load.warmupFactor", "load", "Множитель разминки", "Доля рабочего веса для разминочных сетов.", 0.5, "", min=0.2, max=1, step=0.05),
    _num("load.maxKg", "load", "Макс. нагрузка", "Абсолютный лимит нагрузки на уровне привода.", 150, "кг", min=10, max=300, hard_max=300, step=1, critical=True),
    _num("load.guestMaxKg", "load", "Лимит гостя", "Максимальная нагрузка в гостевом режиме.", 60, "кг", min=5, max=300, step=1, critical=True),
    _num("load.isokineticSpeedMmPerSec", "load", "Скорость изокинетики", "Постоянная скорость в изокинетическом режиме.", 150, "мм/с", min=20, max=800, step=5),
    _enum("load.forceSource", "load", "Источник усилия", "Оценка усилия пользователя по току или по тензодатчику.", "current", ("current", "load_cell")),
    _num("load.forceFilterHz", "load", "Фильтр усилия", "Частота среза фильтра оценки усилия.", 10, "Гц", min=1, max=100, step=1),
    _enum("load.curve", "load", "Кривая нагрузки", "Изменение нагрузки по диапазону движения.", "constant", ("constant", "band", "chain", "descending")),
    _num("load.curveDepthPercent", "load", "Глубина кривой", "Насколько нагрузка меняется от нижней к верхней точке.", 30, "%", min=0, max=100, step=5, integer=True),
    # --- detection --------------------------------------------------------
    _num("detection.repHysteresisMm", "detection", "Гистерезис повтора", "Зона у границ, вход в которую засчитывает фазу повтора.", 15, "мм", min=1, max=100, step=1),
    _num("detection.fullRepPercent", "detection", "Полный повтор", "Минимальная амплитуда полного повтора.", 85, "%", min=50, max=100, step=1, integer=True),
    _num("detection.partialRepPercent", "detection", "Частичный повтор", "Амплитуда, выше которой считается частичный повтор.", 40, "%", min=10, max=90, step=1, integer=True),
    _num("detection.stallTimeoutSec", "detection", "Таймаут застревания", "Гриф под нагрузкой не движется дольше — предлагается помощь.", 2.5, "с", min=0.5, max=15, step=0.1),
    _num("detection.stallSpeedMmPerSec", "detection", "Скорость застревания", "Скорость ниже которой движение считается остановленным.", 5, "мм/с", min=0.5, max=50, step=0.5),
    _num("detection.failureDescentSpeedMmPerSec", "detection", "Скорость опускания при отказе", "Быстрее (при усилии меньше нагрузки) — потеря контроля, включается спасение.", 450, "мм/с", min=50, max=1500, step=10, critical=True),
    _num("detection.releaseForceKg", "detection", "Усилие отпускания", "Ниже этого усилия гриф считается отпущенным.", 1.0, "кг", min=0, max=20, step=0.1),
    _num("detection.releaseTimeoutSec", "detection", "Время до фиксации отпускания", "Сколько секунд без усилия нужно, чтобы перейти в удержание.", 1.0, "с", min=0.1, max=10, step=0.1),
    _bool("detection.spotterEnabled", "detection", "Страховщик", "Автоматическая помощь при отказе на подъёме.", True, critical=True),
    _num("detection.spotterAssistPercent", "detection", "Доля помощи страховщика", "Какую часть нагрузки снимает страховщик.", 50, "%", min=0, max=100, step=5, integer=True),
    _num("detection.spotterDelaySec", "detection", "Задержка страховщика", "Через сколько секунд застревания срабатывает помощь.", 1.5, "с", min=0.2, max=10, step=0.1),
    _enum("detection.onTargetReached", "detection", "При достижении цели подхода", "Продолжать счёт, удерживать или снять нагрузку.", "continue", ("continue", "hold", "unload")),
    # --- safety -----------------------------------------------------------
    _num("safety.currentWarnA", "safety", "Ток: предупреждение", "Ток привода, при котором показывается предупреждение.", 8.0, "А", min=1, max=50, step=0.1, critical=True),
    _num("safety.currentMaxA", "safety", "Ток: остановка", "Ток привода, при котором движение останавливается.", 12.0, "А", min=1, max=60, hard_max=60, step=0.1, critical=True),
    _num("safety.tempWarnC", "safety", "Температура: предупреждение", "Температура привода для предупреждения.", 65, "°C", min=30, max=120, step=1, critical=True),
    _num("safety.tempMaxC", "safety", "Температура: остановка", "Температура привода, при которой движение блокируется.", 80, "°C", min=40, max=130, hard_max=130, step=1, critical=True),
    _num("safety.heartbeatTimeoutMs", "safety", "Heartbeat backend → приводы", "Без heartbeat приводы сами переходят в удержание.", 500, "мс", min=50, max=5000, step=10, integer=True, critical=True),
    _num("safety.commTimeoutMs", "safety", "Таймаут связи", "Таймаут ответа привода.", 100, "мс", min=10, max=2000, step=10, integer=True),
    _num("safety.commRetryCount", "safety", "Повторов при ошибке связи", "После исчерпания — безопасное состояние.", 3, "", min=0, max=10, step=1, integer=True),
    _num("safety.obstacleForceKg", "safety", "Порог препятствия", "Рост усилия без движения при автоматических перемещениях → остановка.", 8.0, "кг", min=1, max=60, step=0.5, critical=True),
    _num("safety.holdOverloadKg", "safety", "Перегрузка удержания", "Нагрузка на удержании выше — предупреждение.", 160, "кг", min=20, max=400, step=5, critical=True),
    _num("safety.idleTimeoutMin", "safety", "Таймаут простоя", "После простоя — парковка и отключение приводов.", 10, "мин", min=1, max=120, step=1, integer=True),
    _bool("safety.postRequired", "safety", "POST обязателен", "Без успешного самотеста запуск блокируется.", True, critical=True),
    _bool("safety.homingRequiredAfterPowerLoss", "safety", "Homing после пропадания питания", "Позиция неизвестна до homing.", True, critical=True),
    _num("safety.torqueRateLimitPercentPerSec", "safety", "Ограничение скорости изменения момента", "Защита от рывков и автоколебаний.", 300, "%/с", min=10, max=2000, step=10, integer=True),
    # --- regulator --------------------------------------------------------
    _num("regulator.positionKp", "regulator", "Kp позиции", "Жёсткость удержания позиции (кг на мм отклонения).", 2.0, "кг/мм", min=0.05, max=20, step=0.05),
    _num("regulator.positionKd", "regulator", "Kd позиции", "Демпфирование удержания (кг на мм/с).", 0.08, "кг·с/мм", min=0, max=2, step=0.005),
    _num("regulator.velocityKv", "regulator", "Kv скорости", "Коэффициент слежения за скоростью в автоматических перемещениях.", 0.15, "кг·с/мм", min=0.005, max=2, step=0.005),
    _num("regulator.velocityFilterHz", "regulator", "Фильтр скорости", "Частота среза фильтра оценки скорости.", 20, "Гц", min=1, max=200, step=1),
    _num("regulator.calibrationDampingKgPerMmPerSec", "regulator", "Демпфирование «невесомого грифа»", "Вязкое сопротивление, чтобы гриф не гулял от касания.", 0.06, "кг·с/мм", min=0, max=1, step=0.005),
    _num("regulator.calibrationMaxSpeedMmPerSec", "regulator", "Скорость руки в калибровке", "Выше — усиленное демпфирование.", 150, "мм/с", min=10, max=800, step=5),
    _num("regulator.weightlessMaxDriftMmPerSec", "regulator", "Допустимый дрейф невесомого грифа", "Дрейф без усилия пользователя дольше 0,5 с — переход в удержание.", 60, "мм/с", min=1, max=300, step=1, critical=True),
    _num("regulator.stillnessMs", "regulator", "Неподвижность для фиксации точки", "Гриф должен быть неподвижен столько мс перед «Зафиксировать».", 500, "мс", min=100, max=5000, step=50, integer=True),
    # --- screw ------------------------------------------------------------
    _num("screw.pitchMmPerRev", "screw", "Шаг ШВП", "Миллиметров за оборот.", 32, "мм/об", min=1, max=100, step=0.5, restart=True),
    _num("screw.gearRatio", "screw", "Передаточное отношение", "Ремень/редуктор между двигателем и винтом.", 1.0, "", min=0.1, max=20, step=0.01, restart=True),
    _bool("screw.leftDirectionInverted", "screw", "Инверсия левой стороны", "Направление вращения левого ШВП.", False),
    _bool("screw.rightDirectionInverted", "screw", "Инверсия правой стороны", "Направление вращения правого ШВП.", True),
    _num("screw.travelLengthMm", "screw", "Длина хода", "Полная длина ШВП.", 2000, "мм", min=500, max=3000, step=10, restart=True),
    _enum("screw.encoderType", "screw", "Тип энкодера", "Инкрементальный требует homing после каждого включения.", "incremental", ("absolute", "incremental")),
    _num("screw.encoderDriftAlarmMm", "screw", "Порог дрейфа энкодера", "Расхождение позиции с ожидаемой, при котором останавливаемся.", 6, "мм", min=1, max=50, step=0.5, critical=True),
    # --- fixed ------------------------------------------------------------
    _num("fixed.torquePercent", "fixed", "Момент удержания", "Момент в режиме фиксированной позиции.", 100, "%", min=20, max=100, hard_max=100, step=1, integer=True),
    _num("fixed.driftToleranceMm", "fixed", "Допуск дрейфа", "Отклонение позиции, выше которого регулятор подстраивается и предупреждает.", 2, "мм", min=0.5, max=20, step=0.5),
    _num("fixed.holdTestSec", "fixed", "Тест удержания", "Длительность теста удержания перед разрешением старта.", 2, "с", min=0.5, max=10, step=0.5),
    _num("fixed.gripHeightMarginMm", "fixed", "Запас высоты турника", "Добавка к росту с вытянутой рукой для пресета «Турник».", 50, "мм", min=0, max=300, step=10),
)

_SPEC_INDEX: dict[str, ParameterSpec] = {spec.key: spec for spec in PARAMETER_SPECS}


class ParameterValidationError(ValueError):
    pass


def get_spec(key: str) -> ParameterSpec:
    try:
        return _SPEC_INDEX[key]
    except KeyError as error:
        raise ParameterValidationError(f"Неизвестный параметр: {key}") from error


def coerce_value(spec: ParameterSpec, raw: Any) -> Any:
    if spec.type == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw)
    if spec.type == "enum":
        value = str(raw)
        if value not in spec.options:
            raise ParameterValidationError(f"{spec.key}: значение '{value}' не входит в {list(spec.options)}")
        return value
    try:
        number = float(raw)
    except (TypeError, ValueError) as error:
        raise ParameterValidationError(f"{spec.key}: ожидается число") from error
    if spec.hard_min is not None and number < spec.hard_min:
        raise ParameterValidationError(f"{spec.key}: {number} ниже жёсткого предела {spec.hard_min}")
    if spec.hard_max is not None and number > spec.hard_max:
        raise ParameterValidationError(f"{spec.key}: {number} выше жёсткого предела {spec.hard_max}")
    if spec.type == "integer":
        return int(round(number))
    return number


@dataclass
class MotionParameters:
    """Effective parameter values = persisted values + temporary overrides."""

    persisted: dict[str, Any] = field(default_factory=dict)
    temporary: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        if key in self.temporary:
            return self.temporary[key]
        if key in self.persisted:
            return self.persisted[key]
        return get_spec(key).default

    def effective(self) -> dict[str, Any]:
        return {spec.key: self.get(spec.key) for spec in PARAMETER_SPECS}

    def set_many(self, values: dict[str, Any], *, temporary: bool) -> dict[str, tuple[Any, Any]]:
        """Validate and apply values. Returns {key: (old, new)} for audit."""

        changes: dict[str, tuple[Any, Any]] = {}
        validated = {key: coerce_value(get_spec(key), raw) for key, raw in values.items()}
        self._validate_relations({**self.effective(), **validated})
        target = self.temporary if temporary else self.persisted
        for key, value in validated.items():
            old = self.get(key)
            target[key] = value
            if not temporary:
                self.temporary.pop(key, None)
            if old != value:
                changes[key] = (old, value)
        return changes

    def revert_temporary(self) -> list[str]:
        keys = list(self.temporary.keys())
        self.temporary.clear()
        return keys

    def reset_to_defaults(self) -> None:
        self.persisted.clear()
        self.temporary.clear()

    def load_persisted(self, values: dict[str, Any]) -> None:
        self.persisted = {}
        for key, raw in values.items():
            if key not in _SPEC_INDEX:
                continue
            try:
                self.persisted[key] = coerce_value(_SPEC_INDEX[key], raw)
            except ParameterValidationError:
                continue

    @staticmethod
    def _validate_relations(values: dict[str, Any]) -> None:
        if values["limits.softMinMm"] < values["limits.workingMinMm"]:
            raise ParameterValidationError("Мягкий нижний лимит не может быть ниже физического минимума")
        if values["limits.softMaxMm"] > values["limits.workingMaxMm"]:
            raise ParameterValidationError("Мягкий верхний лимит не может быть выше физического максимума")
        if values["limits.softMinMm"] >= values["limits.softMaxMm"]:
            raise ParameterValidationError("Мягкий нижний лимит должен быть меньше верхнего")
        if not values["sync.normMm"] <= values["sync.warningMm"] <= values["sync.criticalMm"]:
            raise ParameterValidationError("Пороги рассинхрона должны идти по возрастанию: норма ≤ предупреждение ≤ критично")
        if values["safety.currentWarnA"] > values["safety.currentMaxA"]:
            raise ParameterValidationError("Ток предупреждения не может быть выше тока остановки")
        if values["safety.tempWarnC"] > values["safety.tempMaxC"]:
            raise ParameterValidationError("Температура предупреждения не может быть выше температуры остановки")
        if values["detection.partialRepPercent"] >= values["detection.fullRepPercent"]:
            raise ParameterValidationError("Порог частичного повтора должен быть меньше порога полного")
        if values["load.guestMaxKg"] > values["load.maxKg"]:
            raise ParameterValidationError("Лимит гостя не может превышать общий лимит нагрузки")
        if values["homing.backoffDistanceMm"] > values["homing.releaseDistanceMm"]:
            raise ParameterValidationError("Дистанция отъезда не может превышать предел освобождения датчиков")
        if values["homing.totalTimeoutSec"] <= values["homing.phaseTimeoutSec"]:
            raise ParameterValidationError("Общий таймаут homing должен быть больше таймаута отдельной фазы")


def schema_payload() -> dict[str, Any]:
    return {
        "groups": [{"id": group.id, "label": group.label, "description": group.description} for group in PARAMETER_GROUPS],
        "parameters": [spec.to_payload() for spec in PARAMETER_SPECS],
    }
