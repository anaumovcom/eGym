"""Idempotent grant evaluation, outbox processing and catalog projections."""

from __future__ import annotations

import logging
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Set
from datetime import UTC, datetime
from functools import cache
from itertools import pairwise
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.achievement import (
    AchievementDefinition,
    AchievementEvidence,
    AchievementGrant,
    AchievementOutbox,
    AchievementProgress,
    AchievementReceipt,
)
from app.models.analytics import ExerciseSession, WorkoutSession
from app.models.user import User
from app.services.achievements.collection import CONTENT_VERSION, GROUPS, VERSION, collection
from app.services.achievements.facts import DONE, FactBuilder, facts_digest, utc
from app.services.achievements.media import asset_file, asset_urls, manifest_summary, media_stem
from app.services.achievements.patterns import WORKOUT_STORIES, workout_stories
from app.services.achievements.training_scope import CURATED_PRIMARY_GROUPS

logger = logging.getLogger(__name__)
GATED_ARCHIVE_REVISIONS = {"achievements-rules-1.2.0", "achievements-rules-1.3.0"}


def now() -> datetime:
    return datetime.now(UTC)


def _data_state(line: dict[str, Any], *, has_plan: bool = False, primary_groups: Set[str] = CURATED_PRIMARY_GROUPS) -> str:
    if line["applicability"] == "requires_primary" and line["id"].split(".")[1] not in primary_groups:
        return "insufficient_data"
    if line["applicability"] == "requires_plan" and not has_plan:
        return "insufficient_data"
    return "available"


def sync_definitions(session: Session) -> None:
    existing = {row.id: (row.rules_version, row.content_version) for row in session.execute(
        select(AchievementDefinition.id, AchievementDefinition.rules_version, AchievementDefinition.content_version))}
    definitions = [
        {"id": key, "rules_version": VERSION, "content_version": CONTENT_VERSION, "value": line, "active": not line.get("archived")}
        for key, line in collection().items()
        if existing.get(key) != (VERSION, CONTENT_VERSION) and (not line.get("archived") or key in existing)
    ]
    if definitions:
        # Two different users may be the first to finish after a catalog update.
        insert = postgresql_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
        statement = insert(AchievementDefinition.__table__)
        session.execute(statement.on_conflict_do_update(
            index_elements=["id"],
            set_={key: statement.excluded[key] for key in ("rules_version", "content_version", "value", "active")},
        ), definitions)


def enqueue(session: Session, *, user_id: str, source_type: str, source_id: str, source_revision: str,
            event_type: str) -> None:
    exists = session.scalar(select(AchievementOutbox.id).where(
        AchievementOutbox.user_id == user_id, AchievementOutbox.source_type == source_type,
        AchievementOutbox.source_id == source_id, AchievementOutbox.source_revision == source_revision))
    if exists is None:
        session.add(AchievementOutbox(user_id=user_id, source_type=source_type, source_id=source_id,
                                      source_revision=source_revision, event_type=event_type,
                                      state="pending", attempts=0, created_at=now()))
        session.flush()


def lock_owner(session: Session, user_id: str) -> None:
    connection = session.connection()
    if connection.dialect.name == "sqlite":
        # sqlite3 normally begins its write transaction at the first DML, after our history reads.
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        session.execute(select(User.id).where(User.id == user_id).with_for_update())


def _clear_award_history(session: Session, grant_ids: list[int]) -> None:
    session.execute(delete(AchievementReceipt).where(AchievementReceipt.grant_id.in_(grant_ids)))
    session.execute(delete(AchievementEvidence).where(AchievementEvidence.grant_id.in_(grant_ids),
                                                    AchievementEvidence.source_type == "workout"))


