"""E10: saved results and comparable history, read by owner from the DB. The browser only sends row IDs."""

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, WorkoutSession
from app.models.analytics import SetResult as SetRow
from app.schemas.runtime import CoachWorkoutPlanSchema
from app.services.coach import facts
from app.services.coach.context import ExplicitFeedback
from app.services.coach.facts import AllowedFact, Comparison, FactPackage, HistoryStatus, spoken_quantity
from app.services.coach.workout_plan import load_plan

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
    low, high = metrics.get("targetMinReps"), metrics.get("targetMaxReps")
    exact = (low is None and high is None) or (type(low) is int and low == high)
    planned = row.planned_value if row.planned_value and row.planned_value > 0 else None
    status = metrics.get("completionStatus")
    if status not in {"completed", "partial", "skipped", "aborted"}:
        minimum = planned if exact else low if type(low) is int and type(high) is int and 0 < low <= high else None
        status = ("unknown" if value is None or minimum is None else "aborted" if value == 0
                  else "completed" if value >= minimum else "partial")
    return facts.SetResult(
        set_id=str(row.id), user_id=exercise.user_id, exercise_slug=exercise.exercise_slug,
        progress_unit=progress_unit(exercise),
        set_type=("working" if metrics.get("setType") in {"work", "failure"} else
              metrics.get("setType") if metrics.get("setType") in {"warmup", "working"} else None),
        ordinal=row.set_number, value=value, outcome=status,
        target=high if not exact and type(high) is int and high > 0 else planned,
        target_exact=exact, weight_kg=row.weight_kg,
        load_mode=_text(metrics.get("loadMode")) or exercise.training_mode, range_id=_text(metrics.get("rangeId")),
        # "calibrated" is readiness, not identity of the calibration used by this set.
        calibration_id=_text(metrics.get("calibrationId")), count_method=_text(metrics.get("countMethod")),
        target_min=low if not exact and type(low) is int and low > 0 else None,
        exercise_kind=str(exercise.kind), load_profile_id=_text(metrics.get("loadProfileId")),
        target_open=metrics.get("targetType") == "open" and planned is None and low is None and high is None,
        observed_at_ms=row.created_at.timestamp() * 1000 if row.created_at else None)


def _signature(*records) -> str:
    """Opaque revision of persisted dependencies; never send raw history to a model."""
    data = [{column.key: getattr(record, column.key) for column in record.__table__.columns}
            for record in records if record is not None]
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def _provenance(record, scope_epoch: int, valid_until_ms: float, ref: str) -> dict:
    return {"scope_epoch": scope_epoch, "valid_until_ms": valid_until_ms, "ref": ref,
            "provenance": "persisted-analytics", "quantity_kind": "derived", "sufficiency": "sufficient",
            "observed_at_ms": record.updated_at.timestamp() * 1000 if record.updated_at else None}


@dataclass(frozen=True, slots=True)
class SavedSet:
    current: facts.SetResult
    previous: facts.SetResult | None
    history: HistoryStatus
    comparison: Comparison
    exercise_name: str | None
    exercise_id: int = 0
    target_sets: int = 0
    source_signature: str = ""


def _owned_exercise(db: Session, user_id: str, exercise_id: int) -> ExerciseSession:
    exercise = db.get(ExerciseSession, exercise_id)
    if exercise is None or exercise.user_id != user_id:
        raise HistoryError("owner_mismatch")  # Same answer for missing and foreign rows.
    return exercise


def latest_completed_set(db: Session, exercise: ExerciseSession) -> SetRow | None:
    query = select(SetRow).join(ExerciseSession).where(ExerciseSession.user_id == exercise.user_id,
                                                     SetRow.actual_value > 0)
    query = query.where(ExerciseSession.workout_session_id == exercise.workout_session_id) if (
        exercise.workout_session_id is not None) else query.where(ExerciseSession.id == exercise.id)
    return db.scalar(query.order_by(SetRow.created_at.desc(), SetRow.id.desc()).limit(1))


