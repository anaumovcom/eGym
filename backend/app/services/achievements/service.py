"""Idempotent grant evaluation, outbox processing and catalog projections."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.achievement import (
    AchievementDefinition,
    AchievementEvidence,
    AchievementGrant,
    AchievementOutbox,
    AchievementProgress,
    AchievementReceipt,
)
from app.models.analytics import WorkoutSession
from app.services.achievements.content import load_catalog
from app.services.achievements.facts import FactBuilder, facts_digest, utc
from app.services.achievements.media import asset_file, asset_urls, manifest_summary, media_stem
from app.services.achievements.rules import CATALOG_VERSION, CONTENT_VERSION, GROUPS, RULES


def now() -> datetime:
    return datetime.now(UTC)


def sync_definitions(session: Session) -> None:
    existing = {row.id: row for row in session.scalars(select(AchievementDefinition))}
    for line in load_catalog()["lines"]:
        row = existing.get(line["id"])
        if row is None:
            row = AchievementDefinition(id=line["id"], rules_version=CATALOG_VERSION,
                                        content_version=CONTENT_VERSION, value=line, active=True)
            session.add(row)
        else:
            row.rules_version = CATALOG_VERSION
            row.content_version = CONTENT_VERSION
            row.value = line
            row.active = True
    session.flush()


def enqueue(session: Session, *, user_id: str, source_type: str, source_id: str, source_revision: str,
            event_type: str) -> None:
    exists = session.scalar(select(AchievementOutbox).where(
        AchievementOutbox.user_id == user_id, AchievementOutbox.source_type == source_type,
        AchievementOutbox.source_id == source_id, AchievementOutbox.source_revision == source_revision))
    if exists is None:
        session.add(AchievementOutbox(user_id=user_id, source_type=source_type, source_id=source_id,
                                      source_revision=source_revision, event_type=event_type,
                                      state="pending", attempts=0, created_at=now()))
        session.flush()


def _data_state(session: Session, user_id: str, applicability: str, metric: str = '') -> str:
    if applicability == 'requires_primary':
        from app.models.analytics import ExerciseSession
        from app.services.achievements.training_scope import CURATED_PRIMARY, canonical_primary_targets
        muscle_id = metric.removeprefix('muscle_primary_days:')
        if any(muscle_id in targets for targets in CURATED_PRIMARY.values()):
            return 'available'
        targets = session.scalars(select(ExerciseSession.muscle_targets).where(ExerciseSession.user_id == user_id))
        return 'available' if any(muscle_id in canonical_primary_targets(row) for row in targets) else 'insufficient_data'
    if applicability == "available":
        return "available"
    if applicability == "requires_sensor":
        # Legacy rows never become sensor-verified by inference.
        from app.models.analytics import ExerciseSession, SetResult
        verified = session.scalar(select(SetResult.id).join(ExerciseSession).where(
            ExerciseSession.user_id == user_id,
            SetResult.machine_metrics["sourceClass"].as_string() == "sensor_verified").limit(1))
        return "available" if verified is not None else "insufficient_data"
    if applicability == "requires_plan":
        from sqlalchemy import inspect

        from app.models.analytics import CoachWorkoutPlan
        if not inspect(session.connection()).has_table(CoachWorkoutPlan.__tablename__):
            return "insufficient_data"
        plan = session.scalar(select(CoachWorkoutPlan.workout_id).where(CoachWorkoutPlan.user_id == user_id).limit(1))
        return "available" if plan is not None else "insufficient_data"
    if applicability == "requires_comparison":
        from app.models.analytics import ExerciseSession
        count = len(set(session.scalars(select(ExerciseSession.workout_session_id).where(
            ExerciseSession.user_id == user_id, ExerciseSession.workout_session_id.is_not(None)))))
        return "available" if count >= 2 else "insufficient_data"
    if applicability == "requires_story":
        from app.models.coach import CoachEpisode
        episode = session.scalar(select(CoachEpisode.workout_id).where(CoachEpisode.user_id == user_id).limit(1))
        return "available" if episode is not None else "insufficient_data"
    return "available"


def evaluate_user(session: Session, user_id: str, *, source_workout_id: int | None = None) -> dict[str, Any]:
    sync_definitions(session)
    values = FactBuilder(session, user_id).finish()
    digest = facts_digest(values)
    timestamp = now()
    source = session.get(WorkoutSession, source_workout_id) if source_workout_id is not None else None
    if source is not None and source.user_id != user_id:
        raise LookupError("Workout session not found")
    progress_rows = {row.definition_id: row for row in session.scalars(
        select(AchievementProgress).where(AchievementProgress.user_id == user_id, AchievementProgress.scope_key == "lifetime"))}
    grants = {(row.definition_id, row.tier): row for row in session.scalars(
        select(AchievementGrant).where(AchievementGrant.user_id == user_id, AchievementGrant.scope_key == "lifetime"))}
    gated_grants = set(session.scalars(select(AchievementEvidence.grant_id).join(AchievementGrant).where(
        AchievementGrant.user_id == user_id,
        AchievementEvidence.source_revision.in_({'achievements-rules-1.2.0', CATALOG_VERSION}))))
    evidence_progress = {row.definition_id: row for row in session.scalars(select(AchievementProgress).where(
        AchievementProgress.user_id == user_id, AchievementProgress.scope_key == 'evidence'))}
    awarded: list[AchievementGrant] = []
    for rule in RULES:
        definition_id = rule["id"]
        value = values[rule["metric"]]
        evidence_days = min(values.get(rule['evidenceMetric'], 0), values.get('practice_evidence_days', 0))
        eligible = [value >= threshold and evidence_days >= rule['minimumEvidenceDays'][index]
                for index, threshold in enumerate(rule['thresholds'])]
        highest = sum(eligible)
        progress = progress_rows.get(definition_id)
        if progress is None:
            progress = AchievementProgress(user_id=user_id, definition_id=definition_id, scope_key="lifetime")
            session.add(progress)
            progress_rows[definition_id] = progress
        progress.current_value = value
        progress.highest_tier = highest
        progress.data_state = _data_state(session, user_id, rule["applicability"], rule['metric'])
        progress.computed_through = timestamp
        evidence_row = evidence_progress.get(definition_id)
        if evidence_row is None:
            evidence_row = AchievementProgress(user_id=user_id, definition_id=definition_id, scope_key='evidence')
            session.add(evidence_row)
        evidence_row.current_value = evidence_days
        evidence_row.highest_tier = 0
        evidence_row.data_state = progress.data_state
        evidence_row.computed_through = timestamp
        for tier, threshold in enumerate(rule["thresholds"], 1):
            grant = grants.get((definition_id, tier))
            if eligible[tier - 1]:
                earned_at = utc(source.finished_at or source.started_at) if source else timestamp
                evidence = {"definitionId": definition_id, "tier": tier, "value": value,
                            'evidenceDays': evidence_days, 'rulesVersion': CATALOG_VERSION,
                            "sourceWorkoutId": source_workout_id, "factsDigest": digest}
                evidence_digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
                if grant is None:
                    grant = AchievementGrant(user_id=user_id, definition_id=definition_id, tier=tier, scope_key="lifetime",
                                             status="earned", source_workout_id=source_workout_id, earned_at=earned_at,
                                             awarded_at=timestamp, evidence_digest=evidence_digest)
                    session.add(grant)
                    session.flush()
                    session.add(AchievementEvidence(grant_id=grant.id, source_type="workout" if source else "history",
                                                    source_id=str(source_workout_id or "lifetime"), source_revision=CATALOG_VERSION,
                                                    metric_value=value, unit=rule["unit"]))
                    grants[(definition_id, tier)] = grant
                    awarded.append(grant)
                elif grant.status != "earned":
                    # A revoked grant crosses the threshold again: point it back at the
                    # workout that produced it so the result screen can list the award.
                    grant.status = "earned"
                    grant.awarded_at = timestamp
                    grant.earned_at = earned_at
                    grant.source_workout_id = source_workout_id
                    grant.evidence_digest = evidence_digest
                    awarded.append(grant)
            elif grant is not None and grant.status == "earned" and (value < threshold or grant.id in gated_grants):
                grant.status = "revoked"
        # Rebalancing does not confiscate valid historical awards. Corrections
        # below their original metric threshold still revoke as before.
        progress.highest_tier = max([highest, *[tier for (line_id, tier), grant in grants.items()
                                               if line_id == definition_id and grant.status == 'earned']])
    session.commit()
    return {"awarded": awarded, "computedThrough": timestamp, "factsDigest": digest}


def process_outbox(session: Session, *, limit: int = 20) -> dict[str, int]:
    rows = list(session.scalars(select(AchievementOutbox).where(AchievementOutbox.state == "pending")
                                .order_by(AchievementOutbox.id).limit(limit)))
    result = {"processed": 0, "failed": 0, "remaining": 0}
    for row in rows:
        try:
            workout_id = int(row.source_id) if row.source_type == "workout" else None
            evaluate_user(session, row.user_id, source_workout_id=workout_id)
            row.state = "processed"
            row.processed_at = now()
            row.attempts += 1
            session.commit()
            result["processed"] += 1
        except Exception:
            session.rollback()
            failed = session.get(AchievementOutbox, row.id)
            if failed is not None:
                failed.state = "failed"
                failed.attempts += 1
                session.commit()
            result["failed"] += 1
    result["remaining"] = len(session.scalars(select(AchievementOutbox.id).where(AchievementOutbox.state == "pending")).all())
    return result


def _line_projection(session: Session, line: dict[str, Any], progress: AchievementProgress | None,
                     grants: dict[tuple[str, int], AchievementGrant], media_prefix: str,
                     evidence_days: float = 0, receipts: dict[int, set[str]] | None = None,
                     user_id: str = "") -> dict[str, Any]:
    value = progress.current_value if progress else 0.0
    highest = progress.highest_tier if progress else 0
    state = progress.data_state if progress else _data_state(session, "", line["applicability"], line['metric'])
    tiers = []
    for tier in line["tiers"]:
        grant = grants.get((line["id"], tier["tier"]))
        earned = bool(grant and grant.status == "earned")
        if earned:
            assets = asset_urls(tier["id"], media_prefix, user_id=user_id)
        else:
            # Locked editorial, artwork and speech never leave the trusted catalog projection.
            tier = {**tier, "title": "", "phrase": "", "audioText": "", "fishMarkup": "", "imagePrompt": ""}
            assets = {"imageUrl": None, "thumbnailUrl": None, "audioUrl": None,
                      "imageState": "locked", "audioState": "locked"}
        tiers.append({**tier, **assets, "earned": earned,
                      "earnedAt": grant.earned_at.isoformat() if grant and grant.earned_at else None,
                      "awardedAt": grant.awarded_at.isoformat() if grant and grant.awarded_at else None,
                      "status": grant.status if grant else "not_started"})
    next_tier = next((tier for tier in tiers if not tier['earned']), None)
    previous_threshold = max([0, *[tier["threshold"] for tier in tiers if tier['earned']]])
    percent = 100.0 if next_tier is None else min(100.0, max(0.0,
        (value - previous_threshold) / max(1, next_tier["threshold"] - previous_threshold) * 100))
    if next_tier is not None:
        percent = min(99.0, percent, evidence_days / max(1, next_tier['minimumEvidenceDays']) * 100)
    current_grant = max((grant for (line_id, _), grant in grants.items()
                         if line_id == line["id"] and grant.status == "earned"),
                        key=lambda grant: grant.tier, default=None)
    updated_at = None
    if current_grant is not None:
        updated = max(current_grant.awarded_at, current_grant.earned_at or current_grant.awarded_at)
        updated_at = updated.isoformat()
    current_receipts = (receipts or {}).get(current_grant.id, set()) if current_grant else set()
    discovered = any(tier["earned"] for tier in tiers)
    return {**line, "description": line["description"] if discovered else "", "currentValue": value, "highestTier": highest, "state": state,
            "evidenceDays": evidence_days, "updatedAt": updated_at,
            "isNew": bool(current_grant and not {"detail", "audio"}.issubset(current_receipts)),
            "nextTierId": next_tier["id"] if next_tier else None, "progressPercent": round(percent, 1), "tiers": tiers}


def record_receipt(session: Session, user_id: str, definition_id: str, surface: str,
                   tier: int | None = None) -> dict[str, Any]:
    """Record real owner-scoped detail/audio events once, without changing grants."""
    if surface not in {"detail", "audio"}:
        raise ValueError("Unsupported receipt surface")
    grants = list(session.scalars(select(AchievementGrant).where(
        AchievementGrant.user_id == user_id, AchievementGrant.definition_id == definition_id,
        AchievementGrant.scope_key == "lifetime", AchievementGrant.status == "earned")
        .order_by(AchievementGrant.tier.desc())))
    latest = grants[0] if grants else None
    target = latest if surface == "detail" or tier is None else next(
        (grant for grant in grants if grant.tier == tier), None)
    if latest is None or target is None:
        raise LookupError("Achievement grant not found")
    receipt = session.scalar(select(AchievementReceipt).where(
        AchievementReceipt.user_id == user_id, AchievementReceipt.grant_id == target.id,
        AchievementReceipt.surface == surface))
    if receipt is None:
        receipt = AchievementReceipt(user_id=user_id, grant_id=target.id, surface=surface, viewed_at=now())
        session.add(receipt)
        session.commit()
    surfaces = set(session.scalars(select(AchievementReceipt.surface).where(
        AchievementReceipt.user_id == user_id, AchievementReceipt.grant_id == latest.id)))
    return {"definitionId": definition_id, "tier": target.tier, "surface": surface,
            "viewedAt": utc(receipt.viewed_at).isoformat(), "isNew": not {"detail", "audio"}.issubset(surfaces)}


def catalog(session: Session, user_id: str, *, category: str | None = None, status: str | None = None,
            rarity: str | None = None, query: str | None = None, cursor: int = 0, limit: int = 40,
            media_prefix: str = "/media") -> dict[str, Any]:
    # GET projections never mutate definitions, grants, or progress.
    progress = {row.definition_id: row for row in session.scalars(
        select(AchievementProgress).where(AchievementProgress.user_id == user_id, AchievementProgress.scope_key == "lifetime"))}
    grants = {(row.definition_id, row.tier): row for row in session.scalars(
        select(AchievementGrant).where(AchievementGrant.user_id == user_id, AchievementGrant.scope_key == "lifetime"))}
    evidence_days = {row.definition_id: row.current_value for row in session.scalars(
        select(AchievementProgress).where(AchievementProgress.user_id == user_id, AchievementProgress.scope_key == 'evidence'))}
    receipts: dict[int, set[str]] = {}
    for receipt in session.scalars(select(AchievementReceipt).where(AchievementReceipt.user_id == user_id)):
        receipts.setdefault(receipt.grant_id, set()).add(receipt.surface)
    lines = []
    for line in load_catalog()["lines"]:
        if category and line["group"] != category or rarity and line["tiers"][0]["rarity"] != rarity:
            continue
        projected = _line_projection(session, line, progress.get(line["id"]), grants, media_prefix,
                         evidence_days.get(line['id'], 0), receipts, user_id)
        earned = any(tier["earned"] for tier in projected["tiers"])
        # An undiscovered line can only be found by its section name, never by hidden text.
        searchable = [projected["description"], *[tier["title"] for tier in projected["tiers"]]] if earned else []
        if query and query.casefold() not in json.dumps([line["groupName"], *searchable],
                                                        ensure_ascii=False).casefold():
            continue
        if status == "locked" and earned or status == "new" and not (earned and projected["isNew"]):
            continue
        if status == "earned" and not earned or status == "in_progress" and (earned or projected["currentValue"] <= 0):
            continue
        if status == "not_started" and (earned or projected["currentValue"] > 0):
            continue
        lines.append(projected)
    # Stable ID → next progress → newest earned/awarded update, in that priority's reverse order.
    lines.sort(key=lambda line: line["id"])
    lines.sort(key=lambda line: line["progressPercent"] if line["nextTierId"] else 0, reverse=True)
    lines.sort(key=lambda line: line["updatedAt"] or "", reverse=True)
    start = max(0, cursor)
    page = lines[start:start + min(len(RULES), max(1, limit))]
    computed = max((row.computed_through for row in progress.values() if row.computed_through), default=None)
    return {"lines": page, "total": len(lines), "nextCursor": start + len(page) if start + len(page) < len(lines) else None,
            "computedThrough": computed.isoformat() if computed else None,
            "isRebuilding": bool(session.scalar(select(AchievementOutbox.id).where(
                AchievementOutbox.user_id == user_id, AchievementOutbox.state == "pending").limit(1))),
            "groups": [{"id": key, "name": value} for key, value in GROUPS.items()], "media": manifest_summary()}


def overview(session: Session, user_id: str, *, media_prefix: str = "/media") -> dict[str, Any]:
    full = catalog(session, user_id, limit=len(RULES), media_prefix=media_prefix)
    lines = full["lines"]
    recent_grants = list(session.scalars(select(AchievementGrant).where(
        AchievementGrant.user_id == user_id, AchievementGrant.status == "earned")
        .order_by(AchievementGrant.awarded_at.desc()).limit(5)))
    recent = [_grant_projection(session, grant, media_prefix) for grant in recent_grants]
    upcoming = sorted((line for line in lines if line["nextTierId"] and any(tier["earned"] for tier in line["tiers"])),
                      key=lambda line: (-line["progressPercent"], line["nextTierId"]))[:3]
    return {"earnedTiers": sum(sum(tier['earned'] for tier in line['tiers']) for line in lines),
            "totalTiers": sum(len(line['tiers']) for line in lines),
            "completedLines": sum(all(tier['earned'] for tier in line['tiers']) for line in lines), "totalLines": full['total'],
            "activeDays": next((line["currentValue"] for line in lines if line["id"] == "rhythm.active_days"), 0),
            "recent": recent, "upcoming": upcoming, "computedThrough": full["computedThrough"],
            "isRebuilding": full["isRebuilding"], "media": full["media"]}


def detail(session: Session, user_id: str, definition_id: str, *, media_prefix: str = "/media") -> dict[str, Any] | None:
    full = catalog(session, user_id, limit=len(RULES), media_prefix=media_prefix)
    found = next((line for line in full["lines"] if line["id"] == definition_id), None)
    # An achievement with no earned tier is unknown: it cannot be opened.
    return found if found is not None and any(tier["earned"] for tier in found["tiers"]) else None


def earned_media_path(session: Session, user_id: str, tier_id: str, kind: str):
    """Published image/audio only for a tier this owner has actually earned."""
    try:
        media_stem(tier_id)
        definition_id, tier_text = tier_id.rsplit(":t", 1)
        tier = int(tier_text)
    except ValueError:
        return None
    earned = session.scalar(select(AchievementGrant.id).where(
        AchievementGrant.user_id == user_id, AchievementGrant.definition_id == definition_id,
        AchievementGrant.tier == tier, AchievementGrant.scope_key == "lifetime",
        AchievementGrant.status == "earned").limit(1))
    return asset_file(tier_id, kind) if earned is not None else None


def _grant_projection(session: Session, grant: AchievementGrant, media_prefix: str) -> dict[str, Any]:
    line = next(line for line in load_catalog()["lines"] if line["id"] == grant.definition_id)
    tier = next(tier for tier in line["tiers"] if tier["tier"] == grant.tier)
    surfaces = set(session.scalars(select(AchievementReceipt.surface).where(
        AchievementReceipt.user_id == grant.user_id, AchievementReceipt.grant_id == grant.id)))
    return {"grantId": grant.id, "definitionId": grant.definition_id, "group": line["group"],
            "sourceWorkoutId": grant.source_workout_id, "status": grant.status,
            "isNew": not {"detail", "audio"}.issubset(surfaces),
            "earnedAt": grant.earned_at.isoformat() if grant.earned_at else None,
            "awardedAt": grant.awarded_at.isoformat(),
            "tier": {**tier, **asset_urls(tier["id"], media_prefix, user_id=grant.user_id), "earned": True,
                     "earnedAt": grant.earned_at.isoformat() if grant.earned_at else None,
                     "awardedAt": grant.awarded_at.isoformat(), "status": grant.status},
            "unit": line["unit"], "description": line["description"]}


def workout_awards(session: Session, user_id: str, workout_id: int, *, media_prefix: str = "/media") -> dict[str, Any] | None:
    workout = session.get(WorkoutSession, workout_id)
    if workout is None or workout.user_id != user_id:
        return None
    grants = list(session.scalars(select(AchievementGrant).where(
        AchievementGrant.user_id == user_id, AchievementGrant.source_workout_id == workout_id,
        AchievementGrant.status == "earned").order_by(AchievementGrant.tier.desc(), AchievementGrant.id)))
    return {"workoutId": workout_id, "awards": [_grant_projection(session, grant, media_prefix) for grant in grants],
            "isRebuilding": bool(session.scalar(select(AchievementOutbox.id).where(
                AchievementOutbox.user_id == user_id, AchievementOutbox.source_type == "workout",
                AchievementOutbox.source_id == str(workout_id), AchievementOutbox.state == "pending").limit(1)))}
