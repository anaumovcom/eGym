"""SQLite serialized durable reservations. Production paid dispatch remains unavailable."""

import secrets
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.analytics import WorkoutSession
from app.models.coach import CoachAttempt, CoachCredential, CoachJob, CoachLedgerRun, CoachReceipt, CoachResponseReceipt
from app.schemas.coach_control import PartialUsage, Pricing, ReportedUsage, UsageBounds
from app.services.coach.preferences import load_preferences
from app.services.coach.security import digest


def micros(value: str) -> int:
    amount = Decimal(value)
    if not amount.is_finite() or amount <= 0 or amount > 1000 or amount * 1_000_000 != int(amount * 1_000_000):
        raise HTTPException(422, "invalid_cap")
    return int(amount * 1_000_000)


@contextmanager
def atomic(db: Session):
    if db.get_bind().dialect.name != "sqlite":
        raise HTTPException(503, "coach_ledger_requires_sqlite")
    # DB write lock, not process mutex: independent workers/connections serialize too.
    db.execute(text("BEGIN IMMEDIATE"))
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def create_run(db: Session, user_id: str, ledger: str, cap_usd: str) -> tuple[CoachLedgerRun, str]:
    with atomic(db):
        prefs = load_preferences(db, user_id)
        cap = micros(cap_usd)
        if ledger == "workout" and cap > micros(prefs.budget_usd):
            raise HTTPException(409, "cap_exceeds_user_budget")
        if db.scalar(select(func.count()).select_from(CoachLedgerRun).where(CoachLedgerRun.state == "active")) >= 64:
            raise HTTPException(429, "active_runs_full")
        credential = db.get(CoachCredential, 1)
        token = secrets.token_urlsafe(32)
        row = CoachLedgerRun(id=secrets.token_hex(16), user_id=user_id, access_digest=digest(token), ledger=ledger,
                             cap_micros=cap, pricing={}, generation=0, created_at=time.time(),
                             credential_version=credential.version if credential else 0)
        db.add(row)
    return row, token


def get_run(db: Session, run_id: str, token: str | None = None) -> CoachLedgerRun:
    row = db.get(CoachLedgerRun, run_id, populate_existing=True)
    if row is None or (token is not None and not secrets.compare_digest(row.access_digest, digest(token))):
        raise HTTPException(404, "run_not_found")
    return row


def lease(db: Session, run_id: str, owner: str, generation: int) -> dict:
    with atomic(db):
        row = get_run(db, run_id)
        now = time.time()
        if row.state != "active" or row.generation != generation:
            raise HTTPException(409, "stale_run")
        if row.owner != owner and row.lease_until > now:
            raise HTTPException(409, "owner_mismatch")
        if row.owner != owner or row.lease_until <= now:
            row.generation += 1
            for attempt in db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == run_id)):
                if attempt.status == "reserved":
                    attempt.status = "cancelled"
                elif attempt.status == "sent":
                    attempt.status = "unsettled"
        row.owner, row.lease_until = owner, now + 15
        result = {"generation": row.generation, "leaseUntil": row.lease_until}
    return result


def bind_workout(db: Session, run_id: str, workout_id: int) -> None:
    with atomic(db):
        row = get_run(db, run_id)
        workout = db.get(WorkoutSession, workout_id)
        if row.ledger != "workout" or not workout or workout.user_id != row.user_id:
            raise HTTPException(409, "workout_owner_mismatch")
        if row.workout_id not in {None, workout_id} or db.scalar(select(CoachLedgerRun.id).where(
                CoachLedgerRun.workout_id == workout_id, CoachLedgerRun.id != run_id)):
            raise HTTPException(409, "workout_already_bound")
        row.workout_id = workout_id


def cancel_run(db: Session, run_id: str, *, close: bool = False) -> None:
    with atomic(db):
        row = get_run(db, run_id)
        row.generation += 1
        if close:
            row.state = "closed"
        for attempt in db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == run_id)):
            if attempt.status == "reserved":
                attempt.status = "cancelled"
            elif attempt.status == "sent":
                attempt.status = "unsettled"