def explicit_feedback(db: Session, user_id: str, set_id: int, *, now_ms: float,
                      ttl_ms: float = 300_000) -> ExplicitFeedback | None:
    row = db.get(SetRow, set_id)
    if row is None:
        raise HistoryError("owner_mismatch")
    exercise = _owned_exercise(db, user_id, row.exercise_session_id)
    latest = latest_completed_set(db, exercise)
    metrics = row.machine_metrics if isinstance(row.machine_metrics, dict) else {}
    observed = metrics.get("explicitFeedbackAtMs")
    if (latest is None or latest.id != row.id or row.created_at is None
            or metrics.get("explicitFeedbackVersion") != 1 or type(observed) not in {float, int}):
        return None
    completed = row.created_at.replace(tzinfo=UTC).timestamp() * 1000
    expires = min(completed, observed) + min(300_000, max(0, ttl_ms))
    if not completed <= observed <= now_ms <= expires:
        return None
    effort = row.subjective_effort if type(row.subjective_effort) is int and 0 <= row.subjective_effort <= 10 else None
    discomfort = row.discomfort_level if type(row.discomfort_level) is int and 0 <= row.discomfort_level <= 10 else None
    if effort is None and discomfort is None:
        return None
    return ExplicitFeedback(row.id, effort, discomfort, observed, expires)


def load_saved_set(db: Session, user_id: str, set_id: int, *, history_consent: bool) -> SavedSet:
    row = db.get(SetRow, set_id)
    if row is None:
        raise HistoryError("owner_mismatch")
    exercise = _owned_exercise(db, user_id, row.exercise_session_id)
    duplicates = list(db.scalars(select(SetRow.id).where(
        SetRow.exercise_session_id == exercise.id, SetRow.set_number == row.set_number).limit(2)))
    if len(duplicates) != 1:
        raise HistoryError("ambiguous_results")
    current = to_fact_set(row, exercise)
    if current.value is None and current.outcome != "skipped":
        raise HistoryError("insufficient_facts")
    previous, history, found = None, "unavailable", None
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
            # Latest earlier session that actually has this set number: a shorter last session must not hide history.
            found = db.execute(
                query.add_columns(SetRow).join(SetRow, SetRow.exercise_session_id == ExerciseSession.id)
                .where(SetRow.set_number == row.set_number)
                .order_by(ExerciseSession.started_at.desc(), ExerciseSession.id.desc(), SetRow.id.desc()).limit(1)).first()
            previous = to_fact_set(found[1], found[0]) if found is not None else None
            history = "available" if previous is not None else "limited"
            if found is not None:
                duplicate_previous = list(db.scalars(select(SetRow.id).where(
                    SetRow.exercise_session_id == found[0].id, SetRow.set_number == row.set_number).limit(2)))
                if len(duplicate_previous) != 1:
                    history = "limited"
    return SavedSet(current, previous, history, facts.compare(current, previous, history),
                    speakable_name(exercise.exercise_name), exercise.id, exercise.target_sets or 0,
                    _signature(exercise, row, *(found if found is not None else ())))


def _sets(db: Session, exercise: ExerciseSession) -> list[facts.SetResult]:
    rows = db.scalars(select(SetRow).where(SetRow.exercise_session_id == exercise.id).order_by(SetRow.set_number, SetRow.id))
    return [to_fact_set(row, exercise) for row in rows]


def _exercise_complete(exercise: ExerciseSession, rows: list[facts.SetResult]) -> bool:
    target = exercise.target_sets
    # Cardinality alone misses duplicate/gapped/out-of-plan ordinals. The plan is
    # the persisted target_sets, never the largest observed ordinal or row count.
    return (type(target) is int and 0 < target <= 1000 and len(rows) == target
            and sorted(s.ordinal for s in rows) == list(range(1, target + 1))
            and str(exercise.status) == "completed"
            and all(facts.target_met(s) for s in rows))


def _exercise_outcome(exercise: ExerciseSession, rows: list[facts.SetResult]) -> str:
    if _exercise_complete(exercise, rows):
        return "full"
    known_missing = exercise.target_sets > 0 and (
        len(rows) != exercise.target_sets or sorted(s.ordinal for s in rows) != list(range(1, exercise.target_sets + 1)))
    known_partial = any(s.outcome in {"partial", "skipped", "aborted"}
                        or (s.outcome == "completed" and s.target is not None and not facts.target_met(s)) for s in rows)
    return "partial" if known_missing or known_partial or str(exercise.status) in {"partial", "skipped", "aborted"} else "limited"


