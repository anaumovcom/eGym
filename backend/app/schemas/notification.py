from datetime import datetime

from app.models.enums import NotificationTone
from app.schemas.base import SchemaModel


class NotificationSchema(SchemaModel):
    id: str
    tone: NotificationTone
    title: str
    description: str
    created_at: datetime


class NotificationsResponseSchema(SchemaModel):
    notifications: list[NotificationSchema]
