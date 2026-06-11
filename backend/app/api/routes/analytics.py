from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.schemas.analytics import (
    AchievementsResponseSchema,
    BodyMeasurementCreateSchema,
    BodyMeasurementListResponseSchema,
    FatigueDataSchema,
    FatigueResetResultSchema,
    FatigueResetSchema,
    FatigueHistoryResponseSchema,
    ProgressDataSchema,
    ProgressPhotoAssetSchema,
    ProgressPhotoListResponseSchema,
)
from app.services.media_service import MediaService
from app.services.progress_service import ProgressService

router = APIRouter()

progress_service = ProgressService()
media_service = MediaService()


@router.get("/progress", response_model=ProgressDataSchema)
def get_progress(
    user_id: str = Query(..., alias="userId"),
    period: str = Query(default="30d"),
    exercise_slug: str | None = Query(default=None, alias="exerciseSlug"),
    session: Session = Depends(get_session),
) -> ProgressDataSchema:
    return progress_service.get_progress(session, user_id=user_id, period=period, exercise_slug=exercise_slug)


@router.get("/fatigue", response_model=FatigueDataSchema)
def get_fatigue(
    user_id: str = Query(..., alias="userId"),
    mode: str = Query(default="current"),
    session: Session = Depends(get_session),
) -> FatigueDataSchema:
    return progress_service.get_fatigue(session, user_id=user_id, mode=mode)


@router.post("/fatigue/reset", response_model=FatigueResetResultSchema)
def reset_fatigue(
    payload: FatigueResetSchema,
    session: Session = Depends(get_session),
) -> FatigueResetResultSchema:
    reset_at, reset_count = progress_service.reset_fatigue(session, user_id=payload.user_id)
    session.commit()
    return FatigueResetResultSchema(
        status="ok",
        user_id=payload.user_id,
        reset_at=reset_at,
        reset_count=reset_count,
    )


@router.get("/fatigue/history", response_model=FatigueHistoryResponseSchema)
def get_fatigue_history(
    user_id: str = Query(..., alias="userId"),
    muscle_id: str = Query(..., alias="muscleId"),
    session: Session = Depends(get_session),
) -> FatigueHistoryResponseSchema:
    return progress_service.get_fatigue_history(session, user_id=user_id, muscle_id=muscle_id)


@router.get("/photo-progress", response_model=ProgressPhotoListResponseSchema)
def list_progress_photos(
    user_id: str = Query(..., alias="userId"),
    session: Session = Depends(get_session),
) -> ProgressPhotoListResponseSchema:
    settings = get_settings()
    return progress_service.list_photos(session, user_id=user_id, media_prefix=settings.media_url_prefix)


@router.post("/photo-progress", response_model=ProgressPhotoAssetSchema)
def upload_progress_photo(
    user_id: str = Form(..., alias="userId"),
    mode: str = Form(...),
    view: str = Form(...),
    taken_at: datetime | None = Form(default=None, alias="takenAt"),
    workout_session_id: int | None = Form(default=None, alias="workoutSessionId"),
    note: str | None = Form(default=None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> ProgressPhotoAssetSchema:
    try:
        return media_service.upload_progress_photo(
            session,
            user_id=user_id,
            mode=mode,
            view=view,
            file=file,
            taken_at=taken_at,
            workout_session_id=workout_session_id,
            note=note,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.delete("/photo-progress/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_progress_photo(
    photo_id: int,
    confirm: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> None:
    try:
        media_service.delete_progress_photo(session, photo_id=photo_id, confirm=confirm)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/body-measurements", response_model=BodyMeasurementListResponseSchema)
def list_body_measurements(
    user_id: str = Query(..., alias="userId"),
    session: Session = Depends(get_session),
) -> BodyMeasurementListResponseSchema:
    return progress_service.list_body_measurements(session, user_id=user_id)


@router.post("/body-measurements", response_model=BodyMeasurementListResponseSchema)
def create_body_measurement(
    payload: BodyMeasurementCreateSchema,
    session: Session = Depends(get_session),
) -> BodyMeasurementListResponseSchema:
    progress_service.create_body_measurement(session, payload)
    return progress_service.list_body_measurements(session, user_id=payload.user_id)


@router.get("/achievements", response_model=AchievementsResponseSchema)
def list_achievements(
    user_id: str = Query(..., alias="userId"),
    session: Session = Depends(get_session),
) -> AchievementsResponseSchema:
    return progress_service.list_achievements(session, user_id=user_id)