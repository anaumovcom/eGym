"""Versioned, deterministic achievement rules. Editorial text and provider assets live elsewhere.

A line is an independent metric/scope. Its tiers are not independent lines.
No rule reads provider output, calls a provider, or changes a workout/hardware setting.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TypedDict

from app.services.achievements.version import MAX_TIERS

CATALOG_VERSION = "achievements-rules-1.3.0"
CONTENT_VERSION = "achievements-content-1.1.0"
TIER_NAMES = ("Начало", "Практика", "Мастерство", "Горизонт", "Наследие", "Большой путь",
              "Новая высота", "За пределами привычного")
RARITIES = ("common", "rare", "epic", "legendary")
# The second difficulty axis is independent of historical milestone numbers.
# Keeping milestone IDs/numbers preserves paid editorial and media verbatim.
EVIDENCE_DAY_PROFILES = {
    "start": (12, 24, 48),
    "rhythm": (12, 32, 72, 144, 240, 400),
    "practice": (16, 40, 90, 160, 260, 420),
    "variety": (12, 30, 75, 150, 240),
    "repertoire": (12, 30, 75, 150, 240),
    "volume": (16, 40, 90, 160, 260),
    "plan": (12, 30, 75, 150, 240),
    "progress": (12, 24, 48),
    "reflection": (12, 30, 75, 150, 240),
    "story": (12, 30, 75, 150, 240),
    "chapter": (12, 30, 75),
    "measured": (12, 30, 75, 150, 240),
}
EVIDENCE_DAY_OVERRIDES = {
    # This metric observes a 42-day window: 75 days was unreachable.
    "rhythm.after_return": (12, 20, 30),
    "chapter.30_days": (12, 18, 24),
}
GROUPS = {
    "start": "Начало пути",
    "rhythm": "Регулярность",
    "practice": "Сила практики",
    "variety": "Свобода движения",
    "repertoire": "Атлас движений",
    "volume": "Вес и объём",
    "plan": "По намеченному пути",
    "progress": "Личный прогресс",
    "reflection": "Дневник ощущений",
    "story": "Мир историй",
    "chapter": "Большие главы",
    "measured": "Точность тренажёра",
}


class Rule(TypedDict):
    id: str
    group: str
    metric: str
    unit: str
    description: str
    thresholds: list[int]
    applicability: str
    evidenceMetric: str
    minimumEvidenceDays: list[int]


def _rarity(index: int) -> str:
    # 4 common, 3 rare, 2 epic and 1 legendary line per group; tier counts vary.
    return RARITIES[0] if index < 4 else RARITIES[1] if index < 7 else RARITIES[2] if index < 9 else RARITIES[3]


def line(group: str, index: int, slug: str, metric: str, unit: str, description: str,
         thresholds: tuple[int, ...], applicability: str = "available") -> Rule:
    evidence = 'practice_evidence_days'
    if group == 'exercise' or group == 'muscle':
        evidence = metric
    elif group == 'progress':
        evidence = 'pr_days'
    elif group == 'story' or applicability == 'requires_story':
        evidence = 'episode_days'
    elif group == 'plan' or applicability == 'requires_plan':
        evidence = 'planned_days'
    elif group == 'measured':
        evidence = 'verified_days'
    elif 'note' in metric:
        evidence = 'note_days'
    elif applicability == 'requires_reflection':
        evidence = 'set_feedback_days' if 'feedback' in metric else 'reflection_days'
    elif metric.startswith('bodyweight'):
        evidence = 'bodyweight_days'
    elif metric.startswith('stretch'):
        evidence = 'stretch_days'
    elif metric.startswith('timed'):
        evidence = 'timed_days'
    elif group == 'volume':
        evidence = 'weighted_days'
    if metric == 'post_return_weeks':
        evidence = 'post_return_days'
    elif metric == 'return_active_days':
        evidence = 'return_practice_days'
    days = (list(thresholds) if group in {'exercise', 'muscle'} else
            list(EVIDENCE_DAY_OVERRIDES.get(f'{group}.{slug}', EVIDENCE_DAY_PROFILES[group])[:len(thresholds)]))
    if group not in {'exercise', 'muscle'}:
        evidence = f'evidence:{evidence}'
    description += (" Дополнительно для ступеней нужны разные дни подтверждённой практики: "
                    + ', '.join(map(str, days)) + ". Не подряд; без повышения нагрузки ради награды.")
    return {"id": f"{group}.{slug}", "group": group, "metric": metric, "unit": unit,
            "description": description, "thresholds": list(thresholds), "applicability": applicability,
            'evidenceMetric': evidence, 'minimumEvidenceDays': days}


def _group(group: str, rows: list[tuple[str, str, str, str, tuple[int, ...], str]]) -> list[Rule]:
    return [line(group, index, *row) for index, row in enumerate(rows)]


A = "available"
P = "requires_plan"
C = "requires_comparison"
R = "requires_reflection"
S = "requires_story"
M = "requires_sensor"


_RULE_GROUPS = (
    _group("start", [
        ("first_set", "qualified_sets", "подход", "Закрепить выполненные подходы многодневной рабочей практикой; первый подход сам по себе не награда.", (1, 5, 20), A),
        ("first_workout", "qualified_workouts", "тренировка", "Закрепить сохранённые тренировки многодневной рабочей практикой; одна тренировка не даёт награду.", (1, 3, 10), A),
        ("three_days", "active_days", "тренировочный день", "Потренироваться в разных днях и постепенно познакомиться со своим ритмом.", (3, 7, 14), A),
        ("two_weeks", "active_weeks", "неделя", "Оставить результаты в разных неделях.", (2, 4, 8), A),
        ("exercise_return", "best_exercise_days", "день с упражнением", "Возвращаться к одному упражнению в разные дни.", (3, 7, 15), A),
        ("first_plan", "plan_full_workouts", "тренировка по плану", "Выполнить исходный план и собрать первую серию таких тренировок.", (1, 3, 10), P),
        ("first_feedback", "reflection_days", "день с отметкой", "Сохранять самочувствие или дискомфорт после тренировки.", (1, 3, 10), R),
        ("first_note", "note_days", "день с заметкой", "Добавлять собственные заметки к тренировкам.", (1, 3, 10), R),
        ("first_program", "completed_programs", "программа", "Завершать тренировки из сохранённых программ.", (1, 3, 8), A),
        ("first_story", "episode_days", "эпизод", "Сохранять итоговые эпизоды тренировок.", (1, 3, 10), S),
    ]),
    _group("rhythm", [
        ("active_days", "active_days", "тренировочный день", "Накопить дни с сохранённой работой.", (5, 15, 30, 60, 120, 240), A),
        ("active_weeks", "active_weeks", "активная неделя", "Оставить результаты в разных неделях, не обязательно подряд.", (4, 12, 26, 52, 104), A),
        ("week_streak", "best_week_streak", "неделя подряд", "Собрать серию недель с тренировками без требования заниматься ежедневно.", (3, 6, 12), A),
        ("two_days_week", "two_day_weeks", "неделя с двумя днями", "Накопить недели, в каждой из которых было два тренировочных дня.", (2, 6, 12), A),
        ("months", "active_months", "активный месяц", "Накопить календарные месяцы с минимум двумя тренировочными днями.", (3, 6, 12, 18, 24), A),
        ("quarters", "active_quarters", "квартал", "Накопить кварталы, в каждом из которых было минимум шесть тренировочных дней.", (2, 4, 8), A),
        ("return", "return_active_days", "день после возвращения", "После перерыва от четырнадцати полных дней вернуться и продолжить тренировки.", (1, 3, 7), A),
        ("after_return", "post_return_weeks", "неделя после возвращения", "После первого возвращения оставить результаты в нескольких неделях из следующих шести.", (3, 4, 5), A),
        ("three_days_week", "three_day_weeks", "неделя с тремя днями", "Накопить недели с тремя тренировочными днями, если такой ритм подходит пользователю.", (2, 6, 12), A),
        ("year_weeks", "best_week_streak", "неделя подряд", "Удерживать собственный ритм в течение длинной серии недель.", (26, 39, 52), A),
    ]),
    _group("practice", [
        ("workouts", "qualified_workouts", "тренировка", "Накопить сохранённые тренировки с фактической работой.", (5, 20, 50, 100, 200, 400), A),
        ("sets", "qualified_sets", "подход", "Накопить выполненные подходы, включая разминочные и частичные.", (10, 50, 150), A),
        ("reps", "qualified_reps", "повторение", "Накопить повторения в подходах повторного типа.", (100, 500, 1500, 3000, 7500, 15000), A),
        ("working_sets", "working_sets", "рабочий подход", "Накопить рабочие подходы без разминочных.", (10, 50, 150), A),
        ("exercise_sessions", "completed_exercises", "упражнение", "Накопить завершённые записи упражнений с результатами.", (5, 25, 75), A),
        ("partial_workouts", "partial_workouts", "частичная тренировка", "Сохранить частичные тренировки: выполненная работа тоже имеет значение.", (1, 5, 15), A),
        ("multi_set_days", "multi_set_days", "день с пятью подходами", "Накопить дни, в каждом из которых выполнено минимум пять подходов.", (2, 8, 20), A),
        ("three_exercise_days", "three_exercise_days", "день с тремя упражнениями", "Накопить дни с результатами по трём разным упражнениям.", (2, 8, 20), A),
        ("focus", "best_exercise_days", "день с упражнением", "Возвращаться к одному любимому упражнению в разные дни.", (5, 15, 30), A),
        ("thousand_sets", "qualified_sets", "подход", "Продолжать накапливать большую историю практики.", (400, 1000, 2500), A),
    ]),
    _group("variety", [
        ("timed_seconds", "timed_seconds", "секунда", "Накопить фактические секунды упражнений на время.", (300, 1800, 7200), A),
        ("timed_days", "timed_days", "день на время", "Накопить дни с упражнениями на время или растяжкой.", (3, 10, 25), A),
        ("stretch_seconds", "stretch_seconds", "секунда растяжки", "Накопить секунды сохранённых упражнений на растяжку.", (300, 1800, 7200), A),
        ("stretch_days", "stretch_days", "день растяжки", "Накопить дни с сохранённой растяжкой.", (3, 10, 25, 50, 100), A),
        ("bodyweight_reps", "bodyweight_reps", "повторение", "Накопить повторения в упражнениях с собственным весом.", (50, 300, 1000), A),
        ("bodyweight_sets", "bodyweight_sets", "подход с весом тела", "Накопить подходы с собственным весом.", (5, 25, 75), A),
        ("bodyweight_days", "bodyweight_days", "день с весом тела", "Накопить дни с упражнениями с собственным весом.", (3, 10, 25), A),
        ("mixed_kind_days", "mixed_kind_days", "смешанный день", "Накопить дни с двумя разными типами упражнений.", (2, 8, 20), A),
        ("machine_days", "machine_days", "день на тренажёре", "Накопить дни с упражнениями на тренажёре.", (3, 10, 25), A),
        ("bodyweight_exercises", "bodyweight_exercises", "упражнение с весом тела", "Познакомиться с разными упражнениями с собственным весом.", (2, 5, 10), A),
    ]),
    _group("repertoire", [
        ("distinct_exercises", "distinct_exercises", "упражнение", "Оставить результаты в разных упражнениях.", (3, 8, 15, 25, 40), A),
        ("familiar", "familiar_exercises", "знакомое упражнение", "Накопить упражнения, каждое из которых выполнялось минимум в трёх днях.", (2, 5, 10), A),
        ("exploration", "planned_distinct_exercises", "упражнение по плану", "Выполнить разные упражнения, входившие в исходный согласованный план.", (3, 8, 15), P),
        ("familiar_days", "familiar_days", "день знакомой практики", "Накопить дни с упражнением, уже встречавшимся ранее в трёх днях.", (5, 15, 40), A),
        ("exercise_weeks", "best_exercise_weeks", "неделя с упражнением", "Возвращаться к одному упражнению в разных неделях.", (3, 8, 16), A),
        ("new_exercise_months", "new_exercise_months", "месяц открытий", "Накопить месяцы, в которых впервые выполнено новое упражнение.", (2, 4, 8), A),
        ("machine_exercises", "machine_exercises", "упражнение на тренажёре", "Познакомиться с разными упражнениями на тренажёре.", (2, 5, 10), A),
        ("timed_exercises", "timed_exercises", "упражнение на время", "Познакомиться с разными упражнениями на время и растяжку.", (2, 5, 10), A),
        ("five_exercise_days", "five_exercise_days", "день с пятью упражнениями", "Накопить дни с результатами по пяти разным упражнениям.", (1, 5, 15), A),
        ("repertoire_months", "repertoire_months", "месяц с тремя упражнениями", "Накопить месяцы с результатами минимум по трём разным упражнениям.", (2, 6, 12), A),
    ]),
    _group("volume", [
        ("volume", "volume_grams", "килограмм объёма", "Накопить учётный объём: повторения, умноженные на сохранённый вес.", (1000, 10000, 50000), A),
        ("weighted_sets", "weighted_sets", "подход с весом", "Накопить подходы с положительным сохранённым весом.", (10, 50, 150), A),
        ("weighted_reps", "weighted_reps", "повторение с весом", "Накопить повторения с положительным сохранённым весом.", (100, 500, 1500), A),
        ("volume_days", "volume_days", "день с объёмом", "Накопить дни с положительным учётным объёмом.", (3, 10, 25), A),
        ("weighted_days", "weighted_days", "день с весом", "Накопить дни с подходами с положительным весом.", (3, 10, 25, 50, 100), A),
        ("volume_weeks", "volume_weeks", "неделя с объёмом", "Накопить недели с учётным объёмом от пятисот килограммов.", (2, 6, 12), A),
        ("weight_exercises", "weight_exercises", "упражнение с весом", "Оставить результаты с положительным весом в разных упражнениях.", (2, 5, 10), A),
        ("volume_months", "volume_months", "месяц с объёмом", "Накопить месяцы с учётным объёмом от пяти тысяч килограммов.", (2, 6, 12), A),
        ("volume_milestones", "volume_grams", "килограмм объёма", "Продолжать большую историю учётного объёма без цели на одну тренировку.", (100000, 250000, 500000), A),
        ("weighted_reps_milestones", "weighted_reps", "повторение с весом", "Накопить большую историю повторений с сохранённым весом.", (5000, 15000, 50000), A),
    ]),
    _group("plan", [
        ("complete", "plan_full_workouts", "тренировка по плану", "Выполнить исходный план тренировки без заднего уменьшения целей.", (1, 5, 15), P),
        ("exercise", "plan_full_exercises", "упражнение по плану", "Завершить обязательные подходы упражнений с исходными целями.", (5, 20, 60), P),
        ("repeat_program", "repeat_program_days", "день с программой", "Выполнить одну и ту же версию программы в разные дни.", (3, 8, 20), P),
        ("chapters", "plan_templates", "шаблон программы", "Выполнить исходные планы разных шаблонов программы.", (2, 4, 6), P),
        ("full_weeks", "plan_full_weeks", "неделя с планом", "Накопить недели с минимум одной полностью выполненной исходной тренировкой.", (2, 6, 12), P),
        ("plan_streak", "plan_week_streak", "неделя подряд с планом", "Собрать серию недель с полностью выполненной исходной тренировкой.", (2, 4, 8), P),
        ("planned_sets", "planned_met_sets", "подход по цели", "Достичь исходной цели в запланированных подходах.", (10, 50, 150), P),
        ("planned_days", "planned_days", "день по плану", "Накопить дни с результатами по исходному согласованному плану.", (3, 10, 25, 50, 100), P),
        ("plan_exercises_many", "plan_full_exercises", "упражнение по плану", "Продолжать историю полностью выполненных упражнений из исходного плана.", (100, 200, 400), P),
        ("plan_workouts_many", "plan_full_workouts", "тренировка по плану", "Продолжать историю полностью выполненных исходных тренировок.", (25, 50, 100), P),
    ]),
    _group("progress", [
        ("first_pr", "pr_days", "день улучшения", "Получать подтверждённые улучшения после предыдущих сопоставимых сессий.", (1, 2, 5), C),
        ("rep_pr", "rep_pr_days", "день рекорда повторений", "Улучшить повторения при том же весе и сопоставимых условиях.", (1, 3, 8), C),
        ("weight_pr", "weight_pr_days", "день рекорда веса", "Увеличить рабочий вес в выполненном сопоставимом подходе.", (1, 3, 8), C),
        ("estimate_pr", "e1rm_pr_days", "день расчётного рекорда", "Улучшить оценочный показатель силы более чем на один процент.", (1, 3, 8), C),
        ("multi_exercise", "pr_exercises", "упражнение с улучшением", "Получить подтверждённые улучшения в разных упражнениях.", (2, 4, 8), C),
        ("after_month", "long_arc_exercises", "упражнение с длинной дугой", "Улучшить результат относительно baseline возрастом минимум двадцать восемь дней.", (1, 3, 6), C),
        ("retained", "retained_results", "закреплённый результат", "Повторить новый личный результат ещё в двух последующих днях.", (1, 3, 5), C),
        ("pr_weeks", "pr_weeks", "неделя с улучшением", "Накопить недели с подтверждёнными личными улучшениями.", (2, 6, 12), C),
        ("pr_months", "pr_months", "месяц с улучшением", "Накопить месяцы с подтверждёнными личными улучшениями.", (2, 4, 8), C),
        ("pr_days_many", "pr_days", "день улучшения", "Продолжать историю сопоставимых личных улучшений.", (5, 15, 30), C),
    ]),
    _group("reflection", [
        ("checkin", "reflection_days", "день с отметкой", "Сохранять отметку самочувствия или дискомфорта; её содержание не оценивается.", (3, 10, 30), R),
        ("months", "reflection_months", "месяц наблюдений", "Оставлять отметки ощущений в разных календарных месяцах.", (2, 4, 8), R),
        ("weeks", "reflection_weeks", "неделя наблюдений", "Оставлять отметки ощущений в разных неделях.", (4, 12, 26), R),
        ("note", "note_days", "день с заметкой", "Добавлять собственные заметки к тренировкам.", (1, 5, 15), R),
        ("adjusted", "adjusted_workouts", "корректировка", "Явно сохранять корректировки плана с допустимой причиной.", (1, 3, 8), R),
        ("effort_sets", "effort_feedback_sets", "подход с оценкой", "Сохранять субъективную оценку усилия после подходов.", (3, 15, 50), R),
        ("feedback_days", "set_feedback_days", "день обратной связи", "Накопить дни с явной обратной связью о подходах.", (2, 8, 20), R),
        ("note_weeks", "note_weeks", "неделя с заметкой", "Оставлять собственные заметки в разных неделях.", (2, 6, 12, 26, 52), R),
        ("feedback_exercises", "feedback_exercises", "упражнение с отзывом", "Оставить явную обратную связь в разных упражнениях.", (2, 5, 10), R),
        ("reflection_year", "reflection_weeks", "неделя наблюдений", "Продолжать необязательный дневник ощущений в течение длинной истории.", (39, 52, 78), R),
    ]),
    _group("story", [
        ("world_days", "best_world_days", "день в одном мире", "Возвращаться в один сюжетный мир в разные дни.", (3, 7, 15), S),
        ("explorer", "story_worlds", "сюжетный мир", "Сохранить тренировки в разных сюжетных архетипах.", (3, 6, 10), S),
        ("acts", "story_acts", "акт истории", "Выполнить обязательные baseline-условия сюжетных актов.", (3, 10, 30), S),
        ("finale", "story_finale_days", "финал по плану", "Завершить исходный план тренировки с выбранным сценарием.", (1, 5, 15), S),
        ("return_world", "world_returns", "возвращение в мир", "Вернуться в знакомый архетип после двадцати восьми дней.", (1, 3, 6), S),
        ("archive", "episode_days", "день с эпизодом", "Накопить дни с сохранённым локальным или облачным эпизодом.", (5, 20, 50, 100, 200), S),
        ("world_return", "best_world_months", "месяц одного мира", "Встретить один сюжетный архетип в разных календарных месяцах.", (2, 4, 8), S),
        ("world_chapters", "three_world_triptych", "триптих миров", "Собирать триптихи: минимум три дня в каждом из трёх разных архетипов.", (1, 2, 3), S),
        ("world_months", "story_months", "месяц историй", "Сохранять эпизоды в разных календарных месяцах.", (2, 6, 12), S),
        ("story_weeks", "story_weeks", "неделя историй", "Сохранять эпизоды в разных неделях.", (4, 12, 26), S),
    ]),
    _group("chapter", [
        ("30_days", "chapter_30", "% главы", "Тридцать дней пути и шесть тренировочных дней; прогресс учитывает обе части.", (50, 75, 100), A),
        ("90_days", "chapter_90", "% главы", "Девяносто дней пути и восемнадцать тренировочных дней; прогресс учитывает обе части.", (50, 75, 100), A),
        ("365_days", "chapter_365", "% главы", "Год пути и сорок тренировочных дней; прогресс учитывает обе части.", (50, 75, 100), A),
        ("foundation", "chapter_foundation", "% главы", "Пятнадцать тренировочных дней и четыре активные недели.", (50, 75, 100), A),
        ("craft", "chapter_craft", "% главы", "Тридцать дней, сто пятьдесят подходов и двенадцать активных недель.", (50, 75, 100), A),
        ("atlas", "chapter_atlas", "% главы", "Шестьдесят дней и двадцать шесть активных недель.", (50, 75, 100), A),
        ("balance", "chapter_balance", "% главы", "Базовые ступени регулярности, практики и наблюдений или плана.", (50, 75, 100), A),
        ("worlds", "chapter_worlds", "% главы", "Десять миров, тридцать сюжетных дней и двенадцать активных недель.", (50, 75, 100), S),
        ("second_year", "chapter_second_year", "% главы", "Два года пути, восемьдесят дней и пятьдесят две активные недели.", (50, 75, 100), A),
        ("veteran", "chapter_veteran", "% главы", "Сто двадцать дней, тысяча подходов и пятьдесят две активные недели.", (50, 75, 100), A),
    ]),
    _group("measured", [
        ("rhythm", "measured_rhythm_sets", "стабильный подход", "Накопить подходы с валидным коэффициентом вариации длительности повторений.", (3, 10, 30), M),
        ("rhythm_days", "measured_rhythm_days", "день стабильности", "Накопить дни с двумя валидными стабильными подходами.", (3, 10, 25), M),
        ("repeatable", "measured_repeatable_pairs", "сопоставимая пара", "Повторить ритм одного упражнения в разные дни с близкой медианой.", (1, 5, 15), M),
        ("verified_workouts", "verified_workouts", "подтверждённая тренировка", "Накопить тренировки с доказанным датчиковым происхождением.", (3, 10, 25), M),
        ("verified_sets", "verified_sets", "подтверждённый подход", "Накопить подходы с валидным датчиковым provenance.", (10, 50, 150), M),
        ("verified_days", "verified_days", "подтверждённый день", "Накопить дни с валидными датчиковыми результатами.", (3, 10, 25, 50, 100), M),
        ("verified_reps", "verified_reps", "подтверждённое повторение", "Накопить повторения с валидным датчиковым provenance.", (100, 500, 1500), M),
        ("calibrated", "calibrated_workouts", "калиброванная тренировка", "Накопить тренировки с зафиксированной валидной калибровкой.", (3, 10, 25), M),
        ("paired_sides", "paired_side_days", "день двух сторон", "Накопить дни с канонически подтверждёнными подходами на обе стороны.", (2, 8, 20), M),
        ("range_days", "range_consistent_days", "день диапазона", "Накопить дни с валидной сохранённой моделью границ каждого повторения.", (2, 8, 20), M),
    ]),
)
RULES: tuple[Rule, ...] = tuple(rule for group in _RULE_GROUPS for rule in group)

assert len(RULES) == 120, len(RULES)
assert len({rule["id"] for rule in RULES}) == 120
assert len(TIER_NAMES) == MAX_TIERS
assert all(3 <= len(rule["thresholds"]) <= MAX_TIERS for rule in RULES)
assert all(a < b for rule in RULES for a, b in pairwise(rule["thresholds"]))
assert {rule["group"] for rule in RULES} == set(GROUPS)
assert all(sum(rule["group"] == group for rule in RULES) == 10 for group in GROUPS)


def rarity_for(definition_id: str) -> str:
    group, slug = definition_id.split(".", 1)
    rows = [rule for rule in RULES if rule["group"] == group]
    return _rarity(next(index for index, rule in enumerate(rows) if rule["id"] == definition_id))


# Append-only extension. Historical IDs/thresholds above remain owned by the core registry.
from app.services.achievements.training_scope import (  # noqa: E402
    CANONICAL_GROUP_IDS,
    PRACTICE_DAY_THRESHOLDS,
    SAVED_PROGRAM_EXERCISES,
    exercise_metric,
    muscle_metric,
)
from app.services.muscle_catalog import CANONICAL_MUSCLE_DEFINITIONS  # noqa: E402

GROUPS.update({"exercise": "Практика конкретных упражнений", "muscle": "Практика мышечных групп"})
EXTENSION_RULES: tuple[Rule, ...] = tuple(
    line("exercise", index, slug, exercise_metric(slug), "день практики",
         f"Практиковать {slug} в разные тренировочные дни: минимум два полных рабочих подхода "
         "или 60 фактических секунд за день. Для одностороннего упражнения нужны обе стороны раунда.",
         PRACTICE_DAY_THRESHOLDS)
    for index, slug in enumerate(SAVED_PROGRAM_EXERCISES)
) + tuple(
    line("muscle", index, muscle_id, muscle_metric(muscle_id), "день основной нагрузки",
         f"{CANONICAL_MUSCLE_DEFINITIONS[muscle_id].name}: накопить дни с явной канонической ролью primary, "
         "минимум два полных рабочих подхода или 60 секунд силового удержания. "
         "Вспомогательные роли, кардио и растяжка не засчитываются.", PRACTICE_DAY_THRESHOLDS, 'requires_primary')
    for index, muscle_id in enumerate(CANONICAL_GROUP_IDS)
)
RULES += EXTENSION_RULES
assert len({rule["id"] for rule in RULES}) == len(RULES)
assert all(3 <= len(rule["thresholds"]) <= MAX_TIERS for rule in EXTENSION_RULES)
