from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, WorkoutSession
from app.models.enums import ExerciseSessionStatus, NotificationTone, RuntimeFlowSource, WorkoutSessionStatus
from app.models.profile import BodyMeasurement
from app.models.settings import AppSetting
from app.models.training import ExerciseHistoryRecord, UserExerciseState
from app.repositories.user_repository import UserRepository
from app.schemas.dashboard import (
    DashboardAlertSchema,
    DashboardBuilderWorkoutExerciseSchema,
    DashboardBuilderWorkoutSchema,
    DashboardDataSchema,
    DashboardDayProgressResetResultSchema,
    DashboardProgressMetricSchema,
    DashboardQuickStartItemSchema,
    DashboardRecommendationSchema,
    DashboardWorkoutExerciseSchema,
    DashboardWorkoutSnapshotSchema,
    DashboardWorkoutSchema,
    MuscleCardSchema,
)
from app.services.exercise_library import get_imported_exercise
from app.services.exercise_library import ImportedExercise, get_imported_exercise
from app.services.fatigue_service import FatigueService
from app.services.machine_service import MachineService
from app.services.muscle_catalog import get_muscle_definition
from app.services.training_service import TrainingService


class DashboardProfile(TypedDict):
    greeting: str
    recommendation_title: str
    recommendation_text: str
    readiness_percent: int


class DashboardWorkoutPlan(TypedDict):
    slug: str
    default_weight: float | None
    default_value: int
    default_sets: int
    measure: Literal["reps", "seconds"]


TODAY_WORKOUT_PLAN: tuple[DashboardWorkoutPlan, ...] = (
    {"slug": "machine-pulldown", "default_weight": 45.0, "default_value": 10, "default_sets": 4, "measure": "reps"},
    {"slug": "machine-seated-cable-row", "default_weight": 40.0, "default_value": 10, "default_sets": 4, "measure": "reps"},
    {"slug": "barbell-curl", "default_weight": 20.0, "default_value": 12, "default_sets": 3, "measure": "reps"},
    {"slug": "underhand-pulldown", "default_weight": 35.0, "default_value": 12, "default_sets": 4, "measure": "reps"},
    {"slug": "forearm-plank", "default_weight": None, "default_value": 45, "default_sets": 3, "measure": "seconds"},
)

TODAY_PLAN_SETTING_KEY = "training.today.plan"
BUILDER_PROGRESS_RESET_SETTING_KEY = "training.builder.progress.reset_at"
TRAINING_DAY_RESET_HOUR = 3


