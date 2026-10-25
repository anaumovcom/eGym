"""VD request journal: bounded annotations on ledger attempts, recorded refusals and read models for the panel.

The ledger stays the single source of truth for money. The journal only adds *why* and *how it ended*:
trigger/task, outcome, a short sanitized error, timings, and (with conversation memory on) the spoken text.
Never stored: API keys, request headers or bodies, prompts, raw provider responses.
"""

import math
import re
import secrets
import statistics
import time
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachLedgerRun
from app.services.coach.security import digest

TEXT_LIMITS = {"trigger_id": 8, "task": 40, "exercise_label": 80, "outcome": 24, "error_code": 64,
               "error_detail": 300, "text_preview": 300}
NUMBER_LIMITS = {"set_ordinal": (0, 1000), "http_status": (100, 599), "first_byte_ms": (0, 600_000),
                 "duration_ms": (0, 600_000), "finished_at": (0, 10**11), "markup_bytes": (0, 100_000),
                 "text_bytes": (0, 100_000)}
OUTCOMES = frozenset({"speech", "silence", "rejected", "error", "cancelled", "stale", "spoken", "refused"})
STATUSES = ("ok", "error", "cancelled", "refused", "pending")
KINDS = ("text", "voice", "prebuild", "pack", "scenario", "summary", "episode", "judge")
MAX_REFUSALS_PER_RUN = 512
PREVIEW_TTL_S = 86_400
DETAIL_TTL_S = 30 * 86_400
PAGE_LIMIT = 200
_CONTROL = re.compile(r"[\x00-\x1f\x7f  ]")
# Anything that looks like a credential, bearer token, org/project id, e-mail or long opaque token.
_SECRET = re.compile(r"(?i)(sk-[a-z0-9_\-]{6,}|bearer\s+\S+|(?:org|proj)-[a-z0-9_\-]{4,}|[\w.+-]+@[\w-]+\.[\w.]+"
                     r"|[a-z0-9_\-]{28,}|key[=:]\s*\S+)")


def sanitize(value: object, limit: int = 300) -> str | None:
    """Short, single-line, credential-free text; None if nothing meaningful remains."""
    if not isinstance(value, str):
        return None
    text = _CONTROL.sub(" ", unicodedata.normalize("NFKC", value))
    text = _SECRET.sub("[скрыто]", text)
    text = " ".join(text.split())
    return text[:limit] or None


def clean_fields(fields: dict) -> dict:
    """Drop unknown or out-of-bounds fields instead of failing the paid path that reports them."""
    clean: dict = {}
    for name, value in fields.items():
        if value is None:
            continue
        if name in TEXT_LIMITS:
            text = sanitize(value, TEXT_LIMITS[name])
            if text is not None and (name != "outcome" or text in OUTCOMES):
                clean[name] = text
        elif name in NUMBER_LIMITS and isinstance(value, int | float) and not isinstance(value, bool):
            low, high = NUMBER_LIMITS[name]
            if math.isfinite(value) and low <= value <= high:
                clean[name] = int(value) if name in {"set_ordinal", "http_status", "markup_bytes", "text_bytes"} else round(
                    float(value), 1)
    return clean


def annotate(db: Session, attempt_id: str | None, **fields) -> None:
    """Best-effort journal update; diagnostics must never break speech or billing."""
    clean = clean_fields(fields)
    if not attempt_id or not clean:
        return
    db.execute(update(CoachAttempt).where(CoachAttempt.id == attempt_id).values(**clean))
    db.commit()


def record_refusal(db: Session, run_id: str, *, stage: str, purpose: str, reason: str, model: str,
                   meta: dict | None = None) -> str | None:
    """A request the ledger refused before any provider call: zero cost, never a reservation."""
    run = db.get(CoachLedgerRun, run_id)
    if run is None or stage not in {"text", "voice"}:
        return None
    refused = db.scalar(select(CoachAttempt.id).where(CoachAttempt.run_id == run_id, CoachAttempt.status == "refused")
                        .offset(MAX_REFUSALS_PER_RUN - 1).limit(1))
    if refused is not None:
        return None
    now = time.time()
    attempt_id = secrets.token_hex(16)
    db.add(CoachAttempt(id=attempt_id, run_id=run_id, opportunity=digest(f"refused:{attempt_id}"), stage=stage,
                        ordinal=0, model=model[:80], status="refused", reserve_micros=0, cost_micros=None,
                        pricing={"version": "refused", "model": model[:80]}, bounds={}, generation=run.generation,
                        credential_version=run.credential_version, created_at=now,
                        purpose=purpose if purpose in {"live", "summary", "scenario", "prebuild", "judge", "episode"}
                        else "live",
                        **clean_fields({**(meta or {}), "outcome": "refused", "error_code": reason, "finished_at": now})))
    db.commit()
    return attempt_id


