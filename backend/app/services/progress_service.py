from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import MuscleFatigueEvent, MuscleFatigueSnapshot, ProgressPhoto, WorkoutSession
from app.models.enums import ProgressPeriod, WorkoutSessionStatus
from app.models.profile import BodyMeasurement
from app.models.training import ExerciseHistoryRecord
from app.schemas.analytics import (
    AchievementSchema,
    AchievementsResponseSchema,
    BodyMeasurementCreateSchema,
    BodyMeasurementListResponseSchema,
    ChartPointSchema,
    FatigueDataSchema,
    FatigueExerciseSuggestionSchema,
    FatigueHistoryPointSchema,
    FatigueHistoryResponseSchema,
    FatigueImpactSchema,
    FatigueMuscleSchema,
    MetricCardSchema,
    MuscleCardSchema,
    ProgressBodyMeasurementRowSchema,
    ProgressDataSchema,
    ProgressExerciseDetailsSchema,
    ProgressExerciseHistoryRowSchema,
    ProgressExerciseOptionSchema,
    ProgressPhotoAssetSchema,
    ProgressPhotoEntrySchema,
    ProgressPhotoListResponseSchema,
    ProgressPhotoViewSchema,
)
from app.schemas.machine import MachineHealthSchema
from app.schemas.user import BodyMeasurementSchema
from app.services.exercise_library import get_imported_exercise
from app.services.fatigue_service import FatigueService
from app.services.muscle_catalog import get_muscle_definition
from app.services.machine_service import MachineService


