from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.profile import BodyMeasurement, UserProfile
from app.models.scale import ScaleReading
from app.models.settings import AppSetting
from app.models.user import User
from app.schemas.scale import ScaleMeasurement, ScaleSettings
from app.services.scale_protocol import ScalePacket

SETTINGS_KEY = "ble_body_scale"
DELETED_KEY = "ble_body_scale_deleted"


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def serialize(body: BodyMeasurement, reading: ScaleReading) -> ScaleMeasurement:
    return ScaleMeasurement(
        id=body.id, user_id=body.user_id, weight_kg=float(body.weight_kg),
        timestamp=as_utc(body.measured_at), device_id=reading.device_id,
        impedance_ohm=reading.impedance_ohm,
    )


class ScaleRepository:
    def settings(self, db: Session) -> ScaleSettings:
        row = db.scalar(select(AppSetting).where(AppSetting.key == SETTINGS_KEY, AppSetting.user_id.is_(None)))
        return ScaleSettings.model_validate(row.value) if row else ScaleSettings()

    def configure(self, db: Session, settings: ScaleSettings) -> None:
        row = db.scalar(select(AppSetting).where(AppSetting.key == SETTINGS_KEY, AppSetting.user_id.is_(None)))
        if row is None:
            row = AppSetting(key=SETTINGS_KEY, user_id=None)
            db.add(row)
        row.value = settings.model_dump(mode="json")
        db.commit()

    def history(self, db: Session, user_id: str, days: int = 90, limit: int = 500) -> list[ScaleMeasurement]:
        rows = db.execute(
            select(BodyMeasurement, ScaleReading).join(ScaleReading, ScaleReading.measurement_id == BodyMeasurement.id)
            .where(BodyMeasurement.user_id == user_id, BodyMeasurement.measured_at >= datetime.now(UTC) - timedelta(days=days))
            .order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.id.desc()).limit(limit)
        )
        return [serialize(body, reading) for body, reading in rows]

    def latest(self, db: Session, user_id: str | None = None) -> ScaleMeasurement | None:
        statement = (
            select(BodyMeasurement, ScaleReading).join(ScaleReading, ScaleReading.measurement_id == BodyMeasurement.id)
            .order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.id.desc()).limit(1)
        )
        if user_id is not None:
            statement = statement.where(BodyMeasurement.user_id == user_id)
        row = db.execute(statement).first()
        return serialize(*row) if row else None

    def save_current_measurement(self, db: Session, device_id: str, packet: ScalePacket, now: datetime) -> ScaleMeasurement | None:
        user_id = db.scalar(select(User.id).where(User.is_current.is_(True), User.is_active.is_(True)))
        if user_id is None:
            raise ValueError("Выберите активного пользователя для записи веса")
        return self.save_measurement(db, user_id, device_id, packet, now)

    def save_measurement(
        self, db: Session, user_id: str, device_id: str, packet: ScalePacket, now: datetime,
    ) -> ScaleMeasurement | None:
        if not packet.stable or packet.removed or not 2 <= packet.weight_kg <= 180:
            return None
        if db.get(User, user_id) is None:
            raise ValueError("Профиль весов удалён; выберите профиль заново")
        # The device clock is only an identity token, NEVER the authoritative timestamp.
        token = f"{packet.clock}:{packet.weight_kg}" if packet.clock else uuid4().hex
        key = sha256(token.encode()).hexdigest()
        deleted = db.scalar(select(AppSetting).where(AppSetting.key == DELETED_KEY, AppSetting.user_id.is_(None)))
        for entry in deleted.value.get("entries", []) if deleted else []:
            if entry["deviceId"] != device_id:
                continue
            if packet.clock and entry["key"] == key:
                return None
            if abs((now - datetime.fromisoformat(entry["timestamp"])).total_seconds()) < 120 and abs(entry["weightKg"] - packet.weight_kg) < 0.1:
                return None
        if db.scalar(select(ScaleReading).where(ScaleReading.device_id == device_id, ScaleReading.measurement_key == key)):
            return None
        recent = db.execute(
            select(BodyMeasurement, ScaleReading).join(ScaleReading, ScaleReading.measurement_id == BodyMeasurement.id)
            .where(ScaleReading.device_id == device_id)
            .order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.id.desc()).limit(1)
        ).first()
        if recent and abs((now - as_utc(recent[0].measured_at)).total_seconds()) < 120:
            if abs(float(recent[0].weight_kg) - packet.weight_kg) < 0.1:
                return None
        body = BodyMeasurement(user_id=user_id, measured_at=now, weight_kg=packet.weight_kg)
        db.add(body)
        db.flush()
        reading = ScaleReading(measurement_id=body.id, device_id=device_id, measurement_key=key, impedance_ohm=packet.impedance_ohm)
        db.add(reading)
        profile = db.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            db.add(profile)
        profile.weight_kg = packet.weight_kg
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None
        return serialize(body, reading)

    def enrich_impedance(self, db: Session, measurement_id: int, impedance: int) -> None:
        row = db.get(ScaleReading, measurement_id)
        if row and row.impedance_ohm is None and 0 < impedance < 3000:
            row.impedance_ohm = impedance
            db.commit()

    def delete_measurement(self, db: Session, measurement_id: int, user_id: str) -> None:
        body = db.get(BodyMeasurement, measurement_id)
        reading = db.get(ScaleReading, measurement_id)
        if body is None or reading is None or body.user_id != user_id:
            raise LookupError("Измерение не найдено")
        # Remember a bounded set of deleted packet identities: a subsequent
        # advertisement must not immediately recreate an erroneous weighing.
        tombstones = db.scalar(select(AppSetting).where(AppSetting.key == DELETED_KEY, AppSetting.user_id.is_(None)))
        if tombstones is None:
            tombstones = AppSetting(key=DELETED_KEY, user_id=None, value={})
            db.add(tombstones)
        entries = list(tombstones.value.get("entries", []))
        entries.append({"deviceId": reading.device_id, "key": reading.measurement_key,
                        "weightKg": float(body.weight_kg), "timestamp": as_utc(body.measured_at).isoformat()})
        tombstones.value = {"entries": entries[-256:]}
        latest_body = db.scalar(select(BodyMeasurement).where(
            BodyMeasurement.user_id == user_id, BodyMeasurement.weight_kg.is_not(None),
        ).order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.id.desc()).limit(1))
        previous = db.scalar(select(BodyMeasurement).where(
            BodyMeasurement.user_id == user_id, BodyMeasurement.weight_kg.is_not(None), BodyMeasurement.id != measurement_id,
        ).order_by(BodyMeasurement.measured_at.desc(), BodyMeasurement.id.desc()).limit(1))
        profile = db.get(UserProfile, user_id)
        if latest_body is body and profile and profile.weight_kg == body.weight_kg:
            profile.weight_kg = previous.weight_kg if previous else None
        db.delete(reading)
        db.flush()
        db.delete(body)
        db.commit()