from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import ExerciseSession, SetResult, WorkoutSession
from app.models.enums import ExerciseSessionStatus, RuntimeExerciseKind, WorkoutSessionStatus
from app.models.settings import AppSetting
from app.models.training import ExerciseHistoryRecord, UserExerciseState, UserHiddenWorkoutProgram, WorkoutProgram
from app.models.user import User
from app.schemas.analytics import MuscleCardSchema
from app.schemas.exercise import (
    ExerciseCatalogAvailableFiltersSchema,
    ExerciseCatalogResponseSchema,
    ExerciseCompatibilitySchema,
    ExerciseDetailsSchema,
    ExerciseGuideSchema,
    ExerciseHistoryEntrySchema,
    ExerciseLoadPointSchema,
    ExerciseLoadSettingsSchema,
    ExerciseSummarySchema,
    ExerciseVideoAssetSchema,
)
from app.schemas.machine import MachineHealthSchema
from app.schemas.runtime import ExerciseProfileSchema
from app.schemas.training import (
    BuilderExerciseEditorSchema,
    BuilderExerciseItemSchema,
    BuilderPlanMutationSchema,
    BuilderProgramTabSchema,
    BuilderStrengthSetPlanSchema,
    BuilderSummaryCardSchema,
    BuilderWorkoutGroupSchema,
    CalendarDaySchema,
    CalendarWorkoutExerciseSchema,
    CalendarWorkoutSchema,
    ProgramCompatibilitySchema,
    ProgramDetailsActionsSchema,
    ProgramDetailsSchema,
    ProgramLibraryDataSchema,
    ProgramMutationResultSchema,
    ProgramMutationSchema,
    ProgramOrderMutationSchema,
    ProgramOrderResultSchema,
    ProgramSummarySchema,
    QuickStartDataSchema,
    QuickStartExerciseListItemSchema,
    QuickStartRecommendationSchema,
    QuickStartSelectedExerciseReadinessSchema,
    QuickStartSelectedExerciseSchema,
    QuickStartSelectedExerciseWarningSchema,
    StrengthTrainingModeSchema,
    TodayWorkoutDataSchema,
    TodayWorkoutPlanMutationSchema,
    TodayWorkoutWarningSchema,
    TrainingPlanMutationResultSchema,
    WorkoutBuilderDataSchema,
    WorkoutCalendarDataSchema,
    WorkoutExercisePanelReadinessSchema,
    WorkoutExercisePanelSchema,
    WorkoutExerciseRowSchema,
    WorkoutProgressSchema,
)
from app.services.exercise_library import ImportedExercise, get_imported_exercise, load_imported_exercises
from app.services.exercise_settings import (
    builder_load_type,
    effective_set_params,
    last_performed_working_weight,
    load_mode_rule,
    profile_from_effective,
    profile_set_params,
    read_profile,
    remembered_settings,
    scale_weight,
    store_profile,
    tempo_rule,
)
from app.services.fatigue_service import FatigueService, equipment_affects_fatigue
from app.services.machine_service import MachineService
from app.services.muscle_catalog import CANONICAL_MUSCLE_DEFINITIONS
from app.services.progress_insights import estimate_one_rep_max
from app.services.workout_duration import DurationEstimate, estimate_workout_duration

RU_MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

FEATURED = {
    "quick_start": ["machine-pulldown", "machine-seated-cable-row", "barbell-curl"],
    "recent": ["barbell-bench-press", "barbell-floor-press", "machine-pulldown"],
    "today": ["machine-pulldown", "machine-seated-cable-row", "barbell-curl", "underhand-pulldown", "forearm-plank"],
}

TODAY_PLAN_SETTING_KEY = "training.today.plan"
BUILDER_PLAN_SETTING_KEY = "training.builder.plan"
PROGRAM_ORDER_SETTING_KEY = "training.programs.order"
# session.info marker: this user's builder items already have exercise profiles in this DB session.
PROFILES_READY_KEY = "training.exercise_profiles_ready"
E1RM_LOOKBACK_DAYS = 120
DEFAULT_BUILDER_NOTE = "Следить за техникой и не терять контроль в нижней точке."

STRENGTH_TRAINING_MODES = [
    {
        "id": "basic",
        "title": "Базовый режим",
        "short_description": "Разминка и 2–4 рабочих подхода без полного отказа.",
        "goal": "Стабильность, техника и регулярный прогресс.",
        "level": "Новичок / средний",
        "audience": "Новички, пользователи после перерыва и регулярные занятия.",
    },
    {
        "id": "last_set_failure",
        "title": "Последний подход до отказа",
        "short_description": "Основные подходы почти до отказа, последний — до технического отказа.",
        "goal": "Повысить интенсивность без отказа в каждом подходе.",
        "level": "Средний",
        "audience": "Тренажёры, изоляция, руки, плечи, тяги блока, жим ногами и пресс.",
        "safety_note": "Не выбирать по умолчанию для тяжёлого приседа, становой тяги и жима без страховки.",
    },
    {
        "id": "straight_pyramid",
        "title": "Прямая пирамида",
        "short_description": "Вес растёт от подхода к подходу, количество повторений снижается.",
        "goal": "Плавно войти в рабочий вес и найти нагрузку дня.",
        "level": "Новичок / средний",
        "audience": "Пользователи, которые ещё подбирают точный рабочий вес.",
    },
    {
        "id": "reverse_pyramid",
        "title": "Обратная пирамида",
        "short_description": "После разминки первым идёт самый тяжёлый подход, затем вес снижается.",
        "goal": "Сохранить максимум сил для главного тяжёлого подхода.",
        "level": "Опытный",
        "audience": "Пользователи с устойчивой техникой и известным рабочим весом.",
    },
    {
        "id": "strength",
        "title": "Силовой режим",
        "short_description": "3–5 тяжёлых подходов по 3–6 повторений с длинным отдыхом.",
        "goal": "Развитие максимальной силы без отказных подходов.",
        "level": "Средний / опытный",
        "audience": "Присед, жим, тяга, подтягивания с весом и уверенная техника.",
    },
    {
        "id": "hypertrophy",
        "title": "Мышечный рост",
        "short_description": "3–4 подхода в диапазоне повторений с умеренным отдыхом.",
        "goal": "Гипертрофия и понятный прогресс по верхней границе диапазона.",
        "level": "Новичок / средний",
        "audience": "Большинство регулярных силовых тренировок.",
    },
    {
        "id": "double_progression",
        "title": "Двойная прогрессия",
        "short_description": "Сначала добрать повторы в диапазоне, затем повышать вес.",
        "goal": "Понятное правило прогресса: 12 / 12 / 12 — увеличить вес.",
        "level": "Новичок / средний",
        "audience": "Большинство упражнений и регулярные тренировки.",
    },
    {
        "id": "strength_circuit",
        "title": "Круговая тренировка",
        "short_description": "10–15 повторений, короткий отдых между упражнениями и 3–4 круга.",
        "goal": "Общая физическая подготовка, тонус и расход энергии.",
        "level": "Новичок / средний",
        "audience": "Короткие занятия, домашние тренировки и выносливость.",
    },
    {
        "id": "technique_light",
        "title": "Техника / лёгкая тренировка",
        "short_description": "2–3 подхода без отказа с большим запасом повторов.",
        "goal": "Восстановление, техника и возвращение после перерыва.",
        "level": "Любой",
        "audience": "После болезни, перерыва или в лёгкий тренировочный день.",
    },
    {
        "id": "periodized_day",
        "title": "Лёгкий / средний / тяжёлый день",
        "short_description": "Периодизация нагрузки: лёгкий, средний или тяжёлый день.",
        "goal": "Менять нагрузку от тренировки к тренировке и не перегружаться.",
        "level": "Средний",
        "audience": "Пользователи, которые тренируются примерно 3 раза в неделю.",
        "default_day_type": "medium",
        "day_options": [
            {"id": "light", "label": "Лёгкий", "description": "2–3 подхода по 10–12 повторений, 3–4 повтора в запасе."},
            {"id": "medium", "label": "Средний", "description": "3 подхода по 8–12 повторений, 1–3 повтора в запасе."},
            {"id": "heavy", "label": "Тяжёлый", "description": "3–5 подходов по 4–8 повторений, 1–2 повтора в запасе."},
        ],
    },
]

MUSCLE_TRANSLATIONS = {
    "chest": "Грудь",
    "triceps": "Трицепс",
    "shoulders": "Плечи",
    "delts": "Дельты",
    "biceps": "Бицепс",
    "back": "Спина",
    "lats": "Широчайшие",
    "upper_back": "Верх спины",
    "lower_back": "Низ спины",
    "lowerback": "Низ спины",
    "traps": "Трапеции",
    "abs": "Пресс",
    "obliques": "Косые мышцы живота",
    "glutes": "Ягодицы",
    "quads": "Квадрицепсы",
    "hamstrings": "Бицепс бедра",
    "adductors": "Приводящие",
    "abductors": "Отводящие",
    "calves": "Икры",
    "forearms": "Предплечья",
    "neck": "Шея",
    "core": "Кор",
    "serratus_anterior": "Передняя зубчатая",
    "hip_flexors": "Сгибатели бедра",
}

EQUIPMENT_TRANSLATIONS = {
    "Barbell": "Штанга",
    "Dumbbell": "Гантели",
    "Dumbbells": "Гантели",
    "Machine": "Тренажёр",
    "Cable": "Кроссовер",
    "Cables": "Кроссовер",
    "Bodyweight": "Собственный вес",
    "Smith Machine": "Машина Смита",
    "Smith-Machine": "Машина Смита",
    "Band": "Резина",
    "Kettlebell": "Гиря",
    "Kettlebells": "Гири",
    "Recovery": "Восстановление",
    "Yoga": "Йога",
    "Plate": "Диск",
    "Stretches": "Растяжка",
    "Cardio": "Кардио",
    "Medicine-Ball": "Медбол",
    "Medicine Ball": "Медбол",
    "Bosu-Ball": "Босу",
    "BOSU Ball": "Босу",
    "TRX": "Петли TRX",
}

GRIP_TRANSLATIONS = {
    "Overhand": "Прямой",
    "Underhand": "Обратный",
    "Neutral": "Нейтральный",
    "Mixed": "Смешанный",
    "Rotating": "Вращающийся",
    "Pinch Grip": "Щипковый",
    "None": "Без хвата",
}

DIFFICULTY_LABELS = {
    "Beginner": "Новичок",
    "Intermediate": "Средний",
    "Advanced": "Продвинутый",
}

STATUS_PRIORITY = {
    "ready": 0,
    "light": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
    "no_data": 5,
}


