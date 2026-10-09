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
from app.motor.units import SIDES, Side, rpm_to_mm_s

Scope = Literal["side", "machine", "tunables", "envelope"]
Kind = Literal["float", "int", "bool", "sign", "weight", "counts", "table"]
TRAVEL_MARGIN_MM = 20.0


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
    produced_by: tuple[str, ...] = ()  # calibrations that measure the value (first = main)
    restart: bool = False  # written to the drive at connection: applies after a backend restart / fault reset


GROUPS: tuple[tuple[str, str, str], ...] = (
    ("drive", "Привод и механика", "Свойства приводов и винтов. Направление и масштаб определяют, как команда момента превращается в силу на грифе; ноль и ход — где находятся упоры."),
    ("statics", "Вес и трение", "Окно невесомости: сила, при которой гриф трогается вверх и вниз (S3 — в одной точке, S7 — по высоте). Край окна = вес ± (трение + добавка трогания); D2 делит трение на трение движения и добавку трогания."),
    ("dynamics", "Динамика и связь", "Инерция, вязкое трение, тайминг и задержка шины, связь сторон через гриф и запас устойчивости удержания."),
    ("motion", "Перемещение", "Что нужно автоматическим перемещениям грифа (калибровки, подъём и опускание) сверх окна невесомости: отрыв от упоров, сила для заданной скорости, тормозной путь. Пока не измерены, перемещения подстраиваются на ходу (медленнее и с перелётом)."),
    ("hold", "Удержание и невесомость", "Значения, подобранные калибровками на этом тренажёре (H1, W1, X3). Если измерены — заменяют соответствующие коэффициенты поведения."),
    ("feel", "Ощущение свободного веса", "Что делает движение грифа похожим на настоящий вес: оценка скорости и ускорения (V1–V3), компенсация инерции по нагрузке (F1, F2), трение на скоростях упражнения и по высоте (F3, S10, F7), разворот, трогание, мягкие упоры и отпускание (F4–F11). Пока не измерены — соответствующая компенсация выключена или работает по умолчанию."),
    ("behaviour", "Поведение тренажёра", "Коэффициенты режимов тренировки: компенсация трения, удержание, подсчёт повторений. Применяются сразу после сохранения."),
    ("safety", "Пределы безопасности", "Жёсткие ограничения — последний фильтр перед приводом. Меняйте только понимая последствия."),
)

