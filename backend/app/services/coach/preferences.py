"""Per-user revision CAS. Legacy flags/unknown schema never imply paid consent."""

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.coach import CoachAttempt, CoachLedgerRun, CoachPreference
from app.models.user import User
from app.schemas.coach_control import CoachPreferences, PreferencesSave


def migrate_characters(value: dict) -> dict:
    """Values saved before coach characters get the new default roast set once (user decision 24.10.2026).

    An explicit «no jokes» stays respected; consent, mode and budget are never touched.
    """
    if "persona" in value:
        return value
    kinds = [kind for kind in value.get("humorKinds") or [] if kind != "roast"]
    joking = value.get("humor") != "off"
    return {**value, "persona": "streamer", "profanity": True, "voiceModel": "fish-drama-3",
            "humor": "often" if joking else "off", "humorKinds": ["roast", *kinds][:5] if joking else kinds,
            "edgyOptIn": joking}


def load_preferences(db: Session, user_id: str) -> CoachPreferences:
    if db.get(User, user_id) is None:
        raise HTTPException(404, "user_not_found")
    row = db.get(CoachPreference, user_id)
    if row is None:
        return CoachPreferences()
    try:
        if row.value.get("schemaVersion") != 1:
            raise ValueError("unknown_schema")
        return CoachPreferences.model_validate({**migrate_characters(row.value), "revision": row.revision})
    except (ValidationError, ValueError):
        # Fail-closed migration from unsupported/incomplete legacy values, preserving CAS revision.
        return CoachPreferences(revision=row.revision)


def save_preferences(db: Session, user_id: str, payload: PreferencesSave) -> CoachPreferences:
    current = load_preferences(db, user_id)
    if current.revision != payload.expected_revision:
        raise HTTPException(409, "revision_conflict")
    saved = payload.settings.model_copy(update={"revision": current.revision + 1})
    value = saved.model_dump(mode="json", by_alias=True)
    row = db.get(CoachPreference, user_id)
    if row is None:
        db.add(CoachPreference(user_id=user_id, revision=saved.revision, value=value))
    else:
        changed = db.execute(update(CoachPreference).where(
            CoachPreference.user_id == user_id, CoachPreference.revision == current.revision,
        ).values(value=value, revision=saved.revision))
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "revision_conflict")
    # Any saved settings change invalidates future reserved work; sent attempts remain accounted.
    db.execute(update(CoachLedgerRun).where(CoachLedgerRun.user_id == user_id).values(
        generation=CoachLedgerRun.generation + 1,
    ))
    affected = select(CoachLedgerRun.id).where(CoachLedgerRun.user_id == user_id)
    db.execute(update(CoachAttempt).where(CoachAttempt.run_id.in_(affected), CoachAttempt.status == "reserved").values(status="cancelled"))
    db.execute(update(CoachAttempt).where(CoachAttempt.run_id.in_(affected), CoachAttempt.status == "sent").values(status="unsettled"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "revision_conflict") from None
    from app.services.coach.live import update_memory_preferences

    update_memory_preferences(user_id, saved)
    return saved