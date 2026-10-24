from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.models.analytics import WorkoutSession
from app.models.training import ExerciseHistoryRecord
from app.schemas.analytics import (
    ProgressActivityDaySchema,
    ProgressActivitySchema,
    ProgressExerciseInsightSchema,
    ProgressExerciseSessionSchema,
    ProgressInsightSchema,
    ProgressInsightsSchema,
    ProgressKpiSchema,
    ProgressMoverSchema,
    ProgressMuscleShareSchema,
    ProgressNextTargetSchema,
    ProgressRecordSchema,
    ProgressTimelinePointSchema,
    ProgressTimelineSchema,
)
from app.services.exercise_library import get_imported_exercise

PERIOD_DAYS = {"7d": 7, "30d": 30, "3m": 90, "6m": 180, "1y": 365}
PREVIOUS_LABELS = {"7d": "прошлыми 7 днями", "30d": "прошлыми 30 днями", "3m": "прошлыми 3 месяцами", "6m": "прошлым полугодием", "1y": "прошлым годом"}
ACTIVITY_WEEKS = 20
MONTHS = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")

# Muscle ids from the exercise library folded into the zones a trainee thinks in.
MUSCLE_ZONES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("chest", "Грудь", frozenset({"chest"})),
    ("back", "Спина", frozenset({"lats", "traps", "traps-middle", "lower-back"})),
    ("shoulders", "Плечи", frozenset({"front-shoulders", "rear-shoulders", "shoulders"})),
    ("arms", "Руки", frozenset({"biceps", "triceps", "forearms"})),
    ("legs", "Ноги", frozenset({"quads", "hamstrings", "glutes", "calves"})),
    ("core", "Кор", frozenset({"abdominals", "obliques"})),
)


@dataclass(frozen=True)
class _Session:
    row: ExerciseHistoryRecord
    at: datetime
    day: date
    reps_per_set: int
    e1rm: float | None


def estimate_one_rep_max(weight_kg: float, reps_per_set: int) -> float | None:
    """Epley estimate; comparable across sessions with different rep ranges."""
    if weight_kg <= 0 or reps_per_set <= 0:
        return None
    if reps_per_set == 1:
        return round(weight_kg, 1)
    return round(weight_kg * (1 + min(reps_per_set, 20) / 30), 1)


def next_target(weight_kg: float, reps_per_set: int, sets: int, rpe: int) -> ProgressNextTargetSchema:
    """Double progression: easy sets add load, hard sets add a rep, maximal sets hold."""
    if rpe >= 9:
        return ProgressNextTargetSchema(weight_kg=weight_kg, sets=sets, reps_per_set=reps_per_set, note="Прошлый раз было тяжело — повторите вес и закрепите технику.")
    if rpe >= 8 and reps_per_set < 15:
        return ProgressNextTargetSchema(weight_kg=weight_kg, sets=sets, reps_per_set=reps_per_set + 1, note="Запас небольшой — добавьте по одному повтору в подходе.")
    step = max(0.5, round(weight_kg * 0.05 * 2) / 2)
    return ProgressNextTargetSchema(weight_kg=round(weight_kg + step, 1), sets=sets, reps_per_set=reps_per_set, note=f"Запас есть — добавьте {_kg(step)} кг при тех же повторах.")


