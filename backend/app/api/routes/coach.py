"""Coach control plane and live socket. Provider secrets never appear in responses."""

import asyncio
import contextlib
import json
import time
from collections.abc import Callable

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, get_session_factory
from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachCredential, CoachJob, CoachLedgerRun, CoachOperatorSession
from app.schemas.coach import CoachCapabilities
from app.schemas.coach_control import (
    CapChange,
    CoachPreferences,
    CredentialDelete,
    CredentialProvider,
    CredentialSave,
    JobAction,
    JobCreate,
    LeaseRequest,
    LiveConfigure,
    OperatorLogin,
    PackJobCreate,
    PackPrepare,
    PreferencesSave,
    RunBind,
    RunCreate,
)
from app.services.coach import episode, history, journal, ledger, live, pack_generation, packs, scenario, security
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
    if not settings.memory_enabled:
        journal.forget_previews(db, user_id)  # VD.6: spoken texts leave the journal with the memory.
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
def get_credential(request: Request, response: Response, provider: CredentialProvider = "openai",
                   db: Session = Depends(get_session)):
    security.authorize(db, request)
    response.headers["Cache-Control"] = "no-store"
    return security.credential_status(db, provider)


def rotate_credential(db: Session, expected: int, encrypted: str | None, provider: CredentialProvider = "openai"):
    row_id = security.CREDENTIAL_IDS[provider]
    current = db.get(CoachCredential, row_id)
    version = current.version if current else 0
    if expected != version:
        raise HTTPException(409, "credential_version_conflict")
    if current is None:
        db.add(CoachCredential(id=row_id, version=1, ciphertext=encrypted, disabled=encrypted is None, last_check="not_checked"))
    else:
        result = db.execute(update(CoachCredential).where(CoachCredential.id == row_id, CoachCredential.version == expected).values(
            version=expected + 1, ciphertext=encrypted, disabled=encrypted is None, last_check="not_checked"))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "credential_version_conflict")
    if provider == "openai":
        # Runs pin the OpenAI key version; a Fish rotation only affects voice dispatch (ledger checks its row).
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
def put_credential(payload: CredentialSave, request: Request, provider: CredentialProvider = "openai",
                   db: Session = Depends(get_session)):
    security.authorize(db, request)
    key = payload.key.get_secret_value()
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise HTTPException(422, "invalid_credential")
    encrypted = security.cipher().encrypt(key.encode()).decode()
    rotate_credential(db, payload.expected_version, encrypted, provider)
    return security.credential_status(db, provider)


@router.delete("/coach/credentials")
def delete_credential(payload: CredentialDelete, request: Request, provider: CredentialProvider = "openai",
                      db: Session = Depends(get_session)):
    security.authorize(db, request)
    rotate_credential(db, payload.expected_version, None, provider)
    return security.credential_status(db, provider)


@router.post("/coach/credentials/check")
async def check_credential(request: Request, provider: CredentialProvider = "openai", db: Session = Depends(get_session)):
    security.authorize(db, request)
    key, version = security.read_credential(db, provider)
    db.rollback()  # Never keep a DB transaction over provider await.
    status = await security.metadata_check(key, provider)
    key = ""
    # Rotation during request must not apply the old check result to the new key.
    changed = db.execute(update(CoachCredential).where(CoachCredential.id == security.CREDENTIAL_IDS[provider],
                                                       CoachCredential.version == version).values(last_check=status))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "credential_version_conflict")
    db.commit()
    return security.credential_status(db, provider)


@router.get("/coach/usage/today")
def daily_usage(request: Request, response: Response, since: float | None = None, db: Session = Depends(get_session)):
    """Header counter: paid requests and their cost since the client's local midnight (default: UTC midnight)."""
    security.safe_request(request, mutation=False)
    now = time.time()
    if since is None:
        since = now - now % 86_400
    elif not now - 2 * 86_400 <= since <= now + 60:
        raise HTTPException(422, "invalid_since")
    response.headers["Cache-Control"] = "no-store"
    return ledger.daily_usage(db, since)


