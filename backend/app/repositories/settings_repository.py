from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settings import AppSetting


class SettingsRepository:
    def list_for_user(self, session: Session, user_id: str) -> list[AppSetting]:
        statement = (
            select(AppSetting)
            .where((AppSetting.user_id == user_id) | (AppSetting.user_id.is_(None)))
            .order_by(AppSetting.key)
        )
        return list(session.scalars(statement))
