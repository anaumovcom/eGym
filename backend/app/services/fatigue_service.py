from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import pow, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, MuscleFatigueEvent, MuscleFatigueSnapshot, SetResult
from app.models.enums import FatigueEventSource, MuscleRole
from app.models.profile import UserProfile
from app.services.exercise_library import MuscleLoadProfile
from app.services.muscle_catalog import LEGACY_MUSCLE_SPLITS, get_muscle_definition, split_muscle_targets

ROLE_FACTORS: dict[MuscleRole, float] = {
    MuscleRole.primary: 1.0,
    MuscleRole.secondary: 0.6,
    MuscleRole.assisting: 0.35,
    MuscleRole.stabilizer: 0.2,
}

SET_TYPE_FACTORS: dict[str, float] = {
    "warmup": 0.6,
    "work": 1.0,
    "failure": 1.2,
}

# Recovery and stretching do not tire muscles; cardio and yoga holds are low-intensity endurance work.
EQUIPMENT_FACTORS: dict[str, float] = {
    "Recovery": 0.0,
    "Stretches": 0.0,
    "Cardio": 0.5,
    "Yoga": 0.5,
}


@dataclass
class FatigueReference:
    body_mass_kg: float | None = None
    working_capacity_kg: float = 0.0
    reps: int = 0
    seconds: int = 0


def exercise_references(session: Session, user_id: str, slugs: set[str], before: datetime,
                        workout_id: int | None = None) -> dict[str, FatigueReference]:
    """Personal benchmarks from prior finished sessions, never from the set being scored."""
    statement = (
        select(ExerciseSession.exercise_slug, ExerciseSession.kind, SetResult)
        .join(SetResult, SetResult.exercise_session_id == ExerciseSession.id)
        .where(ExerciseSession.user_id == user_id, ExerciseSession.exercise_slug.in_(slugs),
               ExerciseSession.finished_at < before, ExerciseSession.finished_at >= before - timedelta(days=90),
               SetResult.actual_value > 0)
    )
    if workout_id is not None:
        statement = statement.where(ExerciseSession.workout_session_id.is_distinct_from(workout_id))
    mass = session.scalar(select(UserProfile.weight_kg).where(UserProfile.user_id == user_id))
    result = {slug: FatigueReference(body_mass_kg=float(mass) if mass and mass > 0 else None) for slug in slugs}
    for slug, kind, row in session.execute(statement):
        metrics = row.machine_metrics or {}
        if metrics.get("setType") == "warmup" or metrics.get("completionStatus") == "skipped":
            continue
        ref = result[slug]
        if kind in {"timed", "stretch"}:
            ref.seconds = max(ref.seconds, row.duration_seconds or row.actual_value)
        elif row.weight_kg and row.weight_kg > 0:
            ref.working_capacity_kg = max(ref.working_capacity_kg, row.weight_kg * (1 + min(row.reps or row.actual_value, 30) / 30))
        else:
            ref.reps = max(ref.reps, row.reps or row.actual_value)
    return result


def effort_multiplier(effort: int | None, rir: float | None) -> float:
    if effort is not None:
        return 0.6 + 0.08 * max(0, min(effort, 10))
    if rir is not None:
        return 1.35 - 0.1 * max(0, min(rir, 6))
    return 1.0


@dataclass
class FatigueUpdate:
    muscle_id: str
    name: str
    delta: float
    current_score: int
    readiness_percent: int
    status: str