def reconcile_deleted_workout(session: Session, workout: WorkoutSession) -> None:
    """Run after the workout is flushed away, in the caller's deletion transaction."""
    source_id = str(workout.id)
    pending_deletions = (AchievementOutbox.user_id == workout.user_id, AchievementOutbox.source_type == "workout_deleted",
                         AchievementOutbox.state.in_(("pending", "failed")))
    cutoff = (utc(workout.finished_at), workout.id) if workout.finished_at else None
    if session.scalar(select(AchievementOutbox.id).where(*pending_deletions).limit(1)):
        cutoff = None  # Also repair any unfinished deletion from an older version.
    timestamp = now()
    enqueue(session, user_id=workout.user_id, source_type="workout_deleted", source_id=source_id,
            source_revision=timestamp.isoformat(), event_type="workout_deleted")
    evaluate_user(session, workout.user_id, changed_from=cutoff)
    session.execute(update(AchievementOutbox).where(*pending_deletions).values(
        state="processed", processed_at=now(), attempts=AchievementOutbox.attempts + 1))
    # Retire saved/retry events even on SQLite, where a future workout can reuse the deleted ID.
    session.execute(delete(AchievementOutbox).where(
        AchievementOutbox.user_id == workout.user_id, AchievementOutbox.source_type == "workout",
        AchievementOutbox.source_id == source_id))
    owner_grants = select(AchievementGrant.id).where(AchievementGrant.user_id == workout.user_id)
    session.execute(delete(AchievementEvidence).where(
        AchievementEvidence.grant_id.in_(owner_grants), AchievementEvidence.source_type == "workout",
        AchievementEvidence.source_id == source_id))


def _correct_award_sources(session: Session, history: FactBuilder, earned: list[AchievementGrant],
                           gated: set[int], changed_from: tuple[datetime, int] | None) -> list[AchievementGrant]:
    finishes = sorted((w for w in history.workouts if w.qualified), key=lambda w: w.finish_key)
    indices = {w.row.id: index for index, w in enumerate(finishes)}
    affected = [g for g in earned if g.source_workout_id not in indices or changed_from is None
                or finishes[indices[g.source_workout_id]].finish_key >= changed_from]
    if not affected:
        return []
    chronological_days = all(earlier.day <= later.day for earlier, later in pairwise(finishes))
    evidence_by_grant: dict[int, list[AchievementEvidence]] = defaultdict(list)
    for item in session.scalars(select(AchievementEvidence).where(
            AchievementEvidence.grant_id.in_([g.id for g in affected]), AchievementEvidence.source_type == "workout")):
        evidence_by_grant[item.grant_id].append(item)

    @cache
    def snapshot(index: int) -> dict[str, float]:
        return history.values_through(finishes[index].finish_key)

    def qualifies(index: int, requirements: list[tuple[str, float]]) -> bool:
        values = snapshot(index)
        return all(values.get(metric, 0) >= threshold for metric, threshold in requirements)

    def first_supporting_finish(requirements: list[tuple[str, float]], archived: bool) -> int:
        # Active collection totals accumulate when training days arrive in order. Imported sessions
        # can arrive out of order, and legacy records use comparisons that can change retrospectively.
        if chronological_days and not archived:
            return bisect_left(range(len(finishes)), True, key=lambda i: qualifies(i, requirements))
        return next((i for i in range(len(finishes)) if qualifies(i, requirements)), len(finishes))

    unsupported = []
    for grant in affected:
        line = collection()[grant.definition_id]
        tier = line["tiers"][grant.tier - 1]
        requirements = [(line["metric"], tier["threshold"])]
        if grant.id in gated:
            requirements.append((line["evidenceMetric"], tier["minimumEvidenceDays"]))

        index = indices.get(grant.source_workout_id)
        if index is None or not qualifies(index, requirements):
            index = first_supporting_finish(requirements, bool(line.get("archived")))
        if index == len(finishes):
            unsupported.append(grant)
            continue
        source = finishes[index]
        values = snapshot(index)
        if grant.source_workout_id != source.row.id:
            grant.source_workout_id = source.row.id
            grant.earned_at = source.finish_key[0]
        grant.evidence_digest = facts_digest(values)
        records = evidence_by_grant[grant.id]
        revision = VERSION
        if line.get("archived") and records:
            revision = next((r.source_revision for r in records if r.source_revision in GATED_ARCHIVE_REVISIONS),
                            records[0].source_revision)
        source_id = str(source.row.id)
        evidence = next((r for r in records if r.source_id == source_id), None)
        if evidence is None:
            evidence = AchievementEvidence(grant_id=grant.id, source_type="workout", source_id=source_id)
            session.add(evidence)
        evidence.source_revision = revision
        evidence.metric_value = values[line["metric"]]
        evidence.unit = line["unit"]
        for old in records:
            if old is not evidence:
                session.delete(old)
    return unsupported


