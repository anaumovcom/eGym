"""Coach control plane. No inference dispatch or provider secrets in responses."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachCredential, CoachJob, CoachLedgerRun, CoachOperatorSession
from app.schemas.coach import CoachCapabilities
from app.schemas.coach_control import (
    CapChange,
    CoachPreferences,
    CredentialDelete,
    CredentialSave,
    JobAction,
    JobCreate,
    LeaseRequest,
    OperatorLogin,
    PackJobCreate,
    PreferencesSave,
    RunBind,
    RunCreate,
)
from app.services.coach import ledger, packs, security
from app.services.coach.preferences import load_preferences, save_preferences

router = APIRouter()


@router.get("/coach/capabilities", response_model=CoachCapabilities)
def coach_capabilities() -> CoachCapabilities:
    enabled = get_settings().coach_enabled
    return CoachCapabilities(enabled=enabled, lifecycle_observation=enabled)


@router.get("/coach/users/{user_id}/settings", response_model=CoachPreferences)
def get_preferences(user_id: str, response: Response, db: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    settings = load_preferences(db, user_id)
    response.headers["ETag"] = f'"{settings.revision}"'
    return settings


@router.put("/coach/users/{user_id}/settings", response_model=CoachPreferences)
def put_preferences(user_id: str, payload: PreferencesSave, request: Request, response: Response, db: Session = Depends(get_session)):
    security.safe_request(request)
    settings = save_preferences(db, user_id, payload)
    response.headers["Cache-Control"] = "no-store"
    response.headers["ETag"] = f'"{settings.revision}"'
    return settings


@router.get("/coach/operator/session")
def session_status(request: Request, response: Response, db: Session = Depends(get_session)):
    security.safe_request(request, mutation=False)
    response.headers["Cache-Control"] = "no-store"
    try:
        security.operator_version()
    except HTTPException:
        return {"authorized": False, "setupAvailable": False}
    try:
        security.authorize(db, request)
        authorized = True
    except HTTPException:
        authorized = False
    return {"authorized": authorized, "setupAvailable": True}


@router.post("/coach/operator/session")
def operator_login(payload: OperatorLogin, request: Request, response: Response, db: Session = Depends(get_session)):
    token = security.login(db, request, payload.password.get_secret_value())
    response.set_cookie(security.COOKIE, token, max_age=security.SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict", path="/api/coach")
    response.headers["Cache-Control"] = "no-store"
    return {"authorized": True}


@router.delete("/coach/operator/session")
def operator_logout(request: Request, response: Response, db: Session = Depends(get_session)):
    security.safe_request(request)
    db.execute(delete(CoachOperatorSession).where(CoachOperatorSession.digest == security.digest(request.cookies.get(security.COOKIE, ""))))
    db.commit()
    response.delete_cookie(security.COOKIE, path="/api/coach", httponly=True, samesite="strict")
    return {"authorized": False}


@router.get("/coach/credentials")
def get_credential(request: Request, response: Response, db: Session = Depends(get_session)):
    security.authorize(db, request)
    response.headers["Cache-Control"] = "no-store"
    return security.credential_status(db)


def rotate_credential(db: Session, expected: int, encrypted: str | None):
    current = db.get(CoachCredential, 1)
    version = current.version if current else 0
    if expected != version:
        raise HTTPException(409, "credential_version_conflict")
    if current is None:
        db.add(CoachCredential(id=1, version=1, ciphertext=encrypted, disabled=encrypted is None, last_check="not_checked"))
    else:
        result = db.execute(update(CoachCredential).where(CoachCredential.id == 1, CoachCredential.version == expected).values(
            version=expected + 1, ciphertext=encrypted, disabled=encrypted is None, last_check="not_checked"))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "credential_version_conflict")
    db.execute(update(CoachLedgerRun).values(generation=CoachLedgerRun.generation + 1, credential_version=version + 1))
    db.execute(update(CoachAttempt).where(CoachAttempt.status == "reserved").values(status="cancelled"))
    db.execute(update(CoachAttempt).where(CoachAttempt.status == "sent").values(status="unsettled"))
    from sqlalchemy.exc import IntegrityError

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "credential_version_conflict") from None


@router.put("/coach/credentials")
def put_credential(payload: CredentialSave, request: Request, db: Session = Depends(get_session)):
    security.authorize(db, request)
    key = payload.key.get_secret_value()
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise HTTPException(422, "invalid_credential")
    encrypted = security.cipher().encrypt(key.encode()).decode()
    rotate_credential(db, payload.expected_version, encrypted)
    return security.credential_status(db)


@router.delete("/coach/credentials")
def delete_credential(payload: CredentialDelete, request: Request, db: Session = Depends(get_session)):
    security.authorize(db, request)
    rotate_credential(db, payload.expected_version, None)
    return security.credential_status(db)


@router.post("/coach/credentials/check")
async def check_credential(request: Request, db: Session = Depends(get_session)):
    security.authorize(db, request)
    key, version = security.read_credential(db)
    db.rollback()  # Never keep a DB transaction over provider await.
    status = await security.metadata_check(key)
    key = ""
    # Rotation during request must not apply the old check result to the new key.
    changed = db.execute(update(CoachCredential).where(CoachCredential.id == 1, CoachCredential.version == version).values(last_check=status))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "credential_version_conflict")
    db.commit()
    return security.credential_status(db)


@router.post("/coach/runs")
def create_run(payload: RunCreate, request: Request, db: Session = Depends(get_session)):
    security.safe_request(request)
    if payload.ledger != "workout":
        security.authorize(db, request)
        db.rollback()
    row, token = ledger.create_run(db, payload.user_id, payload.ledger, payload.cap_usd)
    return {**ledger.snapshot(db, row.id), "runToken": token}


def run_access(request: Request, db: Session, run_id: str, *, mutation: bool = True):
    security.safe_request(request, mutation=mutation)
    token = request.headers.get("X-Coach-Run-Token")
    if not token or len(token) > 128:
        raise HTTPException(404, "run_not_found")
    ledger.get_run(db, run_id, token)
    db.rollback()


@router.get("/coach/runs/{run_id}/usage")
def run_usage(run_id: str, request: Request, response: Response, db: Session = Depends(get_session)):
    run_access(request, db, run_id, mutation=False)
    response.headers["Cache-Control"] = "no-store"
    return ledger.snapshot(db, run_id)


@router.post("/coach/runs/{run_id}/lease")
def run_lease(run_id: str, payload: LeaseRequest, request: Request, db: Session = Depends(get_session)):
    run_access(request, db, run_id)
    return ledger.lease(db, run_id, payload.owner_id, payload.expected_generation)


@router.post("/coach/runs/{run_id}/bind")
def run_bind(run_id: str, payload: RunBind, request: Request, db: Session = Depends(get_session)):
    run_access(request, db, run_id)
    ledger.bind_workout(db, run_id, payload.workout_session_id)
    return ledger.snapshot(db, run_id)


@router.post("/coach/runs/{run_id}/cancel")
def run_cancel(run_id: str, request: Request, db: Session = Depends(get_session)):
    run_access(request, db, run_id)
    ledger.cancel_run(db, run_id)
    return ledger.snapshot(db, run_id)


@router.post("/coach/runs/{run_id}/close")
def run_close(run_id: str, request: Request, db: Session = Depends(get_session)):
    run_access(request, db, run_id)
    ledger.cancel_run(db, run_id, close=True)
    return ledger.snapshot(db, run_id)


@router.post("/coach/runs/{run_id}/recover")
def run_recover(run_id: str, request: Request, db: Session = Depends(get_session)):
    run_access(request, db, run_id)
    ledger.recover(db, run_id)
    return ledger.snapshot(db, run_id)


@router.put("/coach/runs/{run_id}/cap")
def run_cap(run_id: str, payload: CapChange, request: Request, db: Session = Depends(get_session)):
    run_access(request, db, run_id)
    if payload.confirm_increase:
        security.authorize(db, request)
        db.rollback()
    ledger.change_cap(db, run_id, payload.cap_usd, operator_increase=payload.confirm_increase)
    return ledger.snapshot(db, run_id)


@router.post("/coach/runs/{run_id}/jobs")
def job_submit(run_id: str, payload: JobCreate, request: Request, db: Session = Depends(get_session)):
    security.authorize(db, request)
    run_access(request, db, run_id)
    job_id = ledger.submit_job(db, run_id, payload.idempotency_key, payload.fingerprint, list(payload.items))
    return {"jobId": job_id, "dispatchAvailable": False}


@router.get("/coach/runs/{run_id}/jobs/{job_id}")
def job_status(run_id: str, job_id: str, request: Request, db: Session = Depends(get_session)):
    run_access(request, db, run_id, mutation=False)
    job = db.get(CoachJob, job_id)
    if not job or job.run_id != run_id:
        raise HTTPException(404, "job_not_found")
    return {"jobId": job.id, "state": job.state, "completed": len(job.completed), "total": len(job.items), "dispatchAvailable": False}


@router.post("/coach/runs/{run_id}/jobs/{job_id}/action")
def job_action(run_id: str, job_id: str, payload: JobAction, request: Request, db: Session = Depends(get_session)):
    security.authorize(db, request)
    run_access(request, db, run_id)
    job = db.get(CoachJob, job_id)
    if not job or job.run_id != run_id:
        raise HTTPException(404, "job_not_found")
    db.rollback()
    ledger.job_state(db, job_id, {"pause": "paused", "resume": "queued", "cancel": "cancelled"}[payload.action])
    return {"jobId": job_id, "dispatchAvailable": False}


def pack_store() -> packs.PackStore:
    return packs.PackStore(get_settings().coach_pack_root)


@router.get("/coach/packs/{slot}/plan")
def pack_plan(slot: str, request: Request, response: Response):
    security.safe_request(request, mutation=False)
    response.headers["Cache-Control"] = "no-store"
    return packs.plan(pack_store(), slot, get_settings().coach_voice_tts_model)


@router.get("/coach/packs/{slot}/manifest")
def pack_manifest(slot: str, response: Response):
    manifest = pack_store().manifest(slot)
    if manifest is None:
        raise HTTPException(404, "pack_not_prepared")
    response.headers["Cache-Control"] = "no-store"
    return manifest


@router.get("/coach/packs/{slot}/{pack_version}/clips/{clip_id}")
def pack_clip(slot: str, pack_version: str, clip_id: str):
    # Whitelisted lookup only: slot, version and clip come from an immutable manifest, never from the path.
    if not packs.PACK_VERSION_RE.match(pack_version):
        raise HTTPException(404, "clip_not_found")
    store = pack_store()
    manifest = store.manifest(slot, pack_version)
    entry = (manifest or {}).get("clips", {}).get(clip_id)
    if entry is None or not packs.FINGERPRINT_RE.match(str(entry.get("fingerprint"))):
        raise HTTPException(404, "clip_not_found")
    path = store.artifact_path(entry["fingerprint"])
    if not path.is_file():
        raise HTTPException(404, "clip_not_found")
    return FileResponse(path, media_type="audio/wav", headers={
        "Cache-Control": "public, max-age=31536000, immutable", "ETag": f'"{entry["sha256"]}"',
        "X-Content-Type-Options": "nosniff"})


@router.post("/coach/packs/{slot}/jobs")
def pack_job_submit(slot: str, payload: PackJobCreate, request: Request, db: Session = Depends(get_session)):
    security.authorize(db, request)
    run_access(request, db, payload.run_id)
    current = packs.plan(pack_store(), slot, get_settings().coach_voice_tts_model)
    if not current["voiceSelected"]:
        raise HTTPException(409, "voice_not_selected")
    if payload.plan_fingerprint != current["planFingerprint"]:
        raise HTTPException(409, "plan_changed")
    allowed = set(current["missing"]) | set(current["corrupt"])
    if not set(payload.clip_ids) <= allowed:
        raise HTTPException(422, "clip_not_missing")
    job_id = ledger.submit_job(db, payload.run_id, payload.idempotency_key, payload.plan_fingerprint, list(payload.clip_ids))
    # Generation requires verified pricing and a paid voice adapter (E08.1/E08.5); both stay fail-closed.
    return {"jobId": job_id, "clips": len(payload.clip_ids), "dispatchAvailable": False}