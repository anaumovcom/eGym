from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, MuscleFatigueEvent, MuscleFatigueSnapshot, SetResult, WorkoutSession
from app.models.coach import CoachLedgerRun
from app.models.enums import (
    DiscomfortLevel,
    ExerciseSessionStatus,
    FatigueEventSource,
    FeelingLevel,
    RuntimeExerciseKind,
    RuntimeFlowSource,
    WorkoutSessionStatus,
)
from app.models.training import ExerciseHistoryRecord, UserExerciseState
from app.models.user import User
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
    ExerciseSessionsResetRequestSchema,
    ExerciseSessionsResetResponseSchema,
    ExerciseSettingsSaveSchema,
    ExerciseSettingsSchema,
    LoadAdjustmentRequestSchema,
    LoadAdjustmentResponseSchema,
    RuntimeExerciseSummarySchema,
    RuntimeExerciseTotalsSchema,
    RuntimePlanVsFactSchema,
    RuntimeSetResultSchema,
    RuntimeWorkoutExerciseRowSchema,
    RuntimeWorkoutMetricSchema,
    RuntimeWorkoutMuscleSchema,
    RuntimeWorkoutSummarySchema,
    SavedSetResponseSchema,
    SetFatigueDeltaSchema,
    SetFeedbackSchema,
    SetResultSaveSchema,
    WorkoutSessionCreateSchema,
)
from app.services.coach.lifecycle import RuntimeObservationBuffer, runtime_observations
from app.services.coach.workout_plan import persist_plan
from app.services.exercise_library import get_imported_exercise
from app.services.exercise_settings import remembered_settings
from app.services.fatigue_service import FatigueService, FatigueUpdate, equipment_affects_fatigue


@dataclass
class ExerciseSaveResult:
    exercise_session: ExerciseSession
    summary: RuntimeExerciseSummarySchema
    coach_notices: tuple[dict[str, object], ...] = ()


