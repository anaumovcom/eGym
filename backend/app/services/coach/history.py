"""E10: saved results and comparable history, read by owner from the DB. The browser only sends row IDs."""

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, WorkoutSession
from app.models.analytics import SetResult as SetRow
from app.services.coach import facts
from app.services.coach.facts import AllowedFact, Comparison, FactPackage, HistoryStatus, spoken_quantity

TIMED_KINDS = {"timed", "stretch"}
_SPEAKABLE_NAME = re.compile(r"^[а-яёА-ЯЁ\s\-«»,()]{2,80}$")


class HistoryError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= 80 else None


def progress_unit(exercise: ExerciseSession) -> Literal["reps", "seconds"]:
    return "seconds" if str(exercise.kind) in TIMED_KINDS else "reps"


def speakable_name(name: str | None) -> str | None:
    """Only a plain Cyrillic name can become a fact: validation rejects Latin letters and stray digits."""
    return name.strip() if name and _SPEAKABLE_NAME.match(name.strip()) else None


def to_fact_set(row: SetRow, exercise: ExerciseSession) -> facts.SetResult:
    metrics = row.machine_metrics if isinstance(row.machine_metrics, dict) else {}
    value = row.actual_value if row.actual_value is not None and row.actual_value >= 0 else None
    status = metrics.get("completionStatus")
    if status not in {"completed", "partial", "skipped"}:
        status = "skipped" if not value else "completed" if value >= row.planned_value else "partial"
    low, high = metrics.get("targetMinReps"), metrics.get("targetMaxReps")
    return facts.SetResult(
        set_id=str(row.id), user_id=exercise.user_id, exercise_slug=exercise.exercise_slug,
        progress_unit=progress_unit(exercise), set_type="warmup" if metrics.get("setType") == "warmup" else "working",
        ordinal=row.set_number, value=value, outcome=status,
        target=row.planned_value if row.planned_value and row.planned_value > 0 else None,
        target_exact=low is None or low == high, weight_kg=row.weight_kg,
        load_mode=_text(metrics.get("loadMode")) or exercise.training_mode, range_id=_text(metrics.get("rangeId")),
        calibration_id=exercise.calibration_state, count_method=_text(metrics.get("countMethod")))


@dataclass(frozen=True, slots=True)
class SavedSet:
    current: facts.SetResult
    previous: facts.SetResult | None
    history: HistoryStatus
    comparison: Comparison
    exercise_name: str | None


def _owned_exercise(db: Session, user_id: str, exercise_id: int) -> ExerciseSession:
    exercise = db.get(ExerciseSession, exercise_id)
    if exercise is None or exercise.user_id != user_id:
        raise HistoryError("owner_mismatch")  # Same answer for missing and foreign rows.
    return exercise


def load_saved_set(db: Session, user_id: str, set_id: int, *, history_consent: bool) -> SavedSet:
    row = db.get(SetRow, set_id)
    if row is None:
        raise HistoryError("owner_mismatch")
    exercise = _owned_exercise(db, user_id, row.exercise_session_id)
    current = to_fact_set(row, exercise)
    previous, history = None, "unavailable"
    if history_consent:
        query = select(ExerciseSession).where(
            ExerciseSession.user_id == user_id, ExerciseSession.exercise_slug == exercise.exercise_slug,
            ExerciseSession.id != exercise.id, ExerciseSession.started_at < exercise.started_at)
        if exercise.workout_session_id is not None:
            query = query.where(or_(ExerciseSession.workout_session_id.is_(None),
                                    ExerciseSession.workout_session_id != exercise.workout_session_id))
        earlier = db.scalar(query.order_by(ExerciseSession.started_at.desc(), ExerciseSession.id.desc()).limit(1))
        if earlier is None:
            history = "empty_confirmed"
        else:
            match = db.scalar(select(SetRow).where(SetRow.exercise_session_id == earlier.id,
                                                   SetRow.set_number == row.set_number).limit(1))
            previous = to_fact_set(match, earlier) if match is not None else None
            history = "available" if previous is not None else "limited"
    return SavedSet(current, previous, history, facts.compare(current, previous, history),
                    speakable_name(exercise.exercise_name))


def _sets(db: Session, exercise: ExerciseSession) -> list[facts.SetResult]:
    rows = db.scalars(select(SetRow).where(SetRow.exercise_session_id == exercise.id).order_by(SetRow.set_number, SetRow.id))
    return [to_fact_set(row, exercise) for row in rows]


def exercise_summary(db: Session, user_id: str, exercise_id: int, *, scope_epoch: int, valid_until_ms: float) -> FactPackage:
    exercise = _owned_exercise(db, user_id, exercise_id)
    done = [s for s in _sets(db, exercise) if s.outcome != "skipped" and s.value]
    common = {"scope_epoch": scope_epoch, "valid_until_ms": valid_until_ms}
    if not done:
        raise HistoryError("insufficient_facts")
    partial = any(s.outcome != "completed" for s in done) or len(done) < (exercise.target_sets or 0)
    unit = progress_unit(exercise)
    best = max(s.value for s in done if s.value is not None)
    found = [AllowedFact("sets-done", f"Выполнено {spoken_quantity(len(done), 'sets')}", "confirmed", len(done), "sets",
                         numbers=(len(done),), **common),
             AllowedFact("best-set", f"Лучший подход — {spoken_quantity(best, unit)}", "confirmed", best, unit,
                         numbers=(best,), **common),
             AllowedFact("outcome", "Часть подходов выполнена не полностью" if partial else "Все подходы выполнены",
                         "confirmed", "partial" if partial else "full", **common)]
    if name := speakable_name(exercise.exercise_name):
        found.append(AllowedFact("exercise", f"Упражнение — {name}", "confirmed", name, **common))
    return FactPackage("T56" if partial else "T55", tuple(found), Comparison("unavailable"), "partial" if partial else "full")


def workout_summary(db: Session, user_id: str, workout_id: int, *, scope_epoch: int, valid_until_ms: float) -> FactPackage:
    workout = db.get(WorkoutSession, workout_id)
    if workout is None or workout.user_id != user_id:
        raise HistoryError("owner_mismatch")
    exercises = list(db.scalars(select(ExerciseSession).where(ExerciseSession.workout_session_id == workout.id)))
    sets = [s for exercise in exercises for s in _sets(db, exercise)]
    done = [s for s in sets if s.outcome != "skipped" and s.value]
    if not done:
        raise HistoryError("insufficient_facts")
    active = len({s.exercise_slug for s in done})
    partial = any(s.outcome != "completed" for s in sets)
    common = {"scope_epoch": scope_epoch, "valid_until_ms": valid_until_ms}
    found = (AllowedFact("exercises-done", f"Сделано {spoken_quantity(active, 'exercises')}", "confirmed", active,
                         "exercises", numbers=(active,), **common),
             AllowedFact("sets-done", f"Всего {spoken_quantity(len(done), 'sets')}", "confirmed", len(done), "sets",
                         numbers=(len(done),), **common),
             AllowedFact("outcome", "Часть подходов выполнена не полностью" if partial else "Все подходы выполнены",
                         "confirmed", "partial" if partial else "full", **common))
    return FactPackage("T59" if partial else "T58", found, Comparison("unavailable"), "partial" if partial else "full")
