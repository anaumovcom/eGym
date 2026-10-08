"""Calibration catalog and dependency graph (plan 15 §2–3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.motor.profile import MachineProfile

Status = Literal["actual", "missing", "planned"]


@dataclass(frozen=True)
class CalibrationSpec:
    code: str
    group: str
    title: str
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    implemented: bool
    hardware: bool = True  # needs the machine and an operator (dead-man)
    description: str = ""
    steps: tuple[str, ...] = ()
    duration_s: int | None = None  # typical, for the UI
    inputs: tuple[str, ...] = ()  # operator values for the start request, e.g. "referenceKg"
    min_points: int = 1  # gravity_map points needed to call the result actual (S7: a map, not one point)


GROUPS = {
    "B": "Привод и шина",
    "S": "Статика: вес и трение",
    "D": "Динамика",
    "C": "Устойчивость управления",
    "G": "Проверка точности",
    "W": "Мастер",
}

CATALOG: tuple[CalibrationSpec, ...] = (
    CalibrationSpec(
        "B0", "B", "Конфигурация привода", (), (), True,
        description="Читает параметры пусконаладки обоих Lichuan A6 и сверяет их с эталоном: режим момента, абсолютный энкодер, SRV-ON по связи, нет аварии, пределы момента и скорости. Ничего не пишет и не двигает — только отчёт «ок / что поправить с панели драйвера».",
        steps=(
            "Регистры PA_1C9, PA_002, PA_00B, PA_08F, PA_090, PA_080, PA_1A0, PA_093, PA_05E, PA_056 читаются с каждого привода.",
            "Каждое значение сравнивается с эталоном; расхождения — списком в отчёте.",
        ),
        duration_s=3,
    ),
    CalibrationSpec(
        "B1", "B", "Тайминг шины", ("B0",), ("loop_period_s", "jitter_p95_s"), True,
        description="Измеряет реальный период цикла «чтение обеих сторон → запись команды» по RS-485 и его разброс. Задержка и джиттер шины ограничивают жёсткость удержания и точность динамических калибровок.",
        steps=(
            "Гриф лежит на упорах на поддержке, движения нет.",
            "200 циклов подряд: чтение телеметрии обеих сторон и запись команды, как в рабочем режиме.",
            "Результат: средний период, p50/p95/p99, опоздавшие кадры; критерий p99 < 2·p50.",
        ),
        duration_s=12,
    ),
    CalibrationSpec(
        "B5", "B", "Направление мотора и энкодера", ("B0",), ("left.direction_sign", "right.direction_sign"), True,
        description="Определяет, какой знак момента поднимает каждую сторону, и что энкодер считает в ту же сторону. Без этого поддержка может давить гриф вниз.",
        steps=(
            "Гриф лежит на нижних упорах, руки убраны от грифа.",
            "На обе стороны плавно подаётся момент «+» до отрыва на 0,5 мм, затем гриф опускается на упоры.",
            "Стороны, которые не поднялись, пробуются моментом «−».",
            "Сравнивается направление момента и счёта энкодера.",
        ),
        duration_s=20,
    ),
    CalibrationSpec(
        "B7", "B", "Абсолютный ноль", ("S3",), ("left.zero_counts", "right.zero_counts"), True,
        description="Запоминает показания абсолютного энкодера на нижних упорах как ноль хода. После сохранения позиция считается от упоров, даже если при включении гриф был поднят. Повторный запуск после цикла питания показывает дрейф нуля (критерий < 0,1 мм).",
        steps=(
            "Гриф плавно опускается на упоры (если висел на поддержке) и прижимается к ним.",
            "2 с читаются сырые показания энкодера PA_1BC/1BD обеих сторон.",
            "Среднее — новый ноль; в отчёте — сдвиг относительно текущего и предыдущего нуля.",
        ),
        duration_s=10,
    ),
    CalibrationSpec(
        "S3", "S", "Окно невесомости: баланс и сухое трение", ("B5",), ("left.gravity_map", "left.coulomb_up_n", "left.coulomb_down_n", "right.gravity_map", "right.coulomb_up_n", "right.coulomb_down_n"), True,
        description="Находит силу, при которой гриф трогается вверх и вниз. Середина окна — вес грифа (баланс), половина ширины — сухое трение. Это основа «невесомости» и всех режимов нагрузки.",
        steps=(
            "Гриф отрывается от упоров и останавливается на высоте ~10 мм.",
            "Сила медленно уменьшается до трогания вниз, гриф ловится.",
            "Сила медленно увеличивается до трогания вверх, гриф ловится.",
            "Цикл вниз/вверх повторяется 3 раза, результат — среднее ± 95 % доверительный интервал.",
        ),
        duration_s=180,
    ),
    CalibrationSpec(
        "S7", "S", "Карта по высоте", ("S3", "B7", "C3"), ("left.gravity_map", "right.gravity_map"), True,
        description="Повторяет измерение окна невесомости на 5 высотах от низа до верхнего программного предела: вес и трение меняются по ходу (перекос рельс, тугие места, кабель). Результат — карта веса W(x) вместо одной точки и среднее сухое трение по всему ходу.",
        steps=(
            "Гриф поднимается со скоростью ~30 мм/с к очередной высоте и останавливается.",
            "На каждой высоте — 2 цикла «трогание вниз / вверх», как в S3.",
            "После верхней точки гриф плавно опускается на упоры.",
            "Результат: W(x) для каждой стороны, наклон и отклонение от прямой (тугие места).",
        ),
        duration_s=480,
        min_points=3,
    ),
    CalibrationSpec(
        "S9", "S", "Шкала силы по эталонному грузу", ("S3",), ("left.n_per_raw", "right.n_per_raw"), True,
        description="Связывает единицы момента привода с ньютонами по известному грузу. Сдвиг баланса с грузом против сохранённого без груза даёт настоящий масштаб вместо паспортного (±15 %). Все силы профиля (вес, трение, масса) пересчитываются в новый масштаб.",
        steps=(
            "До запуска: повесить на гриф известный груз поровну на обе стороны (рекомендуется 20 кг) и ввести его массу. S3 должна быть выполнена с пустым грифом.",
            "Гриф с грузом отрывается на ~10 мм, 3 цикла «трогание вниз / вверх».",
            "Гриф опускается на упоры; груз можно снимать.",
            "Результат: новый сдвиг силы на единицу команды и пересчитанные силы профиля.",
        ),
        duration_s=150,
        inputs=("referenceKg",),
    ),
    CalibrationSpec(
        "D2", "D", "Трение в движении вверх", ("S3", "C3"), ("left.viscous_n_per_mm_s", "right.viscous_n_per_mm_s"), True,
        description="Вязкое трение — рост сопротивления со скоростью. Гриф поднимается постоянными силами чуть выше трогания; по скорости и ускорению уравнение движения решается методом наименьших квадратов: сила = кинетическое трение + c·v + m·a.",
        steps=(
            "Гриф поднимается на 20 мм.",
            "6 подъёмов силой «трогание + Δ» (Δ от 3 % до 40 % трения), каждый ≤ 60 мм или до 50 мм/с, между ними остановка.",
            "Гриф плавно опускается на упоры.",
            "Результат: вязкое трение c, кинетическое трение и оценка массы для сверки с D4.",
        ),
        duration_s=60,
    ),
    CalibrationSpec(
        "D4", "D", "Приведённая масса", ("D2",), ("left.moving_mass_kg", "right.moving_mass_kg"), True,
        description="Инерция грифа, каретки, винта и ротора, приведённая к каждой стороне. Нужна для компенсации инерции: без неё лёгкий вес ощущается «вязким» при рывке.",
        steps=(
            "Гриф поднимается на 50 мм.",
            "14 с качания силой за краями окна невесомости двумя амплитудами: скорость ≤ 40 мм/с, ход ±25 мм.",
            "Гриф останавливается и опускается на упоры.",
            "Результат: масса каждой стороны и кинетическое трение вверх/вниз.",
        ),
        duration_s=35,
    ),
    CalibrationSpec(
        "C1", "C", "Запас устойчивости удержания (relay)", ("S3",), ("hold_ultimate_k_n_per_mm", "hold_ultimate_period_s"), True,
        description="Релейный тест Острёма–Хэгглунда: гриф раскачивается на ±несколько мм вокруг точки, по амплитуде и периоду считается предельная жёсткость удержания с учётом реальной задержки шины. Рабочие коэффициенты удержания берутся как доля от неё.",
        steps=(
            "Если гриф на упорах — подъём на ~10 мм.",
            "Сила переключается между краями окна невесомости ± 6 Н, гриф совершает малые колебания 12 с.",
            "Если цикл нерегулярный — повтор с реле ± 12 Н.",
        ),
        duration_s=40,
    ),
    CalibrationSpec(
        "C3", "C", "Опускание поддержкой", ("S3",), ("left.support_raw", "right.support_raw"), True,
        description="Подбирает момент поддержки (вне тренировки, при СТОП и отпущенной кнопке удержания) так, чтобы гриф опускался сам со скоростью около 15 мм/с: не висел и не падал. Нужна перед калибровками, которые поднимают гриф высоко (S7, D2).",
        steps=(
            "Гриф поднимается на 120 мм.",
            "На приводы подаётся постоянная команда чуть ниже нижнего края окна; скорость опускания замеряется до 30 мм или 6 с.",
            "Команда подбирается удвоением и бисекцией (до 8 попыток); быстрее 40 мм/с — немедленная остановка.",
            "Результат: команда поддержки с ближайшей к 15 мм/с скоростью.",
        ),
        duration_s=120,
    ),
    CalibrationSpec(
        "G1", "G", "Статическая точность нагрузки", ("S9", "C1"), (), True,
        description="Проверка без изменения профиля: с эталонным грузом на грифе машина измеряет его вес по сдвигу баланса и сравнивает с введённой массой. Допуск — 5 % от груза на сторону, но не менее 0,5 кг.",
        steps=(
            "До запуска: повесить на гриф известный груз поровну на обе стороны и ввести его массу (лучше другой, чем в S9).",
            "Гриф с грузом отрывается на ~10 мм, 3 цикла «трогание вниз / вверх», затем опускается на упоры.",
            "Результат: измеренная масса по сторонам и погрешность; выход за допуск = проверка не пройдена.",
        ),
        duration_s=150,
        inputs=("referenceKg",),
    ),
)
BY_CODE = {spec.code: spec for spec in CATALOG}

WIZARD_STAGES = ("B5", "S3", "C1")
WIZARD = CalibrationSpec(
    "WIZARD", "W", "Мастер первичной настройки: B5 → S3 → C1", (), tuple(p for code in WIZARD_STAGES for p in BY_CODE[code].produces), True,
    description="Последовательно выполняет направление, окно невесомости и запас устойчивости. Каждый этап использует результат предыдущего; результат — один новый профиль.",
    steps=tuple(f"{code}: {BY_CODE[code].title}" for code in WIZARD_STAGES),
    duration_s=sum(BY_CODE[code].duration_s or 0 for code in WIZARD_STAGES),
)
RUNNABLE: dict[str, tuple[str, ...]] = {spec.code: (spec.code,) for spec in CATALOG if spec.implemented} | {"WIZARD": WIZARD_STAGES}


def _field(profile: MachineProfile, path: str):  # noqa: ANN202
    target: object = profile
    for part in path.split("."):
        target = getattr(target, part)
    return target


def status(profile: MachineProfile, spec: CalibrationSpec, verified: Mapping[str, str] | None = None) -> Status:
    """``verified``: code → time of the last passed run, for checks that produce no parameters (B0, G1)."""

    if not spec.implemented:
        return "planned"
    if not spec.produces:
        return "actual" if verified and spec.code in verified else "missing"
    fields = [_field(profile, path) for path in spec.produces]
    if not all(item.provenance == "measured" for item in fields):
        return "missing"
    if spec.min_points > 1 and any(len(item.value or ()) < spec.min_points for path, item in zip(spec.produces, fields, strict=True) if path.endswith("gravity_map")):
        return "missing"
    return "actual"


def _measured_at(profile: MachineProfile, spec: CalibrationSpec, verified: Mapping[str, str] | None = None) -> str | None:
    if not spec.produces:
        return (verified or {}).get(spec.code)
    stamps = [_field(profile, path).measured_at for path in spec.produces]
    return max((s for s in stamps if s), default=None)


def graph(profile: MachineProfile, verified: Mapping[str, str] | None = None) -> list[dict[str, object]]:
    return [
        {
            "code": spec.code,
            "group": spec.group,
            "groupTitle": GROUPS[spec.group],
            "title": spec.title,
            "description": spec.description,
            "steps": list(spec.steps),
            "durationS": spec.duration_s,
            "requires": list(spec.requires),
            "produces": list(spec.produces),
            "inputs": list(spec.inputs),
            "implemented": spec.implemented,
            "runnable": spec.code in RUNNABLE,
            "status": status(profile, spec, verified),
            "measuredAt": _measured_at(profile, spec, verified),
        }
        for spec in (WIZARD, *CATALOG)
    ]