JOURNAL_PERIODS = {"today", "7d", "run"}


def journal_since(db: Session, period: str, since: float | None, run_id: str | None, user_id: str) -> float:
    """Local midnight from the client for «today»; a run starts at its creation; 7 days at most."""
    now = time.time()
    if period not in JOURNAL_PERIODS:
        raise HTTPException(422, "invalid_period")
    if period == "run":
        if not run_id:
            raise HTTPException(422, "run_required")
        run = db.get(CoachLedgerRun, run_id)
        if run is None or run.user_id != user_id:
            raise HTTPException(404, "run_not_found")
        return run.created_at - 1
    if period == "7d":
        return now - 7 * 86_400
    if since is None:
        return now - now % 86_400
    if not now - 2 * 86_400 <= since <= now + 60:
        raise HTTPException(422, "invalid_since")
    return since


@router.get("/coach/requests")
def request_journal(request: Request, response: Response, user_id: str = Query(alias="userId", max_length=120),
                    period: str = "today", since: float | None = None, run_id: str | None = Query(None, alias="runId",
                                                                                                  max_length=64),
                    status: str = "all", kind: str = "all", cursor: str | None = Query(None, max_length=120),
                    limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_session)):
    """VD: the user's Coach requests, newest first, with totals for the selected period/kind."""
    security.safe_request(request, mutation=False)
    load_preferences(db, user_id)
    if status not in {"all", *journal.STATUSES} or kind not in {"all", *journal.KINDS}:
        raise HTTPException(422, "invalid_filter")
    response.headers["Cache-Control"] = "no-store"
    return journal.requests(db, user_id=user_id, since=journal_since(db, period, since, run_id, user_id),
                            run_id=run_id if period == "run" else None, status=status, kind_filter=kind,
                            cursor=cursor, limit=limit)


@router.get("/coach/requests/{attempt_id}")
def request_card(attempt_id: str, request: Request, response: Response,
                 user_id: str = Query(alias="userId", max_length=120), db: Session = Depends(get_session)):
    security.safe_request(request, mutation=False)
    found = journal.request_detail(db, user_id, attempt_id[:64])
    if found is None:
        raise HTTPException(404, "request_not_found")
    response.headers["Cache-Control"] = "no-store"
    return found


@router.get("/coach/usage/summary")
def usage_summary(request: Request, response: Response, user_id: str = Query(alias="userId", max_length=120),
                  period: str = "today", since: float | None = None,
                  run_id: str | None = Query(None, alias="runId", max_length=64), db: Session = Depends(get_session)):
    security.safe_request(request, mutation=False)
    load_preferences(db, user_id)
    response.headers["Cache-Control"] = "no-store"
    return journal.usage_summary(db, user_id=user_id, since=journal_since(db, period, since, run_id, user_id),
                                 run_id=run_id)


@router.get("/coach/workouts/{workout_id}/episode")
def workout_episode(workout_id: int, request: Request, response: Response,
                    user_id: str = Query(alias="userId", max_length=120), db: Session = Depends(get_session)):
    """V11: the story recap of a finished workout; a local template from saved facts until one is written."""
    security.safe_request(request, mutation=False)
    load_preferences(db, user_id)
    response.headers["Cache-Control"] = "no-store"
    found = episode.load(db, workout_id, user_id)
    if found is not None:
        return found
    try:
        package = history.workout_summary(db, user_id, workout_id, scope_epoch=0, valid_until_ms=float("inf"))
    except history.HistoryError as error:
        raise HTTPException(404, "episode_unavailable") from error
    run = db.scalar(select(CoachLedgerRun).where(CoachLedgerRun.workout_id == workout_id, CoachLedgerRun.user_id == user_id))
    story = scenario.load(db, run.id, user_id) if run is not None else None
    values = {f.id: f.value for f in package.facts}
    source = episode.EpisodeInput(tuple((f.id, f.claim, tuple(f.numbers)) for f in package.facts),
                                  episode.achievements(fact_ids=set(values), fact_values=values, records=0, steady_sets=0,
                                                       boss_defeated=False),
                                  story[0].get("title") if story else None, story[1].get("finale") if story else None)
    return {**episode.local(source), "achievements": [{"id": a, "label": episode.ACHIEVEMENTS[a]} for a in source.achievements],
            "source": "local"}


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


