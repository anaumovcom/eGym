from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, MuscleFatigueEvent, MuscleFatigueSnapshot, SetResult, WorkoutSession
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
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
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
    SetResultSaveSchema,
    WorkoutSessionCreateSchema,
)
from app.services.exercise_library import get_imported_exercise
from app.services.fatigue_service import FatigueService, FatigueUpdate


@dataclass
class ExerciseSaveResult:
    exercise_session: ExerciseSession
    summary: RuntimeExerciseSummarySchema


class RuntimeService:
    def __init__(self) -> None:
        self.fatigue_service = FatigueService()

    def save_set_result(self, session: Session, payload: SetResultSaveSchema) -> SavedSetResponseSchema:
        exercise_session = session.get(ExerciseSession, payload.exercise_session_id)
        if exercise_session is None:
            raise LookupError("Exercise session not found")

        set_result, updates = self._create_set_result(
            session,
            exercise_session=exercise_session,
            payload=payload,
        )
        session.commit()
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
        if exercise and exercise.equipment == "Recovery":
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
            )
        return set_result, updates

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
            if payload.sets or status == ExerciseSessionStatus.skipped:
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
                training_mode=payload.training_mode,
                training_day_type=payload.training_day_type,
                recommendation=payload.recommendation,
                muscle_targets=[target.model_dump() for target in payload.muscles],
            )
            session.add(exercise_session)
        session.flush()

        for set_payload in payload.sets:
            self._create_set_result(
                session,
                exercise_session=exercise_session,
                payload=SetResultSaveSchema(
                    exercise_session_id=exercise_session.id,
                    **set_payload.model_dump(),
                ),
            )
            session.expire(exercise_session, ["set_results"])

        if not exercise_session.recommendation:
            exercise_session.recommendation = self._build_strength_recommendation(exercise_session, payload.training_mode, payload.training_day_type)
        self._sync_training_state(session, exercise_session)
        summary = self.build_exercise_summary(exercise_session)
        if commit:
            session.commit()
        return ExerciseSaveResult(exercise_session=exercise_session, summary=summary)

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

        exercise_session_ids = set(payload.exercise_session_ids)
        for exercise in payload.exercises:
            if exercise.exercise_session_id is not None:
                exercise_session_ids.add(exercise.exercise_session_id)
                continue

            self.save_exercise_session(session, exercise.model_copy(update={"workout_session_id": workout_session.id}), commit=False)

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
        summary = self.build_workout_summary(session, workout_session.id)
        session.commit()
        return summary

    def adjust_exercise_load(self, session: Session, payload: LoadAdjustmentRequestSchema) -> LoadAdjustmentResponseSchema:
        state = self._user_state(session, payload.user_id, payload.exercise_slug)
        if state is None:
            state = UserExerciseState(user_id=payload.user_id, exercise_slug=payload.exercise_slug)
            session.add(state)

        exercise = get_imported_exercise(payload.exercise_slug)
        direction_sign = 1 if payload.direction == "increase" else -1
        factor = self._strength_weight_factor(payload.training_mode, payload.training_day_type)
        current_weight = payload.current_weight_kg if payload.current_weight_kg is not None else state.working_weight
        weighted = (payload.kind == RuntimeExerciseKind.machine.value) or (current_weight is not None and current_weight > 0)
        current_sets = max(1, payload.current_sets or state.working_sets or 3)
        current_reps = max(1, payload.current_reps or state.working_reps or (45 if payload.kind == RuntimeExerciseKind.timed.value else 10))
        rest_seconds = max(15, payload.rest_seconds or state.rest_seconds or 60)

        if weighted:
            observed_weight = current_weight if current_weight is not None and current_weight > 0 else self._default_working_weight(exercise)
            base_weight = state.working_weight if state.working_weight is not None and state.working_weight > 0 else observed_weight / factor
            display_step = self._load_adjustment_weight_step(payload.training_mode, payload.training_day_type)
            next_base_weight = max(0.0, self._round_weight(base_weight + direction_sign * (display_step / factor)))
            state.working_weight = next_base_weight
            state.working_sets = current_sets
            state.working_reps = state.working_reps or current_reps * current_sets
            state.rest_seconds = rest_seconds
            next_display_weight = self._round_weight(next_base_weight * factor)
            load_label = f"{next_display_weight:g} кг"
            weight_kg: float | None = next_display_weight
            reps = current_reps
        else:
            reps_step = self._load_adjustment_reps_step(payload.kind, payload.training_mode)
            next_reps = max(1, current_reps + direction_sign * reps_step)
            state.working_weight = 0
            state.working_sets = current_sets
            state.working_reps = next_reps * current_sets
            state.rest_seconds = rest_seconds
            load_label = f"{next_reps} сек" if payload.kind == RuntimeExerciseKind.timed.value else f"{next_reps} повторов"
            weight_kg = None
            reps = next_reps

        metadata = dict(state.calibration_payload or {})
        metadata["lastManualAdjustment"] = {
            "direction": payload.direction,
            "trainingMode": payload.training_mode,
            "trainingDayType": payload.training_day_type,
            "loadLabel": load_label,
            "adjustedAt": datetime.now(UTC).isoformat(),
        }
        state.calibration_payload = metadata
        state.notes = self._load_adjustment_note(payload.direction, load_label, payload.training_mode, payload.training_day_type)
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
            training_mode=payload.training_mode,
            training_day_type=payload.training_day_type,
            recommendation=state.notes,
        )

    def get_exercise_summary(self, session: Session, exercise_session_id: int) -> RuntimeExerciseSummarySchema:
        exercise_session = session.get(ExerciseSession, exercise_session_id)
        if exercise_session is None:
            raise LookupError("Exercise session not found")
        return self.build_exercise_summary(exercise_session)

    def get_workout_summary(self, session: Session, workout_session_id: int) -> RuntimeWorkoutSummarySchema:
        return self.build_workout_summary(session, workout_session_id)

    def build_exercise_summary(self, exercise_session: ExerciseSession) -> RuntimeExerciseSummarySchema:
        results = sorted(exercise_session.set_results, key=lambda item: item.set_number)
        total_value = sum(item.actual_value for item in results)
        total_volume = sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in results)
        amplitude_values = [item.amplitude_percent for item in results if item.amplitude_percent is not None]
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
                else f"{exercise_session.exercise_name} · {len(results)} подхода выполнено"
            ),
            set_results=[
                RuntimeSetResultSchema(
                    set_number=item.set_number,
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
                sets_completed=f"{len(results)} из {max(exercise_session.target_sets, len(results))}",
                reps_or_time=f"{total_value} сек" if kind == RuntimeExerciseKind.timed else f"{total_value} повторов",
                volume=f"{int(round(total_volume))} кг" if kind == RuntimeExerciseKind.machine else (f"{total_value} сек" if kind == RuntimeExerciseKind.timed else f"{total_value} повторов"),
                best_set=self._best_set_label(results),
                average_amplitude=f"{int(round(sum(amplitude_values) / len(amplitude_values)))}%" if amplitude_values else None,
                tempo="стабильный",
            ),
            plan_vs_fact=[
                RuntimePlanVsFactSchema(label="Подходы", plan=str(max(exercise_session.target_sets, len(results))), fact=str(len(results)), delta=str(len(results) - max(exercise_session.target_sets, len(results)))),
                RuntimePlanVsFactSchema(label="Секунды" if kind == RuntimeExerciseKind.timed else "Повторы", plan=str(planned_total), fact=str(total_value), delta=str(total_value - planned_total)),
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
        set_results = [item for exercise in exercises for item in exercise.set_results]
        total_reps = sum(item.reps or item.actual_value or 0 for item in set_results)
        total_volume = int(round(sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in set_results)))
        muscle_load = self._build_workout_muscle_load(exercises)
        outcome = workout_session.status.value if workout_session.status != WorkoutSessionStatus.in_progress else "partial"
        if outcome == "completed" and any(exercise.status in {ExerciseSessionStatus.partial, ExerciseSessionStatus.skipped, ExerciseSessionStatus.aborted} for exercise in exercises):
            outcome = "partial"
        completed_exercises = sum(1 for exercise in exercises if exercise.status == ExerciseSessionStatus.completed)
        target_exercises = max(len(exercises), completed_exercises)
        completed_sets = len(set_results)
        target_sets = sum(max(exercise.target_sets, len(exercise.set_results)) for exercise in exercises)
        return RuntimeWorkoutSummarySchema(
            workout_session_id=workout_session.id,
            outcome=outcome,
            title="Тренировка завершена" if outcome != "aborted" else "Тренировка завершена частично",
            subtitle=f"{workout_session.title} · {max(workout_session.duration_seconds // 60, 1)} минут · {completed_exercises} из {target_exercises} упражнений выполнено",
            metrics=[
                RuntimeWorkoutMetricSchema(label="длительность", value=f"{max(workout_session.duration_seconds // 60, 1)} минут", hint="итог тренировки"),
                RuntimeWorkoutMetricSchema(label="упражнений", value=f"{completed_exercises} / {target_exercises}", hint="выполнено без пропусков"),
                RuntimeWorkoutMetricSchema(label="подходов", value=f"{completed_sets} / {target_sets}", hint="засчитано"),
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
                    current_sets=len(exercise.set_results),
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
        total_reps = sum(item.reps or item.actual_value or 0 for item in results)
        total_volume = int(round(sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in results)))
        prefix = "частично • " if exercise.status == ExerciseSessionStatus.partial else ""
        if exercise.kind == RuntimeExerciseKind.timed:
            return f"{prefix}{len(results)} подхода • {total_reps} сек"
        if total_volume > 0:
            return f"{prefix}{len(results)} подхода • {total_reps} повторов • {total_volume} кг"
        return f"{prefix}{len(results)} подхода • {total_reps} повторов"

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
        sets = len(exercise.set_results) or exercise.target_sets
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
        if events:
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
                        MuscleFatigueSnapshot.user_id == exercise_session.user_id,
                        MuscleFatigueSnapshot.muscle_id == muscle_id,
                    )
                ).first()
                if snapshot is None:
                    continue
                self.fatigue_service.hydrate_snapshot(snapshot, now)
                snapshot.fatigue_score = max(0.0, snapshot.fatigue_score - delta)
                snapshot.last_load_at = session.scalar(
                    select(func.max(MuscleFatigueEvent.occurred_at)).where(
                        MuscleFatigueEvent.user_id == exercise_session.user_id,
                        MuscleFatigueEvent.muscle_id == muscle_id,
                    )
                )

        for set_result in list(exercise_session.set_results):
            session.delete(set_result)
        session.flush()
        session.expire(exercise_session, ["set_results"])

    def _metric_str(self, metrics: dict[str, object], key: str) -> str | None:
        value = metrics.get(key)
        return str(value) if value is not None and value != "" else None

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
        if best.weight_kg:
            volume = int(round(best.weight_kg * reps))
            return f"Подход {best.set_number}: {best.weight_kg:g} кг × {reps} = {volume} кг"
        return f"Подход {best.set_number}: {reps} повторов"

    def _build_strength_recommendation(self, exercise_session: ExerciseSession, training_mode: str | None, training_day_type: str | None) -> str:
        results = sorted(exercise_session.set_results, key=lambda item: item.set_number)
        work_results = [item for item in results if item.machine_metrics.get("setType") != "warmup"] or results
        if not work_results:
            return "Сохраните текущую технику и оцените восстановление перед следующим упражнением."

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

    def _sync_training_state(self, session: Session, exercise_session: ExerciseSession) -> None:
        results = list(exercise_session.set_results)
        if not results:
            return
        performed_at = exercise_session.finished_at or results[-1].created_at
        work_results = [item for item in results if item.machine_metrics.get("setType") != "warmup"] or results
        total_reps = sum(item.reps or item.actual_value or 0 for item in results)
        total_volume = sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in results)
        working_weight = max((item.weight_kg or 0) for item in work_results)
        average_work_reps = int(round(sum(item.reps or item.actual_value or 0 for item in work_results) / max(len(work_results), 1)))
        mode_factor = self._strength_weight_factor(exercise_session.training_mode, exercise_session.training_day_type)
        state_statement = select(UserExerciseState).where(
            UserExerciseState.user_id == exercise_session.user_id,
            UserExerciseState.exercise_slug == exercise_session.exercise_slug,
        )
        state = session.scalars(state_statement).first()
        if state is None:
            state = UserExerciseState(user_id=exercise_session.user_id, exercise_slug=exercise_session.exercise_slug)
            session.add(state)
        state.working_weight = self._round_weight(working_weight / mode_factor) if working_weight > 0 else state.working_weight
        state.working_sets = len(work_results)
        state.working_reps = max(1, total_reps)
        rest_values = [item.rest_duration_seconds for item in results if item.rest_duration_seconds is not None]
        if rest_values:
            state.rest_seconds = rest_values[-1]
        state.last_performed_at = performed_at
        metadata = dict(state.calibration_payload or {})
        metadata["lastResult"] = {
            "exerciseSessionId": exercise_session.id,
            "status": exercise_session.status.value,
            "trainingMode": exercise_session.training_mode,
            "trainingDayType": exercise_session.training_day_type,
            "sets": len(work_results),
            "repsPerSet": max(1, average_work_reps),
            "totalReps": total_reps,
            "weightKg": working_weight,
            "baseWeightKg": state.working_weight,
            "volumeKg": total_volume,
            "performedAt": performed_at.isoformat() if performed_at else None,
        }
        state.calibration_payload = metadata
        session.add(
            ExerciseHistoryRecord(
                user_id=exercise_session.user_id,
                exercise_slug=exercise_session.exercise_slug,
                performed_at=performed_at,
                weight_kg=working_weight,
                reps=total_reps,
                sets=len(results),
                volume_kg=total_volume,
                rpe=max(item.subjective_effort or 6 for item in results),
                note=exercise_session.recommendation or "Автосохранение результата",
            )
        )

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
        if kind == RuntimeExerciseKind.timed.value:
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