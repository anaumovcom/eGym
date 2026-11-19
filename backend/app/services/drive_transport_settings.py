from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.schemas.drive_transport import DriveTransportSettings

_SELECTION = select(AppSetting).where(AppSetting.key == "hardware.drive_transport", AppSetting.user_id.is_(None))


def load_transport(session: Session) -> DriveTransportSettings:
    row = session.scalars(_SELECTION).one_or_none()
    return DriveTransportSettings.model_validate(row.value) if row else DriveTransportSettings.from_environment()


def save_transport(session: Session, config: DriveTransportSettings) -> None:
    row = session.scalars(_SELECTION).one_or_none()
    if row is None:
        row = AppSetting(key="hardware.drive_transport")
        session.add(row)
    row.value = config.model_dump(mode="json")
    session.commit()
