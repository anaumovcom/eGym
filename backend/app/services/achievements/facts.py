"""Owner-scoped workout normalization and deterministic fact aggregation for all 120 lines."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import CoachWorkoutPlan, ExerciseSession, SetResult, WorkoutSession
from app.models.coach import CoachEpisode, CoachScenario
from app.models.enums import WorkoutSessionStatus
from app.services.achievements.rules import RULES
from app.services.achievements.training_scope import EXCLUDED_SOURCES, TrainingScopeCounter

DONE = {WorkoutSessionStatus.completed, WorkoutSessionStatus.partial, WorkoutSessionStatus.aborted}
TIMED = {"timed", "stretch"}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def training_day(value: datetime) -> date:
    # Server-local training day; existing runtime uses the same 03:00 reset boundary.
    return (utc(value).astimezone() - timedelta(hours=3)).date()


def week(value: date) -> tuple[int, int]:
    iso = value.isocalendar()
    return iso.year, iso.week


def month(value: date) -> tuple[int, int]:
    return value.year, value.month


def quarter(value: date) -> tuple[int, int]:
    return value.year, (value.month - 1) // 3 + 1


@dataclass(frozen=True)
class FactSet:
    id: int
    workout_id: int
    exercise_id: int
    slug: str
    kind: str
    day: date
    at: datetime
    ordinal: int
    value: int
    reps: int
    seconds: int
    weight_grams: int
    metrics: dict[str, Any]
    per_side: bool
    training_mode: str | None
    status: str

    @property
    def volume_grams(self) -> int:
        return self.reps * self.weight_grams

    @property
    def working(self) -> bool:
        return self.metrics.get("setType") not in {"warmup", None}

    @property
    def verified(self) -> bool:
        return self.metrics.get("sourceClass") == "sensor_verified"

    @property
    def comparison(self) -> tuple[Any, ...]:
        return (self.slug, self.training_mode or self.metrics.get("loadMode"), self.metrics.get("rangeId"),
                self.metrics.get("countBasis"), self.kind)


@dataclass
class WorkoutFacts:
    row: WorkoutSession
    day: date
    sets: list[FactSet]
    plan: CoachWorkoutPlan | None
    episode: CoachEpisode | None
    scenario: CoachScenario | None

    @property
    def qualified(self) -> bool:
        return self.row.status in DONE and bool(self.sets)


class FactBuilder:
    def __init__(self, session: Session, user_id: str):
        self.db = session
        self.user_id = user_id
        self.training_scope = TrainingScopeCounter(user_id)
        self.workouts = self._load()
        self.sets = [item for workout in self.workouts for item in workout.sets]
        self.days = {workout.day for workout in self.workouts if workout.qualified}
        self.weeks = {week(day) for day in self.days}
        self.months = {month(day) for day in self.days}
        self.values: dict[str, float] = defaultdict(float)
        self.evidence_days: dict[str, set[date]] = {}
        self._build()

    def _load(self) -> list[WorkoutFacts]:
        rows = list(self.db.scalars(select(WorkoutSession).where(WorkoutSession.user_id == self.user_id)
                                    .order_by(WorkoutSession.started_at, WorkoutSession.id)))
        exercises = list(self.db.scalars(select(ExerciseSession).where(ExerciseSession.user_id == self.user_id)))
        exercise_map: dict[int, list[ExerciseSession]] = defaultdict(list)
        for exercise in exercises:
            if exercise.workout_session_id is not None:
                exercise_map[exercise.workout_session_id].append(exercise)
        set_rows = list(self.db.scalars(select(SetResult).join(ExerciseSession)
                                        .where(ExerciseSession.user_id == self.user_id).order_by(SetResult.id)))
        sets_map: dict[int, list[SetResult]] = defaultdict(list)
        for row in set_rows:
            sets_map[row.exercise_session_id].append(row)
        plans = {row.workout_id: row for row in self.db.scalars(select(CoachWorkoutPlan)
                 .where(CoachWorkoutPlan.user_id == self.user_id))} if self.db.get_bind().dialect.has_table(
                     self.db.connection(), CoachWorkoutPlan.__tablename__) else {}
        episodes = {row.workout_id: row for row in self.db.scalars(select(CoachEpisode)
                    .where(CoachEpisode.user_id == self.user_id))}
        scenarios = {row.run_id: row for row in self.db.scalars(select(CoachScenario)
                     .where(CoachScenario.user_id == self.user_id))}
        result = []
        for workout in rows:
            if workout.status not in DONE or workout.finished_at is None:
                continue
            normalized = []
            for exercise in exercise_map.get(workout.id, []):
                self.training_scope.add_exercise(workout, exercise, sets_map.get(exercise.id, []), training_day)
                for row in sets_map.get(exercise.id, []):
                    item = self._set(row, exercise, workout)
                    if item is not None:
                        normalized.append(item)
            episode = episodes.get(workout.id)
            scenario = scenarios.get(episode.run_id) if episode and episode.run_id else None
            result.append(WorkoutFacts(workout, training_day(workout.started_at), normalized,
                                       plans.get(workout.id), episode, scenario))
        return result

    @staticmethod
    def _set(row: SetResult, exercise: ExerciseSession, workout: WorkoutSession) -> FactSet | None:
        metrics = row.machine_metrics if isinstance(row.machine_metrics, dict) else {}
        if (row.actual_value <= 0 or metrics.get("completionStatus") not in {'completed', 'partial'}
                or exercise.status not in {'completed', 'partial', 'aborted'}):
            return None
        if (metrics.get("sourceClass") in EXCLUDED_SOURCES
                or any(metrics.get(flag) is True for flag in ('simulation', 'isTest', 'isSimulated'))
                or metrics.get('hardwareAdapter') == 'emulator'):
            return None
        kind = str(exercise.kind)
        if kind not in {'machine', 'bodyweight', *TIMED}:
            return None
        reps = max(0, min(row.reps, row.actual_value) if row.reps is not None else row.actual_value) if kind not in TIMED else 0
        seconds = max(0, min(row.duration_seconds, row.actual_value) if row.duration_seconds is not None else row.actual_value) if kind in TIMED else 0
        if reps == 0 and seconds == 0:
            return None
        weight = max(0, round((row.weight_kg or 0) * 1000))
        return FactSet(row.id, workout.id, exercise.id, exercise.exercise_slug, kind, training_day(workout.started_at),
                       utc(row.created_at or exercise.started_at), row.set_number, row.actual_value, reps, seconds,
                       weight, metrics, exercise.per_side, exercise.training_mode,
                       exercise.status.value if hasattr(exercise.status, "value") else str(exercise.status))

    def add(self, metric: str, value: float) -> None:
        self.values[metric] += value

    def count(self, metric: str, values: set[Any] | list[Any]) -> None:
        self.values[metric] = float(len(values))

    def _build(self) -> None:
        qualified = [w for w in self.workouts if w.qualified]
        sets = self.sets
        self.values["qualified_workouts"] = len(qualified)
        self.values["partial_workouts"] = sum(w.row.status == WorkoutSessionStatus.partial for w in qualified)
        self.values["qualified_sets"] = len(sets)
        self.values["working_sets"] = sum(s.working for s in sets)
        self.values["qualified_reps"] = sum(s.reps for s in sets)
        self.values["timed_seconds"] = sum(s.seconds for s in sets)
        self.values["stretch_seconds"] = sum(s.seconds for s in sets if s.kind == "stretch")
        self.values["volume_grams"] = sum(s.volume_grams for s in sets)
        self.values["weighted_sets"] = sum(s.weight_grams > 0 and s.reps > 0 for s in sets)
        self.values["weighted_reps"] = sum(s.reps for s in sets if s.weight_grams > 0)
        self.values["bodyweight_sets"] = sum(s.kind == "bodyweight" for s in sets)
        self.values["bodyweight_reps"] = sum(s.reps for s in sets if s.kind == "bodyweight")
        self.values["completed_exercises"] = len({s.exercise_id for s in sets})
        self.values["distinct_exercises"] = len({s.slug for s in sets})
        self.values["bodyweight_exercises"] = len({s.slug for s in sets if s.kind == "bodyweight"})
        self.values["machine_exercises"] = len({s.slug for s in sets if s.kind == "machine"})
        self.values["timed_exercises"] = len({s.slug for s in sets if s.kind in TIMED})
        self.values["weight_exercises"] = len({s.slug for s in sets if s.weight_grams > 0})
        self.values["completed_programs"] = sum(
            bool(w.plan and isinstance(w.plan.baseline, dict) and w.plan.baseline.get('programId'))
            and bool(self._plan_result(w)[1]) for w in qualified)
        self._build_days(sets)
        self._build_rhythm(qualified)
        self._build_repertoire(sets)
        self._build_reflection(qualified)
        self._build_plans(qualified)
        self._build_stories(qualified)
        self._build_progress(sets)
        self._build_measured(sets)
        self._build_chapters()

        self._build_evidence(qualified)

    def _build_evidence(self, qualified: list[WorkoutFacts]) -> None:
        practice = self.training_scope.qualifying_days()
        self.evidence_days['practice_evidence_days'] = practice
        for metric, predicate in (
            ('timed_days', lambda s: s.kind in TIMED),
            ('stretch_days', lambda s: s.kind == 'stretch'),
            ('bodyweight_days', lambda s: s.kind == 'bodyweight'),
            ('weighted_days', lambda s: s.weight_grams > 0 and s.reps > 0),
            ('verified_days', lambda s: s.verified),
            ('set_feedback_days', lambda s: s.metrics.get('explicitFeedbackVersion') == 1),
        ):
            self.evidence_days[metric] = {s.day for s in self.sets if predicate(s)} & practice
        self.evidence_days['note_days'] = {
            w.day for w in qualified if w.row.notes and w.row.notes.strip()} & practice
        self.evidence_days['reflection_days'] = {
            w.day for w in qualified if w.row.feeling is not None or w.row.discomfort is not None} & practice
        self.evidence_days['episode_days'] = {w.day for w in qualified if w.episode is not None} & practice
        self.evidence_days['planned_days'] = {w.day for w in qualified if self._plan_result(w)[0]} & practice
        for metric, days in self.evidence_days.items():
            self.values[f'evidence:{metric}'] = len(days & practice)

    def _build_days(self, sets: list[FactSet]) -> None:
        self.values["active_days"] = len(self.days)
        self.values["active_weeks"] = len(self.weeks)
        by_day: dict[date, list[FactSet]] = defaultdict(list)
        for item in sets:
            by_day[item.day].append(item)
        self.values["timed_days"] = sum(any(s.kind in TIMED for s in rows) for rows in by_day.values())
        self.values["stretch_days"] = sum(any(s.kind == "stretch" for s in rows) for rows in by_day.values())
        self.values["bodyweight_days"] = sum(any(s.kind == "bodyweight" for s in rows) for rows in by_day.values())
        self.values["machine_days"] = sum(any(s.kind == "machine" for s in rows) for rows in by_day.values())
        self.values["volume_days"] = sum(any(s.volume_grams > 0 for s in rows) for rows in by_day.values())
        self.values["weighted_days"] = sum(any(s.weight_grams > 0 for s in rows) for rows in by_day.values())
        self.values["multi_set_days"] = sum(len(rows) >= 5 for rows in by_day.values())
        self.values["three_exercise_days"] = sum(len({s.slug for s in rows}) >= 3 for rows in by_day.values())
        self.values["five_exercise_days"] = sum(len({s.slug for s in rows}) >= 5 for rows in by_day.values())
        self.values["mixed_kind_days"] = sum(len({s.kind for s in rows}) >= 2 for rows in by_day.values())
        by_week: dict[tuple[int, int], set[date]] = defaultdict(set)
        by_month: dict[tuple[int, int], set[date]] = defaultdict(set)
        by_quarter: dict[tuple[int, int], set[date]] = defaultdict(set)
        for day in self.days:
            by_week[week(day)].add(day)
            by_month[month(day)].add(day)
            by_quarter[quarter(day)].add(day)
        self.values["two_day_weeks"] = sum(len(days) >= 2 for days in by_week.values())
        self.values["three_day_weeks"] = sum(len(days) >= 3 for days in by_week.values())
        self.values["active_months"] = sum(len(days) >= 2 for days in by_month.values())
        self.values["active_quarters"] = sum(len(days) >= 6 for days in by_quarter.values())
        self.values["best_week_streak"] = longest_consecutive(sorted(self.weeks), weeks_consecutive)
        week_volume = {key: sum(s.volume_grams for s in sets if week(s.day) == key) for key in self.weeks}
        self.values["volume_weeks"] = sum(value >= 500_000 for value in week_volume.values())
        month_volume = {key: sum(s.volume_grams for s in sets if month(s.day) == key) for key in self.months}
        self.values["volume_months"] = sum(value >= 5_000_000 for value in month_volume.values())

    def _build_rhythm(self, qualified: list[WorkoutFacts]) -> None:
        previous: date | None = None
        return_days: set[date] = set()
        for workout in qualified:
            if previous is not None and (workout.day - previous).days - 1 >= 14:
                return_days.add(workout.day)
            previous = workout.day
        self.values["return_active_days"] = sum(day >= min(return_days) for day in self.days) if return_days else 0
        self.evidence_days['return_practice_days'] = {day for day in self.days if return_days and day >= min(return_days)}
        self.evidence_days['post_return_days'] = set()
        if return_days:
            first = min(return_days)
            allowed_weeks = {week(first + timedelta(days=offset)) for offset in range(42)}
            self.values["post_return_weeks"] = len({week(day) for day in self.days if day > first and week(day) in allowed_weeks})
            self.evidence_days['post_return_days'] = {day for day in self.days if first < day < first + timedelta(days=42)}

    def _build_repertoire(self, sets: list[FactSet]) -> None:
        slug_days: dict[str, set[date]] = defaultdict(set)
        slug_weeks: dict[str, set[tuple[int, int]]] = defaultdict(set)
        first_day: dict[str, date] = {}
        for item in sorted(sets, key=lambda row: (row.day, row.id)):
            slug_days[item.slug].add(item.day)
            slug_weeks[item.slug].add(week(item.day))
            first_day.setdefault(item.slug, item.day)
        self.values["best_exercise_days"] = max((len(days) for days in slug_days.values()), default=0)
        self.values["best_exercise_weeks"] = max((len(days) for days in slug_weeks.values()), default=0)
        self.values["familiar_exercises"] = sum(len(days) >= 3 for days in slug_days.values())
        familiar_days = set()
        for days in slug_days.values():
            # Sets on the third day cannot make that same day "prior".
            familiar_days.update(sorted(days)[3:])
        self.values["familiar_days"] = len(familiar_days)
        self.values["new_exercise_months"] = len({month(day) for day in first_day.values()})
        self.values["repertoire_months"] = len({month(day) for day in self.days
                                                if len({s.slug for s in sets if month(s.day) == month(day)}) >= 3})

    def _build_reflection(self, qualified: list[WorkoutFacts]) -> None:
        reflection_days = {w.day for w in qualified if w.row.feeling is not None or w.row.discomfort is not None}
        note_days = {w.day for w in qualified if bool(w.row.notes and w.row.notes.strip())}
        self.values["reflection_days"] = len(reflection_days)
        self.values["reflection_weeks"] = len({week(day) for day in reflection_days})
        self.values["reflection_months"] = len({month(day) for day in reflection_days})
        self.values["note_days"] = len(note_days)
        self.values["note_weeks"] = len({week(day) for day in note_days})
        feedback = [s for s in self.sets if s.metrics.get("explicitFeedbackVersion") == 1]
        self.values["effort_feedback_sets"] = len(feedback)
        self.values["set_feedback_days"] = len({s.day for s in feedback})
        self.values["feedback_exercises"] = len({s.slug for s in feedback})

    def _plan_result(self, workout: WorkoutFacts) -> tuple[int, int, set[str], set[str]]:
        plan = workout.plan
        if plan is None or plan.stale or not isinstance(plan.baseline, dict):
            return 0, 0, set(), set()
        exercises = plan.baseline.get("exercises")
        if not isinstance(exercises, list) or not exercises:
            return 0, 0, set(), set()
        met_sets = 0
        full_exercises: set[str] = set()
        planned_slugs: set[str] = set()
        all_full = True
        for expected in exercises:
            if not isinstance(expected, dict) or not isinstance(expected.get("slug"), str):
                return 0, 0, set(), set()
            slug = expected["slug"]
            planned_slugs.add(slug)
            expected_sets = expected.get("sets")
            actual = [s for s in workout.sets if s.slug == slug]
            if not isinstance(expected_sets, list) or not expected_sets:
                all_full = False
                continue
            exercise_full = True
            for spec in expected_sets:
                if not isinstance(spec, dict):
                    exercise_full = False
                    continue
                ordinal = spec.get("ordinal")
                minimum = spec.get("minimum")
                target_type = spec.get("targetType")
                candidate = next((s for s in actual if s.ordinal == ordinal), None)
                met = candidate is not None and (target_type == "open" or
                    isinstance(minimum, int) and minimum > 0 and candidate.value >= minimum)
                if met:
                    met_sets += 1
                else:
                    exercise_full = False
            if exercise_full:
                full_exercises.add(slug)
            else:
                all_full = False
        return met_sets, int(all_full), full_exercises, planned_slugs

    def _build_plans(self, qualified: list[WorkoutFacts]) -> None:
        full_workouts: list[WorkoutFacts] = []
        full_exercises = 0
        met_sets = 0
        planned_days = set()
        distinct = set()
        program_days: dict[str, set[date]] = defaultdict(set)
        templates = set()
        for workout in qualified:
            met, full, complete_exercises, slugs = self._plan_result(workout)
            met_sets += met
            full_exercises += len(complete_exercises)
            distinct.update(complete_exercises)
            if met:
                planned_days.add(workout.day)
            if full:
                full_workouts.append(workout)
                signature = str(workout.plan.baseline.get("programId") or
                                hashlib.sha256(json.dumps(sorted(slugs)).encode()).hexdigest()[:16]) if workout.plan else ""
                program_days[signature].add(workout.day)
                templates.add(signature)
            if workout.plan and workout.plan.stale and isinstance(workout.plan.current, dict):
                reason = workout.plan.current.get("adjustmentReason")
                if isinstance(reason, str) and reason.strip():
                    self.add("adjusted_workouts", 1)
        self.values["planned_met_sets"] = met_sets
        self.values["plan_full_exercises"] = full_exercises
        self.values["planned_days"] = len(planned_days)
        self.values["planned_distinct_exercises"] = len(distinct)
        self.values["plan_full_workouts"] = len(full_workouts)
        self.values["plan_templates"] = len(templates)
        self.values["repeat_program_days"] = max((len(days) for days in program_days.values()), default=0)
        full_weeks = {week(w.day) for w in full_workouts}
        self.values["plan_full_weeks"] = len(full_weeks)
        self.values["plan_week_streak"] = longest_consecutive(sorted(full_weeks), weeks_consecutive)

    def _build_stories(self, qualified: list[WorkoutFacts]) -> None:
        episodes = [w for w in qualified if w.episode is not None]
        self.values["episode_days"] = len({w.day for w in episodes})
        self.values["story_weeks"] = len({week(w.day) for w in episodes})
        self.values["story_months"] = len({month(w.day) for w in episodes})
        self.values["story_worlds"] = len({w.scenario.archetype for w in episodes if w.scenario})
        world_days: dict[str, set[date]] = defaultdict(set)
        world_months: dict[str, set[tuple[int, int]]] = defaultdict(set)
        last_world: dict[str, date] = {}
        returns = 0
        acts = 0
        finale_days = set()
        for workout in sorted(episodes, key=lambda row: (row.day, row.row.id)):
            archetype = workout.scenario.archetype if workout.scenario else None
            if archetype:
                world_days[archetype].add(workout.day)
                world_months[archetype].add(month(workout.day))
                if archetype in last_world and (workout.day - last_world[archetype]).days >= 28:
                    returns += 1
                last_world[archetype] = workout.day
            payload = workout.episode.payload if workout.episode else {}
            raw_acts = payload.get("acts", []) if isinstance(payload, dict) else []
            if isinstance(raw_acts, list):
                acts += sum(isinstance(act, dict) and act.get("baselineMet") is True for act in raw_acts)
            if self._plan_result(workout)[1]:
                finale_days.add(workout.day)
        self.values["story_acts"] = acts
        self.values["story_finale_days"] = len(finale_days)
        self.values["best_world_days"] = max((len(days) for days in world_days.values()), default=0)
        self.values["best_world_months"] = max((len(months) for months in world_months.values()), default=0)
        self.values["world_returns"] = returns
        counts = sorted((len(days) for days in world_days.values()), reverse=True)
        self.values["three_world_triptych"] = min(count // 3 for count in counts[:3]) if len(counts) >= 3 else 0

    def _build_progress(self, sets: list[FactSet]) -> None:
        candidates = [s for s in sets if s.reps > 0 and s.weight_grams > 0 and s.working
                      and s.metrics.get("completionStatus", "completed") == "completed"]
        rep_days = set()
        weight_days = set()
        e1rm_days = set()
        pr_days = set()
        pr_exercises = set()
        long_arc = set()
        events: list[FactSet] = []
        for current in sorted(candidates, key=lambda row: (row.at, row.id)):
            earlier = [s for s in candidates if s.comparison == current.comparison and s.at < current.at
                       and s.workout_id != current.workout_id]
            if not earlier:
                continue
            is_pr = False
            same_weight = [s.reps for s in earlier if s.weight_grams == current.weight_grams]
            if same_weight and current.reps > max(same_weight):
                rep_days.add(current.day)
                is_pr = True
            if current.weight_grams > max(s.weight_grams for s in earlier) + 250:
                weight_days.add(current.day)
                is_pr = True
            current_e1rm = current.weight_grams * (1 + current.reps / 30) if current.reps <= 12 else None
            previous_e1rm = [s.weight_grams * (1 + s.reps / 30) for s in earlier if s.reps <= 12]
            if current_e1rm is not None and previous_e1rm and current_e1rm > max(previous_e1rm) * 1.01:
                e1rm_days.add(current.day)
                is_pr = True
            if is_pr:
                pr_days.add(current.day)
                pr_exercises.add(current.slug)
                events.append(current)
                baseline = min(earlier, key=lambda row: row.at)
                if (current.day - baseline.day).days >= 28:
                    long_arc.add(current.slug)
        retained = 0
        for event in events:
            later_days = {s.day for s in candidates if s.comparison == event.comparison and s.day > event.day
                          and s.weight_grams >= event.weight_grams and s.reps >= event.reps}
            retained += len(later_days) >= 2
        self.values["rep_pr_days"] = len(rep_days)
        self.values["weight_pr_days"] = len(weight_days)
        self.values["e1rm_pr_days"] = len(e1rm_days)
        self.values["pr_days"] = len(pr_days)
        self.evidence_days['pr_days'] = pr_days
        self.values["pr_exercises"] = len(pr_exercises)
        self.values["long_arc_exercises"] = len(long_arc)
        self.values["retained_results"] = retained
        self.values["pr_weeks"] = len({week(day) for day in pr_days})
        self.values["pr_months"] = len({month(day) for day in pr_days})

    @staticmethod
    def _stable(item: FactSet) -> bool:
        durations = item.metrics.get("repDurationsMs")
        if not item.verified or item.metrics.get("calibrationValid") is not True or item.metrics.get("rangeUnchanged") is not True:
            return False
        if not isinstance(durations, list) or len(durations) < 5 or item.metrics.get("sampleGapCount", 0) != 0:
            return False
        values = [float(value) for value in durations[1:-1] if isinstance(value, int | float) and value > 0]
        return len(values) >= 3 and statistics.pstdev(values) / statistics.mean(values) <= 0.20

    def _build_measured(self, sets: list[FactSet]) -> None:
        stable = [s for s in sets if self._stable(s)]
        self.values["measured_rhythm_sets"] = len(stable)
        stable_days: dict[date, int] = Counter(s.day for s in stable)
        self.values["measured_rhythm_days"] = sum(count >= 2 for count in stable_days.values())
        pairs = 0
        medians: dict[str, list[tuple[date, float]]] = defaultdict(list)
        for item in stable:
            values = [float(value) for value in item.metrics["repDurationsMs"][1:-1]]
            medians[item.slug].append((item.day, statistics.median(values)))
        for rows in medians.values():
            pairs += sum(1 for index, (day, value) in enumerate(rows)
                         if any(other_day != day and abs(value - other) / max(value, other) <= 0.15
                                for other_day, other in rows[:index]))
        self.values["measured_repeatable_pairs"] = pairs
        verified = [s for s in sets if s.verified]
        self.values["verified_workouts"] = len({s.workout_id for s in verified})
        self.values["verified_sets"] = len(verified)
        self.values["verified_days"] = len({s.day for s in verified})
        self.values["verified_reps"] = sum(s.reps for s in verified)
        calibrated = [s for s in verified if s.metrics.get("calibrationValid") is True and s.metrics.get("calibrationId")]
        self.values["calibrated_workouts"] = len({s.workout_id for s in calibrated})
        paired_days = set()
        by_day: dict[date, list[FactSet]] = defaultdict(list)
        for item in verified:
            by_day[item.day].append(item)
        for day, rows in by_day.items():
            sides = {side for s in rows if s.per_side for side in [s.metrics.get("side")] if side in {"left", "right"}}
            if sides == {"left", "right"}:
                paired_days.add(day)
        self.values["paired_side_days"] = len(paired_days)
        self.values["range_consistent_days"] = len({s.day for s in calibrated
                                                   if isinstance(s.metrics.get("repExtrema"), list) and s.metrics["repExtrema"]})

    def _build_chapters(self) -> None:
        if not self.days:
            return
        first = min(self.days)
        span = (max(self.days) - first).days + 1
        day_count = len(self.days)
        week_count = len(self.weeks)
        set_count = self.values["qualified_sets"]
        self.values["chapter_30"] = 100 * min(1, span / 30, day_count / 6)
        self.values["chapter_90"] = 100 * min(1, span / 90, day_count / 18)
        self.values["chapter_365"] = 100 * min(1, span / 365, day_count / 40)
        self.values["chapter_foundation"] = 100 * min(1, day_count / 15, week_count / 4)
        self.values["chapter_craft"] = 100 * min(1, day_count / 30, set_count / 150, week_count / 12)
        self.values["chapter_atlas"] = 100 * min(1, day_count / 60, week_count / 26)
        reflection = self.values["reflection_days"] >= 3
        plan = self.values["plan_full_workouts"] >= 1
        self.values["chapter_balance"] = 100 if self.values["active_days"] >= 5 and set_count >= 10 and (reflection or plan) else 50 * min(
            1, self.values["active_days"] / 5, set_count / 10)
        self.values["chapter_worlds"] = 100 * min(1, self.values["story_worlds"] / 10,
                                                self.values["episode_days"] / 30, week_count / 12)
        self.values["chapter_second_year"] = 100 * min(1, span / 730, day_count / 80, week_count / 52)
        self.values["chapter_veteran"] = 100 * min(1, day_count / 120, set_count / 1000, week_count / 52)

    def finish(self) -> dict[str, float]:
        values = dict(self.values)
        values.update(self.training_scope.values())
        # Public volume is kg; the internal sum stays integer gram-reps until this boundary.
        values["volume_grams"] = values.get("volume_grams", 0) / 1000
        result = {rule["metric"]: values.get(rule["metric"], 0.0) for rule in RULES}
        result.update({rule['evidenceMetric']: values.get(rule['evidenceMetric'], 0.0) for rule in RULES})
        result['practice_evidence_days'] = values.get('practice_evidence_days', 0.0)
        return result


def weeks_consecutive(previous: tuple[int, int], current: tuple[int, int]) -> bool:
    return (date.fromisocalendar(*current, 1) - date.fromisocalendar(*previous, 1)).days == 7


def longest_consecutive(values: list[Any], consecutive: Any) -> int:
    if not values:
        return 0
    best = current = 1
    for index in range(1, len(values)):
        current = current + 1 if consecutive(values[index - 1], values[index]) else 1
        best = max(best, current)
    return best


def facts_digest(values: dict[str, float]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
