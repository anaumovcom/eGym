"""Per-user revision CAS. Legacy flags/unknown schema never imply paid consent."""

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.coach import CoachAttempt, CoachLedgerRun, CoachPreference
from app.models.user import User
from app.schemas.coach_control import CoachPreferences, PreferencesSave


def load_preferences(db: Session, user_id: str) -> CoachPreferences:
    if db.get(User, user_id) is None:
        raise HTTPException(404, "user_not_found")
    row = db.get(CoachPreference, user_id)
    if row is None:
        return CoachPreferences()
    try:
        if row.value.get("schemaVersion") != 1:
            raise ValueError("unknown_schema")
        return CoachPreferences.model_validate({**row.value, "revision": row.revision})
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
    return saved