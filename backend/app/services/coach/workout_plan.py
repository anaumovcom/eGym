"""Optional immutable pre-result baseline. Never create tables from runtime paths."""

from datetime import UTC, datetime

from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from app.models.analytics import CoachWorkoutPlan, WorkoutSession
from app.schemas.runtime import WorkoutSessionCreateSchema


def load_plan(db: Session, workout_id: int) -> CoachWorkoutPlan | None:
    # Inspect this transaction's connection, not a second connection or cached
    # process-wide result. Only absent-table is optional; other DB errors surface.
    if not inspect(db.connection()).has_table(CoachWorkoutPlan.__tablename__):
        return None
    return db.scalar(select(CoachWorkoutPlan).where(CoachWorkoutPlan.workout_id == workout_id)
                     .execution_options(populate_existing=True))


def persist_plan(db: Session, workout: WorkoutSession, payload: WorkoutSessionCreateSchema) -> None:
    if not inspect(db.connection()).has_table(CoachWorkoutPlan.__tablename__):
        return
    declared = payload.coach_plan.model_dump(mode="json") if payload.coach_plan else None
    plan = load_plan(db, workout.id)
    if payload.workout_session_id is None:
        # Finalization/linked or nested results cannot retroactively certify intent.
        if declared is not None and payload.status == "in_progress" and not payload.exercises and not payload.exercise_session_ids:
            db.add(CoachWorkoutPlan(workout_id=workout.id, user_id=workout.user_id, schema_version=1,
                                    revision=1, stale=False, captured_at=datetime.now(UTC),
                                    baseline=declared, current=declared))
        return
    if plan is None:
        return  # Legacy sessions stay limited forever, even if a final save sends a plan.
    if plan.user_id != payload.user_id:
        raise LookupError("Workout plan not found")
    if declared != plan.current:
        # Server-owned monotonic CAS revision. This API can only invalidate, never
        # replace/re-bless the original baseline, including after an edit is undone.
        changed = db.execute(update(CoachWorkoutPlan).where(
            CoachWorkoutPlan.workout_id == workout.id, CoachWorkoutPlan.revision == plan.revision,
            CoachWorkoutPlan.user_id == payload.user_id).values(
                current=declared, stale=True, revision=plan.revision + 1))
        if changed.rowcount != 1:
            raise ValueError("Workout plan revision conflict")