def evaluate_user(session: Session, user_id: str, *, source_workout_id: int | None = None,
                  changed_from: tuple[datetime, int] | None = None) -> dict[str, Any]:
    """Only a finished workout with real work can issue grants. History corrections can only remove them."""
    timestamp = now()
    lock_owner(session, user_id)
    source = session.get(WorkoutSession, source_workout_id) if source_workout_id is not None else None
    if source_workout_id is not None:
        if source is None or source.user_id != user_id:
            raise LookupError("Workout session not found")
        if source.status not in DONE or source.finished_at is None:
            return {"awarded": [], "computedThrough": None, "factsDigest": None}

    grants = {(row.definition_id, row.tier): row for row in session.scalars(select(AchievementGrant).where(
        AchievementGrant.user_id == user_id, AchievementGrant.scope_key == "lifetime"))}
    lines = collection()
    archive_grants = [grant for (key, _), grant in grants.items()
                      if key in lines and lines[key].get("archived") and grant.status == "earned"]
    review_archive = source is None and bool(archive_grants)
    archive_keys = {grant.definition_id for grant in archive_grants} if review_archive else set()
    history = FactBuilder(session, user_id, collection_only=not review_archive)
    values = history.finish()
    digest = facts_digest(values)
    at_finish = values
    if source is not None:
        if not any(w.row.id == source.id and w.qualified for w in history.workouts):
            return {"awarded": [], "computedThrough": None, "factsDigest": digest}
        # A delayed/retried event must never use a later workout to cross its threshold.
        cutoff = (utc(source.finished_at), source.id)
        if any(w.finish_key > cutoff for w in history.workouts):
            at_finish = history.values_through(cutoff)

    revoked: list[AchievementGrant] = []
    gated_grants: set[int] = set()
    if review_archive:
        gated_grants = set(session.scalars(select(AchievementEvidence.grant_id).where(
            AchievementEvidence.grant_id.in_([g.id for g in archive_grants]),
            AchievementEvidence.source_revision.in_(GATED_ARCHIVE_REVISIONS))))
        for grant in archive_grants:
            line = lines[grant.definition_id]
            tier = line["tiers"][grant.tier - 1]
            if (values[line["metric"]] < tier["threshold"] or
                    (grant.id in gated_grants and values[line["evidenceMetric"]] < tier["minimumEvidenceDays"])):
                revoked.append(grant)

    sync_definitions(session)
    progress_rows = {row.definition_id: row for row in session.scalars(select(AchievementProgress).where(
        AchievementProgress.user_id == user_id, AchievementProgress.scope_key == "lifetime"))}
    has_plan = any(w.plan for w in history.workouts)
    evidence_digest = facts_digest(at_finish) if at_finish is not values else digest
    awarded: list[AchievementGrant] = []
    for key, line in lines.items():
        if line.get("archived") and key not in archive_keys:
            continue
        value = values.get(line["metric"], 0)
        progress = progress_rows.get(key)
        if progress is None:
            progress = AchievementProgress(user_id=user_id, definition_id=key, scope_key="lifetime")
            progress_rows[key] = progress
            session.add(progress)
        progress.current_value = value
        progress.computed_through = timestamp
        progress.data_state = _data_state(line, has_plan=has_plan, primary_groups=history.training_scope.available_primary)
        if line.get("archived"):
            continue
        highest = 0
        for tier in line["tiers"]:
            number, threshold = tier["tier"], tier["threshold"]
            grant = grants.get((key, number))
            if value < threshold:
                if grant is not None and grant.status == "earned":
                    revoked.append(grant)
                continue
            if grant is not None and grant.status == "earned":
                highest = max(highest, number)
                continue
            if source is None or at_finish.get(line["metric"], 0) < threshold:
                continue
            if grant is None:
                grant = AchievementGrant(user_id=user_id, definition_id=key, tier=number, scope_key="lifetime")
                session.add(grant)
            else:
                # Older revoked grants can still carry read receipts from their previous award.
                _clear_award_history(session, [grant.id])
            grant.status = "earned"
            grant.source_workout_id = source.id
            grant.earned_at = utc(source.finished_at)
            grant.awarded_at = timestamp
            grant.evidence_digest = evidence_digest
            session.flush()
            session.add(AchievementEvidence(grant_id=grant.id, source_type="workout", source_id=str(source.id),
                                            source_revision=VERSION, metric_value=at_finish[line["metric"]], unit=line["unit"]))
            highest = max(highest, number)
            awarded.append(grant)
        progress.highest_tier = highest
    if source is None:
        below_threshold = {g.id for g in revoked}
        retained = [g for g in grants.values() if g.status == "earned" and g.definition_id in lines and g.id not in below_threshold]
        revoked.extend(_correct_award_sources(session, history, retained, gated_grants, changed_from))
    if revoked:
        _clear_award_history(session, [grant.id for grant in revoked])
        for grant in revoked:
            grant.status = "revoked"
            grant.source_workout_id = None
            grant.earned_at = None
    if source is None:
        highest_earned: dict[str, int] = {}
        for grant in grants.values():
            if grant.status == "earned":
                key = grant.definition_id
                highest_earned[key] = max(grant.tier, highest_earned.get(key, 0))
        for key, progress in progress_rows.items():
            if key in lines and (not lines[key].get("archived") or review_archive):
                progress.highest_tier = highest_earned.get(key, 0)
                progress.current_value = values.get(lines[key]["metric"], 0)
                progress.computed_through = timestamp
    session.flush()
    return {"awarded": awarded, "computedThrough": timestamp, "factsDigest": digest}


