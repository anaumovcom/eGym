from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.analytics import ProgressPhoto
from app.models.enums import RuntimePhotoMode, RuntimePhotoView
from app.schemas.analytics import ProgressPhotoAssetSchema
from app.services.photo_crop import crop_progress_photo


class MediaService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.media_root = Path(self.settings.media_root)

    def upload_progress_photo(
        self,
        session: Session,
        *,
        user_id: str,
        mode: str,
        view: str,
        file: UploadFile,
        taken_at: datetime | None,
        workout_session_id: int | None,
        note: str | None,
    ) -> ProgressPhotoAssetSchema:
        photo_mode = RuntimePhotoMode(mode)
        photo_view = RuntimePhotoView(view)
        content = file.file.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("Фото должно быть не больше 20 МБ.")
        try:
            with Image.open(BytesIO(content)) as original:
                if original.width * original.height > 20_000_000:
                    raise ValueError("Разрешение фото должно быть не больше 20 мегапикселей.")
                original.load()
                image = crop_progress_photo(original, self.settings.photo_person_model_path)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError("Не удалось прочитать изображение. Используйте JPEG или PNG.") from error
        encoded = BytesIO()
        image.save(encoded, format="JPEG", quality=92, optimize=True)
        content = encoded.getvalue()
        target_dir = self.media_root / "progress-photos" / user_id
        thumb_dir = target_dir / "thumbs"
        target_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex}.jpg"
        storage_path = target_dir / file_name
        thumbnail_path = thumb_dir / file_name
        storage_path.write_bytes(content)
        thumbnail = image.copy()
        thumbnail.thumbnail((240, 320))
        thumbnail.save(thumbnail_path, format="JPEG", quality=85)
        photo = ProgressPhoto(
            user_id=user_id,
            workout_session_id=workout_session_id,
            mode=photo_mode,
            view=photo_view,
            taken_at=taken_at or datetime.now(UTC),
            storage_path=str(storage_path.relative_to(self.media_root)),
            thumbnail_path=str(thumbnail_path.relative_to(self.media_root)),
            mime_type="image/jpeg",
            file_size=len(content),
            width=image.width,
            height=image.height,
            note=note,
        )
        session.add(photo)
        session.commit()
        session.refresh(photo)
        return ProgressPhotoAssetSchema(
            id=photo.id,
            mode=photo.mode.value,
            view=photo.view.value,
            taken_at=photo.taken_at.astimezone(UTC).isoformat(),
            image_url=f"{self.settings.media_url_prefix}/{photo.storage_path}".replace("\\", "/"),
            thumbnail_url=f"{self.settings.media_url_prefix}/{photo.thumbnail_path}".replace("\\", "/"),
            width=photo.width,
            height=photo.height,
            note=photo.note,
        )

    def delete_progress_photo(self, session: Session, *, photo_id: int, confirm: bool) -> None:
        if not confirm:
            raise ValueError("Deletion must be confirmed")
        photo = session.get(ProgressPhoto, photo_id)
        if photo is None:
            raise LookupError("Photo not found")
        photo.is_deleted = True
        photo.deleted_at = datetime.now(UTC)
        session.commit()