def prune(db: Session, now: float | None = None) -> None:
    """Previews live at most 24 h and error details 30 days; costs stay forever with the ledger."""
    now = time.time() if now is None else now
    db.execute(update(CoachAttempt).where(CoachAttempt.text_preview.is_not(None),
                                          CoachAttempt.created_at < now - PREVIEW_TTL_S).values(text_preview=None))
    db.execute(update(CoachAttempt).where(CoachAttempt.error_detail.is_not(None),
                                          CoachAttempt.created_at < now - DETAIL_TTL_S).values(error_detail=None))
    db.commit()


def forget_previews(db: Session, user_id: str) -> None:
    runs = select(CoachLedgerRun.id).where(CoachLedgerRun.user_id == user_id)
    db.execute(update(CoachAttempt).where(CoachAttempt.run_id.in_(runs)).values(text_preview=None))
    db.commit()


# ---------- read models ----------

def _committed(attempt: CoachAttempt) -> int:
    if attempt.status in {"cancelled", "refused"}:
        return 0
    if attempt.status == "settled":
        return attempt.cost_micros or 0
    return max(attempt.reserve_micros, attempt.cost_micros or 0)


def category(attempt: CoachAttempt) -> str:
    if attempt.status == "refused":
        return "refused"
    if attempt.status == "cancelled" or attempt.outcome in {"cancelled", "stale"}:
        return "cancelled"
    if attempt.outcome in {"error", "rejected"}:
        return "error"
    if attempt.status in {"reserved", "sent"}:
        return "pending"
    if attempt.status == "unsettled":
        return "error"  # Usage unknown: a liability without a confirmed bill is worth a look.
    return "ok"


def kind(attempt: CoachAttempt, run: CoachLedgerRun) -> str:
    if run.ledger == "pack":
        return "pack"
    if attempt.purpose in {"prebuild", "scenario", "summary", "episode", "judge"}:
        return attempt.purpose
    return attempt.stage


def row(attempt: CoachAttempt, run: CoachLedgerRun) -> dict:
    return {"id": attempt.id, "group": attempt.opportunity[:16], "runId": run.id, "workoutSessionId": run.workout_id,
            "createdAt": attempt.created_at, "finishedAt": attempt.finished_at, "stage": attempt.stage,
            "kind": kind(attempt, run), "purpose": attempt.purpose or "live", "model": attempt.model,
            "triggerId": attempt.trigger_id, "task": attempt.task, "exerciseLabel": attempt.exercise_label,
            "setOrdinal": attempt.set_ordinal, "status": category(attempt), "ledgerStatus": attempt.status,
            "outcome": attempt.outcome, "errorCode": attempt.error_code, "httpStatus": attempt.http_status,
            "durationMs": attempt.duration_ms, "firstByteMs": attempt.first_byte_ms, "retry": attempt.ordinal > 0,
            "costMicros": _committed(attempt), "costSettled": attempt.status == "settled"}


def detail(attempt: CoachAttempt, run: CoachLedgerRun) -> dict:
    return {**row(attempt, run), "errorDetail": attempt.error_detail, "textPreview": attempt.text_preview,
            "usage": attempt.usage or None, "reserveMicros": attempt.reserve_micros,
            "settledMicros": attempt.cost_micros, "completeness": attempt.completeness,
            "markupBytes": attempt.markup_bytes, "textBytes": attempt.text_bytes,
            "pricingVersion": (attempt.pricing or {}).get("version"), "sentAt": attempt.sent_at}


def _load(db: Session, user_id: str, since: float, run_id: str | None) -> list[tuple[CoachAttempt, CoachLedgerRun]]:
    query = (select(CoachAttempt, CoachLedgerRun).join(CoachLedgerRun, CoachAttempt.run_id == CoachLedgerRun.id)
             .where(CoachLedgerRun.user_id == user_id, CoachAttempt.created_at >= since))
    if run_id:
        query = query.where(CoachLedgerRun.id == run_id)
    return [(a, r) for a, r in db.execute(query).all()]


def _percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * share) - 1)]


def totals(rows: list[tuple[CoachAttempt, CoachLedgerRun]]) -> dict:
    counts = {status: 0 for status in STATUSES}
    for attempt, _ in rows:
        counts[category(attempt)] += 1
    durations = [a.duration_ms for a, _ in rows if a.duration_ms is not None and a.status != "refused"]
    settled = sum(a.cost_micros or 0 for a, _ in rows if a.status == "settled")
    committed = sum(_committed(a) for a, _ in rows)
    paid = [a for a, _ in rows if a.status == "settled" and a.cost_micros]
    return {"total": len(rows), **counts, "settledMicros": settled, "pendingMicros": committed - settled,
            "totalMicros": committed, "p50Ms": _percentile(durations, .5), "p95Ms": _percentile(durations, .95),
            "avgMicros": round(statistics.fmean(a.cost_micros for a in paid)) if paid else None}