def process_outbox(session: Session, *, user_id: str, source_type: str, source_id: str | None = None) -> None:
    retryable = AchievementOutbox.state.in_(("pending", "failed"))
    filters = [retryable, AchievementOutbox.user_id == user_id, AchievementOutbox.source_type == source_type]
    if source_id is not None:
        filters.append(AchievementOutbox.source_id == source_id)
    query = select(AchievementOutbox.id).where(*filters)
    for event_id in list(session.scalars(query.order_by(AchievementOutbox.id))):
        try:
            lock_owner(session, user_id)
            # A competing finisher waits for this transaction, then observes the processed state.
            claimed = session.execute(update(AchievementOutbox).where(AchievementOutbox.id == event_id, *filters)
                                      .values(state="processing")).rowcount
            if claimed:
                row = session.get(AchievementOutbox, event_id)
                workout_id = int(row.source_id) if row.event_type == "workout_finalized" and row.source_type == "workout" else None
                if workout_id is None or session.get(WorkoutSession, workout_id) is not None:
                    evaluate_user(session, row.user_id, source_workout_id=workout_id)
                row.state = "processed"
                row.processed_at = now()
                row.attempts += 1
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Could not process achievement event %s", event_id)
            session.execute(update(AchievementOutbox).where(AchievementOutbox.id == event_id, retryable)
                            .values(state="failed", attempts=AchievementOutbox.attempts + 1))
            session.commit()