class FatigueService:
    def migrate_legacy_muscle_data(self, session: Session, user_id: str, now: datetime | None = None) -> None:
        effective_now = now or datetime.now(UTC)
        legacy_snapshots = list(session.scalars(select(MuscleFatigueSnapshot).where(
            MuscleFatigueSnapshot.user_id == user_id, MuscleFatigueSnapshot.muscle_id.in_(LEGACY_MUSCLE_SPLITS))))
        for snapshot in legacy_snapshots:
            self.hydrate_snapshot(snapshot, effective_now)
            for canonical_id, weight in split_muscle_targets(snapshot.muscle_id):
                canonical_snapshot = self.get_or_create_snapshot(
                    session,
                    user_id=user_id,
                    muscle_id=canonical_id,
                    now=snapshot.calculated_at,
                    recovery_half_life_hours=snapshot.recovery_half_life_hours,
                )
                if canonical_snapshot.id != snapshot.id:
                    self.hydrate_snapshot(canonical_snapshot, effective_now)
                    canonical_snapshot.fatigue_score += snapshot.fatigue_score * weight
                    canonical_snapshot.last_load_at = max(
                        [self.ensure_utc(item) for item in (canonical_snapshot.last_load_at, snapshot.last_load_at) if item is not None],
                        default=None,
                    )
            session.delete(snapshot)

        legacy_events = list(
            session.scalars(
                select(MuscleFatigueEvent).where(
                    MuscleFatigueEvent.user_id == user_id, MuscleFatigueEvent.muscle_id.in_(LEGACY_MUSCLE_SPLITS),
                )
            )
        )

        for event in legacy_events:
            for canonical_id, weight in split_muscle_targets(event.muscle_id):
                session.add(
                    MuscleFatigueEvent(
                        user_id=event.user_id,
                        muscle_id=canonical_id,
                        source=event.source,
                        workout_session_id=event.workout_session_id,
                        exercise_session_id=event.exercise_session_id,
                        set_result_id=event.set_result_id,
                        occurred_at=event.occurred_at,
                        fatigue_delta=round(event.fatigue_delta * weight, 2),
                        role=event.role,
                        recovery_half_life_hours=event.recovery_half_life_hours,
                        note=event.note,
                    )
                )
            session.delete(event)

        if legacy_snapshots or legacy_events:
            session.flush()

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
        self.migrate_legacy_muscle_data(session, user_id, effective_now)
        statement = select(MuscleFatigueSnapshot).where(MuscleFatigueSnapshot.user_id == user_id)
        snapshots = list(session.scalars(statement))
        for snapshot in snapshots:
            self.hydrate_snapshot(snapshot, effective_now)
        session.flush()
        return snapshots

    def reset_user_fatigue(self, session: Session, user_id: str, now: datetime | None = None) -> int:
        effective_now = now or datetime.now(UTC)
        self.migrate_legacy_muscle_data(session, user_id, effective_now)
        statement = select(MuscleFatigueSnapshot).where(MuscleFatigueSnapshot.user_id == user_id)
        snapshots = list(session.scalars(statement))

        for snapshot in snapshots:
            snapshot.fatigue_score = 0.0
            snapshot.calculated_at = effective_now
            snapshot.last_load_at = None

        session.flush()
        return len(snapshots)

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
        set_type: str | None = None,
        completion_status: str | None = None,
        equipment: str | None = None,
        profile: MuscleLoadProfile | None = None,
        reference: FatigueReference | None = None,
        rir: float | None = None,
        side_factor: float = 1.0,
    ) -> list[FatigueUpdate]:
        if completion_status == "skipped" or not self._has_performed_work(actual_value, reps, duration_seconds):
            return []

        base_load = self.set_base_load(
            planned_value=planned_value,
            actual_value=actual_value,
            reps=reps,
            weight_kg=weight_kg,
            duration_seconds=duration_seconds,
            amplitude_percent=amplitude_percent,
            subjective_effort=subjective_effort,
            discomfort_level=discomfort_level,
            set_type=set_type,
            equipment=equipment, profile=profile, reference=reference, rir=rir,
        )

        updates: list[FatigueUpdate] = []
        contributions = profile.contributions() if profile else self.target_contributions(muscle_targets)
        for canonical_id, (target_factor, role) in contributions.items():
            definition = get_muscle_definition(canonical_id)
            delta = round(base_load * min(target_factor, 1.0) * side_factor, 2)
            if delta <= 0:
                continue
            snapshot = self.get_or_create_snapshot(
                session,
                user_id=user_id,
                muscle_id=canonical_id,
                now=occurred_at,
            )
            self.hydrate_snapshot(snapshot, occurred_at)
            snapshot.fatigue_score += delta
            snapshot.last_load_at = occurred_at
            session.add(
                MuscleFatigueEvent(
                    user_id=user_id,
                    muscle_id=canonical_id,
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
                    muscle_id=canonical_id,
                    name=definition.name,
                    delta=delta,
                    current_score=int(round(snapshot.fatigue_score)),
                    readiness_percent=self.readiness_percent(snapshot.fatigue_score),
                    status=self.fatigue_status(snapshot.fatigue_score),
                )
            )
        session.flush()
        return updates

    def set_base_load(
        self,
        *,
        planned_value: int,
        actual_value: int,
        reps: int | None,
        weight_kg: float | None,
        duration_seconds: int | None,
        amplitude_percent: float | None = None,
        subjective_effort: int | None = None,
        discomfort_level: int | None = None,
        set_type: str | None = None,
        equipment: str | None = None,
        profile: MuscleLoadProfile | None = None,
        reference: FatigueReference | None = None,
        rir: float | None = None,
    ) -> float:
        """Fatigue one set adds to a fully targeted muscle (role factor 1.0)."""
        activity = profile.activity_factor if profile else EQUIPMENT_FACTORS.get(equipment or "", 1.0)
        reference = reference or FatigueReference()
        kg = max(0.0, weight_kg or 0.0)
        if reps is None:
            seconds = max(0, actual_value if duration_seconds is None else duration_seconds)
            volume = sqrt(seconds / 60)
            relative = sqrt(seconds / reference.seconds) if reference.seconds else 1.0
        else:
            volume = max(0, reps) / 10
            relative = sqrt(max(0, reps) / reference.reps) if reference.reps and not kg else 1.0
        if profile and profile.counterweight:
            relative = (1 - kg / reference.body_mass_kg) if reference.body_mass_kg else 1 / (1 + kg / 60)
        elif kg > 0:
            if reference.working_capacity_kg > 0:
                relative = 0.45 + kg / reference.working_capacity_kg
            else:
                relative = 1 + kg / (100 + kg)
        relative = min(1.65, max(0 if profile and profile.counterweight else 0.25, relative))
        amplitude = 90 if amplitude_percent is None else min(100, max(0, amplitude_percent))
        # A failure label already describes effort. Avoid a second bonus for an explicit RIR/RPE.
        set_factor = SET_TYPE_FACTORS.get(str(set_type or "work"), 1.0)
        if set_type == "failure" and (rir is not None or subjective_effort is not None):
            set_factor = 1.0
        return 8 * volume * relative * effort_multiplier(subjective_effort, rir) * (0.9 + amplitude / 1000) * set_factor * activity

    def _has_performed_work(self, actual_value: int, reps: int | None, duration_seconds: int | None) -> bool:
        return max(actual_value, reps or 0, duration_seconds or 0) > 0

    def _safe_role(self, raw_role: object) -> MuscleRole:
        try:
            return MuscleRole(str(raw_role))
        except ValueError:
            return MuscleRole.secondary

    def target_contributions(self, muscle_targets: list[dict[str, str]]) -> dict[str, tuple[float, MuscleRole]]:
        totals: defaultdict[str, float] = defaultdict(float)
        dominant_roles: dict[str, MuscleRole] = {}

        for target in muscle_targets:
            muscle_id = target.get("muscle_id")
            if not muscle_id:
                continue

            role = self._safe_role(target.get("role", MuscleRole.secondary.value))
            role_factor = ROLE_FACTORS[role]
            for canonical_id, split_weight in split_muscle_targets(muscle_id):
                totals[canonical_id] += role_factor * split_weight
                current_role = dominant_roles.get(canonical_id)
                if current_role is None or ROLE_FACTORS[role] > ROLE_FACTORS[current_role]:
                    dominant_roles[canonical_id] = role

        return {muscle_id: (factor, dominant_roles[muscle_id]) for muscle_id, factor in totals.items()}

    def muscle_history(self, session: Session, user_id: str, muscle_id: str) -> list[MuscleFatigueEvent]:
        statement = (
            select(MuscleFatigueEvent)
            .where(MuscleFatigueEvent.user_id == user_id, MuscleFatigueEvent.muscle_id == muscle_id)
            .order_by(MuscleFatigueEvent.occurred_at.desc())
        )
        return list(session.scalars(statement))