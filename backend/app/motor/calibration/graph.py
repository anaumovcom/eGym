"""Calibration catalog and dependency graph (plan 15 §2–3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.motor.profile import MachineProfile

Status = Literal["actual", "stale", "failed", "missing", "planned"]


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
    uses: tuple[str, ...] = ()  # calibrations whose values enter the fit: newer results make this one stale
    prepare: str = ""  # what the operator must do before the start


GROUPS = {
    "B": "Привод и шина",
    "S": "Статика: вес и трение",
    "M": "Перемещение",
    "D": "Динамика",
    "X": "Две стороны",
    "C": "Устойчивость управления",
    "G": "Проверка точности",
    "Q": "Ежедневный контроль",
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
        "B1", "B", "Тайминг шины и шум покоя", ("B0",), ("loop_period_s", "jitter_p95_s"), True,
        description="Измеряет реальный период цикла «чтение обеих сторон → запись команды» по RS-485 и его разброс, а заодно шум положения и скорости неподвижного грифа (B4). Задержка и джиттер шины ограничивают жёсткость удержания; шум покоя — порог детектора трогания.",
        steps=(
            "Гриф лежит на упорах на поддержке, движения нет.",
            "200 циклов подряд: чтение телеметрии обеих сторон и запись команды, как в рабочем режиме.",
            "Результат: средний период, p50/p95/p99, опоздавшие кадры (критерий p99 < 2·p50), шум положения и скорости (критерий < 0,05 мм).",
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
            "Гриф отрывается от упоров и останавливается на высоте ~30 мм.",
            "Сила медленно уменьшается до трогания вниз, гриф ловится.",
            "Сила медленно увеличивается до трогания вверх, гриф ловится.",
            "Цикл вниз/вверх повторяется 3 раза, результат — среднее ± 95 % доверительный интервал.",
        ),
        duration_s=180,
    ),
    CalibrationSpec(
        "M1", "M", "Отрыв от упоров", ("S3",), ("left.liftoff_extra_n", "right.liftoff_extra_n"), True,
        description="Сколько силы сверх окна невесомости нужно, чтобы оторвать гриф от нижних упоров после стоянки. Окно S3 измеряется в воздухе; на упорах гриф «прилипает» (смазка выдавлена, залипание тем сильнее, чем дольше стоял) — без этой добавки подъёмы с упоров не трогаются (C3: «гриф не трогается с места»). Результат — упреждающая добавка для всех подъёмов с упоров.",
        steps=(
            "Гриф опускается на упоры (если поднят) и стоит на них 3 с.",
            "Сила плавно растёт (6 Н/с) от чуть ниже верхнего края окна до отрыва каждой стороны.",
            "Сразу после отрыва сила — середина окна: гриф останавливается в нескольких мм.",
            "3 повтора; первый — после стоянки до запуска (обычно самый тяжёлый). Гриф опускается на упоры.",
        ),
        duration_s=60,
        uses=("S3", "S7"),
    ),
    CalibrationSpec(
        "M2", "M", "Управляемое перемещение", ("M1",), ("left.travel_extra_up_n", "right.travel_extra_up_n", "left.travel_extra_down_n", "right.travel_extra_down_n"), True,
        description="Сила сверх края окна, при которой гриф идёт вверх и вниз со скоростью 20 мм/с. С ней перемещения сразу выходят на скорость вместо долгого «раскачивания» регулятора и рывка после трогания. Показывает, насколько ровно держится скорость.",
        steps=(
            "Гриф поднимается на 40 мм.",
            "2 раза: подъём 40 → 160 мм и опускание 160 → 40 мм со скоростью 20 мм/с.",
            "На участках с установившейся скоростью усредняется сила сверх окна.",
            "Гриф опускается на упоры. Результат: добавка вверх / вниз по сторонам, точность скорости.",
        ),
        duration_s=90,
        uses=("S3", "S7", "M1"),
    ),
    CalibrationSpec(
        "M3", "M", "Торможение", ("M2",), ("brake_lag_s", "brake_decel_up_mm_s2", "brake_decel_down_mm_s2"), True,
        description="Тормозной путь грифа, когда сила переключается на середину окна невесомости (сухое трение тормозит). Путь = скорость × задержка + v²/(2·замедление), отдельно вверх и вниз. Перемещения начинают остановку заранее и встают в заданную точку без перелёта.",
        steps=(
            "Гриф поднимается на 40 мм.",
            "Для скоростей 15, 25 и 40 мм/с: разгон вверх до установившейся скорости → середина окна → замер пути до остановки; то же вниз от 180 мм.",
            "Гриф опускается на упоры.",
            "Результат: задержка торможения, замедление вверх и вниз, таблица путей.",
        ),
        duration_s=120,
        uses=("S3", "S7", "M2"),
    ),
    CalibrationSpec(
        "M4", "M", "Проверка перемещения", ("M3", "C3"), (), True,
        description="Проверка без изменения профиля: гриф перемещается на 80 → 150 → 50 → 120 → 30 мм со скоростью 20 мм/с. Ошибка остановки должна быть ≤ 5 мм, перекос сторон ≤ 5 мм. Если не проходит — повторите M2/M3 (или S3, если изменилось трение).",
        steps=(
            "5 перемещений на заданные высоты с остановкой.",
            "Для каждого: ошибка остановки, перелёт, перекос, время, максимальная скорость.",
            "Гриф опускается на упоры.",
        ),
        duration_s=90,
        uses=("S3", "S7", "M1", "M2", "M3"),
    ),
    CalibrationSpec(
        "S7", "S", "Карта по высоте", ("S3", "B7", "C3"), ("left.gravity_map", "right.gravity_map"), True,
        description="Повторяет измерение окна невесомости на 5 высотах от низа до верхнего программного предела (но не выше рабочего хода B8): вес и трение меняются по ходу (перекос рельс, тугие места, кабель). Результат — карта веса W(x) вместо одной точки и среднее сухое трение по всему ходу. После S7 нужно повторить D2: разделение трения покоя и движения сбрасывается.",
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
        description="Связывает единицы момента привода с ньютонами по известному грузу. Сдвиг баланса всего грифа с грузом против сохранённого без груза даёт настоящий масштаб вместо паспортного (±15 %). Стороны связаны грифом, поэтому масштаб считается по сумме сторон и применяется к обеим; раскладка по сторонам показывается для справки. Все силы профиля (вес, трение, масса, жёсткости) пересчитываются в новый масштаб.",
        steps=(
            "Гриф с грузом отрывается на ~10 мм, 3 цикла «трогание вниз / вверх».",
            "Гриф опускается на упоры; груз можно снимать.",
            "Результат: новый масштаб силы на единицу команды и пересчитанные силы профиля.",
        ),
        duration_s=150,
        inputs=("referenceKg",),
        prepare="Повесьте на гриф взвешенный груз поровну на обе стороны (рекомендуется 20 кг) и введите его массу. Баланс без груза (S3/S7) должен быть измерен с пустым грифом.",
    ),
    CalibrationSpec(
        "D2", "D", "Трение в движении вверх", ("S3", "C3"), ("left.viscous_n_per_mm_s", "right.viscous_n_per_mm_s", "left.stribeck_extra_n", "right.stribeck_extra_n"), True,
        description="Вязкое трение и трение покоя. Гриф поднимается постоянными силами чуть выше трогания; по скорости и ускорению уравнение движения решается методом наименьших квадратов: сила = трение движения + Штрибек + c·v + m·a. Разница между троганием (S3) и трением движения становится «добавкой трогания»: окно невесомости не меняется, а в движении мотор компенсирует меньшее трение — без этого гриф в движении кажется слишком лёгким.",
        steps=(
            "Гриф поднимается на 20 мм.",
            "6 подъёмов силой «трогание + Δ» (Δ от 3 % до 40 % трения), каждый ≤ 60 мм или до 50 мм/с, между ними остановка.",
            "Гриф плавно опускается на упоры.",
            "Результат: вязкое трение c, трение движения, добавка и скорость Штрибека, оценка массы для сверки с D4.",
        ),
        duration_s=60,
        uses=("S3", "S7"),
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
        uses=("D2",),
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
        "C3", "C", "Опускание поддержкой", ("S3", "M1"), ("left.support_raw", "right.support_raw"), True,
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
        "G1", "G", "Статическая точность нагрузки", ("S9",), (), True,
        description="Проверка без изменения профиля: с эталонным грузом на грифе машина измеряет его вес по сдвигу баланса всего грифа и сравнивает с введённой массой. Допуск — 5 % от груза, но не менее 0,5 кг. Раскладка по сторонам показывается для справки.",
        steps=(
            "Гриф с грузом отрывается на ~10 мм, 3 цикла «трогание вниз / вверх», затем опускается на упоры.",
            "Результат: измеренная масса груза и погрешность; выход за допуск = проверка не пройдена.",
        ),
        duration_s=150,
        inputs=("referenceKg",),
        uses=("S3", "S7", "S9"),
        prepare="Повесьте на гриф взвешенный груз поровну на обе стороны и введите его массу (лучше другой, чем в S9).",
    ),
    CalibrationSpec(
        "B3", "B", "Задержка управления", ("S3",), ("loop_delay_s",), True,
        description="Время от записи команды до первого кадра, в котором гриф уже движется: запись по шине, нарастание момента в приводе, чтение телеметрии. Вместе с периодом цикла (B1) определяет, насколько жёстким может быть удержание и насколько точно компенсируется инерция.",
        steps=(
            "Гриф поднимается на 25 мм и останавливается серединой окна невесомости.",
            "5 раз: ступень силы на 50 % трения выше края окна, отсчёт кадров до первого движения, остановка.",
            "Гриф опускается на упоры.",
            "Результат: средняя задержка и разброс; критерий — разброс не больше полутора периодов цикла.",
        ),
        duration_s=30,
    ),
    CalibrationSpec(
        "B8", "B", "Рабочий ход (верхний упор)", ("S3", "C3"), ("travel_mm",), True,
        description="Гриф медленно поднимается до верхнего упора: остановка при растущей силе = упор. Ход от нижних упоров до верхних задаёт границы карты по высоте и проверку верхнего программного предела. Сила сверх окна невесомости ограничена ~60 % трения — в упор гриф приходит мягко.",
        steps=(
            "Гриф поднимается со скоростью ~30 мм/с до остановки.",
            "Остановка с прижатием к упору 0,5 с — фиксируется высота каждой стороны.",
            "Гриф опускается на нижние упоры.",
            "Результат: рабочий ход и перекос сторон наверху; сверка с верхним программным пределом.",
        ),
        duration_s=120,
        prepare="Над грифом и кареткам до верхних упоров должно быть свободно; рядом с грифом никого нет.",
    ),
    CalibrationSpec(
        "X2", "X", "Связь сторон через гриф", ("S3",), ("side_coupling_n_per_mm",), True,
        description="Жёсткость грифа между сторонами: одна сторона медленно тянется вверх, другая удерживается трением, по перекосу и силе считается жёсткость (Н на 1 мм перекоса). Нужна для выравнивания сторон: коэффициент выравнивания должен быть заметно меньше жёсткости грифа.",
        steps=(
            "Гриф поднимается на 40 мм и останавливается.",
            "Левая сторона: сила плавно растёт до +80 % трения сверх трогания, пока перекос < 1,5 мм и правая сторона стоит.",
            "Стороны выравниваются, то же для правой стороны.",
            "Гриф опускается на упоры. Результат: жёсткость связи (по наклону «сила — перекос»).",
        ),
        duration_s=60,
    ),
    CalibrationSpec(
        "Q1", "Q", "Ежедневная проверка", ("S3",), (), True,
        description="Короткая проверка перед тренировками без изменения профиля: настройки приводов, положение на упорах (ноль энкодера) и окно невесомости в одной точке против сохранённого профиля. Вес отличается > 7 % или трение > 25 % — предупреждение «рекомендуется калибровка»; вес > 15 % — проверка не пройдена.",
        steps=(
            "Чтение регистров пусконаладки обоих приводов.",
            "Положение обеих сторон на упорах: < 5 мм от нуля, перекос < 3 мм.",
            "Гриф отрывается на ~10 мм, 2 цикла «трогание вниз / вверх», затем опускается на упоры.",
            "Результат: отклонения веса и трения от профиля, вердикт.",
        ),
        duration_s=140,
        uses=("S3", "S7", "S9"),
    ),
)
BY_CODE = {spec.code: spec for spec in CATALOG}

# Recommended commissioning order: each step uses only results of the previous ones.
ORDER = ("B0", "B1", "B5", "S3", "M1", "M2", "M3", "C3", "B7", "C1", "B3", "X2", "B8", "S7", "D2", "D4", "M4", "S9", "G1", "Q1")
assert set(ORDER) == set(BY_CODE), "every calibration must have a place in the commissioning order"
assert all(ORDER.index(r) < ORDER.index(spec.code) for spec in CATALOG for r in spec.requires), "a requirement must come earlier"

WIZARD_STAGES = ("B0", "B1", "B5", "S3", "M1", "M2", "M3", "C3", "B7", "C1")
WIZARD = CalibrationSpec(
    "WIZARD", "W", "Мастер базовой настройки", (), tuple(p for code in WIZARD_STAGES for p in BY_CODE[code].produces), True,
    description="Первые 10 шагов пусконаладки подряд, без груза и без участия оператора (кроме удержания кнопки): проверка приводов, шина, направление, окно невесомости, отрыв от упоров, управляемое перемещение и торможение, опускание поддержкой, абсолютный ноль и запас устойчивости. Каждый этап использует результат предыдущего; результат — один новый профиль. Ошибка любого этапа останавливает мастер, профиль не меняется.",
    steps=tuple(f"{code}: {BY_CODE[code].title}" for code in WIZARD_STAGES),
    duration_s=sum(BY_CODE[code].duration_s or 0 for code in WIZARD_STAGES),
)
RUNNABLE: dict[str, tuple[str, ...]] = {spec.code: (spec.code,) for spec in CATALOG if spec.implemented} | {"WIZARD": WIZARD_STAGES}


def _field(profile: MachineProfile, path: str):  # noqa: ANN202
    target: object = profile
    for part in path.split("."):
        target = getattr(target, part)
    return target


@dataclass(frozen=True)
class CheckResult:
    """Last finished run of a check that writes no parameters (B0, G1, Q1)."""

    finished_at: str
    ok: bool


def _ts(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    value = datetime.fromisoformat(stamp)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _base_status(profile: MachineProfile, spec: CalibrationSpec, checks: Mapping[str, CheckResult]) -> Status:
    if not spec.implemented:
        return "planned"
    if not spec.produces:
        check = checks.get(spec.code)
        return "missing" if check is None else "actual" if check.ok else "failed"
    fields = [_field(profile, path) for path in spec.produces]
    if not all(item.provenance == "measured" for item in fields):
        return "missing"
    if spec.min_points > 1 and any(len(item.value or ()) < spec.min_points for path, item in zip(spec.produces, fields, strict=True) if path.endswith("gravity_map")):
        return "missing"
    return "actual"


def _measured_at(profile: MachineProfile, spec: CalibrationSpec, checks: Mapping[str, CheckResult]) -> str | None:
    if not spec.produces:
        check = checks.get(spec.code)
        return check.finished_at if check else None
    stamps = [_field(profile, path).measured_at for path in spec.produces]
    return max((s for s in stamps if s), key=lambda s: _ts(s) or datetime.min.replace(tzinfo=UTC), default=None)


def stale_reason(profile: MachineProfile, spec: CalibrationSpec, checks: Mapping[str, CheckResult] | None = None) -> str | None:
    """A calibration whose inputs were re-measured afterwards is out of date."""

    checks = checks or {}
    own = _ts(_measured_at(profile, spec, checks))
    if own is None:
        return None
    newer = [
        code for code in spec.uses
        if _base_status(profile, BY_CODE[code], checks) == "actual" and (_ts(_measured_at(profile, BY_CODE[code], checks)) or own) > own
    ]
    return f"после неё выполнена {', '.join(newer)}: повторите" if newer else None


def status(profile: MachineProfile, spec: CalibrationSpec, checks: Mapping[str, CheckResult] | None = None) -> Status:
    checks = checks or {}
    base = _base_status(profile, spec, checks)
    if base == "actual" and stale_reason(profile, spec, checks):
        return "stale"
    return base


def graph(profile: MachineProfile, checks: Mapping[str, CheckResult] | None = None) -> list[dict[str, object]]:
    checks = checks or {}
    items = []
    for spec in (WIZARD, *CATALOG):
        state = status(profile, spec, checks)
        check = checks.get(spec.code) if not spec.produces and spec is not WIZARD else None
        items.append({
            "code": spec.code,
            "group": spec.group,
            "groupTitle": GROUPS[spec.group],
            "title": spec.title,
            "description": spec.description,
            "steps": list(spec.steps),
            "durationS": spec.duration_s,
            "requires": list(spec.requires),
            "produces": list(spec.produces),
            "uses": list(spec.uses),
            "inputs": list(spec.inputs),
            "prepare": spec.prepare or None,
            "order": 0 if spec is WIZARD else ORDER.index(spec.code) + 1,
            "stages": list(WIZARD_STAGES) if spec is WIZARD else [spec.code],
            "implemented": spec.implemented,
            "runnable": spec.code in RUNNABLE,
            "status": state,
            "staleReason": stale_reason(profile, spec, checks) if state == "stale" else None,
            "measuredAt": _measured_at(profile, spec, checks),
            "lastCheck": {"finishedAt": check.finished_at, "ok": check.ok} if check else None,
        })
    return items
