from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
    RuntimeExerciseSummarySchema,
    RuntimeWorkoutSummarySchema,
    SavedSetResponseSchema,
    SetResultSaveSchema,
    WorkoutSessionCreateSchema,
)
from app.services.runtime_service import RuntimeService

router = APIRouter()

runtime_service = RuntimeService()


@router.post("/runtime/sets", response_model=SavedSetResponseSchema)
def save_set_result(payload: SetResultSaveSchema, session: Session = Depends(get_session)) -> SavedSetResponseSchema:
    try:
        return runtime_service.save_set_result(session, payload)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/runtime/exercises", response_model=RuntimeExerciseSummarySchema)
def save_exercise_session(
    payload: ExerciseSessionCreateSchema,
    session: Session = Depends(get_session),
) -> RuntimeExerciseSummarySchema:
    return runtime_service.save_exercise_session(session, payload).summary


@router.post("/runtime/workouts", response_model=RuntimeWorkoutSummarySchema)
def save_workout_session(
    payload: WorkoutSessionCreateSchema,
    session: Session = Depends(get_session),
) -> RuntimeWorkoutSummarySchema:
    return runtime_service.save_workout_session(session, payload)


@router.get("/runtime/exercises/{exercise_session_id}/summary", response_model=RuntimeExerciseSummarySchema)
def get_exercise_summary(exercise_session_id: int, session: Session = Depends(get_session)) -> RuntimeExerciseSummarySchema:
    try:
        return runtime_service.get_exercise_summary(session, exercise_session_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/runtime/workouts/{workout_session_id}/summary", response_model=RuntimeWorkoutSummarySchema)
def get_workout_summary(workout_session_id: int, session: Session = Depends(get_session)) -> RuntimeWorkoutSummarySchema:
    try:
        return runtime_service.get_workout_summary(session, workout_session_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error