def _line_projection(line: dict[str, Any], progress: AchievementProgress | None,
                     grants: dict[tuple[str, int], AchievementGrant], media_prefix: str,
                     receipts: dict[int, set[str]], user_id: str) -> dict[str, Any] | None:
    value = progress.current_value if progress else 0.0
    archived = line.get("archived", False)
    tiers = []
    current_grant = None
    for tier in line["tiers"]:
        grant = grants.get((line["id"], tier["tier"]))
        earned = bool(grant and grant.status == "earned")
        if earned:
            current_grant = grant
            assets = asset_urls(tier["id"], media_prefix, user_id=user_id)
        elif archived:
            continue
        else:
            tier = {**tier, "title": "", "phrase": "", "audioText": "", "fishMarkup": "", "imagePrompt": ""}
            assets = {"imageUrl": None, "thumbnailUrl": None, "audioUrl": None, "imageState": "locked", "audioState": "locked"}
        tiers.append({**tier, **assets, "earned": earned, "isNew": bool(earned and "detail" not in receipts.get(grant.id, set())),
                      "earnedAt": utc(grant.earned_at).isoformat() if earned and grant.earned_at else None,
                      "awardedAt": utc(grant.awarded_at).isoformat() if earned else None,
                      "status": grant.status if grant else "not_started"})
    if not tiers:
        return None
    next_tier = next((tier for tier in tiers if not tier["earned"]), None)
    previous = max((tier["threshold"] for tier in tiers if tier["earned"]), default=0)
    percent = 100.0 if next_tier is None else min(99.0, max(0.0,
        (value - previous) / max(1, next_tier["threshold"] - previous) * 100))
    return {**line, "name": line.get("name") or tiers[-1]["title"], "archived": archived,
            "thresholds": [tier["threshold"] for tier in tiers], "currentValue": value,
            "highestTier": current_grant.tier if current_grant else 0, "state": progress.data_state if progress else _data_state(line),
            "updatedAt": max((tier["awardedAt"] for tier in tiers if tier["earned"]), default=None),
            "isNew": any(tier["isNew"] for tier in tiers),
            "nextTierId": next_tier["id"] if next_tier else None, "progressPercent": round(percent, 1), "tiers": tiers}


def record_receipt(session: Session, user_id: str, definition_id: str, surface: str,
                   tier: int | None = None) -> dict[str, Any]:
    """Record real owner-scoped detail/audio events once, without changing grants."""
    if surface not in {"detail", "audio"}:
        raise ValueError("Unsupported receipt surface")
    lock_owner(session, user_id)
    grants = list(session.scalars(select(AchievementGrant).where(
        AchievementGrant.user_id == user_id, AchievementGrant.definition_id == definition_id,
        AchievementGrant.scope_key == "lifetime", AchievementGrant.status == "earned")
        .order_by(AchievementGrant.tier.desc())))
    latest = grants[0] if grants else None
    target = latest if tier is None else next(
        (grant for grant in grants if grant.tier == tier), None)
    if latest is None or target is None:
        raise LookupError("Achievement grant not found")
    receipt_query = select(AchievementReceipt).where(
        AchievementReceipt.user_id == user_id, AchievementReceipt.grant_id == target.id,
        AchievementReceipt.surface == surface)
    receipt = session.scalar(receipt_query)
    if receipt is None:
        receipt = AchievementReceipt(user_id=user_id, grant_id=target.id, surface=surface, viewed_at=now())
        try:
            with session.begin_nested():
                session.add(receipt)
                session.flush()
        except IntegrityError:
            receipt = session.scalars(receipt_query).one()
    grant_ids = [grant.id for grant in grants]
    viewed = set(session.scalars(select(AchievementReceipt.grant_id).where(
        AchievementReceipt.user_id == user_id, AchievementReceipt.grant_id.in_(grant_ids), AchievementReceipt.surface == "detail")))
    result = {"definitionId": definition_id, "tier": target.tier, "surface": surface,
              "viewedAt": utc(receipt.viewed_at).isoformat(), "isNew": len(viewed) < len(grants)}
    session.commit()
    return result


def _user_lines(session: Session, user_id: str, media_prefix: str, definition_id: str | None = None) -> list[dict[str, Any]]:
    progress_query = select(AchievementProgress).where(AchievementProgress.user_id == user_id,
                                                       AchievementProgress.scope_key == "lifetime")
    grants_query = select(AchievementGrant).where(AchievementGrant.user_id == user_id, AchievementGrant.scope_key == "lifetime")
    lines = collection()
    if definition_id is not None:
        if definition_id not in lines:
            return []
        lines = {definition_id: lines[definition_id]}
        progress_query = progress_query.where(AchievementProgress.definition_id == definition_id)
        grants_query = grants_query.where(AchievementGrant.definition_id == definition_id)
    progress = {row.definition_id: row for row in session.scalars(progress_query)}
    grants = {(row.definition_id, row.tier): row for row in session.scalars(grants_query)}
    receipts: dict[int, set[str]] = {}
    for grant_id, surface in session.execute(select(AchievementReceipt.grant_id, AchievementReceipt.surface)
                                              .where(AchievementReceipt.user_id == user_id)):
        receipts.setdefault(grant_id, set()).add(surface)
    result = []
    for key, line in lines.items():
        projected = _line_projection(line, progress.get(key), grants, media_prefix, receipts, user_id)
        if projected is not None:
            result.append(projected)
    return result