def committed(attempt: CoachAttempt) -> int:
    if attempt.status == "cancelled":
        return 0
    if attempt.status == "settled":
        return attempt.cost_micros or 0
    return max(attempt.reserve_micros, attempt.cost_micros or 0)


def snapshot(db: Session, run_id: str) -> dict:
    run = get_run(db, run_id)
    attempts = list(db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == run_id)))
    settled = sum(a.cost_micros or 0 for a in attempts if a.status == "settled")
    pending = sum(committed(a) for a in attempts if a.status not in {"settled", "cancelled"})
    return {"runId": run.id, "userId": run.user_id, "ledger": run.ledger, "state": run.state,
            "generation": run.generation, "workoutSessionId": run.workout_id,
            "capMicros": run.cap_micros, "settledMicros": settled, "pendingMicros": pending,
            "availableMicros": max(0, run.cap_micros - settled - pending), "requests": sum(a.sent_at is not None for a in attempts),
            "limitKind": "strict-reservations" if all(a.pricing.get("verified") and a.pricing.get("enforceableBounds") for a in attempts) and attempts else "target-no-paid-adapter",
            "attempts": [{"attemptId": a.id, "stage": a.stage, "model": a.model, "status": a.status,
                          "completeness": a.completeness, "usage": a.usage or None, "costMicros": a.cost_micros,
                          "reserveMicros": a.reserve_micros, "pricingVersion": a.pricing["version"]} for a in attempts]}


def cost(pricing: Pricing, usage: ReportedUsage) -> int:
    total = ((usage.input_tokens - usage.cached_input_tokens) * pricing.input_rate
             + usage.cached_input_tokens * pricing.cached_rate + usage.output_tokens * pricing.output_rate
             + (usage.audio_input_tokens - usage.cached_audio_input_tokens) * pricing.audio_input_rate
             + usage.cached_audio_input_tokens * pricing.audio_cached_rate + usage.audio_output_tokens * pricing.audio_output_rate)
    return (total + 999_999) // 1_000_000


def reserve(db: Session, run_id: str, owner: str, generation: int, opportunity: str, stage: str,
            pricing: Pricing, bounds: UsageBounds, *, retry: int = 0) -> str:
    if stage not in {"text", "voice"} or retry not in {0, 1} or not opportunity or len(opportunity) > 1024:
        raise HTTPException(422, "invalid_attempt")
    if not pricing.verified or not pricing.enforceable_bounds:
        raise HTTPException(409, "strict_cap_unprovable")
    with atomic(db):
        row = get_run(db, run_id)
        if row.state != "active" or row.owner != owner or row.generation != generation or row.lease_until <= time.time():
            raise HTTPException(409, "owner_mismatch")
        key = digest(opportunity)
        attempts = list(db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == run_id)))
        same = [a for a in attempts if a.opportunity == key and a.stage == stage]
        if any(a.ordinal == retry for a in same):
            raise HTTPException(409, "duplicate_attempt")
        if retry and (not same or any(a.status in {"reserved", "sent"} for a in same)):
            raise HTTPException(409, "retry_not_eligible")
        if any(a.status in {"reserved", "sent"} for a in attempts):
            raise HTTPException(409, "pipeline_busy")
        if len(attempts) >= 1024:
            raise HTTPException(429, "attempts_full")
        receipt = db.scalar(select(CoachReceipt).where(CoachReceipt.run_id == run_id, CoachReceipt.canonical == key))
        if receipt is None:
            db.add(CoachReceipt(id=secrets.token_hex(16), run_id=run_id, canonical=key))
        amount = cost(pricing, ReportedUsage(**bounds.model_dump(exclude={"schema_version"})))
        if sum(committed(a) for a in attempts) + amount > row.cap_micros:
            raise HTTPException(409, "budget")
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        all_attempts = list(db.scalars(select(CoachAttempt).where(
            (func.coalesce(CoachAttempt.sent_at, CoachAttempt.created_at) >= month_start) | CoachAttempt.status.in_(["reserved", "sent", "unsettled"]))))
        cfg = get_settings()
        if sum(committed(a) for a in all_attempts) + amount > micros(cfg.coach_operator_monthly_usd):
            raise HTTPException(409, "operator_budget")
        if sum(committed(a) for a in all_attempts if (a.sent_at or a.created_at) >= day_start or a.status in {"reserved", "sent", "unsettled"}) + amount > micros(cfg.coach_operator_daily_usd):
            raise HTTPException(409, "operator_budget")
        attempt_id = secrets.token_hex(16)
        db.add(CoachAttempt(id=attempt_id, run_id=run_id, opportunity=key, stage=stage, ordinal=retry,
                            model=pricing.model, status="reserved", reserve_micros=amount, pricing=pricing.model_dump(by_alias=True),
                            bounds=bounds.model_dump(by_alias=True), generation=generation, credential_version=row.credential_version,
                            created_at=time.time()))
        row.pricing = {**row.pricing, pricing.model: pricing.model_dump(by_alias=True)}
    return attempt_id