class DashboardService:
    def __init__(self) -> None:
        self.user_repository = UserRepository()
        self.machine_service = MachineService()
        self.fatigue_service = FatigueService()
        self.training_service = TrainingService()

    def get_dashboard(
        self,
        session: Session,
        user_id: str,
        scenario_name: str | None = None,
    ) -> DashboardDataSchema:
        user = self.user_repository.get_user(session, user_id)
        if user is None:
            raise LookupError(f"Unknown user: {user_id}")

        machine = self.machine_service.get_machine_health(session, self._machine_scenario(scenario_name))
        profile = self._profile_copy(user_id, user.readiness_percent)
        base_dashboard = DashboardDataSchema(
            greeting=profile["greeting"],
            recommendation_title=profile["recommendation_title"],
            recommendation_text=profile["recommendation_text"],
            readiness_percent=profile["readiness_percent"],
            today_workout=self._today_workout(session, user_id),
            workouts=self._builder_workouts(session, user_id),
            machine=machine,
            alerts=[],
            recommended_exercises=[
                DashboardRecommendationSchema(name="Тяга сверху", muscles="Спина, бицепс", status="Рекомендуется"),
                DashboardRecommendationSchema(name="Тяга к поясу", muscles="Спина", status="Рекомендуется"),
                DashboardRecommendationSchema(name="Сгибание рук", muscles="Бицепс", status="Можно выполнить"),
            ],
            quick_start=[
                DashboardQuickStartItemSchema(name="Жим лёжа", stats="40 кг × 10 × 3", last="2 дн. назад"),
                DashboardQuickStartItemSchema(name="Присед", stats="60 кг × 10 × 3", last="3 дн. назад"),
                DashboardQuickStartItemSchema(name="Тяга сверху", stats="45 кг × 10 × 3", last="5 дн. назад"),
            ],
            progress=self._progress_metrics(session, user_id),
            muscles=self._muscle_cards(session, user_id),
        )
        return self._apply_scenario(base_dashboard, scenario_name)

    def reset_day_progress(self, session: Session, user_id: str) -> DashboardDayProgressResetResultSchema:
        user = self.user_repository.get_user(session, user_id)
        if user is None:
            raise LookupError(f"Unknown user: {user_id}")

        reset_at = datetime.now(UTC)
        statement = select(AppSetting).where(AppSetting.user_id == user_id, AppSetting.key == BUILDER_PROGRESS_RESET_SETTING_KEY)
        setting = session.scalars(statement).first()
        value = {"resetAt": reset_at.isoformat()}

        if setting is None:
            setting = AppSetting(user_id=user_id, key=BUILDER_PROGRESS_RESET_SETTING_KEY, value=value)
            session.add(setting)
        else:
            setting.value = value

        session.commit()
        return DashboardDayProgressResetResultSchema(status="ok", user_id=user_id, effective_from=reset_at)

    def _progress_metrics(self, session: Session, user_id: str) -> list[DashboardProgressMetricSchema]:
        now = datetime.now(UTC)
        workouts = self._completed_workouts(session, user_id)
        history = self._exercise_history(session, user_id)
        measurements = self._body_measurements(session, user_id)

        workouts_last_month = sum(1 for workout in workouts if self._as_utc(workout.started_at) >= now - timedelta(days=30))
        current_week_volume = self._volume_between(history, start=now - timedelta(days=7), end=now)
        previous_week_volume = self._volume_between(history, start=now - timedelta(days=14), end=now - timedelta(days=7))
        weekly_volume_delta = self._percentage_delta(current_week_volume, previous_week_volume)
        weight_delta = self._monthly_weight_delta(measurements, now)

        return [
            DashboardProgressMetricSchema(label="тренировок за месяц", value=str(workouts_last_month)),
            DashboardProgressMetricSchema(label="недели подряд", value=str(self._streak_weeks(workouts))),
            DashboardProgressMetricSchema(label="к объёму за неделю", value=self._format_percent_delta(weekly_volume_delta)),
            DashboardProgressMetricSchema(label="кг за месяц", value=self._format_weight_delta(weight_delta)),
        ]

    def _completed_workouts(self, session: Session, user_id: str) -> list[WorkoutSession]:
        statement = (
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status.in_([WorkoutSessionStatus.completed, WorkoutSessionStatus.partial]),
            )
            .order_by(WorkoutSession.started_at.asc())
        )
        return list(session.scalars(statement))

    def _exercise_history(self, session: Session, user_id: str) -> list[ExerciseHistoryRecord]:
        statement = select(ExerciseHistoryRecord).where(ExerciseHistoryRecord.user_id == user_id).order_by(ExerciseHistoryRecord.performed_at.asc())
        return list(session.scalars(statement))

    def _body_measurements(self, session: Session, user_id: str) -> list[BodyMeasurement]:
        statement = select(BodyMeasurement).where(BodyMeasurement.user_id == user_id).order_by(BodyMeasurement.measured_at.asc())
        return list(session.scalars(statement))

    def _today_workout(self, session: Session, user_id: str) -> DashboardWorkoutSchema:
        plans = [self._resolve_today_plan(slug) for slug in self._today_plan_slugs(session, user_id)]
        exercises = [self._today_workout_item(session, user_id, plan) for plan in plans]
        total_sets = sum(self._planned_sets(session, user_id, plan) for plan in plans)
        return DashboardWorkoutSchema(
            title="Спина + бицепс",
            exercises=len(exercises),
            sets=total_sets,
            duration="45 минут",
            list=exercises,
        )

    def _today_plan_slugs(self, session: Session, user_id: str) -> list[str]:
        statement = select(AppSetting).where(AppSetting.user_id == user_id, AppSetting.key == TODAY_PLAN_SETTING_KEY)
        setting = session.scalars(statement).first()
        if setting is None or not isinstance(setting.value, dict):
            return [item["slug"] for item in TODAY_WORKOUT_PLAN]

        value = setting.value.get("slugs")
        if not isinstance(value, list):
            return [item["slug"] for item in TODAY_WORKOUT_PLAN]

        slugs = [str(item) for item in value if isinstance(item, str) and get_imported_exercise(item) is not None]
        return slugs or [item["slug"] for item in TODAY_WORKOUT_PLAN]

    def _resolve_today_plan(self, slug: str) -> DashboardWorkoutPlan:
        existing = next((item for item in TODAY_WORKOUT_PLAN if item["slug"] == slug), None)
        if existing is not None:
            return existing

        exercise = get_imported_exercise(slug)
        if exercise is not None and exercise.force == "Static":
            return {"slug": slug, "default_weight": None, "default_value": 45, "default_sets": 3, "measure": "seconds"}

        default_weight = 45.0 if exercise and exercise.equipment == "Machine" else (40.0 if exercise and exercise.equipment == "Barbell" else 20.0)
        return {"slug": slug, "default_weight": default_weight, "default_value": 10, "default_sets": 3, "measure": "reps"}

    def _today_workout_item(self, session: Session, user_id: str, plan: DashboardWorkoutPlan) -> DashboardWorkoutExerciseSchema:
        exercise = get_imported_exercise(plan["slug"])
        latest_result = self._latest_exercise_result(session, user_id, plan["slug"])
        state = self._exercise_state(session, user_id, plan["slug"])
        name = exercise.name_ru if exercise is not None else plan["slug"]
        planned_weight, planned_value, planned_sets = self._planned_targets(state, plan)
        return DashboardWorkoutExerciseSchema(
            slug=plan["slug"],
            name=name,
            preview_video_url=self._preview_video_url(exercise, user_id),
            previous=self._previous_snapshot(latest_result, plan["measure"]),
            planned=self._planned_snapshot(plan["measure"], planned_weight, planned_value, planned_sets, latest_result),
        )

    def _builder_workouts(self, session: Session, user_id: str) -> list[DashboardBuilderWorkoutSchema]:
        programs = list(self.training_service._programs(session, user_id))
        progress_by_title = self._builder_progress_by_title(session, user_id, programs)
        workouts: list[DashboardBuilderWorkoutSchema] = []
        for program in programs:
            builder_value = self.training_service._builder_setting_value(session, user_id, program.id)
            groups = self.training_service._builder_groups(session, user_id, program)
            duration_minutes = self.training_service._builder_estimated_duration_minutes(groups, program.duration_minutes)
            workout_title = self.training_service._builder_workout_name(builder_value, program)
            progress = progress_by_title.get(workout_title)
            exercise_rows = self._builder_workout_exercises(groups, progress)
            workouts.append(
                DashboardBuilderWorkoutSchema(
                    id=program.id,
                    title=workout_title,
                    exercises=exercise_rows,
                    duration=f"≈ {duration_minutes} минут" if duration_minutes > 0 else f"{program.duration_minutes} минут",
                    today_status=progress["status"] if progress else "idle",
                    today_progress_percent=progress["progress_percent"] if progress else 0,
                    today_completed_exercises=progress["completed_exercises"] if progress else 0,
                    today_total_exercises=len(exercise_rows),
                    resume_available=bool(progress and progress["status"] == WorkoutSessionStatus.in_progress.value),
                )
            )
        return workouts

    def _builder_progress_by_title(self, session: Session, user_id: str, programs: list[object]) -> dict[str, dict[str, object]]:
        if not programs:
            return {}

        titles = []
        totals_by_title: dict[str, int] = {}
        for program in programs:
            builder_value = self.training_service._builder_setting_value(session, user_id, program.id)
            title = self.training_service._builder_workout_name(builder_value, program)
            groups = self.training_service._builder_groups(session, user_id, program)
            titles.append(title)
            totals_by_title[title] = sum(len(group.items) for group in groups)

        effective_start = self._effective_builder_progress_start(session, user_id)
        statement = (
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.source == RuntimeFlowSource.builder,
                WorkoutSession.title.in_(titles),
                WorkoutSession.started_at >= effective_start,
            )
            .order_by(WorkoutSession.started_at.desc(), WorkoutSession.id.desc())
        )
        sessions_by_title: dict[str, list[WorkoutSession]] = {}
        for workout_session in session.scalars(statement):
            sessions_by_title.setdefault(workout_session.title, []).append(workout_session)

        progress_by_title: dict[str, dict[str, object]] = {}
        for title, workout_sessions in sessions_by_title.items():
            active_session = next((item for item in workout_sessions if item.status == WorkoutSessionStatus.in_progress), workout_sessions[0])
            total_exercises = max(totals_by_title.get(title, 0), len(active_session.exercise_sessions), 1)
            completed_exercises = sum(1 for exercise in active_session.exercise_sessions if exercise.status != ExerciseSessionStatus.in_progress)
            started_exercises = sum(1 for exercise in active_session.exercise_sessions if exercise.status == ExerciseSessionStatus.in_progress)
            progress_units = completed_exercises + (0.5 if started_exercises else 0.0)
            progress_percent = min(100, int(round((progress_units / total_exercises) * 100)))
            if active_session.status in {WorkoutSessionStatus.completed, WorkoutSessionStatus.partial, WorkoutSessionStatus.aborted}:
                progress_percent = max(progress_percent, int(round((completed_exercises / total_exercises) * 100)))
            progress_by_title[title] = {
                "status": active_session.status.value,
                "progress_percent": progress_percent,
                "completed_exercises": completed_exercises,
                "exercise_sessions": sorted(active_session.exercise_sessions, key=lambda item: item.order_index),
            }

        return progress_by_title

    def _builder_workout_exercises(self, groups: list[object], progress: dict[str, object] | None) -> list[DashboardBuilderWorkoutExerciseSchema]:
        exercise_sessions = progress.get("exercise_sessions") if isinstance(progress, dict) else []
        exercise_sessions_by_order = {
            item.order_index: item
            for item in exercise_sessions
            if isinstance(item, ExerciseSession)
        }

        rows: list[DashboardBuilderWorkoutExerciseSchema] = []
        flattened_items = [item for group in groups for item in group.items]
        for index, item in enumerate(flattened_items, start=1):
            target_sets = len(item.strength_plan) or self.training_service._parse_sets(item.sets)
            exercise_session = exercise_sessions_by_order.get(index)
            completed_sets = len(exercise_session.set_results) if exercise_session is not None else 0

            if exercise_session is None:
                status = "idle"
            elif exercise_session.status == ExerciseSessionStatus.completed:
                status = "completed"
            elif completed_sets > 0:
                status = "in_progress"
            else:
                status = "idle"

            rows.append(
                DashboardBuilderWorkoutExerciseSchema(
                    slug=item.slug,
                    name=item.name,
                    status=status,
                    completed_sets=completed_sets,
                    target_sets=target_sets,
                    progress_percent=min(100, int(round((completed_sets / max(target_sets, 1)) * 100))),
                )
            )

        return rows

    def _effective_builder_progress_start(self, session: Session, user_id: str, now: datetime | None = None) -> datetime:
        day_start = self._training_day_start(now)
        statement = select(AppSetting).where(AppSetting.user_id == user_id, AppSetting.key == BUILDER_PROGRESS_RESET_SETTING_KEY)
        setting = session.scalars(statement).first()
        if setting is None or not isinstance(setting.value, dict):
            return day_start

        reset_at_raw = setting.value.get("resetAt")
        if not isinstance(reset_at_raw, str):
            return day_start

        try:
            reset_at = self._as_utc(datetime.fromisoformat(reset_at_raw))
        except ValueError:
            return day_start

        return reset_at if reset_at >= day_start else day_start

    def _training_day_start(self, now: datetime | None = None) -> datetime:
        effective_now = (now or datetime.now().astimezone()).astimezone()
        day_start = effective_now.replace(hour=TRAINING_DAY_RESET_HOUR, minute=0, second=0, microsecond=0)
        if effective_now < day_start:
            day_start -= timedelta(days=1)
        return day_start.astimezone(UTC)

    def _preview_video_url(self, exercise: ImportedExercise | None, user_id: str) -> str | None:
        if exercise is None or not exercise.videos:
            return None

        preferred_gender = "female" if user_id == "elena" else "male"
        for video in exercise.videos:
            if video.gender == preferred_gender and video.view == "side":
                return video.relative_url
        for video in exercise.videos:
            if video.gender == preferred_gender:
                return video.relative_url
        return exercise.videos[0].relative_url

    def _latest_exercise_result(self, session: Session, user_id: str, slug: str) -> ExerciseHistoryRecord | None:
        statement = (
            select(ExerciseHistoryRecord)
            .where(ExerciseHistoryRecord.user_id == user_id, ExerciseHistoryRecord.exercise_slug == slug)
            .order_by(ExerciseHistoryRecord.performed_at.desc())
            .limit(1)
        )
        return session.scalars(statement).first()

    def _exercise_state(self, session: Session, user_id: str, slug: str) -> UserExerciseState | None:
        statement = select(UserExerciseState).where(UserExerciseState.user_id == user_id, UserExerciseState.exercise_slug == slug)
        return session.scalars(statement).first()

    def _planned_sets(self, session: Session, user_id: str, plan: DashboardWorkoutPlan) -> int:
        state = self._exercise_state(session, user_id, plan["slug"])
        return state.working_sets if state and state.working_sets is not None else plan["default_sets"]

    def _planned_targets(self, state: UserExerciseState | None, plan: DashboardWorkoutPlan) -> tuple[float | None, int, int]:
        planned_sets = state.working_sets if state and state.working_sets is not None else plan["default_sets"]
        planned_value = state.working_reps if state and state.working_reps is not None else plan["default_value"]
        if plan["measure"] == "seconds":
            return None, planned_value, planned_sets
        planned_weight = state.working_weight if state and state.working_weight is not None else plan["default_weight"]
        return planned_weight, planned_value, planned_sets

    def _previous_snapshot(self, record: ExerciseHistoryRecord | None, measure: Literal["reps", "seconds"]) -> DashboardWorkoutSnapshotSchema:
        if record is None:
            return DashboardWorkoutSnapshotSchema(
                label="Прошлый раз",
                primary="Нет истории",
                secondary="Ориентир появится после старта",
            )

        if measure == "seconds" or record.weight_kg <= 0:
            primary = f"{record.reps} сек"
            secondary = "вес тела"
        else:
            primary = f"{record.weight_kg:g} кг"
            secondary = f"{record.reps} повторов"

        return DashboardWorkoutSnapshotSchema(
            label="Прошлый раз",
            primary=primary,
            secondary=secondary,
            meta=f"{self._format_sets(record.sets)} • {self._last_performed_label(record.performed_at)}",
        )

    def _planned_snapshot(
        self,
        measure: Literal["reps", "seconds"],
        weight: float | None,
        value: int,
        sets: int,
        previous: ExerciseHistoryRecord | None,
    ) -> DashboardWorkoutSnapshotSchema:
        if measure == "seconds":
            primary = f"{value} сек"
            secondary = "вес тела"
        elif weight is None or weight <= 0:
            primary = "вес тела"
            secondary = f"{value} повторов"
        else:
            primary = f"{weight:g} кг"
            secondary = f"{value} повторов"

        return DashboardWorkoutSnapshotSchema(
            label="План",
            primary=primary,
            secondary=secondary,
            meta=f"{self._format_sets(sets)} • {self._planned_delta_label(measure, weight, value, previous)}",
        )

    def _planned_delta_label(
        self,
        measure: Literal["reps", "seconds"],
        weight: float | None,
        value: int,
        previous: ExerciseHistoryRecord | None,
    ) -> str:
        if previous is None:
            return "стартовый ориентир"

        if measure == "seconds":
            delta = value - previous.reps
            if delta == 0:
                return "держим прошлое время"
            return f"{delta:+d} сек к прошлому"

        previous_weight = previous.weight_kg
        if weight is not None and previous_weight > 0:
            delta_weight = round(weight - previous_weight, 1)
            if delta_weight != 0:
                return f"{delta_weight:+g} кг к прошлому"

        delta_reps = value - previous.reps
        if delta_reps == 0:
            return "повторяем рабочую схему"
        return f"{delta_reps:+d} повт. к прошлому"

    def _volume_between(self, history: list[ExerciseHistoryRecord], *, start: datetime, end: datetime) -> float:
        return sum(
            item.volume_kg
            for item in history
            if start <= self._as_utc(item.performed_at) < end
        )

    def _monthly_weight_delta(self, measurements: list[BodyMeasurement], now: datetime) -> float:
        weighted_rows = [item for item in measurements if item.weight_kg is not None]
        if not weighted_rows:
            return 0.0

        window_start = now - timedelta(days=30)
        current_rows = [item for item in weighted_rows if self._as_utc(item.measured_at) >= window_start]
        if len(current_rows) >= 2:
            start_weight = float(current_rows[0].weight_kg)
            end_weight = float(current_rows[-1].weight_kg)
            return end_weight - start_weight

        if len(current_rows) == 1:
            previous_rows = [item for item in weighted_rows if self._as_utc(item.measured_at) < window_start]
            if previous_rows:
                return float(current_rows[-1].weight_kg) - float(previous_rows[-1].weight_kg)

        return 0.0

    def _percentage_delta(self, current_value: float, previous_value: float) -> float:
        if previous_value == 0:
            return 100.0 if current_value > 0 else 0.0
        return ((current_value - previous_value) / previous_value) * 100

    def _format_percent_delta(self, value: float) -> str:
        rounded = int(round(value))
        if rounded == 0:
            return "0%"
        return f"{rounded:+d}%"

    def _format_weight_delta(self, value: float) -> str:
        rounded = round(value, 1)
        if rounded == 0:
            return "0 кг"
        return f"{rounded:+.1f} кг"

    def _format_sets(self, value: int) -> str:
        remainder_ten = value % 10
        remainder_hundred = value % 100
        if remainder_ten == 1 and remainder_hundred != 11:
            suffix = "подход"
        elif remainder_ten in {2, 3, 4} and remainder_hundred not in {12, 13, 14}:
            suffix = "подхода"
        else:
            suffix = "подходов"
        return f"{value} {suffix}"

    def _streak_weeks(self, workouts: list[WorkoutSession]) -> int:
        if not workouts:
            return 0
        weeks = sorted({(self._as_utc(item.started_at) - timedelta(days=self._as_utc(item.started_at).weekday())).date() for item in workouts}, reverse=True)
        streak = 0
        cursor = weeks[0]
        for week in weeks:
            if week == cursor:
                streak += 1
                cursor = cursor - timedelta(days=7)
            else:
                break
        return streak

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _last_performed_label(self, performed_at: datetime | None) -> str:
        if performed_at is None:
            return "нет истории"
        normalized = performed_at if performed_at.tzinfo is not None else performed_at.replace(tzinfo=UTC)
        delta_days = max(0, (datetime.now(UTC) - normalized.astimezone(UTC)).days)
        if delta_days == 0:
            return "сегодня"
        if delta_days == 1:
            return "1 день назад"
        return f"{delta_days} дней назад"

    def _muscle_cards(self, session: Session, user_id: str) -> list[MuscleCardSchema]:
        snapshots = self.fatigue_service.list_current_scores(session, user_id)
        return [
            MuscleCardSchema(
                name=get_muscle_definition(item.muscle_id).name,
                status=self.fatigue_service.fatigue_status(item.fatigue_score),
                score=int(round(item.fatigue_score)),
            )
            for item in snapshots
        ]

    @staticmethod
    def _machine_scenario(scenario_name: str | None) -> str | None:
        if scenario_name == "machine-warning":
            return "warning"
        if scenario_name == "drive-error":
            return "blocked"
        return "ready"

    @staticmethod
    def _profile_copy(user_id: str, readiness_percent: int) -> DashboardProfile:
        profiles: dict[str, DashboardProfile] = {
            "alexey": {
                "greeting": "Добрый день, Алексей",
                "recommendation_title": "Сегодня лучше: Спина + бицепс",
                "recommendation_text": "Грудь и трицепс ещё восстанавливаются после прошлой тренировки. Ноги готовы к умеренной нагрузке.",
                "readiness_percent": readiness_percent,
            },
            "elena": {
                "greeting": "Добрый день, Елена",
                "recommendation_title": "Сегодня лучше: Верх тела",
                "recommendation_text": "Ноги ещё утомлены после прошлой сессии. Верх тела готов к плановой нагрузке и контролю техники.",
                "readiness_percent": readiness_percent,
            },
            "guest": {
                "greeting": "Добро пожаловать",
                "recommendation_title": "Сегодня лучше: Быстрый старт",
                "recommendation_text": "Гостевой режим не использует персональную историю. Можно выбрать упражнение из каталога и начать тренировку на моках.",
                "readiness_percent": readiness_percent,
            },
        }
        return profiles.get(user_id, profiles["alexey"])

    def _apply_scenario(self, dashboard: DashboardDataSchema, scenario_name: str | None) -> DashboardDataSchema:
        if scenario_name == "no-workout":
            dashboard.recommendation_title = "Сегодня лучше: Выбрать новый старт"
            dashboard.recommendation_text = "На сегодня не найдено сохранённой тренировки. Можно перейти в быстрый старт или открыть каталог упражнений."
            dashboard.today_workout = None
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.warning,
                    title="План на сегодня не найден",
                    description="Backend показывает состояние без назначенной тренировки, но с доступным быстрым стартом.",
                )
            ]
        elif scenario_name == "high-fatigue":
            dashboard.readiness_percent = 34
            dashboard.recommendation_title = "Сегодня лучше: Восстановление"
            dashboard.recommendation_text = "Уровень усталости слишком высок для полноценной силовой тренировки. Рекомендуется облегчённая сессия или отдых."
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.blocked,
                    title="Высокая усталость мышц",
                    description="Старт силовой тренировки должен быть пересмотрен.",
                )
            ]
            dashboard.muscles = [
                MuscleCardSchema(name="Грудь", status="critical", score=128),
                MuscleCardSchema(name="Трицепс", status="high", score=94),
                MuscleCardSchema(name="Плечи", status="high", score=88),
                MuscleCardSchema(name="Спина", status="medium", score=41),
                MuscleCardSchema(name="Бицепс", status="medium", score=39),
                MuscleCardSchema(name="Предплечья", status="light", score=20),
                MuscleCardSchema(name="Пресс", status="light", score=18),
                MuscleCardSchema(name="Ягодицы", status="medium", score=36),
                MuscleCardSchema(name="Ноги", status="high", score=91),
            ]
        elif scenario_name == "machine-warning":
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.warning,
                    title="Требуется внимание к приводу",
                    description="Правый привод сообщает предупреждение перед началом упражнения.",
                )
            ]
        elif scenario_name == "drive-error":
            dashboard.alerts = [
                DashboardAlertSchema(
                    tone=NotificationTone.blocked,
                    title="Ошибка правого привода",
                    description="Старт тренировки блокируется, пока не будет завершена сервисная проверка оборудования.",
                )
            ]
        return dashboard