def catalog(session: Session, user_id: str, *, category: str | None = None, status: str | None = None,
            rarity: str | None = None, query: str | None = None, cursor: int = 0, limit: int = 40,
            media_prefix: str = "/media") -> dict[str, Any]:
    visible = _user_lines(session, user_id, media_prefix)
    groups = {line["group"] for line in visible}
    lines = []
    for line in visible:
        earned = bool(line["highestTier"])
        if category and line["group"] != category:
            continue
        candidates = [tier for tier in line["tiers"]
                      if (not rarity or tier["rarity"] == rarity)
                      and (status != "earned" or tier["earned"]) and (status != "new" or tier["isNew"])]
        if not candidates:
            continue
        searchable = [line["name"], line["groupName"], line["description"],
                      *[text for tier in candidates if tier["earned"] for text in (tier["title"], tier["phrase"])]]
        if query and query.strip().casefold() not in " ".join(searchable).casefold():
            continue
        if status == "locked" and earned:
            continue
        if status == "in_progress" and (not line["nextTierId"] or line["currentValue"] <= 0):
            continue
        if status == "not_started" and (earned or line["currentValue"] > 0):
            continue
        lines.append(line)
    # Keep the editorial order for brand-new profiles; surface recently earned series first.
    lines.sort(key=lambda line: (line["updatedAt"] or "", line["progressPercent"] if line["nextTierId"] else 0), reverse=True)
    start = max(0, cursor)
    page = lines[start:start + max(1, limit)]
    computed = session.scalar(select(func.max(AchievementProgress.computed_through)).where(
        AchievementProgress.user_id == user_id, AchievementProgress.scope_key == "lifetime"))
    return {"lines": page, "total": len(lines), "nextCursor": start + len(page) if start + len(page) < len(lines) else None,
            "computedThrough": utc(computed).isoformat() if computed else None,
            "isRebuilding": bool(session.scalar(select(AchievementOutbox.id).where(
                AchievementOutbox.user_id == user_id, AchievementOutbox.state == "pending").limit(1))),
            "groups": [{"id": key, "name": name} for key, name in GROUPS.items() if key in groups],
            "media": manifest_summary([line for line in visible if not line["archived"]])}


def overview(session: Session, user_id: str, *, media_prefix: str = "/media") -> dict[str, Any]:
    full = catalog(session, user_id, limit=len(collection()), media_prefix=media_prefix)
    lines = [line for line in full["lines"] if not line["archived"]]
    archived = [line for line in full["lines"] if line["archived"]]
    active_tiers = [tier for line in lines for tier in line["tiers"]]
    recent_grants = list(session.scalars(select(AchievementGrant).where(
        AchievementGrant.user_id == user_id, AchievementGrant.status == "earned", AchievementGrant.scope_key == "lifetime",
        AchievementGrant.definition_id.in_(list(collection())))
        .order_by(AchievementGrant.awarded_at.desc(), AchievementGrant.id.desc()).limit(5)))
    upcoming = sorted((line for line in lines if line["nextTierId"] and line["currentValue"] > 0),
                      key=lambda line: -line["progressPercent"])[:3]
    return {"earnedTiers": sum(tier["earned"] for tier in active_tiers), "newTiers": sum(tier["isNew"] for tier in active_tiers),
            "archivedTiers": sum(len(line["tiers"]) for line in archived), "archivedLines": len(archived),
            "totalTiers": len(active_tiers),
            "completedLines": sum(line["nextTierId"] is None for line in lines), "totalLines": len(lines),
            "activeDays": next((line["currentValue"] for line in lines if line["id"] == "rhythm.active_days"), 0),
            "recent": _project_grants(session, recent_grants, media_prefix),
            "upcoming": upcoming, "computedThrough": full["computedThrough"],
            "isRebuilding": full["isRebuilding"], "media": full["media"]}