def exercise_summary(db: Session, user_id: str, exercise_id: int, *, scope_epoch: int, valid_until_ms: float) -> FactPackage:
    exercise = _owned_exercise(db, user_id, exercise_id)
    rows = _sets(db, exercise)
    if len({s.ordinal for s in rows}) != len(rows):
        raise HistoryError("ambiguous_results")
    done = [s for s in rows if s.outcome != "skipped" and s.value]
    common = _provenance(exercise, scope_epoch, valid_until_ms, f"exercise:{exercise.id}")
    if not done:
        raise HistoryError("insufficient_facts")
    outcome = _exercise_outcome(exercise, rows)
    partial = outcome != "full"
    unit = progress_unit(exercise)
    best = max(s.value for s in done if s.value is not None)
    found = [AllowedFact("sets-done", f"Выполнено {spoken_quantity(len(done), 'sets')}", "confirmed", len(done), "sets",
                         numbers=(len(done),), **common),
             AllowedFact("best-set", f"Лучший подход — {spoken_quantity(best, unit)}", "confirmed", best, unit,
                         numbers=(best,), **common),
             AllowedFact("outcome", "Полнота плана упражнения не подтверждена" if partial else "Все подходы выполнены",
                         "derived-validated", outcome,
                         permits=("exercise-plan-complete",) if not partial else (),
                         **{**common, "sufficiency": "sufficient" if not partial else "limited"})]
    if name := speakable_name(exercise.exercise_name):
        found.append(AllowedFact("exercise", f"Упражнение — {name}", "confirmed", name, **common))
    if 0 < (planned := exercise.target_sets or 0) <= 50 and planned != len(done):
        found.append(AllowedFact("planned-sets", f"По плану было {spoken_quantity(planned, 'sets')}", "confirmed", planned,
                                 "sets", numbers=(planned,), **common))
    if len(done) > 1:
        total = sum(s.value or 0 for s in done)
        found.append(AllowedFact("total", f"Всего за упражнение {spoken_quantity(total, unit)}", "confirmed", total, unit,
                                 numbers=(total,), **common))
    weights = {s.weight_kg for s in done}
    if len(weights) == 1 and (weight := facts.weight_fact(
            weights.pop(), prefix="Плановый вес", **{**common, "quantity_kind": "declared", "provenance": "persisted-plan"})):
        found.append(weight)
    source_rows = list(db.scalars(select(SetRow).where(SetRow.exercise_session_id == exercise.id).order_by(SetRow.id)))
    return FactPackage("T56" if partial else "T55", tuple(found), Comparison("unavailable"), outcome,
                       source_signature=_signature(exercise, *source_rows))


def _workout_plan_complete(db: Session, workout: WorkoutSession, exercises: list[ExerciseSession], plan) -> bool:
    if (plan is None or plan.user_id != workout.user_id or plan.stale or plan.revision != 1
            or plan.schema_version != 1 or plan.current != plan.baseline or str(workout.status) != "completed"):
        return False
    try:
        baseline = CoachWorkoutPlanSchema.model_validate(plan.baseline)
    except ValidationError:
        return False
    if len(exercises) != len(baseline.exercises):
        return False
    for exercise, intended in zip(exercises, baseline.exercises, strict=True):
        # Repeated slugs are legitimate distinct occurrences, bound by physical order.
        unknown = {"unknown", "none", "null", "undefined", "n/a", "?"}
        if (any(not identity.strip() or identity.strip().lower() in unknown
            for identity in (intended.exercise_id, intended.slug))
            or exercise.order_index != intended.order_index or exercise.exercise_slug != intended.slug
                or str(exercise.kind) != intended.kind or intended.kind == "group"
                or exercise.per_side != intended.per_side or exercise.training_mode != intended.training_mode
                or exercise.training_day_type != intended.training_day_type
                or (intended.kind == "machine" and not intended.training_mode)
                or str(exercise.status) != "completed" or exercise.target_sets != len(intended.sets)):
            return False
        rows = list(db.scalars(select(SetRow).where(SetRow.exercise_session_id == exercise.id)
                               .order_by(SetRow.set_number, SetRow.id)))
        if len(rows) != len(intended.sets):
            return False
        for row, target in zip(rows, intended.sets, strict=True):
            result = to_fact_set(row, exercise)
            metrics = row.machine_metrics if isinstance(row.machine_metrics, dict) else {}
            if (result.ordinal != target.ordinal or target.unit != result.progress_unit
                    or target.target_type == "unknown" or target.set_type is None
                    or (intended.kind == "machine" and target.planned_weight_kg is None)
                    or result.set_type != target.set_type or result.weight_kg != target.planned_weight_kg
                    or metrics.get("side") != target.side or metrics.get("roundNumber") != target.round_number
                    # Analytics timestamps have SQLite second precision. Capture is
                    # ordered transactionally before any results at session creation.
                    or row.created_at is None or row.created_at.replace(tzinfo=UTC)
                    < plan.captured_at.replace(tzinfo=UTC, microsecond=0)):
                return False
            # Cross-check declared row targets, then independently evaluate values
            # against the immutable baseline, not just mutable planned_value/labels.
            if target.target_type == "exact":
                matches = result.target_exact and not result.target_open and result.target == target.minimum
            elif target.target_type == "range":
                matches = not result.target_exact and result.target_min == target.minimum and result.target == target.maximum
            else:
                matches = result.target_open
            if not matches or not facts.target_met(replace(
                    result, target=target.maximum, target_min=target.minimum if target.target_type == "range" else None,
                    target_exact=target.target_type != "range", target_open=target.target_type == "open")):
                return False
    return True


