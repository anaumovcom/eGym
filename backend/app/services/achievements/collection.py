"""The workout collection. Stable tier IDs preserve awards across catalog and artwork revisions."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.achievements.content import load_catalog
from app.services.muscle_catalog import CANONICAL_MUSCLE_DEFINITIONS

VERSION = "workout-collection-4.0"
CONTENT_VERSION = "workout-stories-4.0"
TITLES_PATH = Path(__file__).parent / "content" / "workout-titles.ru.json"
GROUPS = {
    "journal": "Дневник тренировок",
    "calendar": "Календарь практики",
    "return": "Возвращения",
    "discovery": "Открытия",
    "duet": "Дуэты движений",
    "signature": "Почерк тренировки",
    "program": "Знакомые программы",
    "exercise": "Любимые упражнения",
    "muscle": "Атлас мышц",
    "archive": "Архив наград",
}

# These milestones still measure the same thing as the original illustrated tiers.
# Only the relevant metric is needed now, without an unrelated minimum number of days.
ILLUSTRATED = {
    "journal": {
        "start.first_workout": "Каждая сохранённая тренировка хотя бы с одним выполненным подходом пополняет дневник.",
        "practice.workouts": "Здесь собираются все занятия с выполненной работой, в том числе частично завершённые.",
        "practice.sets": "Каждый сохранённый подход с повторениями или секундами добавляет строку.",
        "practice.reps": "Повторения из разных тренировок складываются в общий счёт.",
        "practice.exercise_sessions": "Каждая запись упражнения с выполненной работой пополняет картотеку.",
        "variety.timed_seconds": "Складываются фактические секунды упражнений на время и растяжки из разных занятий.",
    },
    "calendar": {
        "rhythm.active_days": "День с одной или несколькими тренировками даёт одну отметку.",
        "rhythm.active_weeks": "Каждая календарная неделя с тренировкой добавляет страницу.",
        "rhythm.months": "В коллекцию входит каждый месяц с тренировками хотя бы в два разных дня.",
        "rhythm.quarters": "Для страницы альбома достаточно шести тренировочных дней за календарный квартал.",
        "chapter.30_days": "Глава складывается из 30 календарных дней с первой тренировки и шести дней практики.",
        "chapter.90_days": "Глава складывается из 90 календарных дней с первой тренировки и 18 дней практики.",
        "chapter.365_days": "Глава складывается из года с первой тренировки и 40 дней практики.",
    },
    "return": {
        "rhythm.return": "После перерыва в 14 полных дней каждый новый день практики продолжает эту серию.",
        "start.exercise_return": "Считаются разные дни, в которые встречалось одно и то же упражнение.",
        "repertoire.exercise_weeks": "Считаются разные недели, в которых встречалось одно и то же упражнение.",
    },
    "discovery": {
        "repertoire.distinct_exercises": "Первый сохранённый результат каждого нового упражнения открывает страницу атласа.",
        "repertoire.familiar": "Упражнение становится знакомым, когда встречается в три разных дня.",
        "repertoire.new_exercise_months": "Каждый месяц, в котором впервые встретилось новое упражнение, засчитывается один раз.",
        "variety.bodyweight_exercises": "Здесь собираются разные упражнения с собственным весом.",
        "repertoire.machine_exercises": "Каждое новое упражнение на тренажёре добавляется в коллекцию один раз.",
        "repertoire.timed_exercises": "В коллекцию попадают разные упражнения, результат которых измеряется в секундах.",
    },
    "signature": {
        "repertoire.familiar_days": "День засчитывается, если в нём встретилось упражнение, знакомое по трём более ранним дням.",
        "repertoire.repertoire_months": "В зачёт идёт каждый месяц, за который в дневнике встретилось три разных упражнения.",
        "variety.stretch_days": "Дни с сохранённой растяжкой складываются в одну нить.",
        "variety.bodyweight_days": "Считаются разные дни с упражнениями с собственным весом.",
        "variety.machine_days": "Считаются разные дни с упражнениями на тренажёре.",
    },
    "program": {
        "plan.planned_days": "Засчитываются разные дни хотя бы с одним подходом, выполненным по исходному плану.",
        "plan.repeat_program": "Считаются разные дни, когда целиком выполнен план с одним и тем же набором упражнений.",
        "plan.chapters": "Каждый новый набор упражнений, выполненный целиком по исходному плану, добавляется на карту.",
        "plan.full_weeks": "Неделя засчитывается, когда в ней есть хотя бы одно занятие целиком по исходному плану.",
    },
}

EXERCISE_NAMES = {
    "butt-kick": "Захлёст голени", "cardio-knee-taps": "Касания коленей", "cardio-quick-feet": "Быстрые шаги",
    "smith-machine-bench-press": "Жим лёжа в Смите", "smith-machine-calf-raise": "Подъём на носки в Смите",
    "smith-machine-close-grip-bench-press": "Жим узким хватом", "smith-machine-drag-curl": "Сгибание вдоль корпуса",
    "smith-machine-incline-bench-press": "Наклонный жим", "smith-machine-inverted-row": "Обратная тяга",
    "smith-machine-narrow-stance-squat": "Присед с узкой постановкой", "smith-machine-overhand-row": "Тяга прямым хватом",
    "smith-machine-romanian-deadlift": "Румынская тяга", "smith-machine-seated-overhead-press": "Жим сидя",
    "smith-machine-skullcrusher": "Французский жим", "smith-machine-squat": "Присед в Смите",
    "smith-machine-upright-row": "Тяга к подбородку", "underhand-pulldown": "Тяга обратным хватом",
}

# Each pair must occur in the same workout. Repeating it twice in one day still counts once.
DUETS = {
    ("bodyweight", "machine"): "упражнение с собственным весом и тренажёр",
    ("machine", "stretch"): "тренажёр и растяжка",
    ("machine", "timed"): "тренажёр и упражнение на время",
    ("bodyweight", "stretch"): "упражнение с собственным весом и растяжка",
    ("bodyweight", "timed"): "упражнение с собственным весом и упражнение на время",
    ("stretch", "timed"): "растяжка и отдельное упражнение на время",
}

FORMATS = {
    "bodyweight": "упражнения с собственным весом",
    "machine": "упражнения на тренажёре",
    "stretch": "упражнения на растяжку",
    "timed": "упражнения на время",
}
SEASONS = ("Зима", "Весна", "Лето", "Осень")


def series(key: str, description: str, fact_label: str, unit: str, thresholds: tuple[int, ...]) -> dict[str, Any]:
    group, _ = key.split(".")
    ranks = ("Начало", "Практика", "Мастерство", "Наследие")
    rarities = ("common", "rare", "epic", "legendary")
    tiers = []
    for index, threshold in enumerate(thresholds):
        tiers.append({"id": f"{key}:t{index + 1}", "tier": index + 1, "tierName": ranks[index],
                      "rarity": rarities[index], "threshold": threshold, "minimumEvidenceDays": 0,
                      "phrase": f"{fact_label} — {threshold}."})
    return {"id": key, "description": description, "group": group, "groupName": GROUPS[group],
            "unit": unit, "metric": key, "thresholds": list(thresholds), "applicability": "available", "tiers": tiers}


def original_series() -> list[dict[str, Any]]:
    lines = [
        series("discovery.crossroads", "Два знакомых по прежним дням упражнения впервые попали в одно занятие. Каждая новая пара считается один раз.",
               "Первых встреч знакомых движений", "пар", (1, 3, 8, 18)),
        series("discovery.encore", "Новое упражнение повторилось в следующий тренировочный день. Между занятиями может пройти сколько угодно времени. Каждое упражнение учитывается один раз.",
               "Упражнений, вернувшихся сразу после дебюта", "упражнений", (1, 3, 6, 12)),
        series("calendar.weekend_guest", "Одно упражнение встретилось и в будний, и в выходной день одной недели. Неделя начинается в понедельник и даёт одну отметку.",
               "Недель со встречей в будни и выходные", "недель", (1, 3, 8, 20)),
        series("signature.bookends", "Первое и последнее упражнения те же, что в один из прежних дней, а набор движений между ними изменился. В каждом занятии нужны три разных упражнения. За день — одна отметка.",
               "Дней с новой серединой знакомого занятия", "дней", (1, 3, 7, 15)),
        series("signature.remix", "В знакомом наборе из трёх или более упражнений заменилось одно движение. Каждый новый состав сравнивается с прошлыми днями и даёт до одной отметки за день. Порядок движений свободный.",
               "Дней с новым вариантом знакомого занятия", "дней", (1, 4, 12, 30)),
        series("discovery.club_host", "Упражнение попадает сюда, когда за три или более разных дня оно побывало в одном занятии как минимум с тремя разными движениями.",
               "Упражнений, собравших свою компанию", "упражнений", (1, 3, 6, 12)),
        series("calendar.format_relay", "В разные дни одной календарной недели встретились разные форматы, например тренажёр во вторник и растяжка в пятницу. Каждая неделя считается один раз.",
               "Недель, в которых форматы передали друг другу эстафету", "недель", (1, 4, 12, 26)),
        series("discovery.old_and_new", "В одном занятии встретились упражнение из прошлых дней и упражнение, которое вы пробуете впервые.",
               "Дней, когда новое движение встретилось со знакомым", "дней", (1, 4, 10, 24)),
        series("discovery.seasoned", "Здесь собираются упражнения, которые встречались зимой, весной, летом и осенью. Годы могут быть разными.",
               "Упражнений, побывавших с вами во всех четырёх сезонах", "упражнений", (1, 3, 6, 12)),
        series("signature.reunited_pairs", "Пара попадает в коллекцию, когда два упражнения встречаются в одном занятии в три разных дня.",
               "Пар упражнений, встретившихся вместе в три разных дня", "пар", (1, 4, 12, 30)),
        series("signature.same_setlist", "Дни, когда уже знакомый набор из двух или более упражнений повторился целиком. Порядок может меняться.",
               "Дней с повторением любимого состава упражнений", "дней", (1, 5, 15, 36)),
        series("signature.familiar_only", "В занятии встретились хотя бы два разных упражнения, и каждое уже было в дневнике в более ранний день.",
               "Дней с занятиями из уже знакомых движений", "дней", (3, 10, 30, 75)),
        series("signature.trio", "В одном занятии встретились три разных формата движения. За день засчитывается одна встреча.",
               "Дней, когда три формата встретились в одном занятии", "дней", (1, 4, 10, 24)),
        series("return.rediscovered", "Упражнение вернулось после перерыва в его практике хотя бы на 28 дней. Каждое такое упражнение учитывается один раз.",
               "Упражнений, к которым вы вернулись после долгой паузы", "упражнений", (1, 3, 8, 16)),
        series("return.homecoming", "В первый день после перерыва в тренировках на 14 полных дней в занятии встретилось знакомое упражнение.",
               "Возвращений в зал со знакомым упражнением", "возвращений", (1, 2, 4, 8)),
        series("calendar.both_halves", "В одном месяце есть занятия в обеих половинах. Первая длится с 1-го по 15-е число, вторая начинается с 16-го.",
               "Месяцев с записями в обеих половинах", "месяцев", (1, 3, 9, 18)),
        series("calendar.month_bridge", "Одно и то же упражнение встретилось в двух соседних календарных месяцах. Каждая граница месяцев считается один раз.",
               "Границ между месяцами, которые связало общее упражнение", "переходов", (1, 4, 12, 24)),
        series("calendar.season_turns", "Каждый календарный сезон с тренировкой добавляет одну отметку. Зима объединяет декабрь, январь и февраль.",
               "Сезонов с вашими тренировками", "сезонов", (2, 4, 8, 16)),
        series("calendar.four_colours", "Полный круг складывается из четырёх разных времён года с тренировками. Для нового круга нужно ещё по одному сезону каждого вида.",
               "Полных кругов из четырёх времён года", "кругов", (1, 2, 3, 5)),
    ]
    for kinds, pairing in DUETS.items():
        lines.append(series(f"duet.{'_'.join(kinds)}", f"В одном занятии встретились {pairing}. Считаются разные дни.",
                            f"Дней, когда вместе встретились {pairing}", "дней", (2, 5, 12, 32)))
    for kind, activities in FORMATS.items():
        lines.append(series(f"calendar.{kind}_weeks", f"Считаются разные недели, в которых были {activities}.",
                            f"Недель, в которых встречались {activities}", "недель", (3, 10, 26, 52)))
        lines.append(series(f"discovery.{kind}_regulars", f"Здесь собираются {activities}. Каждое входит в коллекцию после занятий в три разных дня.",
                            "Знакомых упражнений этого формата", "упражнений", (1, 3, 6, 10)))
    for index, season in enumerate(SEASONS):
        lines.append(series(f"calendar.season_{index}", f"Все тренировочные дни за сезон «{season}» складываются из года в год.",
                            "Тренировочных дней в это время года", "дней", (5, 15, 35, 75)))
    return lines


@lru_cache(maxsize=1)
def collection() -> dict[str, dict[str, Any]]:
    """Index both current series and retired IDs so old links and workout summaries still resolve."""
    legacy = {line["id"]: line for line in load_catalog()["lines"]}
    result: dict[str, dict[str, Any]] = {}

    def illustrate(key: str, group: str, description: str, thresholds: tuple[int, ...] | None = None) -> None:
        line = legacy[key]
        milestones = list(thresholds or line["thresholds"])
        result[key] = {"id": key, "group": group, "groupName": GROUPS[group], "description": description,
                       "metric": line["metric"], "unit": line["unit"], "thresholds": milestones,
                       "applicability": line["applicability"],
                       "tiers": [{**tier, "threshold": n, "minimumEvidenceDays": 0}
                                 for tier, n in zip(line["tiers"], milestones, strict=True)]}

    for group, entries in ILLUSTRATED.items():
        for key, description in entries.items():
            illustrate(key, group, description)
    for line in original_series():
        result[line["id"]] = line
    for slug, name in EXERCISE_NAMES.items():
        illustrate(f"exercise.{slug}", "exercise", f"Упражнение «{name}». День засчитывается за два полных рабочих подхода или минуту работы на время. Для одностороннего движения левая и правая стороны составляют один подход.", (4, 16, 40, 90))
    for muscle_id, muscle in CANONICAL_MUSCLE_DEFINITIONS.items():
        illustrate(f"muscle.{muscle_id}", "muscle", f"{muscle.name}. День засчитывается за два полных рабочих подхода или минуту силового удержания, если на эту группу приходится основная нагрузка.", (6, 20, 50, 110))
    for key, line in legacy.items():
        if key not in result:
            result[key] = {**line, "group": "archive", "groupName": GROUPS["archive"], "archived": True}
    titles = json.loads(TITLES_PATH.read_text(encoding="utf-8"))
    for key, line in result.items():
        names = titles[key]
        line["name"] = names["name"]
        line["tiers"] = [{**tier, "title": title} for tier, title in zip(line["tiers"], names["tiers"], strict=True)]
        for index, tier in enumerate(line["tiers"]):
            if not line.get("archived"):
                tier["phrase"] = names["phrases"][index]
            title = tier["title"]
            tier["audioText"] = f"{title}{'' if title.endswith(('.', '!', '?', '…')) else '.'} {tier['phrase']}"
    for tier, rarity in zip(result["start.first_workout"]["tiers"], ("common", "rare", "epic"), strict=True):
        tier["rarity"] = rarity
    # The first page introduces different ways to earn awards before any personal history exists.
    featured = {key: result[key] for key in (
        "start.first_workout", "discovery.crossroads", "discovery.encore", "signature.bookends", "calendar.weekend_guest",
        "signature.reunited_pairs", "return.rediscovered", "calendar.month_bridge",
        "duet.machine_stretch", "signature.remix", "discovery.club_host", "calendar.format_relay", "discovery.old_and_new", "plan.planned_days",
    )}
    return featured | result