def dispatch(db: Session, attempt_id: str, owner: str, *, test_only: bool = False, adapter: str | None = None) -> None:
    with atomic(db):
        attempt = db.get(CoachAttempt, attempt_id)
        if attempt is None:
            raise HTTPException(404, "attempt_not_found")
        row = get_run(db, attempt.run_id)
        if attempt.status != "reserved" or row.state != "active" or row.owner != owner or row.generation != attempt.generation or row.lease_until <= time.time():
            raise HTTPException(409, "stale_attempt")
        if not test_only:
            # Real dispatch: opt-in text author or opt-in voice adapters only; everything else stays fail-closed.
            cfg = get_settings()
            credential = db.get(CoachCredential, 1)
            voice_models = {"realtime": cfg.coach_voice_realtime_model, "tts": cfg.coach_voice_tts_model}
            text_ok = (adapter == "luna-text" and attempt.stage == "text" and cfg.coach_paid_text_enabled
                       and cfg.coach_text_pricing_verified and attempt.model == cfg.coach_text_model
                       and row.ledger in {"workout", "test"})
            kind = (adapter or "").removeprefix("pack-")
            voice_ok = (attempt.stage == "voice" and cfg.coach_paid_voice_enabled and cfg.coach_voice_pricing_verified
                        and kind in voice_models and attempt.model == voice_models[kind]
                        and row.ledger in ({"pack", "test"} if adapter.startswith("pack-") else {"workout", "test"}))
            if (not (text_ok or voice_ok) or not attempt.pricing.get("verified")
                    or credential is None or credential.disabled or not credential.ciphertext or credential.version != attempt.credential_version):
                raise HTTPException(503, "paid_adapter_unavailable")
            attempt.status, attempt.sent_at = "sent", time.time()
            return
        if row.ledger != "test":
            raise HTTPException(409, "synthetic_dispatch_requires_test_ledger")
        attempt.status, attempt.sent_at = "sent", time.time()


def mark_unsettled(db: Session, attempt_id: str) -> None:
    with atomic(db):
        row = db.get(CoachAttempt, attempt_id)
        if row and row.status == "sent":
            row.status = "unsettled"


def cancel_reserved(db: Session, attempt_id: str) -> None:
    # Only never-dispatched reservations are released; sent liabilities stay.
    with atomic(db):
        row = db.get(CoachAttempt, attempt_id)
        if row and row.status == "reserved":
            row.status = "cancelled"


def lower_cost(pricing: Pricing, value: dict) -> int:
    partial = PartialUsage.model_validate(value)
    # For unknown cached totals choose the cheapest possible known input component.
    full = ReportedUsage(input_tokens=partial.input_tokens or 0, output_tokens=partial.output_tokens or 0,
                         audio_input_tokens=partial.audio_input_tokens or 0, audio_output_tokens=partial.audio_output_tokens or 0,
                         cached_input_tokens=(partial.input_tokens or 0) if partial.cached_input_tokens is None else min(partial.cached_input_tokens, partial.input_tokens or 0),
                         cached_audio_input_tokens=(partial.audio_input_tokens or 0) if partial.cached_audio_input_tokens is None else min(partial.cached_audio_input_tokens, partial.audio_input_tokens or 0))
    return cost(pricing, full)