def get_pack_provider() -> pack_generation.ProviderFactory:
    return pack_generation.provider


@router.post("/coach/packs/{slot}/prepare")
async def prepare_pack(slot: str, payload: PackPrepare, request: Request, background: BackgroundTasks,
                       db: Session = Depends(get_session), sessions: Callable[[], Session] = Depends(get_session_factory),
                       factory: pack_generation.ProviderFactory = Depends(get_pack_provider)):
    security.authorize(db, request)
    prefs = load_preferences(db, payload.user_id)
    if ledger.micros(payload.cap_usd) > min(10_000_000, ledger.micros(prefs.budget_usd)):
        raise HTTPException(409, "cap_exceeds_user_budget")
    db.rollback()
    store, model = pack_store(), packs.pack_model(slot)
    current = packs.plan(store, slot, model)
    # Counts 1..30 and all lifecycle/safety cues are required; optional counts can be added separately.
    items = [row["clipId"] for row in current["clips"] if row["required"] and row["status"] != "ready"]
    if not items:
        store.publish(slot, packs.provider_voice(slot), model)
        return {"state": "completed"}
    if slot in pack_generation.active_slots or len(pack_generation.active_slots) >= 2:
        raise HTTPException(409, "pack_generation_busy")
    pack_generation.require_job_schema(sessions)
    selected = factory(sessions, slot)  # Validate paid switches, verified prices and vault keys before creating a run.
    run_id = None
    try:
        run, token = ledger.create_run(db, payload.user_id, "pack", payload.cap_usd)
        run_id = run.id
        db.rollback()
        owner = f"pack-{run_id}"
        generation = ledger.lease(db, run_id, owner, 0)["generation"]
        job_id = ledger.submit_job(db, run_id, "prepare", current["planFingerprint"], items)
        ledger.job_state(db, job_id, "queued")
        pack_generation.active_slots.add(slot)
        background.add_task(pack_generation.generate, sessions, selected, store, slot, run_id, job_id, owner, generation)
        return {"state": "queued", "runId": run_id, "runToken": token, "jobId": job_id, "total": len(items)}
    except BaseException:
        await selected.close()
        if run_id:
            db.rollback()
            ledger.cancel_run(db, run_id, close=True)
        raise


@router.get("/coach/packs/{slot}/plan")
def pack_plan(slot: str, request: Request, response: Response):
    security.safe_request(request, mutation=False)
    response.headers["Cache-Control"] = "no-store"
    return packs.plan(pack_store(), slot, packs.pack_model(slot))


@router.get("/coach/packs/{slot}/manifest")
def pack_manifest(slot: str, response: Response):
    manifest = pack_store().manifest(slot)
    if manifest is None or manifest.get("model") != packs.pack_model(slot) or manifest.get("voice") != packs.provider_voice(slot):
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
    current = packs.plan(pack_store(), slot, packs.pack_model(slot))
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


@router.delete("/coach/users/{user_id}/memory")
def delete_memory(user_id: str, request: Request, db: Session = Depends(get_session)):
    """Coach memory is session-only (no long-term store yet): clearing resets every live socket of this user."""
    security.safe_request(request)
    load_preferences(db, user_id)  # 404 for unknown users
    db.rollback()
    journal.forget_previews(db, user_id)
    return {"cleared": live.forget_user(user_id), "persistentMemory": False}


# ---------- E10 live socket ----------

LIVE_MESSAGE_LIMIT = 32_768
LIVE_RATE_PER_S = 40
LEASE_RENEW_S = 5.0


