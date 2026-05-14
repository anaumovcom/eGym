from datetime import UTC

from sqlalchemy.orm import Session

from app.models.enums import NotificationTone
from app.repositories.machine_repository import MachineRepository
from app.schemas.notification import NotificationSchema


class NotificationsService:
    def __init__(self) -> None:
        self.machine_repository = MachineRepository()

    def list_notifications(self, session: Session) -> list[NotificationSchema]:
        notifications: list[NotificationSchema] = []
        warning_snapshot = self.machine_repository.get_machine_status(session, "warning")
        if warning_snapshot is not None:
            right_drive = next((drive for drive in warning_snapshot.drives if drive.side == "right"), None)
            if right_drive is not None and right_drive.drive_state.value != "connected":
                notifications.append(
                    NotificationSchema(
                        id=f"drive-{warning_snapshot.id}",
                        tone=NotificationTone.warning,
                        title="Требуется внимание к правому приводу",
                        description=right_drive.message
                        or "Перед тренировкой рекомендуется сервисная проверка привода.",
                        created_at=warning_snapshot.captured_at.astimezone(UTC),
                    )
                )

        blocked_event = self.machine_repository.get_latest_active_safety_event(session)
        if blocked_event is not None:
            notifications.append(
                NotificationSchema(
                    id=f"safety-{blocked_event.id}",
                    tone=NotificationTone.blocked,
                    title=blocked_event.title,
                    description=blocked_event.description,
                    created_at=blocked_event.created_at.astimezone(UTC),
                )
            )
        return notifications