def settle(db: Session, attempt_id: str, response_id: str, usage: ReportedUsage | PartialUsage | None, *, terminal: bool,
           basis: str = "response", complete: bool = True) -> None:
    if not response_id or len(response_id) > 120 or basis not in {"response", "aggregate"}:
        raise HTTPException(422, "invalid_usage_receipt")
    with atomic(db):
        attempt = db.get(CoachAttempt, attempt_id)
        if not attempt or attempt.sent_at is None:
            raise HTTPException(409, "attempt_not_sent")
        exists = db.scalar(select(CoachResponseReceipt).where(CoachResponseReceipt.attempt_id == attempt_id, CoachResponseReceipt.response_id == response_id))
        if exists is not None:
            # Terminal reconciliation may enrich an earlier unavailable/partial receipt.
            if exists.usage["complete"] and exists.usage["value"] is not None:
                terminal_upgrade = terminal and complete and not exists.usage["terminal"] and isinstance(usage, ReportedUsage) and exists.usage["value"] == usage.model_dump(by_alias=True)
                if not terminal_upgrade:
                    return
            if usage is None or not complete or isinstance(usage, PartialUsage):
                return
            if exists.usage["basis"] != basis:
                raise HTTPException(409, "usage_basis_conflict")
        if exists is None and db.scalar(select(func.count()).select_from(CoachResponseReceipt).where(CoachResponseReceipt.attempt_id == attempt_id)) >= 256:
            raise HTTPException(429, "usage_receipts_full")
        record = {"basis": basis, "complete": complete and isinstance(usage, ReportedUsage), "terminal": terminal, "value": usage.model_dump(by_alias=True) if usage else None}
        if exists:
            exists.usage = record
        else:
            db.add(CoachResponseReceipt(id=secrets.token_hex(16), attempt_id=attempt_id, response_id=response_id, usage=record))
        db.flush()
        receipts = list(db.scalars(select(CoachResponseReceipt).where(CoachResponseReceipt.attempt_id == attempt_id)))
        # Alternative sources are never added together. max(cost aggregate, response sum).
        price = Pricing.model_validate(attempt.pricing)
        response_cost = sum(lower_cost(price, r.usage["value"]) for r in receipts if r.usage["value"] and r.usage["basis"] == "response")
        aggregate_cost = max((lower_cost(price, r.usage["value"]) for r in receipts if r.usage["value"] and r.usage["basis"] == "aggregate"), default=0)
        attempt.cost_micros = max(response_cost, aggregate_cost) if any(r.usage["value"] for r in receipts) else None
        responses = [r for r in receipts if r.usage["basis"] == "response"]
        aggregates = [r for r in receipts if r.usage["basis"] == "aggregate"]
        authority = max(aggregates, key=lambda r: lower_cost(price, r.usage["value"]) if r.usage["value"] else -1) if aggregate_cost >= response_cost and aggregates else None
        selected = [authority] if authority else responses
        values = [PartialUsage.model_validate(r.usage["value"]) for r in selected if r.usage["value"]]
        normalized = {field: sum(getattr(v, field) for v in values) if all(getattr(v, field) is not None for v in values) and len(values) == len(selected) else None for field in PartialUsage.model_fields if field != "schema_version"} if values else {}
        attempt.usage = normalized
        limits = UsageBounds.model_validate(attempt.bounds)
        overflow = any((normalized.get(field) or 0) > getattr(limits, field) for field in UsageBounds.model_fields if field != "schema_version")
        if terminal and complete and isinstance(usage, ReportedUsage) and all(r.usage["complete"] and r.usage["value"] for r in selected) and not overflow:
            attempt.status, attempt.completeness = "settled", "complete"
        elif attempt.status != "settled":
            attempt.status, attempt.completeness = "unsettled", "partial" if values else "unavailable"
        if overflow or (attempt.cost_micros or 0) > attempt.reserve_micros:
            run = get_run(db, attempt.run_id)
            run.state, run.generation = "blocked", run.generation + 1
            attempt.status, attempt.completeness = "unsettled", "partial"


