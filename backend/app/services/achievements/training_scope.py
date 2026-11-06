"""Offline scoped practice: curated saved-program inventory, never a live DB registry.

Roles must be explicit canonical IDs. In particular, translated UI muscle lists and
their position-derived `primary` labels are NOT anatomical evidence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime

from app.models.analytics import ExerciseSession, SetResult, WorkoutSession
from app.services.exercise_library import get_imported_exercise
from app.services.muscle_catalog import CANONICAL_MUSCLE_DEFINITIONS

# Read-only snapshot 2026-11-05: active owned programs 2, workout-9, workout-10;
# items live in AppSetting training.builder.plan.<id>, not the empty structure.
SAVED_PROGRAM_EXERCISES: tuple[str, ...] = (
    "butt-kick", "cardio-knee-taps", "cardio-quick-feet",
    "smith-machine-bench-press", "smith-machine-calf-raise",
    "smith-machine-close-grip-bench-press", "smith-machine-drag-curl",
    "smith-machine-incline-bench-press", "smith-machine-inverted-row",
    "smith-machine-narrow-stance-squat", "smith-machine-overhand-row",
    "smith-machine-romanian-deadlift", "smith-machine-seated-overhead-press",
    "smith-machine-skullcrusher", "smith-machine-squat", "smith-machine-upright-row",
    "underhand-pulldown",
)
PRACTICE_DAY_THRESHOLDS = (12, 30, 75, 150)
CANONICAL_GROUP_IDS = tuple(sorted(CANONICAL_MUSCLE_DEFINITIONS))
WORKING_TYPES = frozenset({"work", "working", "failure"})
EXCLUDED_SOURCES = frozenset({"simulated", "simulation", "test", "emulator", "synthetic"})

# Reviewed against the actual movement steps in exercises/<slug>/<slug>.json,
# 2026-11-05. Deliberately conservative agonists, NOT list-order/UI roles.
# Cardio entries have no strength-primary targets. Ambiguous regions stay absent.
CURATED_PRIMARY = {
    'smith-machine-bench-press': ('chest',),
    'smith-machine-calf-raise': ('calves',),
    'smith-machine-close-grip-bench-press': ('triceps',),
    'smith-machine-drag-curl': ('biceps',),
    'smith-machine-incline-bench-press': ('chest',),
    'smith-machine-inverted-row': ('lats', 'traps-middle'),
    'smith-machine-narrow-stance-squat': ('quads',),
    'smith-machine-overhand-row': ('lats', 'traps-middle'),
    'smith-machine-romanian-deadlift': ('hamstrings', 'glutes'),
    'smith-machine-seated-overhead-press': ('front-shoulders',),
    'smith-machine-skullcrusher': ('triceps',),
    'smith-machine-squat': ('quads', 'glutes'),
    'smith-machine-upright-row': ('traps',),
    'underhand-pulldown': ('lats',),
}


def exercise_metric(slug: str) -> str:
    return f"exercise_practice_days:{slug}"


def muscle_metric(muscle_id: str) -> str:
    return f"muscle_primary_days:{muscle_id}"


def canonical_primary_targets(targets: object) -> frozenset[str]:
    """No aliases, Russian name conversion, legacy splits, or list-order fallback."""
    if not isinstance(targets, list):
        return frozenset()
    return frozenset(target["muscle_id"] for target in targets
                     if isinstance(target, dict) and target.get("role") == "primary"
                     and isinstance(target.get("muscle_id"), str)
                     and target["muscle_id"] in CANONICAL_MUSCLE_DEFINITIONS)


class TrainingScopeCounter:
    """Read-only additive evidence; daily sets are deduplicated before qualification."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._seen: set[int] = set()
        self._days: dict[tuple[str, date], list[int]] = defaultdict(lambda: [0, 0])

    def add_exercise(self, workout: WorkoutSession, exercise: ExerciseSession,
                     rows: Iterable[SetResult], day_for: Callable[[datetime], date]) -> None:
        if (workout.user_id != self.user_id or exercise.user_id != self.user_id
                or exercise.workout_session_id != workout.id
                or workout.status not in {"completed", "partial"} or workout.finished_at is None
                or exercise.status not in {"completed", "partial", "aborted"}):
            return
        imported = get_imported_exercise(exercise.exercise_slug)
        is_stretch = exercise.kind == "stretch" or (imported is not None and (
            imported.force == "Stretch" or imported.equipment == "Stretches"))
        is_cardio = imported is not None and imported.equipment == "Cardio"
        timed = exercise.kind in {"timed", "stretch"} or is_stretch
        if exercise.kind not in {"machine", "bodyweight", "timed", "stretch"}:
            return
        metrics = ['practice_evidence_days']
        if exercise.exercise_slug in SAVED_PROGRAM_EXERCISES:
            metrics.append(exercise_metric(exercise.exercise_slug))
        # Cardio and stretching are practice, never strength exposure.
        if not is_stretch and not is_cardio:
            explicit = canonical_primary_targets(exercise.muscle_targets)
            primary = explicit or frozenset(CURATED_PRIMARY.get(exercise.exercise_slug, ()))
            metrics.extend(muscle_metric(group) for group in primary)
        if not metrics:
            return
        pairs: dict[tuple[date, int], dict[str, int]] = defaultdict(dict)
        ordinary: dict[tuple[date, int], int] = {}
        for row in rows:
            if row.id in self._seen or row.exercise_session_id != exercise.id:
                continue
            self._seen.add(row.id)
            data = row.machine_metrics if isinstance(row.machine_metrics, dict) else {}
            if (data.get("completionStatus") != "completed" or data.get("setType") not in WORKING_TYPES
                    or data.get("sourceClass") in EXCLUDED_SOURCES
                    or data.get("simulation") is True or data.get("isTest") is True
                    or data.get("isSimulated") is True or data.get("hardwareAdapter") == "emulator"
                    or row.actual_value <= 0 or row.planned_value <= 0 or row.actual_value < row.planned_value):
                continue
            value = row.duration_seconds if timed else row.reps
            if is_stretch and exercise.kind not in {"timed", "stretch"} and value is None:
                # Misclassified catalog stretching has no documented seconds unit.
                continue
            # actual_value is the documented unit fallback, not an inferred sensor value.
            value = min(row.actual_value, value) if value is not None else row.actual_value
            if value <= 0:
                continue
            day = day_for(row.created_at or exercise.started_at)
            side = data.get("side")
            if exercise.per_side or side is not None:
                round_number = data.get("roundNumber")
                if (side not in {"left", "right"} or type(round_number) is not int or round_number <= 0):
                    continue
                # Duplicate side rows cannot create extra pairs or timed credit.
                sides = pairs[(day, round_number)]
                sides[side] = max(sides.get(side, 0), value)
            elif row.set_number > 0:
                key = (day, row.set_number)
                ordinary[key] = max(ordinary.get(key, 0), value)
        units = [(day, value) for (day, _), value in ordinary.items()]
        units.extend((day, min(sides.values())) for (day, _), sides in pairs.items()
                     if set(sides) == {"left", "right"})
        for day, value in units:
            for metric in metrics:
                counts = self._days[(metric, day)]
                counts[1 if timed else 0] += value if timed else 1

    def values(self) -> dict[str, float]:
        result = {exercise_metric(slug): 0.0 for slug in SAVED_PROGRAM_EXERCISES}
        result.update({muscle_metric(group): 0.0 for group in CANONICAL_GROUP_IDS})
        for (metric, _), (sets, seconds) in self._days.items():
            if sets >= 2 or seconds >= 60:
                result[metric] = result.get(metric, 0.0) + 1
        return result

    def qualifying_days(self, metric: str = 'practice_evidence_days') -> set[date]:
        """Return actual dates so unrelated lifetime counts cannot satisfy a gate."""
        return {day for (key, day), (sets, seconds) in self._days.items()
                if key == metric and (sets >= 2 or seconds >= 60)}