PARAMS: tuple[ParamSpec, ...] = (
    # ---------------------------------------------------------------- drive
    ParamSpec("side", "direction_sign", "drive", "Направление момента", "Знак команды момента, который поднимает сторону. Неверный знак — поддержка давит гриф вниз. Меняется только калибровкой B5.", kind="sign", editable=False, produced_by=("B5",)),
    ParamSpec("side", "n_per_raw", "drive", "Масштаб силы", "Сколько ньютонов на грифе даёт одна единица команды PA_12C (0,1 % номинального момента). Паспортное значение ±15 %; точно — эталонным грузом (S9). Ручная правка не пересчитывает остальные силы — для этого запустите S9.", "Н/ед.", min=0.1, max=5.0, step=0.01, produced_by=("S9",)),
    ParamSpec("side", "mm_per_pulse", "drive", "Ход на импульс энкодера", "Шаг винта 32 мм / 2¹⁷ импульсов на оборот (паспорт). Связь с приводом считает положение по этому же значению; сверка рулеткой (B6) пока не реализована.", "мм", editable=False),
    ParamSpec("side", "support_raw", "drive", "Момент поддержки", "Команда PA_12C, которую приводы держат вне тренировки и при СТОП: гриф должен медленно опускаться (~15 мм/с), а не висеть и не падать.", "ед.", kind="int", min=0, max=400, step=1, produced_by=("C3",)),
    ParamSpec("side", "zero_counts", "drive", "Абсолютный ноль", "Показание абсолютного энкодера на нижних упорах (B7). После сохранения положение считается от упоров, даже если при включении гриф был поднят.", "имп.", kind="counts", editable=False, produced_by=("B7",)),
    ParamSpec("machine", "travel_mm", "drive", "Рабочий ход", "Ход грифа от нижних до верхних упоров (B8). Верхний программный предел должен быть ниже хода минимум на 20 мм.", "мм", min=100, max=2000, step=10, produced_by=("B8",)),
    # -------------------------------------------------------------- statics
    ParamSpec("side", "gravity_map", "statics", "Вес (баланс)", "Сила, удерживающая сторону грифа в равновесии: середина окна невесомости. S3 — одна точка, S7 — карта по высоте (тогда редактируется только калибровкой).", "Н", kind="weight", min=0, max=1500, step=1, produced_by=("S3", "S7")),
    ParamSpec("side", "coulomb_up_n", "statics", "Трение вверх", "Сухое трение винта и направляющих при движении вверх. До D2 — полное трение трогания, после D2 — трение движения (трогание = это + добавка трогания).", "Н", min=0, max=500, step=1, produced_by=("S3", "S7", "D2")),
    ParamSpec("side", "coulomb_down_n", "statics", "Трение вниз", "Сколько можно убрать от веса, прежде чем гриф поедет вниз (без добавки трогания после D2).", "Н", min=0, max=500, step=1, produced_by=("S3", "S7", "D2")),
    ParamSpec("side", "stribeck_extra_n", "statics", "Добавка трогания", "Трение покоя сверх трения движения (эффект Штрибека): разница между троганием (S3) и трением в движении (D2). S3/S7 сбрасывают её в 0.", "Н", min=0, max=200, step=1, produced_by=("D2",)),
    ParamSpec("side", "stribeck_v_mm_s", "statics", "Скорость Штрибека", "Скорость, на которой добавка трогания уже практически исчезла (спад по exp(−(v/vₛ)²)). Оценивается D2, если добавка заметна.", "мм/с", min=0.1, max=50, step=0.1, produced_by=("D2",)),
    # ------------------------------------------------------------- dynamics
    ParamSpec("side", "viscous_n_per_mm_s", "dynamics", "Вязкое трение", "Рост сопротивления со скоростью (D2): при 0,1 Н·с/мм и 300 мм/с — 30 Н.", "Н·с/мм", min=0, max=5, step=0.01, produced_by=("D2",)),
    ParamSpec("side", "moving_mass_kg", "dynamics", "Приведённая масса", "Инерция винта, ротора и грифа, приведённая к стороне (D4, уточняется эталонным грузом D5); по паспорту ожидается 40–80 кг.", "кг", min=1, max=300, step=1, produced_by=("D4", "D5")),
    ParamSpec("machine", "hold_ultimate_k_n_per_mm", "dynamics", "Предельная жёсткость удержания", "K_u из релейного теста C1: при такой жёсткости удержание начинает раскачиваться. Рабочая жёсткость — доля от неё.", "Н/мм", min=0.01, max=100, step=0.01, produced_by=("C1",)),
    ParamSpec("machine", "hold_ultimate_period_s", "dynamics", "Период предельного цикла", "Период колебаний в релейном тесте C1; определяет демпфирование удержания.", "с", min=0.01, max=10, step=0.01, produced_by=("C1",)),
    ParamSpec("machine", "loop_period_s", "dynamics", "Период цикла", "Среднее время одного цикла чтение/запись по RS-485 (B1).", "с", min=0.005, max=0.5, step=0.001, produced_by=("B1",)),
    ParamSpec("machine", "loop_delay_s", "dynamics", "Задержка управления", "Время от записи команды до первого кадра с движением грифа: шина + нарастание момента + чтение (B3).", "с", min=0.005, max=0.5, step=0.001, produced_by=("B3",)),
    ParamSpec("machine", "jitter_p95_s", "dynamics", "Разброс цикла (p95)", "95-й перцентиль отклонения периода цикла от медианы (B1).", "с", min=0, max=0.5, step=0.001, produced_by=("B1",)),
    ParamSpec("machine", "side_coupling_n_per_mm", "dynamics", "Связь сторон", "Жёсткость грифа между сторонами: сила при перекосе на 1 мм (X2). «Выравнивание сторон» должно быть не больше ~20 % от неё.", "Н/мм", min=0, max=5000, step=1, produced_by=("X2",)),
    ParamSpec("machine", "torque_lag_s", "dynamics", "Задержка момента привода", "От записи команды до 63 % момента в PA_1C4 (B2): шина и нарастание тока.", "с", min=0, max=0.5, step=0.001, produced_by=("B2",)),
    ParamSpec("side", "deadband_raw", "dynamics", "Мёртвая зона команды", "Наименьшая команда PA_12C, на которую привод отвечает моментом (D1).", "ед.", kind="int", min=0, max=200, step=1, produced_by=("D1",)),
    ParamSpec("side", "friction_load_up", "statics", "Рост трения вверх с нагрузкой", "На сколько ньютонов растёт трение вверх на каждый ньютон груза (L1). 0,05 = +2,5 кгс трения на 50 кг.", "Н/Н", min=-0.1, max=1, step=0.005, produced_by=("L1",)),
    ParamSpec("side", "friction_load_down", "statics", "Рост трения вниз с нагрузкой", "То же для трения вниз (L2).", "Н/Н", min=-0.1, max=1, step=0.005, produced_by=("L2",)),
    ParamSpec("side", "dwell_extra_n", "statics", "Залипание после стоянки", "На сколько растёт сила трогания после долгой стоянки (S5): первое повторение после отдыха тяжелее на столько.", "Н", min=0, max=300, step=0.5, produced_by=("S5",)),
    ParamSpec("side", "dwell_tau_s", "statics", "Время залипания", "За сколько секунд стоянки залипание набирает 63 % (S5).", "с", min=0.1, max=600, step=0.5, produced_by=("S5",)),
    ParamSpec("side", "screw_ripple_n", "statics", "Неравномерность за оборот винта", "Амплитуда колебания силы с периодом шага винта 32 мм (S6).", "Н", min=0, max=200, step=0.1, produced_by=("S6",)),
    ParamSpec("side", "screw_ripple_phase_rad", "statics", "Фаза неравномерности", "Фаза синусоиды 32 мм относительно нуля хода (S6).", "рад", min=-3.15, max=3.15, step=0.01, produced_by=("S6",)),
    ParamSpec("machine", "tight_spots", "statics", "Тугие места по ходу", "Участки хода, где для движения нужна заметно большая сила (S8): высота и лишняя сила.", "Н", kind="table", editable=False, produced_by=("S8",)),
    # --------------------------------------------------------------- motion
    ParamSpec("side", "liftoff_extra_n", "motion", "Добавка для отрыва от упоров", "Сила сверх верхнего края окна невесомости, нужная чтобы гриф оторвался от нижних упоров после стоянки (залипание). Добавляется к подъёму, пока сторона на упорах.", "Н", min=0, max=300, step=1, produced_by=("M1",)),
    ParamSpec("side", "travel_extra_up_n", "motion", "Сила подъёма сверх окна", "Сила сверх верхнего края окна, при которой гриф поднимается со скоростью 20 мм/с. С неё начинается регулятор скорости. Может быть отрицательной: трение в движении меньше трения трогания.", "Н", min=-200, max=300, step=0.5, produced_by=("M2",)),
    ParamSpec("side", "travel_extra_down_n", "motion", "Сила опускания сверх окна", "На сколько сила ниже нижнего края окна, чтобы гриф опускался со скоростью 20 мм/с.", "Н", min=-200, max=300, step=0.5, produced_by=("M2",)),
    ParamSpec("machine", "brake_lag_s", "motion", "Задержка торможения", "Время от команды «стоп» (середина окна невесомости) до начала замедления: шина и нарастание момента. Часть тормозного пути v·τ.", "с", min=0, max=1, step=0.005, produced_by=("M3",)),
    ParamSpec("machine", "brake_decel_up_mm_s2", "motion", "Замедление при остановке вверх", "С каким замедлением сухое трение и вес останавливают гриф, идущий вверх. Тормозной путь v²/(2a).", "мм/с²", min=10, max=10000, step=10, produced_by=("M3",)),
    ParamSpec("machine", "brake_decel_down_mm_s2", "motion", "Замедление при остановке вниз", "То же для грифа, идущего вниз (обычно меньше: вес помогает движению).", "мм/с²", min=10, max=10000, step=10, produced_by=("M3",)),
    ParamSpec("side", "travel_table_up", "motion", "Сила подъёма по скоростям", "Таблица «скорость → сила сверх окна» для подъёма (P1): регулятор скорости сразу выходит на заданную скорость.", "Н", kind="table", editable=False, produced_by=("P1",)),
    ParamSpec("side", "travel_table_down", "motion", "Сила опускания по скоростям", "То же для опускания (P2).", "Н", kind="table", editable=False, produced_by=("P2",)),
    ParamSpec("machine", "position_speed_up_mm_s", "motion", "Скорость позиционирования вверх", "Самая быстрая скорость подъёма, при которой гриф встаёт в точку ±2 мм без перелёта (P1).", "мм/с", min=5, max=200, step=1, produced_by=("P1",)),
    ParamSpec("machine", "position_speed_down_mm_s", "motion", "Скорость позиционирования вниз", "То же для опускания (P2).", "мм/с", min=5, max=200, step=1, produced_by=("P2",)),
    ParamSpec("machine", "accel_mm_s2", "motion", "Плавный разгон", "Рампа скорости в начале автоматического перемещения (A1): без рывка после трогания.", "мм/с²", min=10, max=5000, step=10, produced_by=("A1",)),
    ParamSpec("machine", "decel_mm_s2", "motion", "Плавная остановка", "Рампа замедления к точке остановки (A2): гриф подходит к точке медленно и встаёт без перелёта.", "мм/с²", min=10, max=5000, step=10, produced_by=("A2",)),
    ParamSpec("machine", "landing_speed_mm_s", "motion", "Скорость посадки на упоры", "Скорость опускания на нижние упоры с мягким касанием (A3).", "мм/с", min=2, max=60, step=1, produced_by=("A3",)),
    ParamSpec("machine", "reversal_stick_s", "motion", "Залипание на развороте", "Сколько гриф стоит при смене направления без остановки (R1): мёртвое время каждого разворота повторения.", "с", min=0, max=3, step=0.01, produced_by=("R1",)),
    ParamSpec("machine", "stop_overshoot_mm", "motion", "Доезд после СТОП", "Насколько гриф доезжает вверх после нажатия СТОП во время подъёма (E1). Запас до верхнего программного предела.", "мм", min=0, max=200, step=0.5, produced_by=("E1",)),
    # ----------------------------------------------------------------- hold
    ParamSpec("machine", "hold_k_n_per_mm", "hold", "Жёсткость удержания", "Подобрана под нагрузкой (H1): самая жёсткая пружина удержания без раскачки. Если измерена — используется вместо доли K_u.", "Н/мм", min=0.01, max=100, step=0.01, produced_by=("H1",)),
    ParamSpec("machine", "hold_c_n_per_mm_s", "hold", "Демпфирование удержания", "Демпфирование пружины удержания (H1).", "Н·с/мм", min=0, max=100, step=0.01, produced_by=("H1",)),
    ParamSpec("machine", "weightless_gain_up", "hold", "Лёгкость невесомости вверх", "Доля трения вверх, которую мотор компенсирует в невесомости (W1): наибольшая, при которой гриф ещё сам останавливается. Если измерена — заменяет «Компенсацию трения вверх».", "×", min=0, max=1.2, step=0.05, produced_by=("W1",)),
    ParamSpec("machine", "weightless_gain_down", "hold", "Лёгкость невесомости вниз", "То же вниз (W1).", "×", min=0, max=1.2, step=0.05, produced_by=("W1",)),
    ParamSpec("machine", "sync_k_n_per_mm", "hold", "Выравнивание сторон (подобрано)", "Сила выравнивания на 1 мм перекоса, подобранная в движении (X3). Если измерена — заменяет «Выравнивание сторон» в поведении.", "Н/мм", min=0, max=200, step=0.5, produced_by=("X3",)),
    # ----------------------------------------------------------------- feel
    ParamSpec("machine", "speed_lag_s", "feel", "Запаздывание скорости привода", "На сколько регистр скорости PA_1C1 отстаёт от энкодера (V1). Наблюдатель добавляет a·τ и меньше доверяет регистру.", "с", min=0, max=0.5, step=0.005, produced_by=("V1",)),
    ParamSpec("machine", "speed_scale", "feel", "Масштаб скорости привода", "Отношение PA_1C1 к истинной скорости по энкодеру (V1); ожидается 1.", "×", min=0.5, max=2, step=0.001, produced_by=("V1",)),
    ParamSpec("machine", "accel_smoothing", "feel", "Сглаживание ускорения", "Доля нового измерения в оценке ускорения за кадр (V2): меньше — меньше шума, но больше запаздывание компенсации инерции.", "×", min=0.01, max=1, step=0.01, produced_by=("V2",)),
    ParamSpec("machine", "accel_noise_mm_s2", "feel", "Ошибка ускорения", "СКО ошибки оценки ускорения при выбранном сглаживании (V2).", "мм/с²", editable=False, produced_by=("V2",)),
    ParamSpec("machine", "predict_horizon_s", "feel", "Упреждение задержки", "Компенсация трения считается для скорости v + a·h — той, что будет, когда команда дойдёт до привода (V3).", "с", min=0, max=0.5, step=0.005, produced_by=("V3",)),
    ParamSpec("machine", "inertia_ratio_max", "feel", "Предел компенсации инерции", "Какую долю массы машины мотор может снять без раскачки (F1, 80 % от устойчивой). Используется, пока нет таблицы F2.", "×", min=0, max=1, step=0.01, produced_by=("F1",)),
    ParamSpec("machine", "inertia_table", "feel", "Компенсация инерции по нагрузке", "Таблица «нагрузка на сторону → доля снятой лишней массы» (F2): чтобы гриф ощущался массой L/g, как свободный вес.", kind="table", editable=False, produced_by=("F2",)),
    ParamSpec("side", "friction_table_up", "feel", "Трение вверх на скоростях упражнения", "Таблица «скорость → сила трения» 40…160 мм/с (F3); заменяет сухое + вязкое трение в компенсации.", "Н", kind="table", editable=False, produced_by=("F3",)),
    ParamSpec("side", "friction_table_down", "feel", "Трение вниз на скоростях упражнения", "То же для опускания (F3).", "Н", kind="table", editable=False, produced_by=("F3",)),
    ParamSpec("side", "friction_map", "feel", "Карта трения по высоте", "Отклонение трения от обычного на каждых 20 мм хода (S10); компенсируется с коэффициентом F7.", "Н", kind="table", editable=False, produced_by=("S10",)),
    ParamSpec("machine", "feel_blend_mm_s", "feel", "Сглаживание трения на развороте", "Подобрано на повторениях (F4); если измерено — заменяет «Сглаживание трения» в поведении.", "мм/с", min=0.5, max=50, step=0.5, produced_by=("F4",)),
    ParamSpec("machine", "feel_phase_hysteresis_mm_s", "feel", "Гистерезис фазы (подобран)", "Наименьший без «мигания» фазы на развороте (F5).", "мм/с", min=1, max=100, step=1, produced_by=("F5",)),
    ParamSpec("machine", "feel_phase_blend_s", "feel", "Переход фаз (подобран)", "1,5 × время разворота (F5): эксцентрическая нагрузка входит без рывка.", "с", min=0.01, max=1, step=0.01, produced_by=("F5",)),
    ParamSpec("machine", "breakaway_soft_s", "feel", "Смягчение трогания", "После стоянки компенсация трения нарастает за это время: гриф не дёргается, когда отпускает залипание (F6). 0 — сразу.", "с", min=0, max=1, step=0.01, produced_by=("F6",)),
    ParamSpec("machine", "track_comp_gain", "feel", "Компенсация неровности хода", "Доля неравномерности винта (S6) и карты трения (S10, S8), которую компенсирует мотор (F7). Пока не проверена — 0.", "×", min=0, max=1.5, step=0.05, produced_by=("F7",)),
    ParamSpec("machine", "deadband_comp_gain", "feel", "Обратная мёртвая зона", "Доля мёртвой зоны D1, добавляемая к малым командам (F8): нагрузка около веса грифа не «проваливается».", "×", min=0, max=1.5, step=0.05, produced_by=("F8",)),
    ParamSpec("machine", "dither_n", "feel", "Микровибрация против трения покоя", "Амплитуда знакопеременной силы на каждом цикле, пока гриф почти стоит (F9). 0 — выключена.", "Н", min=0, max=100, step=0.5, produced_by=("F9",)),
    ParamSpec("machine", "cushion_bottom_mm", "feel", "Мягкий нижний упор", "Зона над нижним программным пределом, в которой допустимая скорость опускания плавно падает до скорости посадки (F10).", "мм", min=0, max=400, step=5, produced_by=("F10",)),
    ParamSpec("machine", "cushion_top_mm", "feel", "Мягкий верхний предел", "То же под верхним программным пределом: брошенный вверх гриф останавливается до него (F10).", "мм", min=0, max=400, step=5, produced_by=("F10",)),
    ParamSpec("machine", "feel_release_force_n", "feel", "Порог отпускания (подобран)", "Если по оценке пользователь давит слабее — гриф отпущен (F11). Заменяет «Силу отпускания».", "Н", min=5, max=300, step=1, produced_by=("F11",)),
    ParamSpec("machine", "feel_release_timeout_s", "feel", "Время отпускания (подобрано)", "Сколько усилие должно быть ниже порога, чтобы тренажёр перешёл к удержанию (F11).", "с", min=0.05, max=30, step=0.05, produced_by=("F11",)),
    ParamSpec("machine", "sync_k_train_n_per_mm", "feel", "Выравнивание сторон в упражнении", "Подобрано на повторениях 100 мм/с (X4); в тренировке заменяет значение X3.", "Н/мм", min=0, max=200, step=0.5, produced_by=("X4",)),
    ParamSpec("machine", "friction_load_gain", "feel", "Компенсация роста трения с нагрузкой", "Доля роста трения L1/L2, которую компенсирует мотор по осевой нагрузке на винт (L3). До L3 — 100 %, если L1/L2 измерены.", "×", min=0, max=2, step=0.05, produced_by=("L3",)),
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
    ParamSpec("envelope", "speed_limit_rpm", "safety", "Предел скорости привода (PA_056)", "Ограничение скорости в режиме момента, записывается в привод (1 об/мин ≈ 0,53 мм/с). Не тормозит опускание под весом. Должен быть выше максимальной скорости грифа и ниже аварийной.", "об/мин", kind="int", min=50, max=3000, step=10, restart=True),
    ParamSpec("envelope", "overspeed_rpm_alarm", "safety", "Аварийная скорость", "Выше этой скорости момент обнуляется и тренажёр блокируется (1 об/мин ≈ 0,53 мм/с). Должна быть выше предела привода PA_056.", "об/мин", min=50, max=3000, step=10),
    ParamSpec("envelope", "max_speed_mm_s", "safety", "Максимальная скорость грифа", "Предел скорости в тренировке; не выше предела привода PA_056 и критической скорости винта (~500 мм/с).", "мм/с", min=50, max=1000, step=10),
    ParamSpec("envelope", "max_descent_mm_s", "safety", "Максимальная скорость опускания", "Предел скорости вниз; не выше максимальной скорости грифа.", "мм/с", min=20, max=1000, step=10),
    ParamSpec("envelope", "soft_min_mm", "safety", "Нижний программный предел", "Ниже этой высоты нагрузка снимается, гриф мягко садится на упоры.", "мм", min=0, max=500, step=1),
    ParamSpec("envelope", "soft_max_mm", "safety", "Верхний программный предел", "Выше этой высоты нагрузка не прикладывается. Минимум на 20 мм ниже рабочего хода (B8).", "мм", min=100, max=2000, step=10),
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
    elif kind == "table":
        points = len(value) if value is not None else None
        value = None
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
                "editable": spec.editable, "min": spec.min, "max": spec.max, "step": spec.step, "producedBy": list(spec.produced_by), "restart": spec.restart,
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
    keys = {change.get("key") for change in changes}
    if keys & {"soft_max_mm", "travel_mm"} and envelope.soft_max_mm > float(machine.travel_mm.value) - TRAVEL_MARGIN_MM:
        raise ValueError(f"Верхний программный предел должен быть ниже рабочего хода минимум на {TRAVEL_MARGIN_MM:.0f} мм (ход {float(machine.travel_mm.value):.0f} мм)")
    if keys & {"max_speed_mm_s", "max_descent_mm_s", "speed_limit_rpm", "overspeed_rpm_alarm"}:
        drive_mm_s, alarm_mm_s = rpm_to_mm_s(envelope.speed_limit_rpm), rpm_to_mm_s(envelope.overspeed_rpm_alarm)
        if envelope.max_descent_mm_s > envelope.max_speed_mm_s:
            raise ValueError("Скорость опускания не может быть выше максимальной скорости грифа")
        if envelope.max_speed_mm_s > drive_mm_s:
            raise ValueError(f"Максимальная скорость грифа выше предела привода PA_056 ({drive_mm_s:.0f} мм/с)")
        if envelope.speed_limit_rpm >= envelope.overspeed_rpm_alarm:
            raise ValueError(f"Аварийная скорость ({alarm_mm_s:.0f} мм/с) должна быть выше предела привода PA_056 ({drive_mm_s:.0f} мм/с), иначе авария срабатывает на штатной скорости")
    if envelope.sync_warning_mm >= envelope.sync_critical_mm:
        raise ValueError("Порог предупреждения о перекосе должен быть меньше порога остановки")
    if envelope.comm_freeze_frames >= envelope.comm_fault_frames:
        raise ValueError("Потерь до заморозки должно быть меньше, чем потерь до ошибки")
    return ProfileBundle(machine, tunables, envelope)


__all__ = ["GROUPS", "PARAMS", "ParamSpec", "apply_changes", "describe"]