def workout_summary(db: Session, user_id: str, workout_id: int, *, scope_epoch: int, valid_until_ms: float) -> FactPackage:
    workout = db.get(WorkoutSession, workout_id)
    if workout is None or workout.user_id != user_id:
        raise HistoryError("owner_mismatch")
    exercises = list(db.scalars(select(ExerciseSession).where(ExerciseSession.workout_session_id == workout.id)
                                .order_by(ExerciseSession.order_index, ExerciseSession.id)))
    if any(exercise.user_id != user_id for exercise in exercises):
        raise HistoryError("owner_mismatch")
    per_exercise = [(exercise, _sets(db, exercise)) for exercise in exercises]
    if any(len({s.ordinal for s in rows}) != len(rows) for _, rows in per_exercise):
        raise HistoryError("ambiguous_results")
    sets = [s for _, rows in per_exercise for s in rows]
    done = [s for s in sets if s.outcome != "skipped" and s.value]
    if not done:
        raise HistoryError("insufficient_facts")
    active = sum(any(s.outcome != "skipped" and s.value for s in rows) for _, rows in per_exercise)
    partial = (str(workout.status) in {"partial", "aborted"}
               or any(_exercise_outcome(exercise, rows) == "partial" for exercise, rows in per_exercise))
    plan = load_plan(db, workout.id)
    complete = _workout_plan_complete(db, workout, exercises, plan)
    outcome = "full" if complete else "partial" if partial else "limited"
    common = _provenance(workout, scope_epoch, valid_until_ms, f"workout:{workout.id}")
    found = [AllowedFact("exercises-done", f"Сделано {spoken_quantity(active, 'exercises')}", "confirmed", active,
                         "exercises", numbers=(active,), **common),
             AllowedFact("sets-done", f"Всего {spoken_quantity(len(done), 'sets')}", "confirmed", len(done), "sets",
                         numbers=(len(done),), **common),
                 AllowedFact("outcome", "Весь план выполнен" if complete else
                                 "Часть запланированных подходов не подтверждена" if partial else
                         "Сохранённые результаты подведены; полнота всего плана неизвестна",
                                 "derived-validated", outcome,
                                 permits=("workout-plan-complete", "exercise-plan-complete") if complete else (),
                                 **{**common, "sufficiency": "sufficient" if complete else "limited",
                                     "provenance": "persisted-declared-client-plan" if complete else "persisted-analytics"})]
    reps = sum(s.value or 0 for s in done if s.progress_unit == "reps")
    if reps > 0:
        found.append(AllowedFact("total-reps", f"Всего {spoken_quantity(reps, 'reps')}", "confirmed", reps, "reps",
                                 numbers=(reps,), **common))
    seconds = workout.duration_seconds or 0
    if seconds <= 0 and workout.finished_at is not None and workout.started_at is not None:
        seconds = int((workout.finished_at - workout.started_at).total_seconds())
    if 1 <= (minutes := round(seconds / 60)) <= 600:
        found.append(AllowedFact("duration", f"Длительность тренировки — {spoken_quantity(minutes, 'minutes')}", "confirmed",
                                 minutes, "minutes", numbers=(minutes,), **common))
    names = list(dict.fromkeys(name for exercise, rows in per_exercise
                               if any(s.outcome != "skipped" and s.value for s in rows)
                               and (name := speakable_name(exercise.exercise_name))))[:3]
    if names:
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " и " + names[-1]
        found.append(AllowedFact("exercise-names", f"Упражнения тренировки: {listed}"[:200], "confirmed", listed,
                                 **common))
    source_rows = list(db.scalars(select(SetRow).join(ExerciseSession).where(
        ExerciseSession.workout_session_id == workout.id).order_by(SetRow.id)))
    return FactPackage("T58" if complete else "T59", tuple(found), Comparison("unavailable"), outcome,
                       notes=() if complete else ("authoritative_workout_plan_unavailable",),
                       source_signature=_signature(workout, plan, *exercises, *source_rows))