def detail(session: Session, user_id: str, definition_id: str, *, media_prefix: str = "/media") -> dict[str, Any] | None:
    return next(iter(_user_lines(session, user_id, media_prefix, definition_id)), None)


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


def _project_grants(session: Session, grants: list[AchievementGrant], media_prefix: str,
                    witnesses: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    if not grants:
        return []
    ids = [g.id for g in grants]
    read = set(session.scalars(select(AchievementReceipt.grant_id).where(AchievementReceipt.grant_id.in_(ids),
        AchievementReceipt.user_id == grants[0].user_id, AchievementReceipt.surface == "detail")))
    values = {(e.grant_id, e.source_id): e.metric_value for e in session.scalars(select(AchievementEvidence).where(
        AchievementEvidence.grant_id.in_(ids), AchievementEvidence.source_type == "workout"))}
    return [_grant_projection(g, media_prefix, g.id not in read, values.get((g.id, str(g.source_workout_id))),
                              (witnesses or {}).get(g.definition_id, [])) for g in grants]


def _grant_projection(grant: AchievementGrant, media_prefix: str, unread: bool, value: float | None,
                      movements: list[str]) -> dict[str, Any]:
    line = collection()[grant.definition_id]
    tier = next(tier for tier in line["tiers"] if tier["tier"] == grant.tier)
    earned_at = utc(grant.earned_at).isoformat() if grant.earned_at else None
    awarded_at = utc(grant.awarded_at).isoformat()
    return {"grantId": grant.id, "definitionId": grant.definition_id, "group": line["group"],
            "sourceWorkoutId": grant.source_workout_id, "status": grant.status,
            "isNew": unread, "valueAtAward": value, "movements": movements,
            "earnedAt": earned_at, "awardedAt": awarded_at,
            "tier": {**tier, **asset_urls(tier["id"], media_prefix, user_id=grant.user_id), "earned": True, "isNew": unread,
                     "earnedAt": earned_at, "awardedAt": awarded_at, "status": grant.status},
            "unit": line["unit"], "description": line["description"]}


def workout_awards(session: Session, user_id: str, workout_id: int, *, media_prefix: str = "/media") -> dict[str, Any] | None:
    workout = session.get(WorkoutSession, workout_id)
    if workout is None or workout.user_id != user_id:
        return None
    if workout.status not in DONE or workout.finished_at is None:
        return {"workoutId": workout_id, "awards": [], "isRebuilding": False}
    grants = list(session.scalars(select(AchievementGrant).where(
        AchievementGrant.user_id == user_id, AchievementGrant.source_workout_id == workout_id,
        AchievementGrant.status == "earned").order_by(AchievementGrant.tier.desc(), AchievementGrant.id)))
    witnesses = {}
    if any(g.definition_id in WORKOUT_STORIES for g in grants):
        history = FactBuilder(session, user_id, collection_only=True, through=workout)
        _, slugs = workout_stories([w for w in history.workouts if w.qualified], workout.id)
        names = dict(session.execute(select(ExerciseSession.exercise_slug, ExerciseSession.exercise_name).where(
            ExerciseSession.user_id == user_id, ExerciseSession.workout_session_id == workout.id)).all())
        witnesses = {key: [names[s] for s in examples if names.get(s)] for key, examples in slugs.items()}
        grants.sort(key=lambda grant: grant.definition_id not in witnesses)
    return {"workoutId": workout_id, "awards": _project_grants(session, grants, media_prefix, witnesses),
            "isRebuilding": bool(session.scalar(select(AchievementOutbox.id).where(
                AchievementOutbox.user_id == user_id, AchievementOutbox.source_type == "workout",
                AchievementOutbox.source_id == str(workout_id), AchievementOutbox.state == "pending").limit(1)))}
