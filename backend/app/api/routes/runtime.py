from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
    ExerciseSessionsResetRequestSchema,
    ExerciseSessionsResetResponseSchema,
    ExerciseSettingsSaveSchema,
    ExerciseSettingsSchema,
    LoadAdjustmentRequestSchema,
    LoadAdjustmentResponseSchema,
    RuntimeExerciseSummarySchema,
    RuntimeWorkoutSummarySchema,
    SavedSetResponseSchema,
    SetFeedbackSchema,
    SetResultSaveSchema,
    WorkoutSessionCreateSchema,
)
from app.services.runtime_service import RuntimeService

router = APIRouter()

runtime_service = RuntimeService()


@router.get("/runtime/exercises/settings", response_model=ExerciseSettingsSchema | None)
def get_exercise_settings(
    user_id: str = Query(..., alias="userId"),
    exercise_slug: str = Query(..., alias="exerciseSlug"),
    session: Session = Depends(get_session),
) -> ExerciseSettingsSchema | None:
    try:
        return runtime_service.get_exercise_settings(session, user_id, exercise_slug)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.put("/runtime/exercises/settings", response_model=ExerciseSettingsSchema)
def save_exercise_settings(
    payload: ExerciseSettingsSaveSchema, session: Session = Depends(get_session),
) -> ExerciseSettingsSchema:
    try:
        return runtime_service.save_exercise_settings(session, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/runtime/sets/{set_id}/feedback", response_model=SetFeedbackSchema)
def save_set_feedback(set_id: int, payload: SetFeedbackSchema,
                      session: Session = Depends(get_session)) -> SetFeedbackSchema:
    # Same selected-user ownership contract as runtime deletion; not a new authentication system.
    try:
        return runtime_service.save_set_feedback(session, set_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Set not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
    try:
        return runtime_service.save_exercise_session(session, payload).summary
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/runtime/exercises/reset", response_model=ExerciseSessionsResetResponseSchema)
def reset_exercise_sessions(
    payload: ExerciseSessionsResetRequestSchema,
    session: Session = Depends(get_session),
) -> ExerciseSessionsResetResponseSchema:
    try:
        return runtime_service.reset_exercise_sessions(session, payload)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/runtime/workouts", response_model=RuntimeWorkoutSummarySchema)
def save_workout_session(
    payload: WorkoutSessionCreateSchema,
    session: Session = Depends(get_session),
) -> RuntimeWorkoutSummarySchema:
    try:
        return runtime_service.save_workout_session(session, payload)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/runtime/exercises/load-adjustment", response_model=LoadAdjustmentResponseSchema)
def adjust_exercise_load(
    payload: LoadAdjustmentRequestSchema,
    session: Session = Depends(get_session),
) -> LoadAdjustmentResponseSchema:
    return runtime_service.adjust_exercise_load(session, payload)


@router.get("/runtime/exercises/{exercise_session_id}/summary", response_model=RuntimeExerciseSummarySchema)
def get_exercise_summary(exercise_session_id: int, session: Session = Depends(get_session)) -> RuntimeExerciseSummarySchema:
    try:
        return runtime_service.get_exercise_summary(session, exercise_session_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.delete("/runtime/workouts/{workout_session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout_session(
    workout_session_id: int,
    user_id: str = Query(..., alias="userId"),
    session: Session = Depends(get_session),
) -> None:
    try:
        runtime_service.delete_workout_session(session, workout_session_id=workout_session_id, user_id=user_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/runtime/workouts/{workout_session_id}/summary", response_model=RuntimeWorkoutSummarySchema)
def get_workout_summary(workout_session_id: int, session: Session = Depends(get_session)) -> RuntimeWorkoutSummarySchema:
    try:
        return runtime_service.get_workout_summary(session, workout_session_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error