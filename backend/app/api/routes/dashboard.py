from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.dashboard import DashboardDataSchema, DashboardDayProgressResetResultSchema, DashboardDayProgressResetSchema
from app.services.dashboard_service import DashboardService

router = APIRouter()

dashboard_service = DashboardService()


@router.get("/dashboard", response_model=DashboardDataSchema)
def get_dashboard(
    user_id: str = Query(..., alias="userId"),
    scenario: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> DashboardDataSchema:
    try:
        return dashboard_service.get_dashboard(session, user_id, scenario)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/dashboard/day-progress/reset", response_model=DashboardDayProgressResetResultSchema)
def reset_dashboard_day_progress(
    payload: DashboardDayProgressResetSchema,
    session: Session = Depends(get_session),
) -> DashboardDayProgressResetResultSchema:
    try:
        return dashboard_service.reset_day_progress(session, payload.user_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