class ProgressService:
    def __init__(self) -> None:
        self.fatigue_service = FatigueService()
        self.machine_service = MachineService()

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def get_progress(
        self,
        session: Session,
        *,
        user_id: str,
        period: str,
        exercise_slug: str | None,
    ) -> ProgressDataSchema:
        machine = self.machine_service.get_machine_health(session, "ready")
        since = self._period_start(period)
        exercise_rows = self._exercise_history_rows(session, user_id, since)
        workout_rows = self._workout_rows(session, user_id, since)
        measurements = self._measurement_rows(session, user_id)
        photos = self._photo_rows(session, user_id)
        fatigue_rows = self.fatigue_service.list_current_scores(session, user_id)
        empty = len(exercise_rows) == 0
        selected_slug = exercise_slug or (exercise_rows[0].exercise_slug if exercise_rows else "barbell-floor-press")
        selected_history = [row for row in exercise_rows if row.exercise_slug == selected_slug]
        selected_exercise = self._build_selected_exercise(selected_slug, selected_history, fatigue_rows)
        muscle_cards = self._fatigue_cards(fatigue_rows)
        return ProgressDataSchema(
            machine=MachineHealthSchema.model_validate(machine),
            updated_at="сейчас",
            period_label=self._period_label(period),
            title="Прогресс",
            subtitle="Данные строятся по сохранённым тренировкам, фото и измерениям.",
            summary_cards=self._summary_cards(workout_rows, exercise_rows),
            summary_volume_series=self._volume_series(exercise_rows),
            main_progress=self._main_progress(exercise_rows, muscle_cards),
            improvements=self._improvements(exercise_rows),
            period_summary=[
                MetricCardSchema(label="Период", value=self._period_label(period)),
                MetricCardSchema(label="Тренировок", value=str(len(workout_rows))),
                MetricCardSchema(label="Упражнений", value=str(len(exercise_rows))),
                MetricCardSchema(label="Фото", value=str(len(photos))),
            ],
            recommendation="Продолжайте отслеживать объём и фотофиксацию, чтобы видеть устойчивую динамику по нагрузке и телу.",
            exercise_options=self._exercise_options(exercise_rows),
            selected_exercise=selected_exercise,
            strength_cards=self._strength_cards(exercise_rows),
            volume_top_exercises=self._volume_top_exercises(exercise_rows),
            regularity_cards=self._regularity_cards(workout_rows),
            activity_calendar=self._activity_calendar(workout_rows),
            weekly_training_series=self._weekly_training_series(workout_rows),
            weekly_minute_series=self._weekly_minute_series(workout_rows),
            day_distribution=self._day_distribution(workout_rows),
            recent_weeks=self._recent_weeks(workout_rows),
            muscle_load=muscle_cards,
            muscle_split=[
                {"rank": index + 1, "name": item.name, "status": item.status, "value": f"{item.score} / 100"}
                for index, item in enumerate(muscle_cards)
            ],
            muscle_coverage=[{"name": item.name, "count": f"{item.score} pts"} for item in muscle_cards],
            muscle_recommendation="Сравнивайте текущую усталость с прогрессом силы, чтобы не перегружать одни и те же зоны подряд.",
            body_cards=self._body_cards(measurements),
            body_weight_series=self._body_weight_series(measurements),
            body_measurements=self._body_measurement_rows(measurements),
            smart_scale={
                "connected": bool(measurements),
                "label": "Умные весы подключены" if measurements else "Нет синхронизации весов",
                "hint": "Последние данные сохранены в backend." if measurements else "Можно ввести измерения вручную.",
            },
            photo_entries=self._photo_entries(photos),
            photo_stats=self._photo_stats(photos),
            photo_recommendation="Сохраняйте одинаковые ракурсы раз в 2–4 недели для корректного сравнения.",
            empty_state={
                "title": "Недостаточно данных для аналитики",
                "description": "Сохраните тренировку, измерение или фото, и здесь появятся графики и рекомендации.",
            }
            if empty
            else None,
        )

    def get_fatigue(self, session: Session, *, user_id: str, mode: str) -> FatigueDataSchema:
        machine = self.machine_service.get_machine_health(session, "ready")
        snapshots = self.fatigue_service.list_current_scores(session, user_id)
        history = self._fatigue_event_lookup(session, user_id)
        muscles = []
        for snapshot in sorted(snapshots, key=lambda item: item.fatigue_score, reverse=True):
            impacts = history.get(snapshot.muscle_id, [])[:3]
            definition = get_muscle_definition(snapshot.muscle_id)
            muscles.append(
                FatigueMuscleSchema(
                    id=snapshot.muscle_id,
                    name=definition.name,
                    short_name=definition.name,
                    group=definition.group,
                    area=definition.area,
                    score=int(round(snapshot.fatigue_score)),
                    readiness_percent=self.fatigue_service.readiness_percent(snapshot.fatigue_score),
                    status=self.fatigue_service.fatigue_status(snapshot.fatigue_score),
                    recovery_hours=int(round(snapshot.recovery_half_life_hours)),
                    last_load_at=self._as_utc(snapshot.last_load_at).strftime("%d.%m %H:%M") if snapshot.last_load_at else "нет данных",
                    impact=[
                        FatigueImpactSchema(
                            exercise=event.note or "Сохранённый подход",
                            date=self._as_utc(event.occurred_at).strftime("%d.%m %H:%M"),
                            share=f"+{int(round(event.fatigue_delta))}",
                            status=self.fatigue_service.fatigue_status(event.fatigue_delta * 3),
                        )
                        for event in impacts
                    ],
                    recommendation=self._fatigue_recommendation(snapshot.fatigue_score),
                    recommended_exercises=self._exercise_suggestions(snapshot.muscle_id, avoid=False),
                    avoid_exercises=self._exercise_suggestions(snapshot.muscle_id, avoid=True),
                )
            )
        readiness = int(round(sum(self.fatigue_service.readiness_percent(item.fatigue_score) for item in snapshots) / max(len(snapshots), 1)))
        return FatigueDataSchema(
            machine=MachineHealthSchema.model_validate(machine),
            updated_at=f"режим: {mode}",
            readiness_percent=readiness,
            overview=[
                MetricCardSchema(label="Средняя готовность", value=f"{readiness}%"),
                MetricCardSchema(label="Мышц с высокой усталостью", value=str(sum(1 for item in snapshots if item.fatigue_score >= 60))),
                MetricCardSchema(label="Перегружено", value=str(sum(1 for item in snapshots if item.fatigue_score >= 100))),
            ],
            muscles=muscles,
            recommended_plan="Выберите для следующей тренировки мышцы с минимальной накопленной усталостью и держите высокий объём вдали от зон с 60+.",
            recovery_note="Восстановление рассчитывается по persisted timestamp и фактической разнице времени, без таймеров в памяти.",
        )

    def reset_fatigue(self, session: Session, *, user_id: str) -> tuple[str, int]:
        reset_at = self._as_utc(datetime.now(UTC)).isoformat()
        reset_count = self.fatigue_service.reset_user_fatigue(session, user_id=user_id)
        return reset_at, reset_count

    def get_fatigue_history(self, session: Session, *, user_id: str, muscle_id: str) -> FatigueHistoryResponseSchema:
        events = self.fatigue_service.muscle_history(session, user_id, muscle_id)
        points = []
        running = 0.0
        for event in reversed(events[-8:]):
            running += event.fatigue_delta
            points.append(
                FatigueHistoryPointSchema(
                    label=self._as_utc(event.occurred_at).strftime("%d.%m"),
                    score=int(round(running)),
                    readiness_percent=self.fatigue_service.readiness_percent(running),
                )
            )
        return FatigueHistoryResponseSchema(muscle_id=muscle_id, points=points)

    def list_photos(self, session: Session, *, user_id: str, media_prefix: str) -> ProgressPhotoListResponseSchema:
        photos = self._photo_rows(session, user_id)
        return ProgressPhotoListResponseSchema(
            photos=[
                ProgressPhotoAssetSchema(
                    id=photo.id,
                    mode=photo.mode.value,
                    view=photo.view.value,
                    taken_at=self._as_utc(photo.taken_at).isoformat(),
                    image_url=f"{media_prefix}/{photo.storage_path}".replace("\\", "/"),
                    thumbnail_url=f"{media_prefix}/{photo.thumbnail_path}".replace("\\", "/"),
                    width=photo.width,
                    height=photo.height,
                    note=photo.note,
                )
                for photo in photos
            ]
        )

    def list_body_measurements(self, session: Session, *, user_id: str) -> BodyMeasurementListResponseSchema:
        measurements = self._measurement_rows(session, user_id)
        return BodyMeasurementListResponseSchema(measurements=[BodyMeasurementSchema.model_validate(item) for item in measurements])

    def create_body_measurement(self, session: Session, payload: BodyMeasurementCreateSchema) -> BodyMeasurementSchema:
        measurement = BodyMeasurement(
            user_id=payload.user_id,
            measured_at=payload.measured_at,
            weight_kg=payload.weight_kg,
            body_fat_percent=payload.body_fat_percent,
            chest_cm=payload.chest_cm,
            waist_cm=payload.waist_cm,
            hips_cm=payload.hips_cm,
        )
        session.add(measurement)
        session.commit()
        session.refresh(measurement)
        return BodyMeasurementSchema.model_validate(measurement)

    def list_achievements(self, session: Session, *, user_id: str) -> AchievementsResponseSchema:
        workouts = self._workout_rows(session, user_id, None)
        photos = self._photo_rows(session, user_id)
        history = self._exercise_history_rows(session, user_id, None)
        achievements = [
            AchievementSchema(id="first-workout", title="Первая тренировка", description="Сохранена хотя бы одна тренировка", unlocked=bool(workouts), unlocked_at=self._as_utc(workouts[0].finished_at).isoformat() if workouts and workouts[0].finished_at else None),
            AchievementSchema(id="five-workouts", title="5 тренировок", description="Выполнено пять тренировок", unlocked=len(workouts) >= 5, unlocked_at=self._as_utc(workouts[4].finished_at).isoformat() if len(workouts) >= 5 and workouts[4].finished_at else None),
            AchievementSchema(id="first-photo", title="Первая фотофиксация", description="Сохранено хотя бы одно фото прогресса", unlocked=bool(photos), unlocked_at=self._as_utc(photos[0].taken_at).isoformat() if photos else None),
            AchievementSchema(id="volume-10000", title="10 000 кг объёма", description="Суммарный объём по истории превысил 10 000 кг", unlocked=sum(item.volume_kg for item in history) >= 10000, unlocked_at=None),
        ]
        return AchievementsResponseSchema(achievements=achievements)

    def _period_start(self, period: str) -> datetime | None:
        now = datetime.now(UTC)
        mapping = {
            ProgressPeriod.days_7.value: now - timedelta(days=7),
            ProgressPeriod.days_30.value: now - timedelta(days=30),
            ProgressPeriod.months_3.value: now - timedelta(days=90),
            ProgressPeriod.months_6.value: now - timedelta(days=180),
            ProgressPeriod.year_1.value: now - timedelta(days=365),
        }
        return mapping.get(period)

    def _period_label(self, period: str) -> str:
        return {
            "7d": "7 дней",
            "30d": "30 дней",
            "3m": "3 месяца",
            "6m": "6 месяцев",
            "1y": "1 год",
            "all": "Всё время",
        }.get(period, "30 дней")

    def _exercise_history_rows(self, session: Session, user_id: str, since: datetime | None) -> list[ExerciseHistoryRecord]:
        statement = select(ExerciseHistoryRecord).where(ExerciseHistoryRecord.user_id == user_id)
        if since is not None:
            statement = statement.where(ExerciseHistoryRecord.performed_at >= since)
        statement = statement.order_by(ExerciseHistoryRecord.performed_at.asc())
        return list(session.scalars(statement))

    def _workout_rows(self, session: Session, user_id: str, since: datetime | None) -> list[WorkoutSession]:
        statement = select(WorkoutSession).where(WorkoutSession.user_id == user_id)
        if since is not None:
            statement = statement.where(WorkoutSession.started_at >= since)
        statement = statement.order_by(WorkoutSession.started_at.asc())
        return list(session.scalars(statement))

    def _measurement_rows(self, session: Session, user_id: str) -> list[BodyMeasurement]:
        statement = select(BodyMeasurement).where(BodyMeasurement.user_id == user_id).order_by(BodyMeasurement.measured_at.asc())
        return list(session.scalars(statement))

    def _photo_rows(self, session: Session, user_id: str) -> list[ProgressPhoto]:
        statement = (
            select(ProgressPhoto)
            .where(ProgressPhoto.user_id == user_id, ProgressPhoto.is_deleted.is_(False))
            .order_by(ProgressPhoto.taken_at.desc())
        )
        return list(session.scalars(statement))

    def _summary_cards(self, workouts: list[WorkoutSession], history: list[ExerciseHistoryRecord]) -> list[MetricCardSchema]:
        total_volume = int(round(sum(item.volume_kg for item in history)))
        total_sets = sum(item.sets for item in history)
        total_reps = sum(item.reps for item in history)
        return [
            MetricCardSchema(label="тренировок", value=str(len(workouts)), hint="за период"),
            MetricCardSchema(label="подходов", value=str(total_sets), hint="сохранено"),
            MetricCardSchema(label="повторов", value=str(total_reps), hint="всего"),
            MetricCardSchema(label="общий объём", value=f"{total_volume} кг", hint="по history"),
            MetricCardSchema(label="серия", value=f"{self._streak_weeks(workouts)} недели", hint="регулярности"),
            MetricCardSchema(label="лучший день", value=f"{self._best_volume(history)} кг", hint="макс. объём", tone="good"),
        ]

    def _volume_series(self, history: list[ExerciseHistoryRecord]) -> list[ChartPointSchema]:
        bucket: dict[str, float] = defaultdict(float)
        for row in history:
            bucket[self._as_utc(row.performed_at).strftime("%d.%m")] += row.volume_kg
        return [ChartPointSchema(label=label, value=round(value, 1), accent=index == len(bucket) - 1) for index, (label, value) in enumerate(bucket.items())][-8:]

    def _main_progress(self, history: list[ExerciseHistoryRecord], muscle_cards: list[MuscleCardSchema]) -> dict[str, object]:
        if not history:
            return {"exercise": "Нет данных", "from": "—", "to": "—", "delta": "—", "muscleFocus": muscle_cards[:3]}
        grouped: dict[str, list[ExerciseHistoryRecord]] = defaultdict(list)
        for row in history:
            grouped[row.exercise_slug].append(row)
        best_slug, rows = max(grouped.items(), key=lambda item: item[1][-1].weight_kg - item[1][0].weight_kg)
        exercise = get_imported_exercise(best_slug)
        delta = rows[-1].weight_kg - rows[0].weight_kg
        return {
            "exercise": exercise.name_ru if exercise else best_slug,
            "from": f"{rows[0].weight_kg:.1f} кг × {rows[0].reps}",
            "to": f"{rows[-1].weight_kg:.1f} кг × {rows[-1].reps}",
            "delta": f"{delta:+.1f} кг к рабочему весу",
            "muscleFocus": muscle_cards[:4],
        }

    def _improvements(self, history: list[ExerciseHistoryRecord]) -> list[str]:
        if not history:
            return ["Сохраните первую тренировку, чтобы начать отслеживание прогресса."]
        return [
            "Backend считает динамику по фактическим сохранённым упражнениям.",
            "История объёма и веса строится по persisted результатам.",
            "Усталость мышц учитывается отдельно от прогресса силы.",
        ]

    def _exercise_options(self, history: list[ExerciseHistoryRecord]) -> list[ProgressExerciseOptionSchema]:
        seen: dict[str, str] = {}
        for row in history:
            exercise = get_imported_exercise(row.exercise_slug)
            seen[row.exercise_slug] = exercise.name_ru if exercise else row.exercise_slug
        return [ProgressExerciseOptionSchema(slug=slug, name=name) for slug, name in seen.items()] or [ProgressExerciseOptionSchema(slug="barbell-floor-press", name="Жим с пола")]

    def _build_selected_exercise(
        self,
        slug: str,
        history: list[ExerciseHistoryRecord],
        fatigue_rows: Sequence[MuscleFatigueSnapshot],
    ) -> ProgressExerciseDetailsSchema:
        exercise = get_imported_exercise(slug)
        affected = self._fatigue_cards(
            [row for row in fatigue_rows if row.muscle_id in {"back", "chest", "biceps", "triceps", "shoulders"}]
        )
        if not history:
            return ProgressExerciseDetailsSchema(
                slug=slug,
                last_result="Нет данных",
                best_result="Нет данных",
                best_volume="Нет данных",
                completed_times="0 раз",
                average_amplitude="—",
                tempo_trend="—",
                work_weight_series=[],
                volume_series=[],
                history=[],
                affected_muscles=affected,
                recommendation="Сначала выполните упражнение хотя бы один раз, чтобы увидеть историю.",
            )
        last = history[-1]
        best = max(history, key=lambda item: item.weight_kg)
        return ProgressExerciseDetailsSchema(
            slug=slug,
            last_result=f"{last.weight_kg:.1f} кг × {last.reps} × {last.sets}",
            best_result=f"{best.weight_kg:.1f} кг × {best.reps}",
            best_volume=f"{int(round(max(item.volume_kg for item in history)))} кг",
            completed_times=f"{len(history)} раз",
            average_amplitude="90%",
            tempo_trend="стабильный",
            work_weight_series=[ChartPointSchema(label=self._as_utc(item.performed_at).strftime("%d.%m"), value=item.weight_kg, accent=index == len(history) - 1) for index, item in enumerate(history[-8:])],
            volume_series=[ChartPointSchema(label=self._as_utc(item.performed_at).strftime("%d.%m"), value=item.volume_kg, accent=index == len(history) - 1) for index, item in enumerate(history[-8:])],
            history=[
                ProgressExerciseHistoryRowSchema(
                    date=self._as_utc(item.performed_at).strftime("%d.%m.%Y"),
                    weight=f"{item.weight_kg:.1f} кг",
                    sets=str(item.sets),
                    reps=str(item.reps),
                    volume=f"{int(round(item.volume_kg))} кг",
                    amplitude="90%",
                )
                for item in reversed(history[-5:])
            ],
            affected_muscles=affected,
            recommendation=f"{exercise.name_ru if exercise else slug}: можно ориентироваться на лучший предыдущий результат и текущую усталость целевых мышц.",
        )

    def _strength_cards(self, history: list[ExerciseHistoryRecord]) -> list[MetricCardSchema]:
        total_volume = sum(item.volume_kg for item in history)
        average_weight = sum(item.weight_kg for item in history) / max(len(history), 1)
        return [
            MetricCardSchema(label="Общий объём", value=f"{int(round(total_volume))} кг"),
            MetricCardSchema(label="Средний рабочий вес", value=f"{average_weight:.1f} кг"),
            MetricCardSchema(label="Подходы", value=str(sum(item.sets for item in history))),
            MetricCardSchema(label="Повторы", value=str(sum(item.reps for item in history))),
        ]

    def _volume_top_exercises(self, history: list[ExerciseHistoryRecord]) -> list[dict[str, object]]:
        grouped: dict[str, float] = defaultdict(float)
        for row in history:
            grouped[row.exercise_slug] += row.volume_kg
        sorted_rows = sorted(grouped.items(), key=lambda item: item[1], reverse=True)[:5]
        rows: list[dict[str, object]] = []
        for index, (slug, value) in enumerate(sorted_rows):
            exercise = get_imported_exercise(slug)
            rows.append(
                {"rank": index + 1, "name": exercise.name_ru if exercise else slug, "value": f"{int(round(value))} кг"}
            )
        return rows

    def _regularity_cards(self, workouts: list[WorkoutSession]) -> list[MetricCardSchema]:
        average_minutes = sum(item.duration_seconds for item in workouts) / max(len(workouts), 1) / 60 if workouts else 0
        return [
            MetricCardSchema(label="тренировок", value=str(len(workouts))),
            MetricCardSchema(label="в неделю", value=str(round(len(workouts) / max(self._streak_weeks(workouts), 1), 1)) if workouts else "0"),
            MetricCardSchema(label="недели подряд", value=str(self._streak_weeks(workouts))),
            MetricCardSchema(label="средняя длительность", value=f"{int(round(average_minutes))} минут"),
        ]

    def _activity_calendar(self, workouts: list[WorkoutSession]) -> list[dict[str, object]]:
        workout_days = {item.started_at.date(): item for item in workouts}
        today = datetime.now(UTC).date()
        days = []
        for offset in range(34, -1, -1):
            day = today - timedelta(days=offset)
            state = "rest"
            if day in workout_days:
                state = "partial" if workout_days[day].status == WorkoutSessionStatus.partial else "done"
            days.append({"id": day.isoformat(), "day": day.day, "state": state})
        return days

    def _weekly_training_series(self, workouts: list[WorkoutSession]) -> list[ChartPointSchema]:
        buckets: dict[str, float] = defaultdict(float)
        for workout in workouts:
            week_start = (workout.started_at - timedelta(days=workout.started_at.weekday())).date()
            buckets[week_start.strftime("%d.%m")] += 1
        return [ChartPointSchema(label=label, value=value, accent=index == len(buckets) - 1) for index, (label, value) in enumerate(buckets.items())][-5:]

    def _weekly_minute_series(self, workouts: list[WorkoutSession]) -> list[ChartPointSchema]:
        buckets: dict[str, float] = defaultdict(float)
        for workout in workouts:
            week_start = (workout.started_at - timedelta(days=workout.started_at.weekday())).date()
            buckets[week_start.strftime("%d.%m")] += workout.duration_seconds / 60
        return [ChartPointSchema(label=label, value=round(value, 1), accent=index == len(buckets) - 1) for index, (label, value) in enumerate(buckets.items())][-5:]

    def _day_distribution(self, workouts: list[WorkoutSession]) -> list[ChartPointSchema]:
        labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        counts = [0] * 7
        for workout in workouts:
            counts[workout.started_at.weekday()] += 1
        return [ChartPointSchema(label=labels[index], value=value) for index, value in enumerate(counts)]

    def _recent_weeks(self, workouts: list[WorkoutSession]) -> list[dict[str, object]]:
        grouped: dict[str, list[WorkoutSession]] = defaultdict(list)
        for workout in workouts:
            week_start = (workout.started_at - timedelta(days=workout.started_at.weekday())).date()
            grouped[week_start.strftime("%d.%m")].append(workout)
        rows: list[dict[str, object]] = []
        for label, items in list(grouped.items())[-5:]:
            minutes = int(round(sum(item.duration_seconds for item in items) / 60))
            rows.append({"label": label, "trainings": f"{len(items)} тренировки", "minutes": f"{minutes} мин", "completion": "100%", "status": "ready" if len(items) >= 2 else "medium"})
        return rows

    def _body_cards(self, measurements: list[BodyMeasurement]) -> list[MetricCardSchema]:
        if not measurements:
            return [MetricCardSchema(label="Вес", value="—"), MetricCardSchema(label="Изменение", value="—")]
        last = measurements[-1]
        delta = (last.weight_kg or 0) - (measurements[0].weight_kg or 0)
        last_weight = float(last.weight_kg) if last.weight_kg is not None else 0.0
        return [
            MetricCardSchema(label="Вес", value=f"{last_weight:.1f} кг"),
            MetricCardSchema(label="Изменение", value=f"{delta:+.1f} кг", tone="good" if delta <= 0 else "warning"),
            MetricCardSchema(label="Последнее измерение", value=self._as_utc(last.measured_at).strftime("%d.%m.%Y")),
        ]

    def _body_weight_series(self, measurements: list[BodyMeasurement]) -> list[ChartPointSchema]:
        return [ChartPointSchema(label=self._as_utc(item.measured_at).strftime("%d.%m"), value=float(item.weight_kg or 0.0), accent=index == len(measurements) - 1) for index, item in enumerate(measurements[-8:])]

    def _body_measurement_rows(self, measurements: list[BodyMeasurement]) -> list[ProgressBodyMeasurementRowSchema]:
        if not measurements:
            return []
        first = measurements[0]
        last = measurements[-1]
        return [
            ProgressBodyMeasurementRowSchema(label="Талия", current=f"{float(last.waist_cm or 0):.1f} см", delta=f"{float((last.waist_cm or 0) - (first.waist_cm or 0)):+.1f} см", tone="good" if (last.waist_cm or 0) <= (first.waist_cm or 0) else "warning"),
            ProgressBodyMeasurementRowSchema(label="Грудь", current=f"{float(last.chest_cm or 0):.1f} см", delta=f"{float((last.chest_cm or 0) - (first.chest_cm or 0)):+.1f} см", tone="neutral"),
            ProgressBodyMeasurementRowSchema(label="Бёдра", current=f"{float(last.hips_cm or 0):.1f} см", delta=f"{float((last.hips_cm or 0) - (first.hips_cm or 0)):+.1f} см", tone="neutral"),
        ]

    def _photo_entries(self, photos: list[ProgressPhoto]) -> list[ProgressPhotoEntrySchema]:
        grouped: dict[date, list[ProgressPhoto]] = defaultdict(list)
        for photo in photos:
            grouped[photo.taken_at.date()].append(photo)
        entries = []
        for index, day in enumerate(sorted(grouped.keys(), reverse=True)):
            entries.append(
                ProgressPhotoEntrySchema(
                    id=day.isoformat(),
                    date=day.strftime("%d %b"),
                    year=str(day.year),
                    views=[ProgressPhotoViewSchema(id=photo.view.value, label={"front": "Спереди", "side": "Сбоку", "back": "Сзади"}[photo.view.value]) for photo in grouped[day]],
                    is_latest=index == 0,
                )
            )
        return entries

    def _photo_stats(self, photos: list[ProgressPhoto]) -> list[MetricCardSchema]:
        intervals = []
        for previous, current in zip(photos[1:], photos[:-1], strict=False):
            intervals.append((previous.taken_at - current.taken_at).days)
        average_interval = abs(sum(intervals) / len(intervals)) if intervals else 0
        return [
            MetricCardSchema(label="Фиксаций сделано", value=str(len(photos))),
            MetricCardSchema(label="Средний интервал", value=f"{int(round(average_interval))} дней" if photos else "—"),
            MetricCardSchema(label="Последняя фиксация", value=self._as_utc(photos[0].taken_at).strftime("%d.%m.%Y") if photos else "—"),
        ]

    def _fatigue_cards(self, snapshots: Sequence[MuscleFatigueSnapshot]) -> list[MuscleCardSchema]:
        cards = []
        for snapshot in snapshots:
            cards.append(
                MuscleCardSchema(
                    name=self._muscle_name(snapshot.muscle_id),
                    status=self.fatigue_service.fatigue_status(snapshot.fatigue_score),
                    score=int(round(snapshot.fatigue_score)),
                )
            )
        return cards

    def _fatigue_event_lookup(self, session: Session, user_id: str) -> dict[str, list[MuscleFatigueEvent]]:
        statement = (
            select(MuscleFatigueEvent)
            .where(MuscleFatigueEvent.user_id == user_id)
            .order_by(MuscleFatigueEvent.occurred_at.desc())
        )
        lookup: dict[str, list[MuscleFatigueEvent]] = defaultdict(list)
        for event in session.scalars(statement):
            lookup[event.muscle_id].append(event)
        return lookup

    def _fatigue_recommendation(self, score: float) -> str:
        if score >= 100:
            return "Перегруз: исключите тяжёлую работу на эту мышцу до восстановления."
        if score >= 60:
            return "Высокая усталость: лучше не давать тяжёлую нагрузку."
        if score >= 30:
            return "Средняя усталость: допустима облегчённая работа."
        return "Мышца готова к нагрузке."

    def _exercise_suggestions(self, muscle_id: str, *, avoid: bool) -> list[FatigueExerciseSuggestionSchema]:
        definition = get_muscle_definition(muscle_id)
        source = definition.avoided if avoid else definition.recommended
        return [FatigueExerciseSuggestionSchema(name=name, note="Подходит" if not avoid else "Лучше отложить", status="ready" if not avoid else "high") for name in source]

    def _muscle_name(self, muscle_id: str) -> str:
        return get_muscle_definition(muscle_id).name

    def _streak_weeks(self, workouts: list[WorkoutSession]) -> int:
        if not workouts:
            return 0
        weeks = sorted({(item.started_at - timedelta(days=item.started_at.weekday())).date() for item in workouts}, reverse=True)
        streak = 0
        cursor = weeks[0]
        for week in weeks:
            if week == cursor:
                streak += 1
                cursor = cursor - timedelta(days=7)
            else:
                break
        return streak

    def _best_volume(self, history: list[ExerciseHistoryRecord]) -> int:
        return int(round(max((item.volume_kg for item in history), default=0.0)))