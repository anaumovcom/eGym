from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import pow

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import MuscleFatigueEvent, MuscleFatigueSnapshot
from app.models.enums import FatigueEventSource, MuscleRole

ROLE_FACTORS: dict[MuscleRole, float] = {
    MuscleRole.primary: 1.0,
    MuscleRole.secondary: 0.6,
    MuscleRole.assisting: 0.35,
    MuscleRole.stabilizer: 0.2,
}


@dataclass
class FatigueUpdate:
    muscle_id: str
    name: str
    delta: float
    current_score: int
    readiness_percent: int
    status: str


class FatigueService:
    def ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def fatigue_status(self, score: float) -> str:
        if score >= 100:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 30:
            return "medium"
        if score >= 10:
            return "light"
        return "ready"

    def readiness_percent(self, score: float) -> int:
        return max(0, min(100, int(round(100 - score))))

    def decay_score(self, score: float, elapsed_hours: float, recovery_half_life_hours: float) -> float:
        if score <= 0 or elapsed_hours <= 0:
            return score
        return score * pow(0.5, elapsed_hours / recovery_half_life_hours)

    def get_or_create_snapshot(
        self,
        session: Session,
        *,
        user_id: str,
        muscle_id: str,
        now: datetime,
        recovery_half_life_hours: float = 24.0,
    ) -> MuscleFatigueSnapshot:
        statement = select(MuscleFatigueSnapshot).where(
            MuscleFatigueSnapshot.user_id == user_id,
            MuscleFatigueSnapshot.muscle_id == muscle_id,
        )
        snapshot = session.scalars(statement).first()
        if snapshot is None:
            snapshot = MuscleFatigueSnapshot(
                user_id=user_id,
                muscle_id=muscle_id,
                fatigue_score=0.0,
                calculated_at=now,
                recovery_half_life_hours=recovery_half_life_hours,
                last_load_at=None,
            )
            session.add(snapshot)
            session.flush()
        return snapshot

    def hydrate_snapshot(self, snapshot: MuscleFatigueSnapshot, now: datetime) -> MuscleFatigueSnapshot:
        normalized_now = self.ensure_utc(now)
        calculated_at = self.ensure_utc(snapshot.calculated_at)
        elapsed_hours = max(0.0, (normalized_now - calculated_at).total_seconds() / 3600)
        snapshot.fatigue_score = self.decay_score(snapshot.fatigue_score, elapsed_hours, snapshot.recovery_half_life_hours)
        snapshot.calculated_at = normalized_now
        return snapshot

    def list_current_scores(self, session: Session, user_id: str, now: datetime | None = None) -> list[MuscleFatigueSnapshot]:
        effective_now = now or datetime.now(UTC)
        statement = select(MuscleFatigueSnapshot).where(MuscleFatigueSnapshot.user_id == user_id)
        snapshots = list(session.scalars(statement))
        for snapshot in snapshots:
            self.hydrate_snapshot(snapshot, effective_now)
        session.flush()
        return snapshots

    def build_set_updates(
        self,
        session: Session,
        *,
        user_id: str,
        workout_session_id: int | None,
        exercise_session_id: int,
        set_result_id: int,
        occurred_at: datetime,
        exercise_name: str,
        muscle_targets: list[dict[str, str]],
        planned_value: int,
        actual_value: int,
        reps: int | None,
        weight_kg: float | None,
        duration_seconds: int | None,
        amplitude_percent: float | None,
        subjective_effort: int | None,
        discomfort_level: int | None,
    ) -> list[FatigueUpdate]:
        effective_reps = reps or actual_value or 1
        volume_factor = max(effective_reps / 10, 0.6) + ((duration_seconds or 0) / 60)
        intensity_factor = 1.0 + max((subjective_effort or 6) - 5, 0) * 0.08 + ((weight_kg or 0) / 100)
        quality_factor = 0.9 + (amplitude_percent or 90) / 1000
        subjective_factor = 1.0 + (discomfort_level or 0) * 0.05
        completion_factor = max(actual_value / planned_value, 0.5) if planned_value else 1.0
        base_load = 8.0 * max(volume_factor, 0.75) * intensity_factor * quality_factor * subjective_factor * completion_factor

        updates: list[FatigueUpdate] = []
        for target in muscle_targets:
            role = MuscleRole(target.get("role", MuscleRole.secondary.value))
            delta = round(base_load * ROLE_FACTORS[role], 2)
            snapshot = self.get_or_create_snapshot(
                session,
                user_id=user_id,
                muscle_id=target["muscle_id"],
                now=occurred_at,
            )
            self.hydrate_snapshot(snapshot, occurred_at)
            snapshot.fatigue_score += delta
            snapshot.last_load_at = occurred_at
            session.add(
                MuscleFatigueEvent(
                    user_id=user_id,
                    muscle_id=target["muscle_id"],
                    source=FatigueEventSource.exercise_set,
                    workout_session_id=workout_session_id,
                    exercise_session_id=exercise_session_id,
                    set_result_id=set_result_id,
                    occurred_at=occurred_at,
                    fatigue_delta=delta,
                    role=role,
                    recovery_half_life_hours=snapshot.recovery_half_life_hours,
                    note=exercise_name,
                )
            )
            updates.append(
                FatigueUpdate(
                    muscle_id=target["muscle_id"],
                    name=target.get("name", target["muscle_id"]),
                    delta=delta,
                    current_score=int(round(snapshot.fatigue_score)),
                    readiness_percent=self.readiness_percent(snapshot.fatigue_score),
                    status=self.fatigue_status(snapshot.fatigue_score),
                )
            )
        session.flush()
        return updates

    def muscle_history(self, session: Session, user_id: str, muscle_id: str) -> list[MuscleFatigueEvent]:
        statement = (
            select(MuscleFatigueEvent)
            .where(MuscleFatigueEvent.user_id == user_id, MuscleFatigueEvent.muscle_id == muscle_id)
            .order_by(MuscleFatigueEvent.occurred_at.desc())
        )
        return list(session.scalars(statement))