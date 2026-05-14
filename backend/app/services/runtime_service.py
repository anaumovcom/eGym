from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, SetResult, WorkoutSession
from app.models.enums import (
    DiscomfortLevel,
    ExerciseSessionStatus,
    FeelingLevel,
    RuntimeExerciseKind,
    RuntimeFlowSource,
    WorkoutSessionStatus,
)
from app.models.training import ExerciseHistoryRecord, UserExerciseState
from app.schemas.runtime import (
    ExerciseSessionCreateSchema,
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
            machine_metrics=payload.machine_metrics,
        )
        session.add(set_result)
        session.flush()
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
        )
        return set_result, updates

    def save_exercise_session(
        self,
        session: Session,
        payload: ExerciseSessionCreateSchema,
        *,
        commit: bool = True,
    ) -> ExerciseSaveResult:
        exercise_session = ExerciseSession(
            workout_session_id=payload.workout_session_id,
            user_id=payload.user_id,
            exercise_slug=payload.exercise_slug,
            exercise_name=payload.exercise_name,
            exercise_secondary_name=payload.exercise_secondary_name,
            kind=RuntimeExerciseKind(payload.kind),
            order_index=payload.order_index,
            status=ExerciseSessionStatus(payload.status),
            started_at=payload.started_at,
            finished_at=payload.finished_at,
            calibration_state=payload.calibration_state,
            target_sets=payload.target_sets,
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

        self._sync_training_state(session, exercise_session)
        summary = self.build_exercise_summary(exercise_session)
        if commit:
            session.commit()
        return ExerciseSaveResult(exercise_session=exercise_session, summary=summary)

    def save_workout_session(self, session: Session, payload: WorkoutSessionCreateSchema) -> RuntimeWorkoutSummarySchema:
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

        for exercise in payload.exercises:
            self.save_exercise_session(
                session,
                exercise.model_copy(update={"workout_session_id": workout_session.id}),
                commit=False,
            )
        session.flush()
        summary = self.build_workout_summary(session, workout_session.id)
        session.commit()
        return summary

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
        outcome = "aborted" if exercise_session.status == ExerciseSessionStatus.aborted else "completed"
        kind = exercise_session.kind
        return RuntimeExerciseSummarySchema(
            exercise_session_id=exercise_session.id,
            outcome=outcome,
            exercise_id=f"{exercise_session.exercise_slug}-{exercise_session.id}",
            title="Группа завершена" if kind == RuntimeExerciseKind.group else "Упражнение завершено",
            subtitle=f"{exercise_session.exercise_name} · {len(results)} подхода выполнено",
            set_results=[
                RuntimeSetResultSchema(
                    set_number=item.set_number,
                    planned_value=item.planned_value,
                    actual_value=item.actual_value,
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
                average_amplitude=f"{int(round(sum(amplitude_values) / len(amplitude_values)))}%" if amplitude_values else None,
                tempo="стабильный",
            ),
            plan_vs_fact=[
                RuntimePlanVsFactSchema(label="Подходы", plan=str(max(exercise_session.target_sets, len(results))), fact=str(len(results)), delta=str(len(results) - max(exercise_session.target_sets, len(results)))),
                RuntimePlanVsFactSchema(label="Секунды" if kind == RuntimeExerciseKind.timed else "Повторы", plan=str(planned_total), fact=str(total_value), delta=str(total_value - planned_total)),
                RuntimePlanVsFactSchema(label="Вес", plan=f"{results[0].weight_kg:.1f} кг" if results and results[0].weight_kg else "—", fact=f"{results[-1].weight_kg:.1f} кг" if results and results[-1].weight_kg else "—", delta="—"),
            ],
            recommendation=exercise_session.recommendation or "Сохраните текущую технику и оцените восстановление перед следующим упражнением.",
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
        return RuntimeWorkoutSummarySchema(
            workout_session_id=workout_session.id,
            outcome=outcome,
            title="Тренировка завершена" if outcome != "aborted" else "Тренировка завершена частично",
            subtitle=f"{workout_session.title} · {max(workout_session.duration_seconds // 60, 1)} минут · {len(exercises)} упражнений выполнено",
            metrics=[
                RuntimeWorkoutMetricSchema(label="длительность", value=f"{max(workout_session.duration_seconds // 60, 1)} минут", hint="итог тренировки"),
                RuntimeWorkoutMetricSchema(label="упражнений", value=f"{len(exercises)} / {len(exercises)}", hint="выполнено"),
                RuntimeWorkoutMetricSchema(label="подходов", value=f"{len(set_results)}", hint="выполнено"),
                RuntimeWorkoutMetricSchema(label="повторов", value=str(total_reps), hint="суммарно"),
                RuntimeWorkoutMetricSchema(label="объём", value=f"{total_volume} кг", hint="общий объём"),
            ],
            exercises=[
                RuntimeWorkoutExerciseRowSchema(
                    name=exercise.exercise_name,
                    result=self._format_exercise_result(exercise),
                    status="moved" if exercise.status == ExerciseSessionStatus.skipped else "done",
                )
                for exercise in exercises
            ],
            muscle_load=muscle_load,
            recommendation="Следующую тяжёлую тренировку на те же мышцы лучше провести через 48 часов.",
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
        if not results:
            return "нет данных"
        total_reps = sum(item.reps or item.actual_value or 0 for item in results)
        total_volume = int(round(sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in results)))
        if exercise.kind == RuntimeExerciseKind.timed:
            return f"{len(results)} подхода • {total_reps} сек"
        if total_volume > 0:
            return f"{len(results)} подхода • {total_reps} повторов • {total_volume} кг"
        return f"{len(results)} подхода • {total_reps} повторов"

    def _sync_training_state(self, session: Session, exercise_session: ExerciseSession) -> None:
        results = list(exercise_session.set_results)
        if not results:
            return
        performed_at = exercise_session.finished_at or results[-1].created_at
        total_reps = sum(item.reps or item.actual_value or 0 for item in results)
        total_volume = sum((item.weight_kg or 0) * (item.reps or item.actual_value or 0) for item in results)
        working_weight = max((item.weight_kg or 0) for item in results)
        state_statement = select(UserExerciseState).where(
            UserExerciseState.user_id == exercise_session.user_id,
            UserExerciseState.exercise_slug == exercise_session.exercise_slug,
        )
        state = session.scalars(state_statement).first()
        if state is None:
            state = UserExerciseState(user_id=exercise_session.user_id, exercise_slug=exercise_session.exercise_slug)
            session.add(state)
        state.working_weight = working_weight if working_weight > 0 else state.working_weight
        state.working_sets = len(results)
        state.working_reps = total_reps
        state.last_performed_at = performed_at
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

    def _normalize_target(self, target: dict[str, object]) -> dict[str, str]:
        return {
            "muscle_id": str(target.get("muscle_id", "unknown")),
            "name": str(target.get("name", target.get("muscle_id", "unknown"))),
            "role": str(target.get("role", "secondary")),
        }