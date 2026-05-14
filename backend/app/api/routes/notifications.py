from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.notification import NotificationsResponseSchema
from app.services.notifications_service import NotificationsService

router = APIRouter()

notifications_service = NotificationsService()


@router.get("/notifications", response_model=NotificationsResponseSchema)
def list_notifications(session: Session = Depends(get_session)) -> NotificationsResponseSchema:
    return NotificationsResponseSchema(notifications=notifications_service.list_notifications(session))