class ProgressInsightsBuilder:
    def __init__(self, *, period: str, history: list[ExerciseHistoryRecord], workouts: list[WorkoutSession], now: datetime | None = None) -> None:
        self.now = (now or datetime.now(UTC)).astimezone()
        self.today = self.now.date()
        days = PERIOD_DAYS.get(period)
        self.period = period
        self.since = self.now - timedelta(days=days) if days else None
        self.previous_since = self.now - timedelta(days=days * 2) if days else None
        self.workouts = workouts
        self.by_exercise: dict[str, list[_Session]] = defaultdict(list)
        for row in sorted(history, key=lambda item: item.performed_at):
            at = _local(row.performed_at)
            reps_per_set = int(round(row.reps / max(row.sets, 1)))
            self.by_exercise[row.exercise_slug].append(_Session(row, at, at.date(), reps_per_set, estimate_one_rep_max(row.weight_kg, reps_per_set)))
        self.sessions = sorted((item for items in self.by_exercise.values() for item in items), key=lambda item: item.at)
        self.pr_rows = self._personal_records()

    def build(self) -> ProgressInsightsSchema:
        current = [item for item in self.sessions if self._in_period(item.at)]
        records = [item for item in self.pr_rows if self._in_period(item[0].at)]
        timeline = self._timeline(current)
        exercises = self._exercises()
        muscle_balance = self._muscle_balance(current)
        movers = self._movers()
        return ProgressInsightsSchema(
            period_start=self.since.date().isoformat() if self.since else None,
            previous_label=PREVIOUS_LABELS.get(self.period),
            kpis=self._kpis(current, records, timeline),
            activity=self._activity(),
            timeline=timeline,
            records=[
                ProgressRecordSchema(
                    exercise_slug=item.row.exercise_slug, exercise_name=_exercise_name(item.row.exercise_slug), date=item.at.isoformat(),
                    e1rm=item.e1rm or 0, previous=previous, weight_kg=item.row.weight_kg, reps_per_set=item.reps_per_set,
                )
                for item, previous in sorted(records, key=lambda pair: pair[0].at, reverse=True)[:6]
            ],
            record_count=len(records),
            movers=movers,
            muscle_balance=muscle_balance,
            insights=self._insights(current, movers, muscle_balance),
            exercises=exercises,
        )

    def _in_period(self, at: datetime) -> bool:
        return self.since is None or at >= self.since

    def _in_previous(self, at: datetime) -> bool:
        return self.since is not None and self.previous_since is not None and self.previous_since <= at < self.since

    def _personal_records(self) -> list[tuple[_Session, float]]:
        records: list[tuple[_Session, float]] = []
        for items in self.by_exercise.values():
            best: float | None = None
            for item in items:
                if item.e1rm is None:
                    continue
                if best is not None and item.e1rm > best:
                    records.append((item, best))
                best = item.e1rm if best is None else max(best, item.e1rm)
        return records

    def _minutes(self, workouts: list[WorkoutSession]) -> float:
        # Abandoned runtime sessions are only a few seconds long and would only add noise.
        return round(sum(item.duration_seconds for item in workouts if item.duration_seconds >= 60) / 60)

    def _kpis(self, current: list[_Session], records: list[tuple[_Session, float]], timeline: ProgressTimelineSchema) -> list[ProgressKpiSchema]:
        previous = [item for item in self.sessions if self._in_previous(item.at)]
        current_workouts = [item for item in self.workouts if self._in_period(_local(item.started_at))]
        previous_workouts = [item for item in self.workouts if self._in_previous(_local(item.started_at))]
        previous_records = [item for item in self.pr_rows if self._in_previous(item[0].at)]
        has_previous = self.since is not None and bool(previous or previous_workouts)
        spark_buckets = [point.start for point in timeline.points]

        def spark(values: dict[str, float]) -> list[float]:
            return [round(values.get(start, 0.0), 1) for start in spark_buckets]

        days_by_bucket: dict[str, float] = {point.start: point.days for point in timeline.points}
        volume_by_bucket: dict[str, float] = {point.start: point.volume_kg for point in timeline.points}
        minutes_by_bucket: dict[str, float] = defaultdict(float)
        for workout in current_workouts:
            if workout.duration_seconds >= 60:
                minutes_by_bucket[self._bucket_start(_local(workout.started_at).date(), timeline.granularity).isoformat()] += workout.duration_seconds / 60
        records_by_bucket: dict[str, float] = defaultdict(float)
        for item, _ in records:
            records_by_bucket[self._bucket_start(item.day, timeline.granularity).isoformat()] += 1

        def kpi(id_: str, label: str, value: float, unit: str, before: float, series: dict[str, float]) -> ProgressKpiSchema:
            delta = round((value - before) / before * 100) if has_previous and before > 0 else None
            return ProgressKpiSchema(id=id_, label=label, value=value, unit=unit, previous=before if has_previous else None, delta_pct=delta, spark=spark(series))

        return [
            kpi("days", "Тренировочных дней", len({item.day for item in current}), "", len({item.day for item in previous}), days_by_bucket),
            kpi("volume", "Поднятый объём", round(sum(item.row.volume_kg for item in current)), "кг", round(sum(item.row.volume_kg for item in previous)), volume_by_bucket),
            kpi("minutes", "Время тренировок", self._minutes(current_workouts), "мин", self._minutes(previous_workouts), minutes_by_bucket),
            kpi("records", "Личных рекордов", len(records), "", len(previous_records), records_by_bucket),
        ]

    def _activity(self) -> ProgressActivitySchema:
        week_start = self.today - timedelta(days=self.today.weekday())
        first = week_start - timedelta(weeks=ACTIVITY_WEEKS - 1)
        sets: dict[date, int] = defaultdict(int)
        volume: dict[date, float] = defaultdict(float)
        for item in self.sessions:
            if item.day >= first:
                sets[item.day] += item.row.sets
                volume[item.day] += item.row.volume_kg
        peak = max(sets.values(), default=0)
        weeks: list[list[ProgressActivityDaySchema]] = []
        for week in range(ACTIVITY_WEEKS):
            days = []
            for weekday in range(7):
                day = first + timedelta(weeks=week, days=weekday)
                level = 0 if not sets.get(day) else min(4, 1 + int(3 * sets[day] / max(peak, 1)))
                days.append(ProgressActivityDaySchema(date=day.isoformat(), level=level, sets=sets.get(day, 0), volume_kg=round(volume.get(day, 0.0)), future=day > self.today))
            weeks.append(days)
        last_day = self.sessions[-1].day if self.sessions else None
        return ProgressActivitySchema(
            weeks=weeks,
            active_days=sum(1 for day in sets if day >= first),
            streak_weeks=self._streak_weeks(),
            days_since_last=(self.today - last_day).days if last_day else None,
        )

    def _streak_weeks(self) -> int:
        weeks = {item.day - timedelta(days=item.day.weekday()) for item in self.sessions}
        cursor = self.today - timedelta(days=self.today.weekday())
        if cursor not in weeks:
            # The current week is still open: a streak survives until it ends without training.
            cursor -= timedelta(weeks=1)
        streak = 0
        while cursor in weeks:
            streak += 1
            cursor -= timedelta(weeks=1)
        return streak

    def _granularity(self) -> str:
        start = self.since.date() if self.since else (self.sessions[0].day if self.sessions else self.today)
        span = (self.today - start).days
        return "day" if span <= 31 else "week" if span <= 200 else "month"

    def _bucket_start(self, day: date, granularity: str) -> date:
        if granularity == "week":
            return day - timedelta(days=day.weekday())
        if granularity == "month":
            return day.replace(day=1)
        return day

    def _timeline(self, current: list[_Session]) -> ProgressTimelineSchema:
        granularity = self._granularity()
        start = self._bucket_start(self.since.date() if self.since else (self.sessions[0].day if self.sessions else self.today), granularity)
        buckets: list[date] = []
        cursor = start
        while cursor <= self.today:
            buckets.append(cursor)
            if granularity == "day":
                cursor += timedelta(days=1)
            elif granularity == "week":
                cursor += timedelta(weeks=1)
            else:
                cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        volume: dict[date, float] = defaultdict(float)
        sets: dict[date, int] = defaultdict(int)
        days: dict[date, set[date]] = defaultdict(set)
        for item in current:
            key = self._bucket_start(item.day, granularity)
            volume[key] += item.row.volume_kg
            sets[key] += item.row.sets
            days[key].add(item.day)
        return ProgressTimelineSchema(
            granularity=granularity,
            points=[
                ProgressTimelinePointSchema(start=day.isoformat(), label=_bucket_label(day, granularity), volume_kg=round(volume[day]), sets=sets[day], days=len(days[day]))
                for day in buckets
            ],
        )

    def _growth(self, items: list[_Session]) -> tuple[float, float, list[_Session]] | None:
        """Start = last result before the period (or its first one); end = best of the latest three sessions."""
        weighted = [item for item in items if item.e1rm is not None]
        in_period = [item for item in weighted if self._in_period(item.at)]
        baseline = [item for item in weighted if not self._in_period(item.at)][-1:] + in_period
        if not in_period or len(baseline) < 2:
            return None
        start, end = baseline[0].e1rm or 0, max(item.e1rm or 0 for item in in_period[-3:])
        return (start, end, baseline) if start > 0 else None

    def _movers(self) -> list[ProgressMoverSchema]:
        movers = []
        for slug, items in self.by_exercise.items():
            growth = self._growth(items)
            if growth is None or growth[1] <= growth[0]:
                continue
            start, end, baseline = growth
            movers.append(ProgressMoverSchema(
                slug=slug, name=_exercise_name(slug), from_value=start, to_value=end,
                delta_pct=round((end - start) / start * 100, 1), series=[item.e1rm or 0 for item in baseline[-12:]],
            ))
        return sorted(movers, key=lambda item: item.delta_pct, reverse=True)[:5]

    def _muscle_balance(self, current: list[_Session]) -> list[ProgressMuscleShareSchema]:
        sets: dict[str, int] = defaultdict(int)
        for item in current:
            exercise = get_imported_exercise(item.row.exercise_slug)
            if exercise is None or exercise.equipment == "Cardio":
                continue
            for zone_id, _, muscles in MUSCLE_ZONES:
                if muscles.intersection(exercise.muscles):
                    sets[zone_id] += item.row.sets
        total = sum(sets.values())
        return [
            ProgressMuscleShareSchema(id=zone_id, name=name, sets=sets[zone_id], share=round(sets[zone_id] / total, 3) if total else 0)
            for zone_id, name, _ in MUSCLE_ZONES
        ]

    def _exercises(self) -> list[ProgressExerciseInsightSchema]:
        result = []
        pr_ids = {id(item) for item, _ in self.pr_rows}
        for slug, items in self.by_exercise.items():
            exercise = get_imported_exercise(slug)
            weighted = [item for item in items if item.e1rm is not None]
            in_period = [item for item in items if self._in_period(item.at)]
            growth = self._growth(items)
            trend = round((growth[1] - growth[0]) / growth[0] * 100, 1) if growth else None
            last = weighted[-1] if weighted else None
            result.append(ProgressExerciseInsightSchema(
                slug=slug,
                name=_exercise_name(slug),
                kind="weighted" if weighted else "bodyweight",
                unit="сек" if exercise is not None and exercise.equipment == "Cardio" else "повт.",
                sessions_in_period=len(in_period),
                last_date=items[-1].at.isoformat(),
                best_e1rm=max((item.e1rm or 0 for item in weighted), default=None) if weighted else None,
                best_weight=max(item.row.weight_kg for item in items),
                best_volume=round(max(item.row.volume_kg for item in items)),
                best_reps=max(item.reps_per_set for item in items),
                trend_pct=trend,
                sessions=[
                    ProgressExerciseSessionSchema(
                        date=item.at.isoformat(), weight_kg=item.row.weight_kg, sets=item.row.sets, reps=item.row.reps,
                        reps_per_set=item.reps_per_set, volume_kg=round(item.row.volume_kg), rpe=item.row.rpe, e1rm=item.e1rm, is_pr=id(item) in pr_ids,
                    )
                    for item in items
                ],
                next_target=next_target(last.row.weight_kg, last.reps_per_set, last.row.sets, last.row.rpe) if last else None,
            ))
        return sorted(result, key=lambda item: (item.sessions_in_period, item.last_date), reverse=True)

    def _insights(self, current: list[_Session], movers: list[ProgressMoverSchema], balance: list[ProgressMuscleShareSchema]) -> list[ProgressInsightSchema]:
        insights: list[ProgressInsightSchema] = []
        last_day = self.sessions[-1].day if self.sessions else None
        idle = (self.today - last_day).days if last_day else None
        if idle is not None and idle >= 4:
            insights.append(ProgressInsightSchema(tone="warning", title=f"Пауза {idle} {_plural(idle, 'день', 'дня', 'дней')}", text="Мышцы уже восстановились — самое время вернуться к тренировкам, чтобы не терять набранный уровень.", href="/dashboard"))
        if movers:
            best = movers[0]
            insights.append(ProgressInsightSchema(tone="good", title=f"{best.name}: +{_pct(best.delta_pct)}%", text=f"Расчётный максимум вырос с {_kg(best.from_value)} до {_kg(best.to_value)} кг. Это лучший рост за период.", href=f"/progress?tab=strength&exercise={best.slug}"))
        days = len({item.day for item in current})
        period_days = PERIOD_DAYS.get(self.period)
        if period_days and period_days >= 14 and days:
            per_week = days / (period_days / 7)
            if per_week >= 2.5:
                insights.append(ProgressInsightSchema(tone="good", title=f"{_pct(per_week)} тренировки в неделю", text="Отличная регулярность — именно она даёт стабильный рост силы."))
            elif per_week < 1.5:
                insights.append(ProgressInsightSchema(tone="info", title=f"{_pct(per_week)} тренировки в неделю", text="Для заметного прогресса стоит заниматься хотя бы 2–3 раза в неделю.", href="/calendar"))
        trained = [item for item in balance if item.sets > 0]
        if len(trained) >= 2:
            lagging = [item for item in balance if item.share < 0.08]
            if lagging:
                names = ", ".join(item.name.lower() for item in lagging[:3])
                insights.append(ProgressInsightSchema(tone="info", title="Перекос нагрузки", text=f"Почти не тренировались: {names}. Добавьте упражнения на эти зоны для гармоничного развития.", href="/catalog"))
        return insights[:4]


def _local(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone()


def _exercise_name(slug: str) -> str:
    exercise = get_imported_exercise(slug)
    return exercise.name_ru if exercise else slug


def _bucket_label(day: date, granularity: str) -> str:
    if granularity == "month":
        return f"{MONTHS[day.month - 1]} {day.year % 100:02d}"
    return f"{day.day} {MONTHS[day.month - 1]}"


def _kg(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _pct(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _plural(value: int, one: str, few: str, many: str) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return one
    if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        return few
    return many