def get_live_factory() -> live.PipelineFactory:
    return live.default_pipeline


@router.websocket("/coach/runs/{run_id}/live")
async def coach_live(websocket: WebSocket, run_id: str, sessions: Callable[[], Session] = Depends(get_session_factory),
                     factory: live.PipelineFactory = Depends(get_live_factory)):
    try:
        security.safe_request(websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    lock = asyncio.Lock()

    async def send_json(payload: dict) -> None:
        async with lock:
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))

    async def send_bytes(data: bytes) -> None:
        async with lock:
            await websocket.send_bytes(data)

    async def refuse(reason: str) -> None:
        with contextlib.suppress(Exception):
            await send_json({"type": "error", "reason": reason})
            await websocket.close(code=1008)

    try:
        first = await asyncio.wait_for(websocket.receive_text(), 5)
        if len(first) > 1024:
            raise ValueError("too_large")
        config = LiveConfigure.model_validate_json(first)
    except (TimeoutError, ValidationError, ValueError, KeyError, WebSocketDisconnect):
        await refuse("configure_required")
        return
    if not get_settings().coach_enabled:
        # Master switch: paid flags default on, so a disabled coach must never open a paid pipeline.
        await refuse("coach_disabled")
        return
    try:
        with sessions() as db:
            run = ledger.get_run(db, run_id, config.run_token)
            # workout: real training; test: capped sound-test wizard/CI with synthetic adapters.
            if run.ledger not in {"workout", "test"} or run.state != "active":
                raise HTTPException(409, "run_not_live")
            user_id, current = run.user_id, run.generation
            db.rollback()
            generation = ledger.lease(db, run_id, config.owner_id, current)["generation"]
            prefs = load_preferences(db, user_id)
    except HTTPException as error:
        await refuse(str(error.detail))
        return
    if (not prefs.enabled or prefs.mode == "local" or prefs.consent_version is None
            or prefs.network_consent_version != 1):
        await refuse("local_mode")
        return
    pipeline = await factory(sessions, prefs)
    coach = live.LiveCoach(sessions, run_id=run_id, owner=config.owner_id, generation=generation, user_id=user_id,
                           scope_run_id=config.runtime_run_id or run_id,
                           settings=prefs, author=pipeline.author, voice=pipeline.voice,
                           send_json=send_json, send_bytes=send_bytes)
    live.register(coach)

    def lease() -> None:
        with sessions() as db:
            ledger.lease(db, run_id, config.owner_id, generation)

    async def renew() -> None:
        while True:
            await asyncio.sleep(LEASE_RENEW_S)
            try:
                # a locked SQLite file waits up to 5 s: never on the event loop
                await asyncio.to_thread(lease)
            except HTTPException as error:
                # Settings change, takeover or closed run: this socket's generation is over; the client reconnects.
                await refuse(str(error.detail))
                return

    renewal = asyncio.create_task(renew())
    try:
        await send_json({"type": "configured", "generation": generation, "mode": prefs.mode,
                         "voiceId": prefs.voice_profile, "voiceModel": prefs.voice_model,
                         "text": pipeline.author is not None,
                         "voice": pipeline.voice is not None, "degraded": pipeline.reason is not None,
                         "degradedReason": pipeline.reason})
        await coach.announce()
        window, count = time.monotonic(), 0
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            now = time.monotonic()
            if now - window >= 1:
                window, count = now, 0
            count += 1
            if count > LIVE_RATE_PER_S:
                await refuse("rate_limited")
                break
            text = message.get("text")
            try:
                if text is None or len(text) > LIVE_MESSAGE_LIMIT:
                    raise ValueError("invalid_message")
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError("invalid_message")
            except ValueError:
                await send_json({"type": "error", "reason": "invalid_message"})
                continue
            await coach.handle(data)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        renewal.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await renewal  # never let a renewal step race the teardown below
        live.unregister(coach)
        try:
            await coach.close()
        finally:
            await pipeline.close()