class TrainingService:
    def __init__(self) -> None:
        self.machine_service = MachineService()
        self.fatigue_service = FatigueService()

    def get_exercise_catalog(
        self,
        session: Session,
        *,
        user_id: str,
        search: str | None = None,
        muscles: list[str] | None = None,
        equipment: list[str] | None = None,
        difficulty: list[str] | None = None,
        force: list[str] | None = None,
        mechanic: list[str] | None = None,
        grips: list[str] | None = None,
        favorites: list[str] | None = None,
        blacklist: list[str] | None = None,
    ) -> ExerciseCatalogResponseSchema:
        filtered = []
        for exercise in load_imported_exercises():
            summary = self._summary(session, exercise, user_id, favorites, blacklist)
            haystack = " ".join(
                [
                    exercise.slug,
                    exercise.name,
                    exercise.name_ru,
                    exercise.equipment,
                    exercise.difficulty,
                    exercise.force,
                    exercise.grips,
                    exercise.mechanic,
                    *exercise.muscles,
                    *exercise.steps,
                    *exercise.guide.setup,
                    *exercise.guide.how_to_perform,
                    *exercise.guide.technique,
                    *exercise.guide.things_to_avoid,
                ]
            ).lower()
            if search and search.lower() not in haystack:
                continue
            if muscles and not any(item in summary.muscles for item in muscles):
                continue
            if equipment and summary.equipment not in equipment:
                continue
            if difficulty and summary.difficulty not in difficulty:
                continue
            if force and summary.force not in force:
                continue
            if mechanic and summary.mechanic not in mechanic:
                continue
            if grips and summary.grips not in grips:
                continue
            filtered.append(summary)
        all_exercises = load_imported_exercises()
        return ExerciseCatalogResponseSchema(
            items=filtered,
            total=len(filtered),
            available_filters=ExerciseCatalogAvailableFiltersSchema(
                muscles=sorted({self._translate_muscle(item) for exercise in all_exercises for item in exercise.muscles}),
                equipment=sorted({self._translate_equipment(exercise.equipment) for exercise in all_exercises}),
                difficulty=["Beginner", "Intermediate", "Advanced"],
                force=["Push", "Pull", "Static", "Stretch"],
                mechanic=["Compound", "Isolation", "Mobility"],
                grips=sorted({self._translate_grip(exercise.grips) for exercise in all_exercises}),
            ),
        )

    def get_exercise_details(
        self,
        session: Session,
        *,
        user_id: str,
        slug: str,
        favorites: list[str] | None = None,
        blacklist: list[str] | None = None,
    ) -> ExerciseDetailsSchema:
        exercise = get_imported_exercise(slug) or load_imported_exercises()[0]
        summary = self._summary(session, exercise, user_id, favorites, blacklist)
        compatibility = self._compatibility(session, exercise, user_id, blacklist)
        load_settings = self._load_settings(session, user_id, exercise.slug, exercise)
        history = self._history_rows(session, user_id, exercise.slug)
        videos = [
            ExerciseVideoAssetSchema(
                url=video.relative_url,
                label=f"{'Мужчина' if video.gender == 'male' else 'Женщина'} · {'Сбоку' if video.view == 'side' else 'Спереди'}",
                view=video.view,
                gender=video.gender,
            )
            for video in exercise.videos
        ]
        primary_muscles = [self._translate_muscle(item) for item in exercise.muscles[:2]]
        secondary_muscles = [self._translate_muscle(item) for item in exercise.muscles[2:4]]
        return ExerciseDetailsSchema(
            **summary.model_dump(),
            description=self._description(exercise),
            short_steps=list(exercise.steps[:3]),
            guide=ExerciseGuideSchema(
                setup=list(exercise.guide.setup),
                how_to_perform=list(exercise.guide.how_to_perform),
                technique=list(exercise.guide.technique),
                things_to_avoid=list(exercise.guide.things_to_avoid),
                key_tips=list(exercise.guide.technique[:5]),
            ),
            videos=videos,
            primary_muscles=primary_muscles,
            secondary_muscles=secondary_muscles,
            stabilizers=["Кор", "Плечевой пояс"],
            muscle_role_text=f"{summary.name} нагружает {' и '.join(primary_muscles).lower() or 'целевые мышцы'} и использует {', '.join(secondary_muscles).lower() or 'стабилизаторы корпуса'} как вспомогательную группу.",
            compatibility=compatibility,
            load_settings=load_settings,
            history=history,
            load_progress=self._load_progress(history),
            similar=self._similar_exercises(exercise, session, user_id, favorites, blacklist),
            equipment_alternatives=[f"{self._translate_equipment(exercise.equipment)} → Тренажёр", f"{self._translate_equipment(exercise.equipment)} → Собственный вес"],
            when_to_choose_alternative=["Нет подходящего оборудования", "Нужно снизить нагрузку на суставы", "Нужно сместить акцент на другие мышцы"],
        )

    def get_quick_start(
        self,
        session: Session,
        *,
        user_id: str,
        selected: str | None,
        favorites: list[str] | None,
        blacklist: list[str] | None,
    ) -> QuickStartDataSchema:
        selected_slug = selected or FEATURED["quick_start"][0]
        machine = self.machine_service.get_machine_health(session, "ready")
        return QuickStartDataSchema(
            recommendation=QuickStartRecommendationSchema(
                title="Сегодня лучше: спина + бицепс" if user_id != "guest" else "Гостевой режим: быстрый выбор",
                description=(
                    "Грудь и трицепс ещё восстанавливаются, поэтому система рекомендует тяговые движения и умеренную работу на бицепс."
                    if user_id != "guest"
                    else "История пользователя не используется. Можно выбрать упражнение и сразу перейти к настройке."
                ),
                cta="Подробнее",
            ),
            machine=MachineHealthSchema.model_validate(machine),
            filter_groups={
                "audience": ["Рекомендовано", "Последние", "Избранные"],
                "muscleFocus": ["Спина", "Бицепс", "Грудь", "Ноги", "Плечи", "Кор"],
                "equipment": ["Штанга", "Тренажёр", "Кроссовер", "Собственный вес"],
            },
            recommended=[
                self._quick_start_item(session, FEATURED["quick_start"][0], "Причина: спина готова к нагрузке", user_id, favorites, blacklist),
                self._quick_start_item(session, FEATURED["today"][1], "Причина: подходит под цель «сила + форма»", user_id, favorites, blacklist),
                self._quick_start_item(session, FEATURED["today"][2], "Причина: лёгкая усталость, можно выполнить", user_id, favorites, blacklist),
            ],
            recent=[self._quick_start_item(session, slug, "Последняя удачная сессия", user_id, favorites, blacklist) for slug in FEATURED["recent"]],
            favorites=[self._quick_start_item(session, slug, "В избранном", user_id, favorites, blacklist) for slug in (favorites or FEATURED["recent"][:2])],
            selected_exercise_slug=selected_slug,
            selected_exercise=self._selected_quick_start_exercise(session, selected_slug, user_id, favorites, blacklist),
        )

    def get_today_workout(
        self,
        session: Session,
        *,
        user_id: str,
        scenario: str,
        selected: str | None,
        favorites: list[str] | None,
        blacklist: list[str] | None,
    ) -> TodayWorkoutDataSchema:
        plan_slugs = self._today_plan_slugs(session, user_id)
        selected_slug = selected if selected in plan_slugs else plan_slugs[0]
        machine_scenario = "blocked" if scenario == "blocked" else "ready"
        machine = self.machine_service.get_machine_health(session, machine_scenario)
        readiness_percent = 42 if scenario == "recovery" else 78
        rows = []
        for index, slug in enumerate(plan_slugs):
            details = self.get_exercise_details(session, user_id=user_id, slug=slug, favorites=favorites, blacklist=blacklist)
            base_status = "up-next" if index == 0 else ("planned" if index < 3 else "warning")
            if scenario == "completed":
                status = "completed" if index < 4 else "planned"
            elif scenario == "in-progress":
                status = "in-progress" if slug == selected_slug else ("completed" if index == 0 else base_status)
            elif scenario == "recovery":
                status = "warning" if index == 0 else base_status
            elif scenario == "blocked":
                status = "warning"
            else:
                status = base_status
            rows.append(
                WorkoutExerciseRowSchema(
                    id=slug,
                    slug=slug,
                    name=details.name,
                    muscles=", ".join(details.muscles[:2]),
                    image_url=details.image_url,
                    load=f"{details.load_settings.weight:g} кг • {details.load_settings.sets}×{details.load_settings.reps}",
                    rest=f"{details.load_settings.rest_seconds} сек",
                    status=status,
                    calibration="Потребуется перед упражнением" if details.load_settings.calibration == "required" else "Сохранена",
                    note="Следующее" if index == 0 else None,
                )
            )
        warnings = []
        if scenario == "blocked":
            warnings.append(TodayWorkoutWarningSchema(tone="blocked", title="Тренажёр не готов к старту", description="Один из приводов недоступен. Запуск упражнений временно заблокирован."))
        elif scenario == "recovery":
            warnings.append(TodayWorkoutWarningSchema(tone="warning", title="Высокая усталость груди", description="Сегодня лучше держать объём под контролем и при необходимости заменить жимовые движения."))
        selected_panel = self._workout_panel(session, selected_slug, user_id, favorites, blacklist)
        return TodayWorkoutDataSchema(
            title="Спина + бицепс",
            subtitle="План на сегодня с учётом целей, усталости мышц и последних результатов.",
            readiness_percent=readiness_percent,
            machine=MachineHealthSchema.model_validate(machine),
            start_state=scenario if scenario in {"planned", "in-progress", "completed", "blocked", "recovery"} else "planned",
            summary={"exercises": len(rows), "sets": sum(self._load_settings(session, user_id, row.slug, get_imported_exercise(row.slug)).sets for row in rows), "duration": "45 мин"},
            main_action="Продолжить тренировку" if scenario == "in-progress" else ("Открыть результат" if scenario == "completed" else ("Старт заблокирован" if scenario == "blocked" else "Начать тренировку")),
            exercise_rows=rows,
            selected_exercise_id=selected_slug,
            selected_exercise=selected_panel,
            warnings=warnings,
            muscles=self._muscle_cards(session, user_id),
            progress=WorkoutProgressSchema(
                completed_exercises=len(rows) if scenario == "completed" else (min(2, len(rows)) if scenario == "in-progress" else 0),
                total_exercises=len(rows),
                completed_sets=18 if scenario == "completed" else (7 if scenario == "in-progress" else 0),
                total_sets=sum(self._load_settings(session, user_id, row.slug, get_imported_exercise(row.slug)).sets for row in rows),
                minutes_left=0 if scenario == "completed" else (27 if scenario == "in-progress" else 45),
                percent=100 if scenario == "completed" else (39 if scenario == "in-progress" else 0),
                next_step="Тренировка завершена" if scenario == "completed" else "Сгибание рук",
            ),
            quick_actions=["Изменить тренировку", "Заменить упражнение", "Сохранить как программу", "Перенести тренировку"],
        )

    def save_today_workout_plan(self, session: Session, payload: TodayWorkoutPlanMutationSchema) -> TrainingPlanMutationResultSchema:
        slugs = self._sanitize_today_plan_slugs(payload.slugs)
        self._save_setting(session, payload.user_id, TODAY_PLAN_SETTING_KEY, {"slugs": slugs})
        return TrainingPlanMutationResultSchema(status="saved")

    def get_program_library(self, session: Session, *, selected_program_id: str | None) -> ProgramLibraryDataSchema:
        programs = self._programs(session)
        selected = next((item for item in programs if item.id == selected_program_id), programs[0])
        summaries = [self._program_summary(program) for program in programs]
        return ProgramLibraryDataSchema(
            search_placeholder="Найти программу...",
            category_filters=["Все", "Для меня", "Силовые", "Фуллбоди", "Восстановление"],
            duration_filters=["30 минут", "45 минут"],
            level_filters=["Новичок", "Средний"],
            equipment_filters=["Тренажёр", "Штанга", "Кроссовер"],
            recommended=summaries[:4],
            all_programs=summaries,
            selected_program=self._program_details(selected),
        )

    def create_program(self, session: Session, payload: ProgramMutationSchema) -> ProgramMutationResultSchema:
        existing_ids = set(session.scalars(select(WorkoutProgram.id)))
        existing_ids.update(program.id for program in self._default_programs())
        base_id = self._program_slug(payload.name)
        program_id = base_id
        suffix = 2
        while program_id in existing_ids:
            program_id = f"{base_id}-{suffix}"
            suffix += 1

        raw_groups = payload.structure.get("builderGroups") if isinstance(payload.structure, dict) else None
        exercise_count = 0
        set_count = 0
        if isinstance(raw_groups, list):
            for raw_group in raw_groups:
                if not isinstance(raw_group, dict):
                    continue
                raw_items = raw_group.get("items")
                if not isinstance(raw_items, list):
                    continue
                exercise_count += len(raw_items)
                set_count += len(raw_items)

        program = WorkoutProgram(
            id=program_id,
            owner_user_id=payload.user_id,
            source="custom",
            name=payload.name,
            subtitle=payload.subtitle,
            program_type=payload.program_type,
            difficulty=payload.difficulty,
            duration_minutes=max(1, payload.duration_minutes),
            exercise_count=exercise_count,
            set_count=set_count,
            focus_tags=list(payload.focus_tags),
            recommended_today=payload.recommended_today,
            description=payload.description,
            structure=dict(payload.structure),
        )
        session.add(program)
        session.commit()
        return ProgramMutationResultSchema(id=program_id, status="created")

    def delete_program(self, session: Session, *, program_id: str, user_id: str) -> bool:
        program = next((item for item in self._programs(session, user_id) if item.id == program_id), None)
        if program is None:
            return False

        if program.source == "custom" and program.owner_user_id == user_id:
            persisted_program = session.scalar(
                select(WorkoutProgram).where(
                    WorkoutProgram.id == program_id,
                    WorkoutProgram.deleted.is_(False),
                    WorkoutProgram.source == "custom",
                    WorkoutProgram.owner_user_id == user_id,
                )
            )
            if persisted_program is None:
                return False
            persisted_program.deleted = True
        else:
            hidden_program = session.scalar(
                select(UserHiddenWorkoutProgram).where(
                    UserHiddenWorkoutProgram.user_id == user_id,
                    UserHiddenWorkoutProgram.program_id == program_id,
                )
            )
            if hidden_program is None:
                session.add(UserHiddenWorkoutProgram(user_id=user_id, program_id=program_id))

        session.commit()
        return True

    def get_calendar(self, session: Session, *, user_id: str, month: str | None) -> WorkoutCalendarDataSchema:
        # History journal only: days come from the calendar month, entries from
        # saved WorkoutSession results. Nothing here is planned or scheduled.
        today = datetime.now().astimezone().date()
        first_day = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
        grid_start = first_day - timedelta(days=first_day.weekday())
        grid_days = [grid_start + timedelta(days=offset) for offset in range(42)]
        statement = (
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status.in_([WorkoutSessionStatus.completed, WorkoutSessionStatus.partial, WorkoutSessionStatus.aborted]),
                WorkoutSession.started_at >= datetime.combine(grid_days[0] - timedelta(days=1), time.min, tzinfo=UTC),
                WorkoutSession.started_at < datetime.combine(grid_days[-1] + timedelta(days=2), time.min, tzinfo=UTC),
            )
            .order_by(WorkoutSession.started_at.asc(), WorkoutSession.id.asc())
        )
        workouts_by_day: dict[date, list[CalendarWorkoutSchema]] = {}
        for workout_session in session.scalars(statement):
            local_started = self._as_local(workout_session.started_at)
            workouts_by_day.setdefault(local_started.date(), []).append(self._calendar_workout(workout_session, local_started))
        days = [
            CalendarDaySchema(
                id=day.isoformat(),
                day=day.day,
                in_month=day.month == first_day.month,
                is_today=day == today,
                workouts=workouts_by_day.get(day, []),
            )
            for day in grid_days
        ]
        return WorkoutCalendarDataSchema(
            month=first_day.strftime("%Y-%m"),
            title=f"{RU_MONTHS[first_day.month - 1]} {first_day.year}",
            today=today.isoformat(),
            weekdays=["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
            days=days,
            workout_count=sum(len(day.workouts) for day in days if day.in_month),
        )

    def _calendar_workout(self, workout_session: WorkoutSession, local_started: datetime) -> CalendarWorkoutSchema:
        exercises = sorted(workout_session.exercise_sessions, key=lambda item: (item.order_index, item.id))
        set_results = [result for exercise in exercises for result in exercise.set_results]
        volume = int(round(sum((result.weight_kg or 0) * (result.reps or result.actual_value or 0) for result in set_results)))
        finished_local = self._as_local(workout_session.finished_at) if workout_session.finished_at else None
        duration_minutes = max(1, int(round(workout_session.duration_seconds / 60))) if workout_session.duration_seconds else None
        return CalendarWorkoutSchema(
            id=workout_session.id,
            title=workout_session.title,
            status=workout_session.status.value,
            started_at=workout_session.started_at.astimezone(UTC) if workout_session.started_at.tzinfo else workout_session.started_at.replace(tzinfo=UTC),
            finished_at=(workout_session.finished_at.astimezone(UTC) if workout_session.finished_at.tzinfo else workout_session.finished_at.replace(tzinfo=UTC)) if workout_session.finished_at else None,
            time_label=f"{local_started:%H:%M}–{finished_local:%H:%M}" if finished_local else f"{local_started:%H:%M}",
            duration=f"{duration_minutes} мин" if duration_minutes else "—",
            exercise_count=len(exercises),
            set_count=len(set_results),
            volume=f"{volume:,} кг".replace(",", " ") if volume > 0 else "—",
            exercises=[self._calendar_exercise(exercise) for exercise in exercises],
        )

    def _calendar_exercise(self, exercise: ExerciseSession) -> CalendarWorkoutExerciseSchema:
        results = sorted(exercise.set_results, key=lambda item: item.set_number)
        if exercise.status == ExerciseSessionStatus.skipped or not results:
            result = "пропущено" if exercise.status == ExerciseSessionStatus.skipped else "без сохранённых подходов"
        elif exercise.kind == RuntimeExerciseKind.timed:
            result = f"{len(results)} подх. · {sum(item.duration_seconds or item.actual_value or 0 for item in results)} сек"
        else:
            total_reps = sum(item.reps or item.actual_value or 0 for item in results)
            weights = [item.weight_kg for item in results if item.weight_kg]
            result = f"{len(results)} подх. · {total_reps} повт." + (f" · до {max(weights):g} кг" if weights else "")
        return CalendarWorkoutExerciseSchema(name=exercise.exercise_name, status=exercise.status.value, set_count=len(results), result=result)

    def _as_local(self, value: datetime) -> datetime:
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone()

    def get_builder(self, session: Session, *, user_id: str, program_id: str | None, selected_exercise_id: str | None) -> WorkoutBuilderDataSchema:
        programs = self._programs(session, user_id)
        selected_program = next((item for item in programs if item.id == program_id), programs[0] if programs else None)
        if selected_program is None:
            return WorkoutBuilderDataSchema(
                title="Конструктор тренировок",
                subtitle="Соберите тренировку из упражнений, настройте нагрузку — изменения сохраняются автоматически.",
                programs=[],
                strength_modes=self.get_strength_modes(),
                selected_program_id="",
                info={
                    "name": "Нет тренировок",
                    "type": "—",
                    "duration": "",
                    "difficulty": "—",
                    "description": "Создайте новую тренировку.",
                },
                groups=[],
                selected_exercise_id="",
                selected_exercise=self._empty_builder_editor("Новая тренировка"),
                add_suggestions=[],
                summary_cards=[],
                warnings=[],
            )

        builder_value = self._builder_setting_value(session, user_id, selected_program.id)
        groups = self._builder_groups(session, user_id, selected_program)
        duration = self._builder_duration_estimate(session, user_id, groups)
        persisted_selected_id = self._builder_selected_exercise_id(session, user_id, selected_program.id)
        available_items = [item for group in groups for item in group.items]
        selected_item = next((item for item in available_items if item.id == (selected_exercise_id or persisted_selected_id)), None)
        if selected_item is None and available_items:
            selected_item = available_items[0]

        if selected_item is not None:
            selected_item_id = selected_item.id
            selected_editor = self._builder_editor(session, user_id, selected_program.id, selected_item)
        else:
            selected_item_id = ""
            selected_editor = self._empty_builder_editor(self._builder_workout_name(builder_value, selected_program))

        return WorkoutBuilderDataSchema(
            title="Конструктор тренировок",
            subtitle="Соберите тренировку из упражнений, настройте нагрузку — изменения сохраняются автоматически.",
            programs=[self._builder_program_tab(self._builder_workout_name(self._builder_setting_value(session, user_id, program.id), program), program) for program in programs],
            strength_modes=self.get_strength_modes(),
            selected_program_id=selected_program.id,
            info=self._builder_info(selected_program, self._builder_workout_name(builder_value, selected_program), duration.minutes),
            groups=groups,
            selected_exercise_id=selected_item_id,
            selected_exercise=selected_editor,
            add_suggestions=[],
            summary_cards=self._builder_summary_cards(groups, duration),
            warnings=[
                {"tone": "warning", "title": "Длинная тренировка", "description": "Расчётное время больше целевого. Можно убрать один вспомогательный блок."},
                {"tone": "warning", "title": "Короткий отдых", "description": "Для тяжёлых подходов рекомендуется отдых 60–90 секунд."},
                {"tone": "success", "title": "Упражнения из чёрного списка отсутствуют", "description": "Текущая версия плана безопасна для пользователя."},
            ],
        )

    def get_strength_modes(self) -> list[StrengthTrainingModeSchema]:
        return [StrengthTrainingModeSchema.model_validate(item) for item in STRENGTH_TRAINING_MODES]

    def save_builder_plan(self, session: Session, payload: BuilderPlanMutationSchema) -> TrainingPlanMutationResultSchema:
        programs = self._programs(session, payload.user_id)
        if not programs and not payload.program_id:
            return TrainingPlanMutationResultSchema(status="saved")

        program_id = payload.program_id or programs[0].id
        selected_program = next((item for item in programs if item.id == program_id), None)
        if selected_program is None:
            return TrainingPlanMutationResultSchema(status="saved")

        user_id = payload.user_id
        # Legacy plans become profiles first, so this save edits the same profiles every workout reads.
        self.ensure_exercise_profiles(session, user_id)
        groups = self._sanitize_builder_groups(payload.groups, user_id)
        current_value = self._builder_setting_value(session, user_id, program_id)
        previous_items = {item.id: item for group in self._stored_builder_groups(session, user_id, selected_program) for item in group.items}
        raw_editors = current_value.get("editors") if isinstance(current_value.get("editors"), dict) else {}
        items = [item for group in groups for item in group.items]
        states = self._user_states(session, user_id, {item.slug for item in items})
        workout_name = self._sanitize_builder_workout_name(payload.workout_name, current_value, selected_program)
        edited_slugs: set[str] = set()
        editors: dict[str, Any] = {}

        selected_item = next((item for item in items if item.id == payload.selected_exercise_id), None) if payload.selected_exercise_id else None
        if selected_item is not None and payload.selected_exercise and payload.selected_exercise.name == selected_item.name:
            exercise = get_imported_exercise(selected_item.slug)
            load_type = payload.selected_exercise.load_type or selected_item.load_type or self._builder_load_type(exercise)
            default_target = self._parse_builder_target_value(selected_item.sets, selected_item.load, self._default_builder_target_value(exercise))
            editor = self._normalize_builder_editor(payload.selected_exercise, load_type, default_target, self._builder_item_set_count(selected_item, load_type))
            snapshot = {**editor.model_dump(mode="json", by_alias=True), "exerciseSlug": selected_item.slug}
            # An editor identical to the one saved last time is a re-send, not an edit: it must not
            # undo a change made to the same exercise from another workout or the runtime.
            if raw_editors.get(selected_item.id) != snapshot:
                self._store_user_profile(session, user_id, selected_item.slug, self._editor_profile(editor), states)
            editors[selected_item.id] = snapshot
            edited_slugs.add(selected_item.slug)

        for item in items:
            if item.slug in edited_slugs:
                continue
            previous = previous_items.get(item.id)
            if previous is not None and previous.slug == item.slug and self._item_load_signature(previous) == self._item_load_signature(item):
                continue
            # Added, replaced or re-configured through the group payload: these values are explicit input.
            profile = self._item_profile(item, read_profile(states.get(item.slug)))
            self._store_user_profile(session, user_id, item.slug, profile, states)
            edited_slugs.add(item.slug)

        groups = self._apply_exercise_profiles(session, user_id, groups, states)
        self._save_setting(
            session,
            user_id,
            self._builder_setting_key(program_id),
            {
                "workoutName": workout_name,
                "groups": [group.model_dump(mode="json", by_alias=True) for group in groups],
                "editors": editors,
                "selectedExerciseId": payload.selected_exercise_id,
            },
        )
        return TrainingPlanMutationResultSchema(status="saved")

    def _today_plan_slugs(self, session: Session, user_id: str) -> list[str]:
        setting = self._get_setting(session, user_id, TODAY_PLAN_SETTING_KEY)
        if setting is None:
            return list(FEATURED["today"])

        value = setting.value.get("slugs") if isinstance(setting.value, dict) else None
        if not isinstance(value, list):
            return list(FEATURED["today"])

        slugs = self._sanitize_today_plan_slugs(value)
        return slugs or list(FEATURED["today"])

    def _sanitize_today_plan_slugs(self, slugs: list[object]) -> list[str]:
        sanitized = [str(item) for item in slugs if isinstance(item, str) and get_imported_exercise(item) is not None]
        return sanitized or list(FEATURED["today"])

    def _builder_groups(self, session: Session, user_id: str, program: WorkoutProgram) -> list[BuilderWorkoutGroupSchema]:
        """Workout structure from the plan, load settings from the shared exercise profiles."""
        self.ensure_exercise_profiles(session, user_id)
        groups = self._stored_builder_groups(session, user_id, program)
        return self._apply_exercise_profiles(session, user_id, groups)

    def _stored_builder_groups(self, session: Session, user_id: str, program: WorkoutProgram) -> list[BuilderWorkoutGroupSchema]:
        value = self._builder_setting_value(session, user_id, program.id)
        if value:
            raw_groups = value.get("groups")
            if isinstance(raw_groups, list):
                try:
                    groups = [BuilderWorkoutGroupSchema.model_validate(item) for item in raw_groups if isinstance(item, dict)]
                except ValidationError:
                    groups = []
                groups = self._sanitize_builder_groups(groups, user_id)
                if groups:
                    return groups

        return self._sanitize_builder_groups(self._program_builder_groups(program), user_id)

    def _user_states(self, session: Session, user_id: str, slugs: set[str] | None = None) -> dict[str, UserExerciseState]:
        statement = select(UserExerciseState).where(UserExerciseState.user_id == user_id)
        if slugs is not None:
            if not slugs:
                return {}
            statement = statement.where(UserExerciseState.exercise_slug.in_(slugs))
        return {row.exercise_slug: row for row in session.scalars(statement)}

    def _store_user_profile(
        self, session: Session, user_id: str, slug: str, profile: ExerciseProfileSchema, states: dict[str, UserExerciseState],
    ) -> None:
        state = states.get(slug)
        if state is None:
            state = UserExerciseState(user_id=user_id, exercise_slug=slug)
            session.add(state)
            states[slug] = state
        store_profile(state, profile)

    def ensure_exercise_profiles(self, session: Session, user_id: str, *, commit: bool = True) -> None:
        """One-time migration of per-workout load values into shared exercise profiles.

        The first workout in "Мои тренировки" order that contains an exercise defines its profile;
        the weight actually performed last time is kept on top of it. Runtime writes call this
        before their first profile write (``commit=False``: their own transaction commits it).
        """
        ready = session.info.setdefault(PROFILES_READY_KEY, set())
        if user_id in ready:
            return
        if session.get(User, user_id) is None:
            return
        states = self._user_states(session, user_id)
        seeded = False
        for program in self._programs(session, user_id):
            value = self._builder_setting_value(session, user_id, program.id)
            editors = value.get("editors") if isinstance(value.get("editors"), dict) else {}
            for group in self._stored_builder_groups(session, user_id, program):
                for item in group.items:
                    seeded = self._seed_exercise_profile(session, user_id, item, states, editors) or seeded
        if seeded:
            session.commit() if commit else session.flush()
        ready.add(user_id)

    def _seed_exercise_profile(
        self, session: Session, user_id: str, item: BuilderExerciseItemSchema,
        states: dict[str, UserExerciseState], editors: dict[str, Any] | None = None,
    ) -> bool:
        state = states.get(item.slug)
        if read_profile(state) is not None:
            return False
        editor = self._saved_builder_editor(item, (editors or {}).get(item.id))
        profile = self._editor_profile(editor) if editor is not None else self._item_profile(item, None)
        performed = last_performed_working_weight(session, user_id, item.slug) if profile.load_type == "weighted" else None
        if performed is not None:
            profile = profile_from_effective(profile, weight=performed)
        self._store_user_profile(session, user_id, item.slug, profile, states)
        return True

    def _apply_exercise_profiles(
        self, session: Session, user_id: str, groups: list[BuilderWorkoutGroupSchema],
        states: dict[str, UserExerciseState] | None = None,
    ) -> list[BuilderWorkoutGroupSchema]:
        items = [item for group in groups for item in group.items]
        if states is None:
            states = self._user_states(session, user_id, {item.slug for item in items})
        if session.get(User, user_id) is not None:
            # Exercises added after the migration (e.g. a new custom program) get a profile on first read.
            seeded = False
            for item in items:
                seeded = self._seed_exercise_profile(session, user_id, item, states) or seeded
            if seeded:
                session.commit()
        return [
            group.model_copy(update={"items": [
                self._profile_item(item, profile) if (profile := read_profile(states.get(item.slug))) is not None else item
                for item in group.items
            ]})
            for group in groups
        ]

    def _profile_item(self, item: BuilderExerciseItemSchema, profile: ExerciseProfileSchema) -> BuilderExerciseItemSchema:
        load_type = profile.load_type
        params = effective_set_params(load_type, profile_set_params(profile), profile.load_mode, profile.tempo)
        strength_mode_id = self._normalize_strength_mode_id(profile.strength_mode_id)
        strength_day_type = self._normalize_strength_day_type(strength_mode_id, profile.strength_day_type)
        return item.model_copy(update={
            "load_type": load_type,
            "per_side": profile.per_side,
            "sets": self._format_builder_sets(load_type, int(params["sets"]), int(params["reps"]), params.get("durationSeconds")),
            "load": self._format_builder_load(load_type, float(params["weight"])),
            "rest": f"{params['restSeconds']} сек",
            "strength_mode_id": strength_mode_id,
            "strength_day_type": strength_day_type,
            "strength_plan": self._builder_strength_plan(strength_mode_id, strength_day_type, load_type, params),
        })

    def _editor_profile(self, editor: BuilderExerciseEditorSchema) -> ExerciseProfileSchema:
        params = editor.set_params
        load_type = editor.load_type or "weighted"
        return ExerciseProfileSchema(
            load_type=load_type,
            sets=int(params.get("sets") or 1),
            reps=int(params.get("reps") or 1),
            weight=float(params.get("weight") or 0),
            rest_seconds=int(params.get("restSeconds") or 60),
            duration_seconds=int(params["durationSeconds"]) if load_type == "timed" and params.get("durationSeconds") else None,
            load_mode=editor.load_mode,
            tempo=editor.tempo,
            strength_mode_id=editor.strength_mode_id,
            strength_day_type=editor.strength_day_type,
            per_side=editor.per_side,
            note=editor.note,
        )

    def _item_profile(self, item: BuilderExerciseItemSchema, base: ExerciseProfileSchema | None) -> ExerciseProfileSchema:
        """Profile from an item's effective plan values, keeping the base profile's modifiers."""
        exercise = get_imported_exercise(item.slug)
        load_type = item.load_type or self._builder_load_type(exercise)
        sets = self._builder_item_set_count(item, load_type)
        target = self._parse_builder_target_value(item.sets, item.load, self._default_builder_target_value(exercise))
        duration = self._parse_builder_duration(item.sets) if load_type == "timed" else None
        reps = duration or target
        weight = self._parse_weight(item.load) if load_type == "weighted" else 0.0
        rest = self._parse_builder_rest(item.rest)
        identity = {
            "load_type": load_type,
            "strength_mode_id": item.strength_mode_id,
            "strength_day_type": item.strength_day_type,
            "per_side": item.per_side,
        }
        if base is None:
            return ExerciseProfileSchema(
                **identity, sets=sets, reps=reps, weight=weight, rest_seconds=rest,
                duration_seconds=reps if load_type == "timed" else None,
            )
        base = base.model_copy(update={
            **identity,
            **({} if load_type == "timed" else {"duration_seconds": None}),
            # The item explicitly says "вес тела": no external weight.
            **({} if load_type == "weighted" else {"weight": 0}),
        })
        return profile_from_effective(base, weight=weight, reps=reps, sets=sets, rest_seconds=rest)

    def _item_load_signature(self, item: BuilderExerciseItemSchema) -> tuple[object, ...]:
        return (item.load_type, item.sets, item.load, item.rest, item.strength_mode_id, item.strength_day_type, item.per_side)

    def _sanitize_builder_groups(self, groups: list[BuilderWorkoutGroupSchema], user_id: str = "alexey") -> list[BuilderWorkoutGroupSchema]:
        sanitized: list[BuilderWorkoutGroupSchema] = []
        for group in groups:
            items = []
            for item in group.items:
                exercise = get_imported_exercise(item.slug)
                if exercise is None:
                    continue
                load_type = item.load_type or self._builder_load_type(exercise)
                sets = self._builder_item_set_count(item, load_type)
                target_value = self._parse_builder_target_value(item.sets, item.load, self._default_builder_target_value(exercise))
                duration_seconds = self._parse_builder_duration(item.sets) if load_type == "timed" else None
                rest_seconds = self._parse_builder_rest(item.rest)
                weight = self._parse_weight(item.load)
                if load_type == "weighted" and weight <= 0 and duration_seconds is None:
                    weight = self._default_builder_weight(exercise)
                strength_mode_id = self._normalize_strength_mode_id(item.strength_mode_id)
                strength_day_type = self._normalize_strength_day_type(strength_mode_id, item.strength_day_type)
                strength_plan = self._builder_strength_plan(
                    strength_mode_id,
                    strength_day_type,
                    load_type,
                    {
                        "sets": sets,
                        "reps": target_value,
                        "weight": weight,
                        "restSeconds": rest_seconds,
                        **({"durationSeconds": duration_seconds} if duration_seconds is not None else {}),
                    },
                )

                items.append(
                    item.model_copy(
                        update={
                            "muscles": [self._translate_muscle(muscle) for muscle in exercise.muscles],
                            "affects_fatigue": equipment_affects_fatigue(exercise.equipment),
                            "preview_video_url": self._preview_video_url(exercise, user_id),
                            "load_type": load_type,
                            "per_side": item.per_side,
                            "sets": self._format_builder_sets(load_type, sets, target_value, duration_seconds),
                            "load": self._format_builder_load(load_type, weight),
                            "rest": f"{rest_seconds} сек",
                            "strength_mode_id": strength_mode_id,
                            "strength_day_type": strength_day_type,
                            "strength_plan": strength_plan,
                        }
                    )
                )
            sanitized.append(group.model_copy(update={"items": items}))
        return sanitized or self._sanitize_builder_groups(self._default_builder_groups(), user_id)

    def _builder_setting_key(self, program_id: str) -> str:
        return f"{BUILDER_PLAN_SETTING_KEY}.{program_id}"

    def _builder_setting_value(self, session: Session, user_id: str, program_id: str) -> dict[str, Any]:
        setting = self._get_setting(session, user_id, self._builder_setting_key(program_id))
        if setting and isinstance(setting.value, dict):
            return setting.value

        default_programs = self._default_programs()
        if default_programs and program_id == default_programs[0].id:
            legacy_setting = self._get_setting(session, user_id, BUILDER_PLAN_SETTING_KEY)
            if legacy_setting and isinstance(legacy_setting.value, dict):
                return legacy_setting.value

        return {}

    def _builder_selected_exercise_id(self, session: Session, user_id: str, program_id: str) -> str | None:
        value = self._builder_setting_value(session, user_id, program_id).get("selectedExerciseId")
        return value if isinstance(value, str) else None

    def _saved_builder_editor(self, item: BuilderExerciseItemSchema, raw_editor: Any) -> BuilderExerciseEditorSchema | None:
        if not isinstance(raw_editor, dict):
            return None
        # Old snapshots have no slug: retain them only when their name still matches.
        if raw_editor.get("exerciseSlug", item.slug) != item.slug or raw_editor.get("name") != item.name:
            return None
        try:
            editor = BuilderExerciseEditorSchema.model_validate(raw_editor)
        except ValidationError:
            return None
        exercise = get_imported_exercise(item.slug)
        load_type = item.load_type or self._builder_load_type(exercise)
        if editor.load_type is not None and editor.load_type != load_type:
            return None
        editor = self._normalize_builder_editor(
            editor, load_type,
            self._parse_builder_target_value(item.sets, item.load, self._default_builder_target_value(exercise)),
            self._builder_item_set_count(item, load_type),
        )
        params = editor.effective_set_params
        # Compare effective values, not raw controls: mode/tempo modifiers apply only once.
        if (
            self._format_builder_sets(load_type, params["sets"], params["reps"], params.get("durationSeconds")) != item.sets
            or self._format_builder_load(load_type, params["weight"]) != item.load
            or params["restSeconds"] != self._parse_builder_rest(item.rest)
            or editor.strength_mode_id != item.strength_mode_id
            or editor.strength_day_type != item.strength_day_type
            or editor.per_side != item.per_side
        ):
            return None
        return editor

    def _builder_editor(
        self,
        session: Session,
        user_id: str,
        program_id: str,
        selected_item: BuilderExerciseItemSchema,
    ) -> BuilderExerciseEditorSchema:
        exercise = get_imported_exercise(selected_item.slug)
        load_type = selected_item.load_type or self._builder_load_type(exercise)
        default_target = self._parse_builder_target_value(selected_item.sets, selected_item.load, self._default_builder_target_value(exercise))
        default_sets = self._builder_item_set_count(selected_item, load_type)
        state = self._user_state(session, user_id, selected_item.slug)
        profile = read_profile(state)
        if profile is not None:
            # The exercise profile is shared: every workout edits the same settings of this exercise.
            editor = BuilderExerciseEditorSchema(
                name=selected_item.name,
                subtitle=selected_item.muscle_group,
                set_params=profile_set_params(profile),
                load_type=profile.load_type,
                per_side=profile.per_side,
                load_mode=profile.load_mode,
                tempo=profile.tempo,
                strength_mode_id=self._normalize_strength_mode_id(profile.strength_mode_id),
                strength_day_type=profile.strength_day_type,
                note=profile.note or DEFAULT_BUILDER_NOTE,
            )
            return self._normalize_builder_editor(editor, profile.load_type, default_target, profile.sets)

        set_params: dict[str, int | float] = {
            "sets": default_sets,
            "reps": default_target,
            "weight": self._parse_weight(selected_item.load) if load_type == "weighted" else 0,
            "restSeconds": self._parse_builder_rest(selected_item.rest),
        }
        if load_type == "timed":
            set_params["durationSeconds"] = default_target
        editor = BuilderExerciseEditorSchema(
            name=selected_item.name,
            subtitle=selected_item.muscle_group,
            set_params=set_params,
            load_type=load_type,
            per_side=selected_item.per_side,
            # Group values already describe the effective plan; global modifiers would apply twice.
            load_mode="Обычный вес",
            tempo="Обычный",
            strength_mode_id=selected_item.strength_mode_id,
            strength_day_type=selected_item.strength_day_type,
            strength_plan=selected_item.strength_plan,
            note=DEFAULT_BUILDER_NOTE,
        )
        return self._normalize_builder_editor(editor, load_type, default_target, default_sets)

    def _empty_builder_editor(self, workout_name: str) -> BuilderExerciseEditorSchema:
        return BuilderExerciseEditorSchema(
            name=workout_name,
            subtitle="Добавьте упражнение, чтобы настроить нагрузку.",
            set_params={"reps": 10, "weight": 0, "restSeconds": 60},
            load_type="weighted",
            load_mode="Обычный вес",
            tempo="Обычный",
            strength_mode_id="basic",
            strength_day_type=None,
            strength_plan=[],
            note="",
        )

    def _builder_program_tab(self, workout_name: str, program: WorkoutProgram) -> BuilderProgramTabSchema:
        return BuilderProgramTabSchema(
            id=program.id,
            name=workout_name,
            subtitle=program.subtitle,
            recommended_today=program.recommended_today,
            can_delete=True,
        )

    def _builder_info(self, program: WorkoutProgram, workout_name: str, duration_minutes: int) -> dict[str, str]:
        type_labels = {"strength": "Силовая", "fullbody": "Фуллбоди", "mobility": "Восстановление"}
        difficulty_labels = {"novice": "Новичок", "easy": "Лёгкая", "medium": "Средняя", "advanced": "Продвинутая"}
        return {
            "name": workout_name,
            "type": type_labels.get(program.program_type, program.program_type),
            "duration": f"≈ {duration_minutes} минут" if duration_minutes > 0 else "",
            "difficulty": difficulty_labels.get(program.difficulty, program.difficulty),
            "description": program.description,
        }

    def _builder_workout_name(self, value: dict[str, Any], program: WorkoutProgram) -> str:
        stored = value.get("workoutName") if isinstance(value, dict) else None
        return stored.strip() if isinstance(stored, str) and stored.strip() else program.name

    def _sanitize_builder_workout_name(self, workout_name: str | None, value: dict[str, Any], program: WorkoutProgram) -> str:
        if isinstance(workout_name, str) and workout_name.strip():
            return workout_name.strip()
        return self._builder_workout_name(value, program)

    def _builder_summary_cards(self, groups: list[BuilderWorkoutGroupSchema], duration: DurationEstimate) -> list[BuilderSummaryCardSchema]:
        exercise_count = sum(len(group.items) for group in groups)
        set_count = sum(len(item.strength_plan) or self._parse_sets(item.sets) for group in groups for item in group.items)
        tonnage = sum(self._builder_item_tonnage(item) for group in groups for item in group.items)
        return [
            BuilderSummaryCardSchema(label="упражнений", value=str(exercise_count), hint="структура тренировки"),
            BuilderSummaryCardSchema(label="подходов", value=str(set_count), hint="общий объём"),
            BuilderSummaryCardSchema(label="минут", value=str(duration.minutes), hint=self._builder_duration_hint(duration)),
            BuilderSummaryCardSchema(label="кг", value=f"{int(round(tonnage)):,}".replace(",", " "), hint="общий тоннаж"),
        ]

    def _builder_duration_estimate(self, session: Session, user_id: str, groups: list[BuilderWorkoutGroupSchema]) -> DurationEstimate:
        items = [item for group in groups for item in group.items]
        slugs = {item.slug for item in items}
        tempo_by_slug = {
            slug: profile.tempo
            for slug, state in self._user_states(session, user_id, slugs).items()
            if (profile := read_profile(state)) is not None
        }
        return estimate_workout_duration(items, tempo_by_slug=tempo_by_slug, e1rm_by_slug=self._recent_e1rm_by_slug(session, user_id, slugs))

    def _recent_e1rm_by_slug(self, session: Session, user_id: str, slugs: set[str]) -> dict[str, float]:
        """Best Epley e1RM over recent sets: tells the duration estimate how heavy the planned weights are."""
        if not slugs:
            return {}
        since = datetime.now(UTC) - timedelta(days=E1RM_LOOKBACK_DAYS)
        best: dict[str, float] = {}
        set_rows = session.execute(
            select(ExerciseSession.exercise_slug, SetResult.weight_kg, SetResult.reps)
            .join(SetResult, SetResult.exercise_session_id == ExerciseSession.id)
            .where(ExerciseSession.user_id == user_id, ExerciseSession.exercise_slug.in_(slugs), ExerciseSession.started_at >= since)
        )
        history_rows = session.execute(
            select(ExerciseHistoryRecord.exercise_slug, ExerciseHistoryRecord.weight_kg, ExerciseHistoryRecord.reps, ExerciseHistoryRecord.sets)
            .where(ExerciseHistoryRecord.user_id == user_id, ExerciseHistoryRecord.exercise_slug.in_(slugs), ExerciseHistoryRecord.performed_at >= since)
        )
        rows = [*set_rows, *((slug, weight, round(reps / max(sets, 1))) for slug, weight, reps, sets in history_rows)]
        for slug, weight, reps in rows:
            e1rm = estimate_one_rep_max(weight or 0, int(reps or 0))
            if e1rm is not None and e1rm > best.get(slug, 0):
                best[slug] = e1rm
        return best

    def _builder_duration_hint(self, duration: DurationEstimate) -> str:
        if duration.total_seconds <= 0:
            return "оценка длительности"
        parts = [("подходы", duration.work_seconds), ("отдых", duration.rest_seconds), ("переходы", duration.transition_seconds)]
        return "≈ " + " · ".join(f"{label} {int(round(seconds / 60))}" for label, seconds in parts) + " мин"

    def _builder_item_tonnage(self, item: BuilderExerciseItemSchema) -> float:
        if item.strength_plan:
            return sum(self._parse_weight(set_plan.recommended_weight_label) * self._parse_strength_target_reps(set_plan.target_reps_label) for set_plan in item.strength_plan)

        return self._parse_weight(item.load) * self._parse_sets(item.sets) * self._parse_reps(item.sets)

    def _parse_strength_target_reps(self, value: str) -> int:
        matches = [int(match) for match in re.findall(r"\d+", value)]
        return max(matches) if matches else 1

    def _parse_sets(self, value: str) -> int:
        head = value.split("×", 1)[0].strip()
        return int(head) if head.isdigit() else 1

    def _parse_reps(self, value: str) -> int:
        tail = value.split("×", 1)[1].strip().split()[0] if "×" in value else "1"
        return int(tail) if tail.isdigit() else 1

    def _parse_weight(self, value: str) -> float:
        head = value.replace(",", ".").split()[0] if value.strip() else "0"
        try:
            return float(head)
        except ValueError:
            return 0.0

    def _program_slug(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
        slug = slug.strip("-")
        return slug or "workout"

    def _normalize_builder_editor(self, editor: BuilderExerciseEditorSchema, load_type: str, default_target: int, default_sets: int = 3) -> BuilderExerciseEditorSchema:
        set_params = dict(editor.set_params)
        normalized_set_params = {
            "sets": self._coerce_builder_int(set_params.get("sets"), default_sets, 1),
            "reps": self._coerce_builder_int(set_params.get("reps"), default_target, 1),
            "weight": self._coerce_builder_weight(set_params.get("weight")),
            "restSeconds": self._coerce_builder_int(set_params.get("restSeconds"), 60, 15),
        }
        duration_seconds = self._coerce_builder_optional_int(set_params.get("durationSeconds"), 1)
        if load_type == "timed":
            normalized_set_params["durationSeconds"] = duration_seconds if duration_seconds is not None else default_target

        strength_mode_id = self._normalize_strength_mode_id(editor.strength_mode_id)
        strength_day_type = self._normalize_strength_day_type(strength_mode_id, editor.strength_day_type)

        effective_set_params = self._builder_effective_set_params(load_type, normalized_set_params, editor.load_mode, editor.tempo)

        return editor.model_copy(
            update={
                "set_params": normalized_set_params,
                "effective_set_params": effective_set_params,
                "load_type": load_type,
                "load_mode_description": self._builder_load_mode_rule(editor.load_mode)["description"],
                "tempo_description": self._builder_tempo_rule(editor.tempo)["description"],
                "strength_mode_id": strength_mode_id,
                "strength_day_type": strength_day_type,
                "strength_plan": self._builder_strength_plan(strength_mode_id, strength_day_type, load_type, effective_set_params),
            }
        )

    def _normalize_strength_mode_id(self, mode_id: str | None) -> str:
        known = {str(item["id"]) for item in STRENGTH_TRAINING_MODES}
        return mode_id if mode_id in known else "basic"

    def _normalize_strength_day_type(self, mode_id: str, day_type: str | None) -> str | None:
        if mode_id != "periodized_day":
            return None
        return day_type if day_type in {"light", "medium", "heavy"} else "medium"

    def _builder_strength_plan(self, mode_id: str, day_type: str | None, load_type: str, set_params: dict[str, int]) -> list[BuilderStrengthSetPlanSchema]:
        """Mode template, reshaped to the user's set count when one is given (mirrors the frontend)."""
        sets = set_params.get("sets")
        template = self._builder_strength_template(mode_id, day_type, load_type, set_params, sets is not None)
        if sets is None:
            return template

        total = max(1, int(sets))
        if load_type == "timed":
            seconds = max(1, int(set_params.get("durationSeconds") or set_params.get("reps", 45)))
            return [
                BuilderStrengthSetPlanSchema(
                    set_number=index,
                    set_type="work",
                    label="Подход",
                    target_reps_label=f"{seconds} сек",
                    recommended_weight_label="вес тела",
                    rest_seconds=max(15, int(set_params.get("restSeconds", 60))),
                    rir_label="ровный темп",
                    note="Держите заданное время без потери техники.",
                )
                for index in range(1, total + 1)
            ]
        return self._resize_builder_strength_plan(template, total, mode_id)

    def _resize_builder_strength_plan(self, template: list[BuilderStrengthSetPlanSchema], total: int, mode_id: str) -> list[BuilderStrengthSetPlanSchema]:
        warmups = [item for item in template if item.set_type == "warmup"]
        failures = [item for item in template if item.set_type == "failure"]
        work = [item for item in template if item.set_type == "work"]
        warmup_count = min(len(warmups), max(0, total - 2))
        failure_count = min(len(failures), max(0, total - warmup_count - 1))
        work_count = total - warmup_count - failure_count
        work_source = work or failures[:1]
        if work_count <= len(work_source):
            chosen_work = work_source[len(work_source) - work_count:] if mode_id == "straight_pyramid" else work_source[:work_count]
        else:
            chosen_work = work_source + [work_source[-1]] * (work_count - len(work_source))
        chosen_warmups = warmups[len(warmups) - warmup_count:] if warmup_count else []
        return [
            item.model_copy(update={"set_number": index, "label": f"Круг {index}" if item.label.startswith("Круг ") else item.label})
            for index, item in enumerate([*chosen_warmups, *chosen_work, *failures[:failure_count]], start=1)
        ]

    def _builder_strength_template(self, mode_id: str, day_type: str | None, load_type: str, set_params: dict[str, int], use_target_reps: bool) -> list[BuilderStrengthSetPlanSchema]:
        reps = max(1, int(set_params.get("reps", 10)))
        rest_seconds = max(15, int(set_params.get("restSeconds", 90)))
        weight = max(0.0, float(set_params.get("weight", 0)))

        def weight_label(factor: float) -> str:
            if load_type != "weighted" or weight <= 0:
                return "вес тела"
            return f"{scale_weight(weight, factor):g} кг"

        def target_range(min_reps: int, max_reps: int | None = None) -> str:
            return f"{min_reps}–{max_reps}" if max_reps and max_reps != min_reps else str(min_reps)

        def item(set_number: int, set_type: Literal["warmup", "work", "failure"], label: str, target_reps_label: str, factor: float, rest: int, rir_label: str, note: str) -> BuilderStrengthSetPlanSchema:
            return BuilderStrengthSetPlanSchema(
                set_number=set_number,
            set_type=set_type,
                label=label,
                target_reps_label=target_reps_label,
                recommended_weight_label=weight_label(factor),
                rest_seconds=rest,
                rir_label=rir_label,
                note=note,
            )

        if mode_id == "last_set_failure":
            return [
                item(1, "warmup", "Разминка", "10–12", 0.5, 60, "4–5 в запасе", "Лёгкий вход в движение."),
                item(2, "work", "Рабочий подход", "8–12", 1.0, 120, "2 в запасе", "Не доводить до отказа."),
                item(3, "work", "Рабочий подход", "8–12", 1.0, 120, "1 в запасе", "Остановиться при ухудшении техники."),
                item(4, "failure", "До отказа", "максимум", 1.0, 120, "0", "Только технический отказ без боли."),
            ]
        if mode_id == "straight_pyramid":
            return [
                item(1, "work", "Рабочий подход", "12", 0.7, 90, "3 в запасе", "Лёгкий вес."),
                item(2, "work", "Рабочий подход", "10", 0.8, 90, "2 в запасе", "Средний вес."),
                item(3, "work", "Рабочий подход", "8", 0.9, 120, "1–2 в запасе", "Тяжёлый вес."),
                item(4, "work", "Рабочий подход", "6–8", 1.0, 120, "1–2 в запасе", "Самый тяжёлый подход без потери техники."),
            ]
        if mode_id == "reverse_pyramid":
            return [
                item(1, "warmup", "Подводящий", "8–10", 0.5, 60, "4–5 в запасе", "Разогреть движение."),
                item(2, "warmup", "Подводящий", "5–6", 0.75, 90, "3–4 в запасе", "Подготовиться к тяжёлому весу."),
                item(3, "work", "Рабочий подход", "6–8", 1.0, 180, "1–2 в запасе", "Самый тяжёлый рабочий подход."),
                item(4, "work", "Рабочий подход", "8–10", 0.9, 150, "1–2 в запасе", "Снизить вес примерно на 10%."),
                item(5, "work", "Рабочий подход", "10–12", 0.8, 150, "1–2 в запасе", "Ещё снизить вес примерно на 10%."),
            ]
        if mode_id == "strength":
            return [item(index, "work", "Рабочий подход", "3–6", 1.0, max(rest_seconds, 180), "1–3 в запасе", "Без отказа; увеличивать вес только при уверенном выполнении.") for index in range(1, 5)]
        if mode_id == "hypertrophy":
            return [item(index, "work", "Рабочий подход", "8–12", 1.0, max(60, min(rest_seconds, 120)), "1–2 в запасе", "Держать диапазон повторений, а не одно число.") for index in range(1, 4)]
        if mode_id == "double_progression":
            return [item(index, "work", "Рабочий подход", "8–12", 1.0, max(60, min(rest_seconds, 120)), "1–2 в запасе", "Вес повышается только после 12 / 12 / 12.") for index in range(1, 4)]
        if mode_id == "strength_circuit":
            return [item(index, "work", f"Круг {index}", "10–15", 0.75, 30, "2–3 в запасе", "Короткий отдых перед следующим упражнением.") for index in range(1, 4)]
        if mode_id == "technique_light":
            return [item(index, "work", "Техника", "8–12", 0.7, max(60, min(rest_seconds, 90)), "3–5 в запасе", "Цель — чистая техника, не максимальный вес.") for index in range(1, 3)]
        if mode_id == "periodized_day":
            if day_type == "light":
                return [item(index, "work", "Лёгкий день", "10–12", 0.75, 75, "3–4 в запасе", "Не форсировать увеличение веса.") for index in range(1, 4)]
            if day_type == "heavy":
                return [item(index, "work", "Тяжёлый день", "4–8", 1.0, 180, "1–2 в запасе", "Отдых длиннее, отказ не нужен.") for index in range(1, 5)]
            return [item(index, "work", "Средний день", "8–12", 0.9, 90, "1–3 в запасе", "Средняя нагрузка без перегруза.") for index in range(1, 4)]

        work_rest = max(60, min(rest_seconds, 120))
        work_target = str(reps) if use_target_reps else "8–12"
        if load_type != "weighted" or weight <= 0:
            # Without external weight the warm-up can't be lighter, so it is shorter: half the reps.
            warmup_target = str(-(-reps // 2))
        else:
            warmup_target = target_range(max(8, reps - 2), max(10, reps))
        return [
            item(1, "warmup", "Разминка", warmup_target, 0.5, 60, "4–5 в запасе", "Лёгкий разминочный подход."),
            item(2, "work", "Рабочий подход", work_target, 1.0, work_rest, "1–3 в запасе", "Стабильная техника без отказа."),
            item(3, "work", "Рабочий подход", work_target, 1.0, work_rest, "1–3 в запасе", "Сохранять амплитуду."),
            item(4, "work", "Рабочий подход", work_target, 1.0, work_rest, "1–3 в запасе", "Остановиться до потери техники."),
        ]

    def _apply_builder_editor_to_groups(self, groups: list[BuilderWorkoutGroupSchema], selected_exercise_id: str, editor: BuilderExerciseEditorSchema) -> list[BuilderWorkoutGroupSchema]:
        profile = self._editor_profile(editor)
        return [
            group.model_copy(update={"items": [self._profile_item(item, profile) if item.id == selected_exercise_id else item for item in group.items]})
            for group in groups
        ]

    def _builder_effective_set_params(self, load_type: str, set_params: dict[str, int | float], load_mode: str, tempo: str) -> dict[str, int | float]:
        return effective_set_params(load_type, set_params, load_mode, tempo)

    def _builder_load_mode_rule(self, load_mode: str) -> dict[str, float | int | str]:
        return load_mode_rule(load_mode)

    def _builder_tempo_rule(self, tempo: str) -> dict[str, float | int | str]:
        return tempo_rule(tempo)

    def _coerce_builder_weight(self, value: Any) -> int | float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0
        if parsed != parsed or parsed in {float("inf"), float("-inf")}:
            return 0
        weight = max(0.0, min(2000.0, round(parsed * 2) / 2))
        return int(weight) if weight.is_integer() else weight

    def _coerce_builder_int(self, value: Any, default: int, minimum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, parsed)

    def _coerce_builder_optional_int(self, value: Any, minimum: int) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return max(minimum, parsed) if parsed >= minimum else None

    def _program_builder_groups(self, program: WorkoutProgram) -> list[BuilderWorkoutGroupSchema]:
        raw_groups = program.structure.get("builderGroups")
        if isinstance(raw_groups, list):
            try:
                groups = [BuilderWorkoutGroupSchema.model_validate(item) for item in raw_groups if isinstance(item, dict)]
            except ValidationError:
                groups = []
            if groups:
                return groups

        if program.id == "back-biceps":
            return self._default_builder_groups()

        slugs = [str(item) for item in program.structure.get("exerciseSlugs", FEATURED["today"]) if isinstance(item, str) and get_imported_exercise(item) is not None]
        items = []
        for index, slug in enumerate(slugs or FEATURED["today"], start=1):
            exercise = get_imported_exercise(slug)
            if exercise is None:
                continue
            settings = self._load_settings_fallback(slug, exercise)
            load_type = self._builder_load_type(exercise)
            items.append(
                BuilderExerciseItemSchema(
                    id=f"{program.id}-{index}",
                    slug=slug,
                    name=exercise.name_ru,
                    muscle_group=", ".join(self._translate_muscle(item) for item in exercise.muscles[:2]),
                    sets=self._format_builder_sets(load_type, settings.sets, self._default_builder_target_value(exercise), self._default_builder_target_value(exercise) if load_type == "timed" else None),
                    rest=f"{settings.rest_seconds} сек",
                    load=self._format_builder_load(load_type, settings.weight),
                    load_type=load_type,
                )
            )

        return [BuilderWorkoutGroupSchema(id=f"{program.id}-main", kind="single", title=program.name, items=items)]

    def _default_builder_groups(self) -> list[BuilderWorkoutGroupSchema]:
        return [
            BuilderWorkoutGroupSchema(
                id="group-a",
                kind="alternating",
                title="Тяга сверху + Присед",
                rounds="3 круга • 8–12 мин",
                between_exercises_rest="30 сек",
                between_rounds_rest="90 сек",
                items=[
                    BuilderExerciseItemSchema(id="group-pullups-1", slug="machine-pulldown", name="Тяга сверху", muscle_group="Спина", sets="3×10", rest="30 сек", load="45 кг", load_type="weighted"),
                    BuilderExerciseItemSchema(id="group-squat-1", slug="barbell-heels-up-back-squat", name="Присед", muscle_group="Ноги", sets="3×8", rest="30 сек", load="60 кг", load_type="weighted"),
                ],
            ),
            BuilderWorkoutGroupSchema(
                id="group-b",
                kind="single",
                title="Основной блок",
                items=[
                    BuilderExerciseItemSchema(id="row-1", slug="machine-seated-cable-row", name="Тяга горизонтального блока", muscle_group="Спина", sets="3×10", rest="90 сек", load="45 кг", load_type="weighted"),
                    BuilderExerciseItemSchema(id="row-2", slug="underhand-pulldown", name="Тяга обратным хватом", muscle_group="Спина", sets="4×12", rest="90 сек", load="40 кг", load_type="weighted"),
                    BuilderExerciseItemSchema(id="curl-1", slug="barbell-curl", name="Сгибание рук", muscle_group="Бицепс", sets="3×12", rest="75 сек", load="20 кг", load_type="weighted"),
                    BuilderExerciseItemSchema(id="plank-1", slug="forearm-plank", name="Планка", muscle_group="Кор", sets="3×45 сек", rest="45 сек", load="вес тела", load_type="timed"),
                ],
            ),
        ]

    def _builder_load_type(self, exercise: ImportedExercise | None) -> str:
        return builder_load_type(exercise)

    def _default_builder_weight(self, exercise: ImportedExercise | None) -> float:
        if self._builder_load_type(exercise) != "weighted":
            return 0.0
        if exercise and exercise.equipment == "Machine":
            return 45.0
        if exercise and exercise.equipment == "Barbell":
            return 40.0
        return 20.0

    def _default_builder_target_value(self, exercise: ImportedExercise | None) -> int:
        return 45 if self._builder_load_type(exercise) == "timed" else 10

    def _format_builder_load(self, load_type: str, weight: float) -> str:
        if load_type == "weighted":
            if weight <= 0:
                return "—"
            return f"{weight:g} кг"
        return "вес тела"

    def _format_builder_sets(self, load_type: str, sets: int, target_value: int, duration_seconds: int | None = None) -> str:
        if load_type == "timed" and duration_seconds is not None:
            return f"{max(1, sets)}×{max(1, duration_seconds)} сек"

        return f"{max(1, sets)}×{max(1, target_value)}"

    def _parse_builder_set_count(self, value: str) -> int:
        match = re.search(r"(\d+)", value)
        if match:
            return max(1, int(match.group(1)))
        return 3

    def _builder_item_set_count(self, item: BuilderExerciseItemSchema, load_type: str) -> int:
        # The saved plan is the source of truth for strength sets; timed items keep the "N×" prefix.
        if item.strength_plan and load_type != "timed":
            return len(item.strength_plan)
        return self._parse_builder_set_count(item.sets)

    def _parse_builder_target_value(self, sets_value: str, load_value: str, default: int) -> int:
        sets_match = re.search(r"[×x]\s*(\d+)", sets_value, re.IGNORECASE)
        if sets_match:
            return max(1, int(sets_match.group(1)))

        load_match = re.search(r"[×x]\s*(\d+)", load_value, re.IGNORECASE)
        if load_match:
            return max(1, int(load_match.group(1)))

        return default

    def _parse_builder_duration(self, value: str) -> int | None:
        matches = re.findall(r"(\d+)\s*сек", value, re.IGNORECASE)
        return max(1, int(matches[-1])) if matches else None

    def _parse_builder_rest(self, value: str) -> int:
        match = re.search(r"(\d+)", value)
        return max(15, int(match.group(1))) if match else 90

    def _get_setting(self, session: Session, user_id: str, key: str) -> AppSetting | None:
        statement = select(AppSetting).where(AppSetting.user_id == user_id, AppSetting.key == key)
        return session.scalars(statement).first()

    def _save_setting(self, session: Session, user_id: str, key: str, value: dict[str, object]) -> None:
        setting = self._get_setting(session, user_id, key)
        if setting is None:
            setting = AppSetting(user_id=user_id, key=key, value=value)
            session.add(setting)
        else:
            setting.value = value
        session.commit()

    def _summary(
        self,
        session: Session,
        exercise: ImportedExercise,
        user_id: str,
        favorites: list[str] | None,
        blacklist: list[str] | None,
    ) -> ExerciseSummarySchema:
        favorite_set = set(favorites or [])
        blacklist_set = set(blacklist or [])
        muscle_cards = self._exercise_muscle_cards(session, user_id, exercise)
        readiness_status = self._worst_status(muscle_cards)
        compatibility_tone = self._compatibility_tone(exercise, muscle_cards, blacklist_set)
        preview_video_url = self._preview_video_url(exercise, user_id)
        return ExerciseSummarySchema(
            slug=exercise.slug,
            name=exercise.name_ru,
            secondary_name=exercise.name,
            equipment=self._translate_equipment(exercise.equipment),
            difficulty=exercise.difficulty,
            force=exercise.force,
            grips=self._translate_grip(exercise.grips),
            mechanic=exercise.mechanic,
            muscles=[self._translate_muscle(item) for item in exercise.muscles],
            favorite=exercise.slug in favorite_set,
            blacklisted=exercise.slug in blacklist_set,
            recommended=compatibility_tone == "recommended",
            compatibility_tone=compatibility_tone,
            readiness_status=readiness_status,
            difficulty_label=DIFFICULTY_LABELS.get(exercise.difficulty, exercise.difficulty),
            image_url=None,
            preview_video_url=preview_video_url,
            badges=self._badges(exercise.slug, favorite_set, blacklist_set, compatibility_tone),
        )

    def _preview_video_url(self, exercise: ImportedExercise, user_id: str) -> str | None:
        if not exercise.videos:
            return None

        preferred_gender = "female" if user_id == "elena" else "male"
        for video in exercise.videos:
            if video.gender == preferred_gender and video.view == "side":
                return video.relative_url
        for video in exercise.videos:
            if video.gender == preferred_gender:
                return video.relative_url
        return exercise.videos[0].relative_url

    def _quick_start_item(self, session: Session, slug: str, reason: str, user_id: str, favorites: list[str] | None, blacklist: list[str] | None) -> QuickStartExerciseListItemSchema:
        exercise = get_imported_exercise(slug) or load_imported_exercises()[0]
        summary = self._summary(session, exercise, user_id, favorites, blacklist)
        settings = self._load_settings(session, user_id, slug, exercise)
        state = self._user_state(session, user_id, slug)
        return QuickStartExerciseListItemSchema(
            **summary.model_dump(),
            reason=reason,
            last_result=f"{settings.weight:g} кг × {settings.reps} × {settings.sets}",
            last_performed=self._last_performed_label(state.last_performed_at if state else None),
        )

    def _selected_quick_start_exercise(self, session: Session, slug: str, user_id: str, favorites: list[str] | None, blacklist: list[str] | None) -> QuickStartSelectedExerciseSchema:
        details = self.get_exercise_details(session, user_id=user_id, slug=slug, favorites=favorites, blacklist=blacklist)
        warnings: list[QuickStartSelectedExerciseWarningSchema] = []
        if details.compatibility.tone == "blocked":
            warnings.append(QuickStartSelectedExerciseWarningSchema(tone="blocked", title="Упражнение заблокировано", description=details.compatibility.description))
        elif details.compatibility.tone == "caution":
            warnings.append(QuickStartSelectedExerciseWarningSchema(tone="warning", title="Нужна осторожность", description=details.compatibility.description))
        return QuickStartSelectedExerciseSchema(
            exercise=ExerciseSummarySchema.model_validate(details.model_dump()),
            readiness=[
                QuickStartSelectedExerciseReadinessSchema(
                    label=item.name,
                    tone="caution" if item.status in {"high", "critical", "medium"} else ("recommended" if item.status == "ready" else "okay"),
                    description="Готова" if item.status == "ready" else ("Лёгкая усталость" if item.status == "light" else ("Нужен контроль" if item.status == "medium" else "Снизьте нагрузку")),
                )
                for item in details.compatibility.affected_muscles[:3]
            ],
            last_result=f"{details.load_settings.weight:g} кг × {details.load_settings.reps} × {details.load_settings.sets}",
            forma_recommendation=details.load_settings.recommendation,
            settings=details.load_settings,
            warnings=warnings,
        )

    def _workout_panel(self, session: Session, slug: str, user_id: str, favorites: list[str] | None, blacklist: list[str] | None) -> WorkoutExercisePanelSchema:
        details = self.get_exercise_details(session, user_id=user_id, slug=slug, favorites=favorites, blacklist=blacklist)
        return WorkoutExercisePanelSchema(
            id=slug,
            slug=slug,
            name=details.name,
            muscles=", ".join(details.muscles[:2]),
            last_result=f"{details.load_settings.weight:g} кг × {details.load_settings.reps} × {details.load_settings.sets}",
            forma_recommendation=details.load_settings.recommendation,
            readiness=[
                WorkoutExercisePanelReadinessSchema(
                    label=item.name,
                    value="Готова" if item.status == "ready" else ("Лёгкая усталость" if item.status == "light" else ("Средняя усталость" if item.status == "medium" else "Нужен контроль")),
                    tone="recommended" if item.status == "ready" else ("caution" if item.status in {"medium", "high", "critical"} else "okay"),
                )
                for item in details.compatibility.affected_muscles[:3]
            ],
            settings=details.load_settings,
            alerts=[details.compatibility.description] if details.compatibility.tone == "caution" else [],
        )

    def _compatibility(self, session: Session, exercise: ImportedExercise, user_id: str, blacklist: list[str] | None) -> ExerciseCompatibilitySchema:
        muscle_cards = self._exercise_muscle_cards(session, user_id, exercise)
        tone = self._compatibility_tone(exercise, muscle_cards, set(blacklist or []))
        if tone == "blocked":
            title = "Упражнение находится в чёрном списке"
            description = "Система помечает упражнение как нежелательное для текущего пользователя."
        elif tone == "caution":
            title = "Совместимость сегодня: осторожно"
            description = "Некоторые целевые мышцы уже утомлены. Рекомендуется снизить рабочий вес или выбрать альтернативу."
        elif tone == "recommended":
            title = "Совместимость: хорошо подходит сегодня"
            description = "Упражнение совпадает с целью дня и доступным оборудованием, а профиль усталости не мешает старту."
        else:
            title = "Совместимость: можно выполнять"
            description = "Явных ограничений не найдено. Упражнение можно добавить в тренировку и скорректировать нагрузку при необходимости."
        return ExerciseCompatibilitySchema(tone=tone, title=title, description=description, affected_muscles=muscle_cards)

    def _load_settings(self, session: Session, user_id: str, slug: str, exercise: ImportedExercise | None) -> ExerciseLoadSettingsSchema:
        self.ensure_exercise_profiles(session, user_id)
        state = self._user_state(session, user_id, slug)
        base_weight = 45.0 if exercise and exercise.equipment == "Machine" else (40.0 if exercise and exercise.equipment == "Barbell" else 20.0)
        weight = state.working_weight if state and state.working_weight is not None else base_weight
        sets = state.working_sets if state and state.working_sets is not None else 3
        reps = state.working_reps if state and state.working_reps is not None else 10
        rest_seconds = state.rest_seconds if state and state.rest_seconds is not None else 60
        calibration = state.calibration_status if state and state.calibration_status else ("required" if exercise and exercise.equipment == "Machine" else "recommended")
        profile = read_profile(state)
        if profile is not None:
            # Raw profile controls, like the builder editor; the mode/tempo modifiers apply on top.
            weight = profile.weight if profile.load_type == "weighted" else 0.0
            return ExerciseLoadSettingsSchema(
                weight=weight,
                sets=profile.sets,
                reps=(profile.duration_seconds or profile.reps) if profile.load_type == "timed" else profile.reps,
                rest_seconds=profile.rest_seconds,
                mode=profile.load_mode,
                tempo=profile.tempo,
                recommendation="Можно сохранить рабочий вес и контролировать амплитуду движения.",
                safe_range=(max(0.0, weight - 10.0), weight + 5.0),
                calibration=calibration,
                configured=True,
                training_mode=profile.strength_mode_id,
                training_day_type=profile.strength_day_type,
                per_side=profile.per_side,
                note=profile.note or None,
            )
        remembered = remembered_settings(session, state)
        if remembered is not None:
            weight, sets, reps, rest_seconds = remembered.weight, remembered.sets, remembered.reps, remembered.rest_seconds
        return ExerciseLoadSettingsSchema(
            weight=weight,
            sets=sets,
            reps=reps,
            rest_seconds=rest_seconds,
            mode=remembered.mode if remembered else ("Обычный вес" if weight > 0 else "Контроль техники"),
            tempo=remembered.tempo if remembered else "Обычный",
            recommendation="Можно сохранить рабочий вес и контролировать амплитуду движения.",
            safe_range=(max(0.0, weight - 10.0), weight + 5.0),
            calibration=calibration,
            training_mode=remembered.training_mode if remembered else None,
            training_day_type=remembered.training_day_type if remembered else None,
        )

    def _history_rows(self, session: Session, user_id: str, slug: str) -> list[ExerciseHistoryEntrySchema]:
        statement = (
            select(ExerciseHistoryRecord)
            .where(ExerciseHistoryRecord.user_id == user_id, ExerciseHistoryRecord.exercise_slug == slug)
            .order_by(ExerciseHistoryRecord.performed_at.desc())
            .limit(6)
        )
        rows = list(session.scalars(statement))
        return [
            ExerciseHistoryEntrySchema(
                date=self._format_date(row.performed_at),
                weight=f"{row.weight_kg:g} кг",
                reps=f"{row.reps}",
                sets=row.sets,
                volume=f"{int(round(row.volume_kg))} кг",
                rpe=row.rpe,
                note=row.note,
            )
            for row in rows
        ]

    def _load_progress(self, history: list[ExerciseHistoryEntrySchema]) -> list[ExerciseLoadPointSchema]:
        if not history:
            return []
        points = []
        for item in reversed(history[-5:]):
            weight = float(item.weight.split()[0].replace(",", "."))
            points.append(ExerciseLoadPointSchema(label=item.date[:5], value=weight, caption=item.volume))
        return points

    def _similar_exercises(self, exercise: ImportedExercise, session: Session, user_id: str, favorites: list[str] | None, blacklist: list[str] | None) -> list[dict[str, Any]]:
        all_exercises = [item for item in load_imported_exercises() if item.slug != exercise.slug]
        all_exercises.sort(key=lambda item: len(set(item.muscles) & set(exercise.muscles)), reverse=True)
        result = []
        for candidate in all_exercises[:4]:
            result.append(
                {
                    "slug": candidate.slug,
                    "name": candidate.name_ru,
                    "secondaryName": candidate.name,
                    "muscles": [self._translate_muscle(item) for item in candidate.muscles],
                    "equipment": self._translate_equipment(candidate.equipment),
                }
            )
        return result

    def _exercise_muscle_cards(self, session: Session, user_id: str, exercise: ImportedExercise) -> list[MuscleCardSchema]:
        snapshots = {item.muscle_id: item for item in self.fatigue_service.list_current_scores(session, user_id)}
        cards = []
        for muscle in exercise.muscles[:4]:
            snapshot = snapshots.get(muscle)
            if snapshot is None:
                cards.append(MuscleCardSchema(name=self._translate_muscle(muscle), status="light", score=22))
                continue
            cards.append(
                MuscleCardSchema(
                    name=self._translate_muscle(muscle),
                    status=self.fatigue_service.fatigue_status(snapshot.fatigue_score),
                    score=int(round(snapshot.fatigue_score)),
                )
            )
        return cards

    def _muscle_cards(self, session: Session, user_id: str) -> list[MuscleCardSchema]:
        snapshots = self.fatigue_service.list_current_scores(session, user_id)
        return [
            MuscleCardSchema(name=self._translate_muscle(item.muscle_id), status=self.fatigue_service.fatigue_status(item.fatigue_score), score=int(round(item.fatigue_score)))
            for item in snapshots
        ]

    def _compatibility_tone(self, exercise: ImportedExercise, cards: list[MuscleCardSchema], blacklist: set[str]) -> str:
        if exercise.slug in blacklist:
            return "blocked"
        worst = self._worst_status(cards)
        if exercise.slug in FEATURED["quick_start"]:
            return "recommended"
        if worst in {"high", "critical"}:
            return "caution"
        return "okay"

    def _worst_status(self, cards: list[MuscleCardSchema]) -> str:
        return max((card.status for card in cards), key=lambda item: STATUS_PRIORITY.get(item, 0), default="ready")

    def _badges(self, slug: str, favorites: set[str], blacklist: set[str], tone: str) -> list[str]:
        badges = []
        if slug in favorites:
            badges.append("Избранное")
        if slug in blacklist:
            badges.append("В чёрном списке")
        if tone == "recommended":
            badges.append("Рекомендуется")
        return badges

    def _translate_muscle(self, value: str) -> str:
        translated = MUSCLE_TRANSLATIONS.get(value)
        if translated is not None:
            return translated
        if value in CANONICAL_MUSCLE_DEFINITIONS:
            return CANONICAL_MUSCLE_DEFINITIONS[value].name
        return value.replace("_", " ").replace("-", " ").title()

    def _translate_equipment(self, value: str) -> str:
        return EQUIPMENT_TRANSLATIONS.get(value, value)

    def _translate_grip(self, value: str) -> str:
        return ", ".join(GRIP_TRANSLATIONS.get(part.strip(), part.strip()) for part in value.split(",") if part.strip()) or value

    def _description(self, exercise: ImportedExercise) -> str:
        muscles = " и ".join(self._translate_muscle(item).lower() for item in exercise.muscles[:2])
        return f"{exercise.name_ru} — упражнение для группы {muscles or 'основных мышц'}, которое выполняется с оборудованием «{self._translate_equipment(exercise.equipment)}»."

    def _user_state(self, session: Session, user_id: str, slug: str) -> UserExerciseState | None:
        statement = select(UserExerciseState).where(UserExerciseState.user_id == user_id, UserExerciseState.exercise_slug == slug)
        return session.scalars(statement).first()

    def _last_performed_label(self, performed_at: datetime | None) -> str:
        if performed_at is None:
            return "нет истории"
        normalized = performed_at if performed_at.tzinfo is not None else performed_at.replace(tzinfo=UTC)
        delta_days = max(0, (datetime.now(UTC) - normalized.astimezone(UTC)).days)
        return f"{delta_days} дней назад"

    def _programs(self, session: Session, user_id: str | None = None) -> list[WorkoutProgram]:
        programs = list(session.scalars(select(WorkoutProgram).where(WorkoutProgram.deleted.is_(False)).order_by(WorkoutProgram.recommended_today.desc(), WorkoutProgram.name.asc())))
        merged: dict[str, WorkoutProgram] = {program.id: program for program in self._default_programs()}
        for program in programs:
            merged[program.id] = program

        visible_programs = list(merged.values())
        if user_id:
            hidden_program_ids = set(
                session.scalars(
                    select(UserHiddenWorkoutProgram.program_id).where(UserHiddenWorkoutProgram.user_id == user_id)
                )
            )
            visible_programs = [program for program in visible_programs if program.id not in hidden_program_ids]

        visible_programs.sort(key=lambda program: (not program.recommended_today, program.name.lower(), program.id))
        if user_id:
            # A user-arranged order wins; programs it does not know yet keep the default order after it.
            positions = {program_id: index for index, program_id in enumerate(self._program_order(session, user_id))}
            visible_programs.sort(key=lambda program: positions.get(program.id, len(positions)))
        return visible_programs

    def _program_order(self, session: Session, user_id: str) -> list[str]:
        setting = self._get_setting(session, user_id, PROGRAM_ORDER_SETTING_KEY)
        program_ids = setting.value.get("programIds") if setting and isinstance(setting.value, dict) else None
        return [item for item in program_ids if isinstance(item, str)] if isinstance(program_ids, list) else []

    def save_program_order(self, session: Session, payload: ProgramOrderMutationSchema) -> ProgramOrderResultSchema:
        visible_ids = [program.id for program in self._programs(session, payload.user_id)]
        known_ids = set(visible_ids)
        ordered_ids = list(dict.fromkeys(item for item in payload.program_ids if item in known_ids))
        ordered_ids += [item for item in visible_ids if item not in ordered_ids]
        self._save_setting(session, payload.user_id, PROGRAM_ORDER_SETTING_KEY, {"programIds": ordered_ids})
        return ProgramOrderResultSchema(program_ids=ordered_ids)

    def _default_programs(self) -> list[WorkoutProgram]:
        return [
            WorkoutProgram(id="back-biceps", owner_user_id=None, source="template", name="Спина + бицепс", subtitle="Силовая тренировка", program_type="strength", difficulty="medium", duration_minutes=45, exercise_count=5, set_count=18, focus_tags=["Спина", "Бицепс", "Предплечья"], recommended_today=True, description="Тяговая силовая тренировка.", structure={"exerciseSlugs": FEATURED["today"]}),
            WorkoutProgram(id="fullbody-base", owner_user_id=None, source="template", name="Фуллбоди база", subtitle="Баланс силы и техники", program_type="fullbody", difficulty="easy", duration_minutes=42, exercise_count=5, set_count=15, focus_tags=["Ноги", "Спина", "Кор"], recommended_today=False, description="Базовая тренировка всего тела с умеренной нагрузкой.", structure={"exerciseSlugs": ["barbell-heels-up-back-squat", "machine-seated-cable-row", "barbell-floor-press", "barbell-curl", "forearm-plank"]}),
            WorkoutProgram(id="mobility-recovery", owner_user_id=None, source="template", name="Восстановление", subtitle="Мобилизация и лёгкая техника", program_type="mobility", difficulty="novice", duration_minutes=30, exercise_count=4, set_count=10, focus_tags=["Кор", "Плечи", "Мобилити"], recommended_today=False, description="Лёгкая программа для восстановления и контроля амплитуды.", structure={"exerciseSlugs": ["forearm-plank", "ankle-circle", "backward-arm-circle", "abdominals-stretch-variation-one"]}),
        ]

    def _program_summary(self, program: WorkoutProgram) -> ProgramSummarySchema:
        return ProgramSummarySchema(
            id=program.id,
            name=program.name,
            subtitle=program.subtitle,
            exercise_count=program.exercise_count,
            set_count=program.set_count,
            duration_minutes=program.duration_minutes,
            difficulty=program.difficulty,
            focus_tags=list(program.focus_tags),
            recommended_today=program.recommended_today,
            image_url=program.image_url,
        )

    def _program_details(self, program: WorkoutProgram) -> ProgramDetailsSchema:
        slugs = [str(item) for item in program.structure.get("exerciseSlugs", FEATURED["today"]) if isinstance(item, str)]
        exercise_lines = []
        for index, slug in enumerate(slugs, start=1):
            exercise = get_imported_exercise(slug)
            settings = self._load_settings_fallback(slug, exercise)
            exercise_lines.append({"order": index, "name": exercise.name_ru if exercise else slug, "load": f"{settings.weight:g} кг × {settings.sets}×{settings.reps}", "rest": f"{settings.rest_seconds} сек"})
        tone = "great" if program.recommended_today else ("caution" if program.difficulty == "advanced" else "okay")
        return ProgramDetailsSchema(
            **self._program_summary(program).model_dump(),
            compatibility=ProgramCompatibilitySchema(
                tone=tone,
                title="Совместимость: хорошо подходит сегодня" if tone == "great" else ("Совместимость: осторожно" if tone == "caution" else "Совместимость: можно адаптировать"),
                description="Программа хорошо совпадает с текущей готовностью пользователя." if tone == "great" else ("Потребуется скорректировать объём и рабочий вес." if tone == "caution" else "Программу можно использовать после небольшой адаптации."),
            ),
            equipment_coverage="Доступно 100%",
            blacklist_issues=0,
            exercise_lines=exercise_lines,
            actions=ProgramDetailsActionsSchema(primary="Начать сегодня", secondary="Адаптировать под меня", save="Сохранить в мои программы", calendar="Назначить в календарь", builder="Открыть в конструкторе"),
        )

    def _load_settings_fallback(self, slug: str, exercise: ImportedExercise | None) -> ExerciseLoadSettingsSchema:
        base_weight = 45.0 if exercise and exercise.equipment == "Machine" else (40.0 if exercise and exercise.equipment == "Barbell" else 20.0)
        return ExerciseLoadSettingsSchema(weight=base_weight, sets=3, reps=10, rest_seconds=60, mode="Обычный вес", tempo="Обычный", recommendation="Можно сохранить рабочий вес и контролировать амплитуду движения.", safe_range=(max(0.0, base_weight - 10.0), base_weight + 5.0), calibration="required" if exercise and exercise.equipment == "Machine" else "recommended")

    def _format_date(self, value: datetime) -> str:
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).strftime("%d.%m.%Y")