def recover(db: Session, run_id: str) -> None:
    # Explicit lease-expired recovery, never erase sent liabilities or receipts.
    with atomic(db):
        row = get_run(db, run_id)
        if row.lease_until > time.time():
            raise HTTPException(409, "owner_still_active")
        row.generation += 1
        row.owner, row.lease_until = None, 0
        for attempt in db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == run_id)):
            if attempt.status == "reserved":
                attempt.status = "cancelled"
            elif attempt.status == "sent":
                attempt.status = "unsettled"


def change_cap(db: Session, run_id: str, value: str, *, operator_increase: bool = False) -> None:
    with atomic(db):
        row = get_run(db, run_id)
        amount = micros(value)
        if amount > row.cap_micros and not operator_increase:
            raise HTTPException(403, "operator_confirmation_required")
        if row.ledger == "workout" and amount > micros(load_preferences(db, row.user_id).budget_usd):
            raise HTTPException(409, "cap_exceeds_user_budget")
        row.cap_micros, row.generation = amount, row.generation + 1
        for attempt in db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == run_id)):
            if attempt.status == "reserved":
                attempt.status = "cancelled"
            elif attempt.status == "sent":
                attempt.status = "unsettled"


def submit_job(db: Session, run_id: str, key: str, fingerprint: str, items: list[str]) -> str:
    if not 1 <= len(key) <= 120 or len(fingerprint) != 64 or not 1 <= len(items) <= 256 or len(set(items)) != len(items) or any(not item or len(item) > 120 for item in items):
        raise HTTPException(422, "invalid_job")
    with atomic(db):
        run = get_run(db, run_id)
        if run.ledger not in {"test", "pack"} or run.state != "active":
            raise HTTPException(409, "job_ledger_required")
        existing = db.scalar(select(CoachJob).where(CoachJob.run_id == run_id, CoachJob.idempotency_key == key))
        if existing:
            if existing.fingerprint != fingerprint or existing.items != items:
                raise HTTPException(409, "idempotency_conflict")
            return existing.id
        if db.scalar(select(func.count()).select_from(CoachJob).where(CoachJob.run_id == run_id)) >= 32:
            raise HTTPException(429, "jobs_full")
        job_id = secrets.token_hex(16)
        db.add(CoachJob(id=job_id, run_id=run_id, idempotency_key=key, fingerprint=fingerprint, items=items, completed=[]))
    return job_id


def job_state(db: Session, job_id: str, state: str) -> None:
    if state not in {"paused", "queued", "cancelled"}:
        raise HTTPException(422, "invalid_job_state")
    with atomic(db):
        job = db.get(CoachJob, job_id)
        if job is None or job.state in {"completed", "cancelled", "failed"}:
            raise HTTPException(409, "job_closed")
        job.state = state
        if state == "cancelled":
            get_run(db, job.run_id).generation += 1
            for attempt in db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == job.run_id)):
                if attempt.status == "reserved":
                    attempt.status = "cancelled"
                elif attempt.status == "sent":
                    attempt.status = "unsettled"


def alias_receipt(db: Session, run_id: str, opportunity: str, backend_set_id: int) -> None:
    from app.models.analytics import ExerciseSession, SetResult

    with atomic(db):
        run = get_run(db, run_id)
        saved = db.get(SetResult, backend_set_id)
        exercise = db.get(ExerciseSession, saved.exercise_session_id) if saved else None
        if not exercise or exercise.user_id != run.user_id:
            raise HTTPException(409, "alias_owner_mismatch")
        row = db.scalar(select(CoachReceipt).where(CoachReceipt.run_id == run_id, CoachReceipt.canonical == digest(opportunity)))
        duplicate = db.scalar(select(CoachReceipt).where(CoachReceipt.run_id == run_id, CoachReceipt.backend_set_id == backend_set_id))
        if not row or row.backend_set_id not in {None, backend_set_id} or (duplicate and duplicate.id != row.id):
            raise HTTPException(409, "alias_conflict")
        row.backend_set_id = backend_set_id