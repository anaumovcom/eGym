"""Achievement collection, awards and owner-scoped interaction receipts."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from starlette.staticfiles import StaticFiles

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.schemas.achievement import (
    AchievementCatalogResponseSchema,
    AchievementLineSchema,
    AchievementOverviewResponseSchema,
    AchievementReceiptSchema,
    WorkoutAwardsResponseSchema,
)
from app.services.achievements import service

router = APIRouter()


@router.get("/achievements/overview", response_model=AchievementOverviewResponseSchema)
def achievement_overview(user_id: str = Query(..., alias="userId"), session: Session = Depends(get_session)):
    return service.overview(session, user_id, media_prefix=get_settings().media_url_prefix)


@router.get("/achievements/catalog", response_model=AchievementCatalogResponseSchema)
def achievement_catalog(
    user_id: str = Query(..., alias="userId"),
    category: str | None = None,
    status: str | None = None,
    rarity: str | None = None,
    query: str | None = None,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=40, ge=1, le=200),
    session: Session = Depends(get_session),
):
    return service.catalog(session, user_id, category=category, status=status, rarity=rarity, query=query,
                           cursor=cursor, limit=limit, media_prefix=get_settings().media_url_prefix)


@router.get("/achievements/tiers/{tier_id}/{kind}")
def achievement_tier_media(request: Request, tier_id: str, kind: Literal["image", "audio"], user_id: str = Query(..., alias="userId"),
                           session: Session = Depends(get_session)):
    """Serve artwork/speech only for tiers the owner has earned; locked media is indistinguishable from absent."""
    path = service.earned_media_path(session, user_id, tier_id, kind)
    if path is None:
        raise HTTPException(status_code=404, detail="Achievement media not found", headers={"Cache-Control": "no-store"})
    response = StaticFiles().file_response(path, path.stat(), request.scope)
    if response.status_code == 200:
        response.headers["Content-Type"] = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".webp": "image/webp"}[path.suffix.lower()]
    response.headers.update({"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"})
    return response


@router.get("/achievements/{definition_id}", response_model=AchievementLineSchema)
def achievement_detail(definition_id: str, user_id: str = Query(..., alias="userId"),
                       session: Session = Depends(get_session)):
    result = service.detail(session, user_id, definition_id, media_prefix=get_settings().media_url_prefix)
    if result is None:
        raise HTTPException(status_code=404, detail="Achievement not found")
    return result


@router.post("/achievements/{definition_id}/receipts/{surface}", response_model=AchievementReceiptSchema)
def achievement_receipt(definition_id: str, surface: Literal["detail", "audio"],
                        user_id: str = Query(..., alias="userId"), tier: int | None = Query(default=None, ge=1),
                        session: Session = Depends(get_session)):
    try:
        return service.record_receipt(session, user_id, definition_id, surface, tier)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Achievement grant not found") from exc


@router.get("/runtime/workouts/{workout_id}/awards", response_model=WorkoutAwardsResponseSchema)
def runtime_workout_awards(workout_id: int, user_id: str = Query(..., alias="userId"),
                           session: Session = Depends(get_session)):
    result = service.workout_awards(session, user_id, workout_id, media_prefix=get_settings().media_url_prefix)
    if result is None:
        raise HTTPException(status_code=404, detail="Workout session not found")
    return result