class RuntimeService:
    def __init__(self, *, coach_observer: RuntimeObservationBuffer | None = None) -> None:
        self.fatigue_service = FatigueService()
        self.coach_observer = coach_observer if coach_observer is not None else runtime_observations

    def _validate_settings_owner(self, session: Session, user_id: str, slug: str) -> None:
        if session.get(User, user_id) is None:
            raise LookupError("User not found")
        if get_imported_exercise(slug) is None:
            raise LookupError("Exercise not found")

    def get_exercise_settings(self, session: Session, user_id: str, slug: str) -> ExerciseSettingsSchema | None:
        self._validate_settings_owner(session, user_id, slug)
        return remembered_settings(session, self._user_state(session, user_id, slug))

    def _store_settings(self, state: UserExerciseState, settings: ExerciseSettingsSchema) -> None:
        state.working_weight = settings.weight
        state.working_sets = settings.sets
        state.working_reps = settings.reps
        state.rest_seconds = settings.rest_seconds
        state.calibration_payload = {**(state.calibration_payload or {}),
                                     "lastSettings": settings.model_dump(by_alias=True)}

    def save_exercise_settings(self, session: Session, payload: ExerciseSettingsSaveSchema) -> ExerciseSettingsSchema:
        self._validate_settings_owner(session, payload.user_id, payload.exercise_slug)
        state = self._user_state(session, payload.user_id, payload.exercise_slug)
        if state is None:
            state = UserExerciseState(user_id=payload.user_id, exercise_slug=payload.exercise_slug)
            session.add(state)
        settings = ExerciseSettingsSchema.model_validate(payload.model_dump())
        self._store_settings(state, settings)
        state.calibration_payload = {**state.calibration_payload, "lastSettingsSavedAt": datetime.now(UTC).isoformat()}
        session.commit()
        return settings

    def save_set_feedback(self, session: Session, set_id: int, payload: SetFeedbackSchema) -> SetFeedbackSchema:
        from app.services.coach.history import latest_completed_set

        row = session.get(SetResult, set_id)
        exercise = session.get(ExerciseSession, row.exercise_session_id) if row else None
        if exercise is None or exercise.user_id != payload.user_id:
            raise LookupError("Set not found")
        latest = latest_completed_set(session, exercise)
        now = datetime.now(UTC)
        if (latest is None or latest.id != set_id or row.created_at is None
                or not 0 <= (now - row.created_at.replace(tzinfo=UTC)).total_seconds() <= 300):
            raise ValueError("Feedback window expired")
        metrics = dict(row.machine_metrics or {})
        # Legacy fabricated values are not preserved on first explicit input.
        prior = metrics.get("explicitFeedbackVersion") == 1
        row.subjective_effort = payload.subjective_effort if payload.subjective_effort is not None else (
            row.subjective_effort if prior else None)
        row.discomfort_level = payload.discomfort_level if payload.discomfort_level is not None else (
            row.discomfort_level if prior else None)
        metrics.update(explicitFeedbackVersion=1, explicitFeedbackAtMs=now.timestamp() * 1000)
        row.machine_metrics = metrics
        session.commit()
        return SetFeedbackSchema(user_id=payload.user_id, subjective_effort=row.subjective_effort,
                                 discomfort_level=row.discomfort_level)

    def save_set_result(self, session: Session, payload: SetResultSaveSchema) -> SavedSetResponseSchema:
        exercise_session = session.get(ExerciseSession, payload.exercise_session_id)
        if exercise_session is None:
            raise LookupError("Exercise session not found")

        set_result, updates = self._create_set_result(
            session,
            exercise_session=exercise_session,
            payload=payload,
        )
        # This endpoint observes a newly performed set, not a replayed final-session payload.
        set_result.machine_metrics = {**set_result.machine_metrics,
                                      "settingsPerformedAt": (payload.occurred_at or datetime.now(UTC)).isoformat()}
        session.expire(exercise_session, ["set_results"])
        self._remember_performed_settings(session, exercise_session, [set_result])
        notice = {
            "kind": "set_persisted", "user_id": exercise_session.user_id,
            "workout_session_id": exercise_session.workout_session_id,
            "exercise_session_id": exercise_session.id, "set_id": set_result.id,
            "set_ordinal": set_result.set_number, "actual_value": set_result.actual_value,
            "outcome": set_result.machine_metrics.get("completionStatus"),
        }
        session.commit()
        self.coach_observer.record(**notice)
        return SavedSetResponseSchema(
            set_id=set_result.id,
            exercise_session_id=exercise_session.id,
            fatigue=[SetFatigueDeltaSchema.model_validate(update.__dict__) for update in updates],
        )

    def _create_set_result(
        self,
        session: Session,
        *,
        exercise_session: ExerciseSession,
        payload: SetResultSaveSchema,
    ) -> tuple[SetResult, list[FatigueUpdate]]:
        occurred_at = payload.occurred_at or datetime.now(UTC)
        exercise = get_imported_exercise(exercise_session.exercise_slug)
        machine_metrics = dict(payload.machine_metrics or {})
        # Only the dedicated explicit-input endpoint can attest to feedback provenance.
        machine_metrics.pop("explicitFeedbackVersion", None)
        machine_metrics.pop("explicitFeedbackAtMs", None)
        machine_metrics.pop("settingsPerformedAt", None)
        machine_metrics.update(
            {
                "setType": payload.set_type,
                "targetMinReps": payload.target_min_reps,
                "targetMaxReps": payload.target_max_reps,
                "rir": payload.rir,
                "pain": payload.pain,
                "techniqueBreakdown": payload.technique_breakdown,
                "comment": payload.comment,
            }
        )
        machine_metrics = {key: value for key, value in machine_metrics.items() if value is not None}
        set_result = SetResult(
            exercise_session_id=exercise_session.id,
            set_number=payload.set_number,
            planned_value=payload.planned_value,
            actual_value=payload.actual_value,
            reps=payload.reps,
            weight_kg=payload.weight_kg,
            duration_seconds=payload.duration_seconds,
            tempo_label=payload.tempo_label,
            amplitude_percent=payload.amplitude_percent,
            rest_duration_seconds=payload.rest_duration_seconds,
            subjective_effort=payload.subjective_effort,
            discomfort_level=payload.discomfort_level,
            sync_label=payload.sync_label,
            machine_metrics=machine_metrics,
        )
        session.add(set_result)
        session.flush()
        if exercise and not equipment_affects_fatigue(exercise.equipment):
            updates = []
        else:
            updates = self.fatigue_service.build_set_updates(
                session,
                user_id=exercise_session.user_id,
                workout_session_id=exercise_session.workout_session_id,
                exercise_session_id=exercise_session.id,
                set_result_id=set_result.id,
                occurred_at=occurred_at,
                exercise_name=exercise_session.exercise_name,
                muscle_targets=[self._normalize_target(item) for item in exercise_session.muscle_targets],
                planned_value=payload.planned_value,
                actual_value=payload.actual_value,
                reps=payload.reps,
                weight_kg=payload.weight_kg,
                duration_seconds=payload.duration_seconds,
                amplitude_percent=payload.amplitude_percent,
                subjective_effort=payload.subjective_effort,
                discomfort_level=payload.discomfort_level,
                set_type=payload.set_type,
                completion_status=str(machine_metrics.get("completionStatus")) if machine_metrics.get("completionStatus") is not None else None,
                equipment=exercise.equipment if exercise else None,
            )
        return set_result, updates

    def reset_exercise_sessions(
        self,
        session: Session,
        payload: ExerciseSessionsResetRequestSchema,
    ) -> ExerciseSessionsResetResponseSchema:
        try:
            missing_ids: list[int] = []
            existing: list[ExerciseSessionCreateSchema] = []
            # Check every owner before any reset can flush deletions or metadata updates.
            with session.no_autoflush:
                for exercise in payload.exercises:
                    if exercise.exercise_session_id is None:
                        raise ValueError("Reset requires an exercise session ID")
                    row = session.get(ExerciseSession, exercise.exercise_session_id)
                    if row is None:
                        missing_ids.append(exercise.exercise_session_id)
                    elif row.user_id != exercise.user_id:
                        raise LookupError("Exercise session not found")
                    else:
                        existing.append(exercise)

            for exercise in existing:
                self.save_exercise_session(session, exercise, commit=False)
            session.commit()
        except Exception:
            session.rollback()
            raise
        return ExerciseSessionsResetResponseSchema(missing_exercise_session_ids=missing_ids)

    def save_exercise_session(
        self,
        session: Session,
        payload: ExerciseSessionCreateSchema,
        *,
        commit: bool = True,
    ) -> ExerciseSaveResult:
        status = ExerciseSessionStatus(payload.status)
        if payload.exercise_session_id is not None:
            exercise_session = session.get(ExerciseSession, payload.exercise_session_id)
            if exercise_session is None or exercise_session.user_id != payload.user_id:
                raise LookupError("Exercise session not found")
            if payload.sets or payload.reset_sets or status == ExerciseSessionStatus.skipped:
                self._clear_exercise_sets_and_fatigue(session, exercise_session)
            exercise_session.workout_session_id = payload.workout_session_id if payload.workout_session_id is not None else exercise_session.workout_session_id
            exercise_session.exercise_slug = payload.exercise_slug
            exercise_session.exercise_name = payload.exercise_name
            exercise_session.exercise_secondary_name = payload.exercise_secondary_name
            exercise_session.kind = RuntimeExerciseKind(payload.kind)
            exercise_session.order_index = payload.order_index
            exercise_session.status = status
            exercise_session.started_at = payload.started_at
            exercise_session.finished_at = payload.finished_at
            exercise_session.calibration_state = payload.calibration_state
            exercise_session.target_sets = payload.target_sets
            # Finalization by older callers must not erase the original plan.
            if "per_side" in payload.model_fields_set:
                exercise_session.per_side = payload.per_side
            if "planned_total" in payload.model_fields_set:
                exercise_session.planned_total = payload.planned_total
            exercise_session.training_mode = payload.training_mode
            exercise_session.training_day_type = payload.training_day_type
            exercise_session.recommendation = payload.recommendation
            exercise_session.muscle_targets = [target.model_dump() for target in payload.muscles]
        else:
            exercise_session = ExerciseSession(
                workout_session_id=payload.workout_session_id,
                user_id=payload.user_id,
                exercise_slug=payload.exercise_slug,
                exercise_name=payload.exercise_name,
                exercise_secondary_name=payload.exercise_secondary_name,
                kind=RuntimeExerciseKind(payload.kind),
                order_index=payload.order_index,
                status=status,
                started_at=payload.started_at,
                finished_at=payload.finished_at,
                calibration_state=payload.calibration_state,
                target_sets=payload.target_sets,
                per_side=payload.per_side,
                planned_total=payload.planned_total,
                training_mode=payload.training_mode,
                training_day_type=payload.training_day_type,
                recommendation=payload.recommendation,
                muscle_targets=[target.model_dump() for target in payload.muscles],
            )
            session.add(exercise_session)
        session.flush()

        pending_notices: list[dict[str, object]] = []
        for set_payload in payload.sets:
            saved_set, _ = self._create_set_result(
                session,
                exercise_session=exercise_session,
                payload=SetResultSaveSchema(
                    exercise_session_id=exercise_session.id,
                    **set_payload.model_dump(),
                ),
            )
            pending_notices.append({
                "kind": "set_persisted", "user_id": exercise_session.user_id,
                "workout_session_id": exercise_session.workout_session_id,
                "exercise_session_id": exercise_session.id, "set_id": saved_set.id,
                "set_ordinal": saved_set.set_number, "actual_value": saved_set.actual_value,
                "outcome": saved_set.machine_metrics.get("completionStatus"),
            })
            session.expire(exercise_session, ["set_results"])

        if not exercise_session.recommendation:
            exercise_session.recommendation = self._build_strength_recommendation(exercise_session, payload.training_mode, payload.training_day_type)
        self._sync_training_state(session, exercise_session)
        summary = self.build_exercise_summary(exercise_session)
        if status != ExerciseSessionStatus.in_progress:
            pending_notices.append({
                "kind": "exercise_finalized", "user_id": exercise_session.user_id,
                "workout_session_id": exercise_session.workout_session_id,
                "exercise_session_id": exercise_session.id, "outcome": status.value,
            })
        if commit:
            session.commit()
            for notice in pending_notices:
                self.coach_observer.record(**notice)
        return ExerciseSaveResult(exercise_session=exercise_session, summary=summary, coach_notices=tuple(pending_notices))

    def save_workout_session(self, session: Session, payload: WorkoutSessionCreateSchema) -> RuntimeWorkoutSummarySchema:
        if payload.workout_session_id is not None:
            workout_session = session.get(WorkoutSession, payload.workout_session_id)
            if workout_session is None or workout_session.user_id != payload.user_id:
                raise LookupError("Workout session not found")
            workout_session.source = RuntimeFlowSource(payload.source)
            workout_session.title = payload.title
            workout_session.subtitle = payload.subtitle
            workout_session.status = WorkoutSessionStatus(payload.status)
            workout_session.started_at = payload.started_at
            workout_session.finished_at = payload.finished_at
            workout_session.duration_seconds = payload.duration_seconds
            workout_session.feeling = FeelingLevel(payload.feeling) if payload.feeling else workout_session.feeling
            workout_session.discomfort = DiscomfortLevel(payload.discomfort) if payload.discomfort else workout_session.discomfort
            workout_session.notes = payload.notes
        else:
            workout_session = WorkoutSession(
                user_id=payload.user_id,
                source=RuntimeFlowSource(payload.source),
                title=payload.title,
                subtitle=payload.subtitle,
                status=WorkoutSessionStatus(payload.status),
                started_at=payload.started_at,
                finished_at=payload.finished_at,
                duration_seconds=payload.duration_seconds,
                feeling=FeelingLevel(payload.feeling) if payload.feeling else None,
                discomfort=DiscomfortLevel(payload.discomfort) if payload.discomfort else None,
                notes=payload.notes,
            )
            session.add(workout_session)
            session.flush()

        persist_plan(session, workout_session, payload)
        exercise_session_ids = set(payload.exercise_session_ids)
        nested_exercise_notices: list[dict[str, object]] = []
        for exercise in payload.exercises:
            if exercise.exercise_session_id is not None:
                exercise_session_ids.add(exercise.exercise_session_id)
                continue

            saved = self.save_exercise_session(session, exercise.model_copy(update={"workout_session_id": workout_session.id}), commit=False)
            nested_exercise_notices.extend(saved.coach_notices)

        if exercise_session_ids:
            linked_sessions = session.scalars(select(ExerciseSession).where(ExerciseSession.id.in_(exercise_session_ids))).all()
            found_ids = {item.id for item in linked_sessions}
            missing_ids = exercise_session_ids - found_ids
            if missing_ids:
                raise LookupError("Exercise session not found")
            for exercise_session in linked_sessions:
                if exercise_session.user_id != payload.user_id:
                    raise LookupError("Exercise session not found")
                exercise_session.workout_session_id = workout_session.id
                for event in session.scalars(select(MuscleFatigueEvent).where(MuscleFatigueEvent.exercise_session_id == exercise_session.id)):
                    event.workout_session_id = workout_session.id

        session.flush()
        if workout_session.status != WorkoutSessionStatus.in_progress:
            nested_exercise_notices.extend(self._finalize_open_exercises(session, workout_session))
            session.flush()
        summary = self.build_workout_summary(session, workout_session.id)
        notice = {
            "kind": "workout_finalized", "user_id": workout_session.user_id,
            "workout_session_id": workout_session.id, "outcome": workout_session.status.value,
        }
        session.commit()
        for nested_notice in nested_exercise_notices:
            self.coach_observer.record(**nested_notice)
        if payload.status != "in_progress":
            self.coach_observer.record(**notice)
        return summary

    def adjust_exercise_load(self, session: Session, payload: LoadAdjustmentRequestSchema) -> LoadAdjustmentResponseSchema:
        state = self._user_state(session, payload.user_id, payload.exercise_slug)
        if state is None:
            state = UserExerciseState(user_id=payload.user_id, exercise_slug=payload.exercise_slug)
            session.add(state)

        exercise = get_imported_exercise(payload.exercise_slug)
        remembered = remembered_settings(session, state)
        training_mode = payload.training_mode if payload.training_mode is not None else (
            remembered.training_mode if remembered else None)
        training_day_type = payload.training_day_type if payload.training_day_type is not None else (
            remembered.training_day_type if remembered else None)
        direction_sign = 1 if payload.direction == "increase" else -1
        factor = self._strength_weight_factor(training_mode, training_day_type)
        current_weight = payload.current_weight_kg if payload.current_weight_kg is not None else (
            remembered.weight if remembered else state.working_weight)
        weighted = (payload.kind == RuntimeExerciseKind.machine.value) or (current_weight is not None and current_weight > 0)
        current_sets = max(1, payload.current_sets or state.working_sets or 3)
        current_reps = max(1, payload.current_reps or (remembered.reps if remembered else state.working_reps) or (
            45 if payload.kind in {"timed", "stretch"} else 10))
        rest_seconds = payload.rest_seconds if payload.rest_seconds is not None else (
            state.rest_seconds if state.rest_seconds is not None else 60)

        if weighted:
            observed_weight = current_weight if current_weight is not None else self._default_working_weight(exercise)
            base_weight = observed_weight / factor
            display_step = self._load_adjustment_weight_step(training_mode, training_day_type)
            next_base_weight = max(0.0, self._round_weight(base_weight + direction_sign * (display_step / factor)))
            state.working_weight = next_base_weight
            state.working_sets = current_sets
            state.working_reps = current_reps
            state.rest_seconds = rest_seconds
            next_display_weight = self._round_weight(next_base_weight * factor)
            load_label = f"{next_display_weight:g} кг"
            weight_kg: float | None = next_display_weight
            reps = current_reps
        else:
            reps_step = self._load_adjustment_reps_step(payload.kind, training_mode)
            next_reps = max(1, current_reps + direction_sign * reps_step)
            state.working_weight = 0
            state.working_sets = current_sets
            state.working_reps = next_reps
            state.rest_seconds = rest_seconds
            load_label = f"{next_reps} сек" if payload.kind in {"timed", "stretch"} else f"{next_reps} повторов"
            weight_kg = None
            reps = next_reps

        self._store_settings(state, ExerciseSettingsSchema(
            weight=weight_kg if weight_kg is not None else 0, sets=current_sets, reps=reps,
            rest_seconds=rest_seconds, mode=remembered.mode if remembered else "Обычный вес",
            tempo=remembered.tempo if remembered else "Обычный",
            training_mode=training_mode, training_day_type=training_day_type,
        ))
        metadata = dict(state.calibration_payload or {})
        metadata["lastSettingsSavedAt"] = datetime.now(UTC).isoformat()
        metadata["lastManualAdjustment"] = {
            "direction": payload.direction,
            "trainingMode": training_mode,
            "trainingDayType": training_day_type,
            "loadLabel": load_label,
            "adjustedAt": datetime.now(UTC).isoformat(),
        }
        state.calibration_payload = metadata
        state.notes = self._load_adjustment_note(payload.direction, load_label, training_mode, training_day_type)
        session.commit()

        return LoadAdjustmentResponseSchema(
            user_id=payload.user_id,
            exercise_slug=payload.exercise_slug,
            direction=payload.direction,
            load_label=load_label,
            weight_kg=weight_kg,
            reps=reps,
            sets=state.working_sets,
            rest_seconds=state.rest_seconds,
            training_mode=training_mode,
            training_day_type=training_day_type,
            recommendation=state.notes,
        )

    def get_exercise_summary(self, session: Session, exercise_session_id: int) -> RuntimeExerciseSummarySchema:
        exercise_session = session.get(ExerciseSession, exercise_session_id)
        if exercise_session is None:
            raise LookupError("Exercise session not found")
        return self.build_exercise_summary(exercise_session)

    def get_workout_summary(self, session: Session, workout_session_id: int) -> RuntimeWorkoutSummarySchema:
        return self.build_workout_summary(session, workout_session_id)

    def delete_workout_session(self, session: Session, *, workout_session_id: int, user_id: str) -> None:
        """Remove a finished workout from history together with everything derived from it."""
        workout_session = session.get(WorkoutSession, workout_session_id)
        if workout_session is None or workout_session.user_id != user_id:
            raise LookupError("Workout session not found")
        if workout_session.status == WorkoutSessionStatus.in_progress:
            raise ValueError("Workout session is still in progress")

        exercises = list(workout_session.exercise_sessions)
        exercise_ids = [exercise.id for exercise in exercises]
        set_ids = [result.id for exercise in exercises for result in exercise.set_results]
        conditions = [MuscleFatigueEvent.workout_session_id == workout_session.id]
        if exercise_ids:
            conditions.append(MuscleFatigueEvent.exercise_session_id.in_(exercise_ids))
        if set_ids:
            conditions.append(MuscleFatigueEvent.set_result_id.in_(set_ids))
        events = list(session.scalars(select(MuscleFatigueEvent).where(MuscleFatigueEvent.user_id == user_id, or_(*conditions))))
        self._remove_fatigue_events(session, user_id, events)

        self._delete_exercise_history(session, user_id, exercises)
        session.execute(update(CoachLedgerRun).where(CoachLedgerRun.workout_id == workout_session.id).values(workout_id=None))
        session.delete(workout_session)
        session.flush()
        self._refresh_exercise_states(session, user_id, exercises)
        session.commit()

    def _delete_exercise_history(self, session: Session, user_id: str, exercises: list[ExerciseSession]) -> None:
        # History rows have no FK to the exercise session; _sync_training_state stamps them with
        # the exercise finish time or a set's creation time, so match on those per exercise slug.
        performed_by_slug: dict[str, set[datetime]] = {}
        for exercise in exercises:
            if not exercise.set_results:
                continue
            candidates = performed_by_slug.setdefault(exercise.exercise_slug, set())
            if exercise.finished_at is not None:
                candidates.add(self.fatigue_service.ensure_utc(exercise.finished_at))
            candidates.update(self.fatigue_service.ensure_utc(result.created_at) for result in exercise.set_results)
        if not performed_by_slug:
            return
        records = session.scalars(
            select(ExerciseHistoryRecord).where(
                ExerciseHistoryRecord.user_id == user_id,
                ExerciseHistoryRecord.exercise_slug.in_(list(performed_by_slug)),
            )
        ).all()
        for record in records:
            if self.fatigue_service.ensure_utc(record.performed_at) in performed_by_slug[record.exercise_slug]:
                session.delete(record)

    def _refresh_exercise_states(self, session: Session, user_id: str, exercises: list[ExerciseSession]) -> None:
        deleted_ids = {exercise.id for exercise in exercises}
        for slug in {exercise.exercise_slug for exercise in exercises}:
            state = self._user_state(session, user_id, slug)
            if state is None:
                continue
            metadata = dict(state.calibration_payload or {})
            last_result = metadata.get("lastResult")
            if not isinstance(last_result, dict) or last_result.get("exerciseSessionId") not in deleted_ids:
                continue
            metadata.pop("lastResult")
            state.calibration_payload = metadata
            state.last_performed_at = session.scalar(
                select(func.max(ExerciseHistoryRecord.performed_at)).where(
                    ExerciseHistoryRecord.user_id == user_id,
                    ExerciseHistoryRecord.exercise_slug == slug,
                )
            )

    def build_exercise_summary(self, exercise_session: ExerciseSession) -> RuntimeExerciseSummarySchema:
        results = sorted(exercise_session.set_results, key=lambda item: item.set_number)
        sided = self._exercise_is_sided(exercise_session)
        performed = self._performed_results(results) if sided else results
        completed, target, sides, target_sides = self._set_counts(exercise_session)
        sets_label = self._sided_sets_label(exercise_session) if sided else f"{completed} из {target}"
        total_value = sum(item.actual_value for item in performed)
        total_volume = sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in performed)
        amplitude_values = [item.amplitude_percent for item in results if item.amplitude_percent is not None]
        planned_total = exercise_session.planned_total
        if planned_total is None:
            planned_total = sum(item.planned_value for item in results) or exercise_session.target_sets * 10
        outcome = exercise_session.status.value if exercise_session.status in {ExerciseSessionStatus.aborted, ExerciseSessionStatus.partial, ExerciseSessionStatus.skipped} else "completed"
        kind = exercise_session.kind
        return RuntimeExerciseSummarySchema(
            exercise_session_id=exercise_session.id,
            outcome=outcome,
            exercise_id=f"{exercise_session.exercise_slug}-{exercise_session.id}",
            title=(
                "Упражнение пропущено"
                if exercise_session.status == ExerciseSessionStatus.skipped
                else "Упражнение сохранено частично"
                if exercise_session.status == ExerciseSessionStatus.partial
                else "Упражнение завершено досрочно"
                if exercise_session.status == ExerciseSessionStatus.aborted
                else "Группа завершена"
                if kind == RuntimeExerciseKind.group
                else "Упражнение завершено"
            ),
            subtitle=(
                f"{exercise_session.exercise_name} · пропуск сохранён"
                if exercise_session.status == ExerciseSessionStatus.skipped
                else f"{exercise_session.exercise_name} · {sets_label}"
                if sided
                else f"{exercise_session.exercise_name} · {len(results)} подхода выполнено"
            ),
            set_results=[
                RuntimeSetResultSchema(
                    set_number=item.set_number,
                    side=self._set_side(item),
                    round_number=self._metric_int(item.machine_metrics, "roundNumber"),
                    planned_value=item.planned_value,
                    actual_value=item.actual_value,
                    set_type=self._metric_str(item.machine_metrics, "setType"),
                    target_min_reps=self._metric_int(item.machine_metrics, "targetMinReps"),
                    target_max_reps=self._metric_int(item.machine_metrics, "targetMaxReps"),
                    reps=item.reps,
                    weight_kg=item.weight_kg,
                    rir=self._metric_int(item.machine_metrics, "rir"),
                    subjective_effort=item.subjective_effort,
                    discomfort_level=item.discomfort_level,
                    pain=bool(item.machine_metrics.get("pain", False)),
                    technique_breakdown=bool(item.machine_metrics.get("techniqueBreakdown", False)),
                    comment=self._metric_str(item.machine_metrics, "comment"),
                    volume_kg=(item.weight_kg or 0) * (item.reps or item.actual_value or 0) if item.weight_kg else None,
                    amplitude_percent=item.amplitude_percent,
                    tempo_label=item.tempo_label,
                    sync_label=item.sync_label,
                )
                for item in results
            ],
            totals=RuntimeExerciseTotalsSchema(
                sets_completed=sets_label,
                reps_or_time=f"{total_value} сек" if kind == RuntimeExerciseKind.timed else f"{total_value} повторов",
                volume=f"{int(round(total_volume))} кг" if kind == RuntimeExerciseKind.machine else (f"{total_value} сек" if kind == RuntimeExerciseKind.timed else f"{total_value} повторов"),
                best_set=self._best_set_label(performed),
                average_amplitude=f"{int(round(sum(amplitude_values) / len(amplitude_values)))}%" if amplitude_values else None,
                tempo="стабильный",
            ),
            plan_vs_fact=[
                RuntimePlanVsFactSchema(label="Стороны" if sided else "Подходы", plan=str(target_sides), fact=str(sides), delta=str(sides - target_sides)),
                RuntimePlanVsFactSchema(label="Секунды" if kind == RuntimeExerciseKind.timed else "Повторы", plan=f"{planned_total:g}", fact=str(total_value), delta=f"{total_value - planned_total:g}"),
                RuntimePlanVsFactSchema(label="Вес", plan=f"{results[0].weight_kg:.1f} кг" if results and results[0].weight_kg else "—", fact=f"{results[-1].weight_kg:.1f} кг" if results and results[-1].weight_kg else "—", delta="—"),
            ],
            recommendation=exercise_session.recommendation or ("Пропуск сохранён. Можно перейти к следующему упражнению без изменения нагрузки." if exercise_session.status == ExerciseSessionStatus.skipped else "Сохраните текущую технику и оцените восстановление перед следующим упражнением."),
            next_step_label="Открыть итог тренировки" if exercise_session.workout_session_id else "Перейти к следующему упражнению",
        )

    def build_workout_summary(self, session: Session, workout_session_id: int) -> RuntimeWorkoutSummarySchema:
        workout_session = session.get(WorkoutSession, workout_session_id)
        if workout_session is None:
            raise LookupError("Workout session not found")
        exercises = list(workout_session.exercise_sessions)
        set_results = [item for exercise in exercises for item in (
            self._performed_results(exercise.set_results) if self._exercise_is_sided(exercise) else exercise.set_results
        )]
        total_reps = sum(
            item.reps or item.actual_value or 0
            for exercise in exercises if exercise.kind != RuntimeExerciseKind.timed
            for item in (self._performed_results(exercise.set_results) if self._exercise_is_sided(exercise) else exercise.set_results)
        )
        total_volume = int(round(sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in set_results)))
        muscle_load = self._build_workout_muscle_load(exercises)
        outcome = workout_session.status.value if workout_session.status != WorkoutSessionStatus.in_progress else "partial"
        if outcome == "completed" and any(exercise.status in {ExerciseSessionStatus.partial, ExerciseSessionStatus.skipped, ExerciseSessionStatus.aborted} for exercise in exercises):
            outcome = "partial"
        completed_exercises = sum(1 for exercise in exercises if exercise.status == ExerciseSessionStatus.completed)
        target_exercises = max(len(exercises), completed_exercises)
        completed_sets = len(set_results)
        target_sets = sum(self._set_counts(exercise)[3] for exercise in exercises)
        sided = any(self._exercise_is_sided(exercise) for exercise in exercises)
        return RuntimeWorkoutSummarySchema(
            workout_session_id=workout_session.id,
            outcome=outcome,
            title="Тренировка завершена" if outcome != "aborted" else "Тренировка завершена частично",
            subtitle=f"{workout_session.title} · {max(workout_session.duration_seconds // 60, 1)} минут · {completed_exercises} из {target_exercises} упражнений выполнено",
            metrics=[
                RuntimeWorkoutMetricSchema(label="длительность", value=f"{max(workout_session.duration_seconds // 60, 1)} минут", hint="итог тренировки"),
                RuntimeWorkoutMetricSchema(label="упражнений", value=f"{completed_exercises} / {target_exercises}", hint="выполнено без пропусков"),
                RuntimeWorkoutMetricSchema(label="подходов / сторон" if sided else "подходов", value=f"{completed_sets} / {target_sets}", hint="стороны считаются отдельно" if sided else "засчитано"),
                RuntimeWorkoutMetricSchema(label="повторов", value=str(total_reps), hint="суммарно"),
                RuntimeWorkoutMetricSchema(label="объём", value=f"{total_volume} кг", hint="общий объём"),
            ],
            exercises=[
                RuntimeWorkoutExerciseRowSchema(
                    exercise_session_id=exercise.id,
                    exercise_slug=exercise.exercise_slug,
                    name=exercise.exercise_name,
                    result=self._format_exercise_result(exercise),
                    status=self._format_workout_row_status(exercise),
                    kind=exercise.kind.value,
                    current_load=self._format_current_load(exercise),
                    current_weight_kg=self._exercise_current_weight(exercise),
                    current_reps=self._exercise_current_reps(exercise),
                    current_sets=self._set_counts(exercise)[0],
                    rest_seconds=self._exercise_rest_seconds(exercise),
                    training_mode=exercise.training_mode,
                    training_day_type=exercise.training_day_type,
                )
                for exercise in exercises
            ],
            muscle_load=muscle_load,
            recommendation="Следующую тяжёлую тренировку на те же мышцы лучше провести через 48 часов." if outcome == "completed" else "Тренировка сохранена частично: пропущенные или незавершённые упражнения можно выполнить в следующий раз.",
            next_workout="Через 1–2 дня · Следующая рекомендованная тренировка",
            feeling=(workout_session.feeling or FeelingLevel.normal).value,
            discomfort=(workout_session.discomfort or DiscomfortLevel.none).value,
        )

    def _build_workout_muscle_load(self, exercises: list[ExerciseSession]) -> list[RuntimeWorkoutMuscleSchema]:
        totals: dict[str, float] = {}
        for exercise in exercises:
            exercise_volume = sum((result.weight_kg or 0) * (result.reps or result.actual_value or 0) for result in exercise.set_results)
            target_count = max(len(exercise.muscle_targets), 1)
            for target in exercise.muscle_targets:
                role_factor = {"primary": 1.0, "secondary": 0.6, "assisting": 0.35, "stabilizer": 0.2}.get(str(target.get("role", "secondary")), 0.6)
                totals[str(target.get("name", target.get("muscle_id", "Мышца")))] = totals.get(str(target.get("name", target.get("muscle_id", "Мышца"))), 0.0) + max(exercise_volume / max(target_count, 1), 20) * role_factor / 20
        return [
            RuntimeWorkoutMuscleSchema(
                name=name,
                score=min(100, int(round(value))),
                status="high" if value >= 60 else "medium" if value >= 35 else "light" if value >= 10 else "ready",
            )
            for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]

    def _format_exercise_result(self, exercise: ExerciseSession) -> str:
        results = exercise.set_results
        if exercise.status == ExerciseSessionStatus.skipped:
            return "пропущено"
        if not results:
            return "нет данных"
        sided = self._exercise_is_sided(exercise)
        if sided:
            results = self._performed_results(results)
        sets_label = self._sided_sets_label(exercise) if sided else f"{len(results)} подхода"
        total_reps = sum(item.reps or item.actual_value or 0 for item in results)
        total_volume = int(round(sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in results)))
        prefix = "частично • " if exercise.status == ExerciseSessionStatus.partial else ""
        if exercise.kind == RuntimeExerciseKind.timed:
            return f"{prefix}{sets_label} • {total_reps} сек"
        if total_volume > 0:
            return f"{prefix}{sets_label} • {total_reps} повторов • {total_volume} кг"
        return f"{prefix}{sets_label} • {total_reps} повторов"

    def _format_workout_row_status(self, exercise: ExerciseSession) -> str:
        if exercise.status == ExerciseSessionStatus.skipped:
            return "skipped"
        if exercise.status == ExerciseSessionStatus.partial:
            return "partial"
        if exercise.status == ExerciseSessionStatus.aborted:
            return "moved"
        return "done"

    def _format_current_load(self, exercise: ExerciseSession) -> str | None:
        weight = self._exercise_current_weight(exercise)
        reps = self._exercise_current_reps(exercise)
        completed, target, _, _ = self._set_counts(exercise)
        sets = completed if self._exercise_is_sided(exercise) else completed or target
        if exercise.kind == RuntimeExerciseKind.timed:
            return f"{sets}×{reps} сек" if reps else None
        if weight and reps:
            return f"{weight:g} кг × {sets}×{reps}"
        if reps:
            return f"{sets}×{reps}"
        return None

    def _exercise_current_weight(self, exercise: ExerciseSession) -> float | None:
        weights = [item.weight_kg for item in exercise.set_results if item.weight_kg is not None and item.weight_kg > 0]
        return max(weights) if weights else None

    def _exercise_current_reps(self, exercise: ExerciseSession) -> int | None:
        values = [item.reps or item.actual_value or 0 for item in exercise.set_results if (item.reps or item.actual_value or 0) > 0]
        if not values:
            return None
        return max(1, int(round(sum(values) / len(values))))

    def _exercise_rest_seconds(self, exercise: ExerciseSession) -> int | None:
        values = [item.rest_duration_seconds for item in exercise.set_results if item.rest_duration_seconds is not None]
        return values[-1] if values else None

    def _clear_exercise_sets_and_fatigue(self, session: Session, exercise_session: ExerciseSession) -> None:
        events = list(
            session.scalars(
                select(MuscleFatigueEvent).where(
                    MuscleFatigueEvent.exercise_session_id == exercise_session.id,
                    MuscleFatigueEvent.source == FatigueEventSource.exercise_set,
                )
            )
        )
        self._remove_fatigue_events(session, exercise_session.user_id, events)

        for set_result in list(exercise_session.set_results):
            session.delete(set_result)
        session.flush()
        session.expire(exercise_session, ["set_results"])

    def _remove_fatigue_events(self, session: Session, user_id: str, events: list[MuscleFatigueEvent]) -> None:
        """Delete fatigue events and subtract their still-remaining (decayed) load from the snapshots."""
        if not events:
            return
        now = datetime.now(UTC)
        decayed_deltas: dict[str, float] = {}
        for event in events:
            event_time = self.fatigue_service.ensure_utc(event.occurred_at)
            elapsed_hours = max(0.0, (now - event_time).total_seconds() / 3600)
            decayed_delta = self.fatigue_service.decay_score(event.fatigue_delta, elapsed_hours, event.recovery_half_life_hours)
            decayed_deltas[event.muscle_id] = decayed_deltas.get(event.muscle_id, 0.0) + decayed_delta
            session.delete(event)

        session.flush()
        for muscle_id, delta in decayed_deltas.items():
            snapshot = session.scalars(
                select(MuscleFatigueSnapshot).where(
                    MuscleFatigueSnapshot.user_id == user_id,
                    MuscleFatigueSnapshot.muscle_id == muscle_id,
                )
            ).first()
            if snapshot is None:
                continue
            self.fatigue_service.hydrate_snapshot(snapshot, now)
            snapshot.fatigue_score = max(0.0, snapshot.fatigue_score - delta)
            snapshot.last_load_at = session.scalar(
                select(func.max(MuscleFatigueEvent.occurred_at)).where(
                    MuscleFatigueEvent.user_id == user_id,
                    MuscleFatigueEvent.muscle_id == muscle_id,
                )
            )

    def _metric_str(self, metrics: dict[str, object], key: str) -> str | None:
        value = metrics.get(key)
        return str(value) if value is not None and value != "" else None

    def _set_side(self, result: SetResult) -> Literal["left", "right"] | None:
        side = result.machine_metrics.get("side")
        return side if side in ("left", "right") else None

    def _is_sided(self, results: list[SetResult]) -> bool:
        return any(self._set_side(item) is not None for item in results)

    def _exercise_is_sided(self, exercise: ExerciseSession) -> bool:
        # Preserve side-metadata detection for sessions saved before migration 0011.
        return exercise.per_side or self._is_sided(exercise.set_results)

    def _performed_results(self, results: list[SetResult]) -> list[SetResult]:
        return [item for item in results if item.machine_metrics.get("completionStatus") != "skipped" and item.actual_value > 0]

    def _logical_set_count(self, results: list[SetResult]) -> int:
        rounds: dict[int, set[str]] = {}
        for item in self._performed_results(results):
            side = self._set_side(item)
            if side is not None:
                round_number = self._metric_int(item.machine_metrics, "roundNumber") or (item.set_number + 1) // 2
                rounds.setdefault(round_number, set()).add(side)
        return sum(sides == {"left", "right"} for sides in rounds.values())

    def _set_counts(self, exercise: ExerciseSession) -> tuple[int, int, int, int]:
        """Completed/target logical sets and performed/target physical sides."""
        results = exercise.set_results
        target_sides = max(exercise.target_sets, len(results))
        if not self._exercise_is_sided(exercise):
            return len(results), target_sides, len(results), target_sides
        target = max((target_sides + 1) // 2, max(
            (self._metric_int(item.machine_metrics, "roundNumber") or (item.set_number + 1) // 2 for item in results),
            default=0,
        ))
        return self._logical_set_count(results), target, len(self._performed_results(results)), target * 2

    def _sided_sets_label(self, exercise: ExerciseSession) -> str:
        completed, target, sides, target_sides = self._set_counts(exercise)
        return f"{completed} из {target} пар · {sides} из {target_sides} сторон"

    def _metric_int(self, metrics: dict[str, object], key: str) -> int | None:
        value = metrics.get(key)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _best_set_label(self, results: list[SetResult]) -> str | None:
        if not results:
            return None
        best = max(results, key=lambda item: (item.weight_kg or 0) * (item.reps or item.actual_value or 0))
        reps = best.reps or best.actual_value or 0
        side = self._set_side(best)
        label = f"Подход {best.set_number}"
        if side is not None:
            round_number = self._metric_int(best.machine_metrics, "roundNumber") or (best.set_number + 1) // 2
            label = f"Подход {round_number}, {'левая' if side == 'left' else 'правая'} сторона"
        if best.weight_kg:
            volume = int(round(best.weight_kg * reps))
            return f"{label}: {best.weight_kg:g} кг × {reps} = {volume} кг"
        return f"{label}: {reps} повторов"

    def _build_strength_recommendation(self, exercise_session: ExerciseSession, training_mode: str | None, training_day_type: str | None) -> str:
        results = sorted(exercise_session.set_results, key=lambda item: item.set_number)
        work_results = [item for item in results if item.machine_metrics.get("setType") != "warmup"] or results
        if not work_results:
            return "Сохраните текущую технику и оцените восстановление перед следующим упражнением."

        if self._exercise_is_sided(exercise_session):
            completed, target, _, _ = self._set_counts(exercise_session)
            if completed < target:
                return "Не все пары сторон выполнены. Сохраните текущую нагрузку до выполнения обеих сторон."

        pain_or_bad_technique = any(
            bool(item.machine_metrics.get("pain"))
            or bool(item.machine_metrics.get("techniqueBreakdown"))
            or (item.discomfort_level is not None and item.discomfort_level >= 5)
            for item in work_results
        )
        high_fatigue = any((item.subjective_effort or 0) >= 9 for item in work_results)
        actual_reps = [item.reps or item.actual_value or 0 for item in work_results]
        max_targets = [self._metric_int(item.machine_metrics, "targetMaxReps") or item.planned_value for item in work_results]
        min_targets = [self._metric_int(item.machine_metrics, "targetMinReps") or item.planned_value for item in work_results]
        all_upper = all(actual >= target for actual, target in zip(actual_reps, max_targets, strict=False))
        any_below_min = any(actual < target for actual, target in zip(actual_reps, min_targets, strict=False))
        result_line = " / ".join(str(value) for value in actual_reps)

        if pain_or_bad_technique:
            return f"Ты выполнил {result_line}. Ты отметил боль или потерю техники. Не увеличивай вес на следующей тренировке."

        if training_mode == "double_progression":
            if all_upper and not high_fatigue:
                return f"Ты выполнил {result_line}. Можно увеличить вес на следующей тренировке."
            return f"Ты выполнил {result_line}. Оставь текущий вес и попробуй добавить повторения."

        if training_mode == "strength":
            if all_upper and not high_fatigue:
                return f"Ты выполнил {result_line}. Можно немного увеличить вес на следующей тренировке."
            return f"Ты выполнил {result_line}. Оставь текущий вес до уверенного выполнения всех подходов."

        if training_mode == "last_set_failure":
            failure_set = next((item for item in work_results if item.machine_metrics.get("setType") == "failure"), work_results[-1])
            failure_reps = failure_set.reps or failure_set.actual_value or 0
            failure_min = self._metric_int(failure_set.machine_metrics, "targetMinReps") or 8
            if failure_reps < failure_min:
                return f"Отказной подход: {failure_reps} повторов. Вес слишком тяжёлый, лучше немного снизить нагрузку."
            return f"Отказной подход: {failure_reps} повторов. Вес подобран нормально, в следующий раз остановись до потери техники."

        if training_mode == "technique_light" or (training_mode == "periodized_day" and training_day_type == "light"):
            return f"Ты выполнил {result_line}. Это лёгкая или техническая тренировка: пока оставь текущий вес и закрепи технику."

        if all_upper and not high_fatigue:
            return f"Ты выполнил {result_line}. Ты выполнил все подходы в верхней границе диапазона. На следующей тренировке можно немного увеличить вес."

        if any_below_min or high_fatigue:
            return f"Ты выполнил {result_line}. Пока оставь текущий вес. На следующей тренировке попробуй добавить 1–2 повтора."

        return f"Ты выполнил {result_line}. Вес подобран нормально: сохрани его и добирай повторы в заданном диапазоне."

    def _finalize_open_exercises(self, session: Session, workout_session: WorkoutSession) -> list[dict[str, object]]:
        """Close exercises left in progress by an early finish so their saved sets reach history and progress."""
        notices: list[dict[str, object]] = []
        open_exercises = session.scalars(
            select(ExerciseSession).where(
                ExerciseSession.workout_session_id == workout_session.id,
                ExerciseSession.status == ExerciseSessionStatus.in_progress,
            )
        ).all()
        for exercise_session in open_exercises:
            has_sets = bool(exercise_session.set_results)
            exercise_session.status = ExerciseSessionStatus.partial if has_sets else ExerciseSessionStatus.skipped
            exercise_session.finished_at = exercise_session.finished_at or workout_session.finished_at or datetime.now(UTC)
            if has_sets:
                if not exercise_session.recommendation:
                    exercise_session.recommendation = self._build_strength_recommendation(
                        exercise_session, exercise_session.training_mode, exercise_session.training_day_type
                    )
                self._sync_training_state(session, exercise_session)
            notices.append({
                "kind": "exercise_finalized", "user_id": exercise_session.user_id,
                "workout_session_id": workout_session.id,
                "exercise_session_id": exercise_session.id, "outcome": exercise_session.status.value,
            })
        return notices

    def _sync_training_state(self, session: Session, exercise_session: ExerciseSession) -> None:
        results = list(exercise_session.set_results)
        sided = self._exercise_is_sided(exercise_session)
        if sided:
            results = self._performed_results(results)
        if not results:
            return
        performed_at = exercise_session.finished_at or results[-1].created_at
        work_results = sorted((item for item in self._performed_results(results)
                       if item.machine_metrics.get("setType") != "warmup"), key=lambda item: item.set_number)
        total_reps = sum(item.reps or item.actual_value or 0 for item in results)
        total_volume = sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in results)
        weights = [item.weight_kg for item in work_results if item.weight_kg is not None]
        working_weight = weights[-1] if weights else 0
        average_work_reps = int(round(sum(item.reps or item.actual_value or 0 for item in work_results) / max(len(work_results), 1)))
        working_sets = self._logical_set_count(work_results) if sided else len(work_results)
        state_statement = select(UserExerciseState).where(
            UserExerciseState.user_id == exercise_session.user_id,
            UserExerciseState.exercise_slug == exercise_session.exercise_slug,
        )
        state = session.scalars(state_statement).first()
        if state is None:
            state = UserExerciseState(user_id=exercise_session.user_id, exercise_slug=exercise_session.exercise_slug)
            session.add(state)
        self._remember_performed_settings(session, exercise_session, results, state=state)
        state.last_performed_at = performed_at
        metadata = dict(state.calibration_payload or {})
        last_result = {
            "exerciseSessionId": exercise_session.id,
            "status": exercise_session.status.value,
            "trainingMode": exercise_session.training_mode,
            "trainingDayType": exercise_session.training_day_type,
            "sets": working_sets,
            "repsPerSet": max(1, average_work_reps),
            "totalReps": total_reps,
            "weightKg": working_weight,
            "baseWeightKg": state.working_weight,
            "volumeKg": total_volume,
            "performedAt": performed_at.isoformat() if performed_at else None,
        }
        if work_results:
            metadata["lastResult"] = last_result
        state.calibration_payload = metadata
        session.add(
            ExerciseHistoryRecord(
                user_id=exercise_session.user_id,
                exercise_slug=exercise_session.exercise_slug,
                performed_at=performed_at,
                weight_kg=working_weight,
                reps=total_reps,
                sets=self._logical_set_count(results) if sided else len(results),
                volume_kg=total_volume,
                rpe=max(item.subjective_effort or 6 for item in results),
                note=exercise_session.recommendation or "Автосохранение результата",
            )
        )

    def _remember_performed_settings(
        self, session: Session, exercise: ExerciseSession, results: list[SetResult],
        *, state: UserExerciseState | None = None,
    ) -> None:
        work = sorted((row for row in self._performed_results(results)
                       if row.machine_metrics.get("setType") != "warmup"), key=lambda row: row.set_number)
        if not work:
            return
        if state is None:
            state = self._user_state(session, exercise.user_id, exercise.exercise_slug)
        if state is None:
            state = UserExerciseState(user_id=exercise.user_id, exercise_slug=exercise.exercise_slug)
            session.add(state)
        metadata = dict(state.calibration_payload or {})
        latest = work[-1]
        observed_at = latest.machine_metrics.get("settingsPerformedAt") or exercise.started_at.isoformat()
        observed_time = self.fatigue_service.ensure_utc(datetime.fromisoformat(str(observed_at)))
        # A finalized old session must not undo a newer setup save/manual adjustment or set.
        for key in ("lastSettingsSavedAt", "lastSettingsWeightAt"):
            if metadata.get(key) and observed_time < self.fatigue_service.ensure_utc(datetime.fromisoformat(str(metadata[key]))):
                return
        settings = remembered_settings(session, state)
        # target_sets counts physical steps, including warmup steps; settings count working rounds.
        all_results = exercise.set_results
        warmup_count = sum(row.machine_metrics.get("setType") == "warmup" for row in all_results)
        physical_targets = max(exercise.target_sets, len(all_results)) - warmup_count
        target_sets = (physical_targets + 1) // 2 if self._exercise_is_sided(exercise) else physical_targets
        if settings is None:
            settings = ExerciseSettingsSchema(
                weight=state.working_weight if state.working_weight is not None and exercise.kind not in {
                    RuntimeExerciseKind.timed, RuntimeExerciseKind.stretch} else 0,
                sets=max(1, min(100, target_sets)), reps=max(1, min(86400, latest.planned_value)),
                rest_seconds=state.rest_seconds if state.rest_seconds is not None else 60,
                training_mode=exercise.training_mode, training_day_type=exercise.training_day_type,
                tempo=latest.tempo_label or "Обычный",
            )
        changes: dict[str, object] = {}
        if not metadata.get("lastSettingsSavedAt"):
            # Inferred snapshots follow the plan, never shortened actual performance.
            changes["reps"] = max(1, min(86400, latest.planned_value))
            changes["sets"] = max(1, min(100, target_sets))
        weighted = [row for row in work if row.weight_kg is not None]
        if weighted:
            changes["weight"] = weighted[-1].weight_kg
        rests = [row.rest_duration_seconds for row in work if row.rest_duration_seconds is not None]
        if rests:
            changes["rest_seconds"] = rests[-1]
        self._store_settings(state, settings.model_copy(update=changes))
        state.calibration_payload = {**state.calibration_payload, "lastSettingsWeightAt": str(observed_at)}

    def _user_state(self, session: Session, user_id: str, slug: str) -> UserExerciseState | None:
        return session.scalars(select(UserExerciseState).where(UserExerciseState.user_id == user_id, UserExerciseState.exercise_slug == slug)).first()

    def _default_working_weight(self, exercise: object | None) -> float:
        equipment = getattr(exercise, "equipment", None)
        if equipment == "Machine":
            return 45.0
        if equipment == "Barbell":
            return 40.0
        if equipment == "Dumbbell":
            return 20.0
        return 20.0

    def _round_weight(self, value: float) -> float:
        return round(value * 2) / 2

    def _strength_weight_factor(self, training_mode: str | None, training_day_type: str | None) -> float:
        if training_mode == "technique_light":
            return 0.7
        if training_mode == "strength_circuit":
            return 0.75
        if training_mode == "periodized_day":
            if training_day_type == "light":
                return 0.75
            if training_day_type == "medium":
                return 0.9
        return 1.0

    def _load_adjustment_weight_step(self, training_mode: str | None, training_day_type: str | None) -> float:
        if training_mode == "technique_light" or (training_mode == "periodized_day" and training_day_type == "light"):
            return 1.0
        if training_mode == "strength":
            return 2.5
        return 2.5

    def _load_adjustment_reps_step(self, kind: str | None, training_mode: str | None) -> int:
        if kind in {RuntimeExerciseKind.timed.value, RuntimeExerciseKind.stretch.value}:
            return 5
        if training_mode == "strength_circuit":
            return 2
        return 1

    def _load_adjustment_note(self, direction: str, load_label: str, training_mode: str | None, training_day_type: str | None) -> str:
        action = "повышена" if direction == "increase" else "понижена"
        mode_label = training_mode or "basic"
        if training_mode == "periodized_day" and training_day_type:
            mode_label = f"{mode_label}/{training_day_type}"
        return f"Нагрузка {action} для следующего выполнения: {load_label}. Режим: {mode_label}."

    def _normalize_target(self, target: dict[str, object]) -> dict[str, str]:
        return {
            "muscle_id": str(target.get("muscle_id", "unknown")),
            "name": str(target.get("name", target.get("muscle_id", "unknown"))),
            "role": str(target.get("role", "secondary")),
        }