def requests(db: Session, *, user_id: str, since: float, run_id: str | None = None, status: str = "all",
             kind_filter: str = "all", cursor: str | None = None, limit: int = 50) -> dict:
    prune(db)
    loaded = _load(db, user_id, since, run_id)
    if kind_filter != "all":
        loaded = [(a, r) for a, r in loaded if kind(a, r) == kind_filter or (kind_filter == "text" and a.stage == "text"
                  and kind(a, r) not in {"pack"}) or (kind_filter == "voice" and a.stage == "voice" and kind(a, r) != "pack")]
    summary = totals(loaded)
    if status != "all":
        loaded = [(a, r) for a, r in loaded if category(a) == status]
    loaded.sort(key=lambda item: (item[0].created_at, item[0].id), reverse=True)
    if cursor:
        try:
            stamp, attempt_id = cursor.split(":", 1)
            mark = (float(stamp), attempt_id)
            loaded = [(a, r) for a, r in loaded if (a.created_at, a.id) < mark]
        except ValueError:
            pass
    page = loaded[:max(1, min(PAGE_LIMIT, limit))]
    next_cursor = f"{page[-1][0].created_at}:{page[-1][0].id}" if len(loaded) > len(page) else None
    return {"rows": [row(a, r) for a, r in page], "nextCursor": next_cursor, "totals": summary,
            "matching": len(loaded) if not cursor else None}


def request_detail(db: Session, user_id: str, attempt_id: str) -> dict | None:
    found = db.execute(select(CoachAttempt, CoachLedgerRun).join(CoachLedgerRun, CoachAttempt.run_id == CoachLedgerRun.id)
                       .where(CoachAttempt.id == attempt_id, CoachLedgerRun.user_id == user_id)).first()
    return detail(*found) if found else None


def _period_starts(now: float) -> tuple[float, float]:
    current = datetime.fromtimestamp(now, UTC)
    day = current.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    month = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    return day, month


def usage_summary(db: Session, *, user_id: str, since: float, run_id: str | None = None) -> dict:
    """Spend by kind/model/purpose for the period, the five most expensive requests, and the three limits."""
    from app.services.coach import ledger  # Late import: ledger imports journal for refusals.

    loaded = _load(db, user_id, since, run_id)
    by_kind: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_purpose: dict[str, int] = {}
    for attempt, run in loaded:
        cost = _committed(attempt)
        for table, key in ((by_kind, kind(attempt, run)), (by_model, attempt.model)):
            entry = table.setdefault(key, {"requests": 0, "micros": 0, "errors": 0, "durations": []})
            entry["requests"] += attempt.status != "refused"
            entry["micros"] += cost
            entry["errors"] += category(attempt) == "error"
            if attempt.duration_ms is not None:
                entry["durations"].append(attempt.duration_ms)
        by_purpose[attempt.purpose or "live"] = by_purpose.get(attempt.purpose or "live", 0) + cost
    for table in (by_kind, by_model):
        for entry in table.values():
            durations = entry.pop("durations")
            entry["p95Ms"] = _percentile(durations, .95)
            entry["avgMicros"] = round(entry["micros"] / entry["requests"]) if entry["requests"] else None
    top = sorted(loaded, key=lambda item: _committed(item[0]), reverse=True)[:5]
    cfg = get_settings()
    now = time.time()
    day, month = _period_starts(now)
    everyone = list(db.scalars(select(CoachAttempt).where(
        (CoachAttempt.created_at >= month) | CoachAttempt.status.in_(["reserved", "sent", "unsettled"]))))
    limits = {"day": {"usedMicros": sum(_committed(a) for a in everyone if (a.sent_at or a.created_at) >= day),
                      "capMicros": ledger.micros(cfg.coach_operator_daily_usd)},
              "month": {"usedMicros": sum(_committed(a) for a in everyone),
                        "capMicros": ledger.micros(cfg.coach_operator_monthly_usd)}}
    budget = None
    if run_id:
        run = db.get(CoachLedgerRun, run_id)
        if run is not None and run.user_id == user_id:
            attempts = list(db.scalars(select(CoachAttempt).where(CoachAttempt.run_id == run_id)))
            limits["workout"] = {"usedMicros": sum(_committed(a) for a in attempts), "capMicros": run.cap_micros}
            budget = ledger.budget_state(run, attempts)
    return {"byKind": by_kind, "byModel": by_model, "byPurpose": by_purpose, "limits": limits, "budget": budget,
            "top": [row(a, r) for a, r in top if _committed(a) > 0], "totals": totals(loaded)}
