"""Read last settings without interpreting historical total repetitions as a set target."""
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession
from app.models.enums import RuntimeExerciseKind
from app.models.training import UserExerciseState
from app.schemas.runtime import ExerciseSettingsSchema


def remembered_settings(session: Session, state: UserExerciseState | None) -> ExerciseSettingsSchema | None:
    if state is None:
        return None
    metadata = state.calibration_payload or {}
    snapshot = metadata.get("lastSettings")
    if isinstance(snapshot, dict):
        try:
            return ExerciseSettingsSchema.model_validate(snapshot)
        except ValidationError:
            pass
    legacy = metadata.get("lastResult")
    if not isinstance(legacy, dict):
        return None
    reps = legacy.get("repsPerSet", state.working_reps)
    exercise = session.get(ExerciseSession, legacy["exerciseSessionId"]) if legacy.get("exerciseSessionId") else None
    if exercise and exercise.kind in {RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch}:
        targets = [row.planned_value for row in sorted(exercise.set_results, key=lambda row: row.set_number)
                   if row.planned_value > 0 and row.machine_metrics.get("setType") != "warmup"]
        if targets:
            reps = targets[-1]
    try:
        return ExerciseSettingsSchema(
            weight=legacy.get("weightKg", state.working_weight),
            sets=legacy.get("sets", state.working_sets), reps=reps,
            rest_seconds=state.rest_seconds if state.rest_seconds is not None else 60,
            training_mode=legacy.get("trainingMode"), training_day_type=legacy.get("trainingDayType"),
        )
    except ValidationError:
        return None