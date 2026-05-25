from __future__ import annotations

from datetime import UTC, date, datetime
import re
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.training import ExerciseHistoryRecord, UserExerciseState, UserHiddenWorkoutProgram, WorkoutProgram, WorkoutScheduleEntry
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
from app.schemas.training import (
    BuilderExerciseEditorSchema,
    BuilderExerciseItemSchema,
    BuilderPlanMutationSchema,
    BuilderProgramTabSchema,
    BuilderStrengthSetPlanSchema,
    BuilderSummaryCardSchema,
    BuilderWorkoutGroupSchema,
    ProgramCompatibilitySchema,
    ProgramDetailsActionsSchema,
    ProgramDetailsSchema,
    ProgramLibraryDataSchema,
    ProgramMutationResultSchema,
    ProgramMutationSchema,
    ProgramSummarySchema,
    QuickStartDataSchema,
    QuickStartExerciseListItemSchema,
    QuickStartRecommendationSchema,
    QuickStartSelectedExerciseReadinessSchema,
    QuickStartSelectedExerciseSchema,
    QuickStartSelectedExerciseWarningSchema,
    StrengthTrainingModeSchema,
    TodayWorkoutPlanMutationSchema,
    TodayWorkoutDataSchema,
    TrainingPlanMutationResultSchema,
    TodayWorkoutWarningSchema,
    WorkoutBuilderDataSchema,
    WorkoutCalendarDataSchema,
    WorkoutExercisePanelReadinessSchema,
    WorkoutExercisePanelSchema,
    WorkoutExerciseRowSchema,
    WorkoutProgressSchema,
    CalendarDayCardSchema,
    CalendarDayDetailsSchema,
)
from app.schemas.analytics import MuscleCardSchema
from app.services.exercise_library import ImportedExercise, get_imported_exercise, load_imported_exercises
from app.services.fatigue_service import FatigueService
from app.services.machine_service import MachineService


FEATURED = {
    "quick_start": ["machine-pulldown", "machine-seated-cable-row", "barbell-curl"],
    "recent": ["barbell-bench-press", "barbell-floor-press", "machine-pulldown"],
    "today": ["machine-pulldown", "machine-seated-cable-row", "barbell-curl", "underhand-pulldown", "forearm-plank"],
}

BUILDER_LOAD_MODE_RULES = {
    "Обычный вес": {"weight_factor": 1.0, "reps_factor": 1.0, "duration_factor": 1.0, "rest_delta": 0, "description": "Без корректировок: в план попадают заданные вес, повторы, длительность и отдых."},
    "Контроль техники": {"weight_factor": 0.9, "reps_factor": 0.9, "duration_factor": 0.9, "rest_delta": 15, "description": "Для техники план снижает вес и целевые повторы/секунды на 10%, а отдых увеличивает на 15 сек."},
    "Лёгкий режим": {"weight_factor": 0.8, "reps_factor": 0.8, "duration_factor": 0.8, "rest_delta": 15, "description": "Для разгрузки план снижает вес и целевые повторы/секунды на 20%, а отдых увеличивает на 15 сек."},
}

BUILDER_TEMPO_RULES = {
    "Обычный": {"weight_factor": 1.0, "reps_factor": 1.0, "duration_factor": 1.0, "rest_delta": 0, "description": "Без корректировок темпа: параметры остаются такими, как заданы выше."},
    "Плавный": {"weight_factor": 1.0, "reps_factor": 1.0, "duration_factor": 1.1, "rest_delta": 15, "description": "Плавный темп добавляет 15 сек отдыха; если задана длительность, цель по времени увеличивается на 10%."},
    "Контроль эксцентрики": {"weight_factor": 0.9, "reps_factor": 0.9, "duration_factor": 1.15, "rest_delta": 30, "description": "Контроль эксцентрики снижает вес и повторы на 10%, увеличивает заданную длительность на 15% и добавляет 30 сек отдыха."},
}

TODAY_PLAN_SETTING_KEY = "training.today.plan"
BUILDER_PLAN_SETTING_KEY = "training.builder.plan"

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
    "traps": "Трапеции",
    "abs": "Пресс",
    "obliques": "Косые мышцы",
    "glutes": "Ягодицы",
    "quads": "Квадрицепс",
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
    "Machine": "Тренажёр",
    "Cable": "Кроссовер",
    "Bodyweight": "Собственный вес",
    "Smith Machine": "Машина Смита",
    "Band": "Резина",
    "Kettlebell": "Гиря",
}

GRIP_TRANSLATIONS = {
    "Overhand": "Прямой",
    "Underhand": "Обратный",
    "Neutral": "Нейтральный",
    "Mixed": "Смешанный",
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

    def get_calendar(self, session: Session, *, mode: str, selected_day_id: str | None) -> WorkoutCalendarDataSchema:
        entries = self._schedule_entries(session)
        selected_entry = next((item for item in entries if str(item.scheduled_date) == selected_day_id), entries[0])
        if mode == "week":
            days = entries[:7]
            title = f"Неделя {days[0].scheduled_date.strftime('%d.%m')}–{days[-1].scheduled_date.strftime('%d.%m')}"
        else:
            days = entries
            title = selected_entry.scheduled_date.strftime("%B %Y").capitalize()
        card_days = [self._calendar_day(entry, str(entry.scheduled_date) == (selected_day_id or str(selected_entry.scheduled_date)), mode) for entry in days]
        return WorkoutCalendarDataSchema(
            mode="week" if mode == "week" else "month",
            title=title,
            legend=["Выполнено", "Запланировано", "Пропущено", "Отдых"],
            days=card_days,
            selected_day_id=str(selected_entry.scheduled_date),
            selected_day=CalendarDayDetailsSchema(
                date_label=selected_entry.scheduled_date.strftime("%d %B"),
                title=selected_entry.title,
                subtitle="Сегодня" if selected_entry.status == "today" else "План",
                exercise_count=selected_entry.exercise_count or 0,
                set_count=selected_entry.set_count or 0,
                duration=f"{selected_entry.duration_minutes or 0} минут",
                target_muscles=selected_entry.target_muscles or "спина, бицепс",
                status_text=selected_entry.status,
                readiness_percent=selected_entry.readiness_percent or 0,
                recommendation=selected_entry.recommendation or "Сохраните план и контролируйте мышечный баланс по неделе.",
            ),
            quick_actions=["Сгенерировать месяц", "Добавить тренировку", "Скопировать прошлую неделю"],
            summary=[
                {"label": "запланировано", "value": str(sum(1 for item in entries if item.status in {"planned", "today"}))},
                {"label": "выполнено", "value": str(sum(1 for item in entries if item.status == "completed"))},
                {"label": "минут", "value": str(sum(item.duration_minutes or 0 for item in entries))},
                {"label": "выполнение", "value": f"{int(round(sum(1 for item in entries if item.status == 'completed') / max(len(entries), 1) * 100))}%"},
            ],
            muscle_balance=[
                {"label": "Спина", "value": "Высокая", "tone": "high"},
                {"label": "Грудь", "value": "Средняя", "tone": "medium"},
                {"label": "Ноги", "value": "Высокая", "tone": "high"},
                {"label": "Кор", "value": "Средняя", "tone": "medium"},
            ],
        )

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
        estimated_duration_minutes = self._builder_estimated_duration_minutes(groups, selected_program.duration_minutes)
        persisted_selected_id = self._builder_selected_exercise_id(session, user_id, selected_program.id)
        available_items = [item for group in groups for item in group.items]
        selected_item = next((item for item in available_items if item.id == (selected_exercise_id or persisted_selected_id)), None)
        if selected_item is None and available_items:
            selected_item = available_items[0]

        if selected_item is not None:
            exercise = get_imported_exercise(selected_item.slug)
            settings = self._load_settings(session, user_id, selected_item.slug, exercise)
            selected_item_id = selected_item.id
            selected_editor = self._builder_editor(session, user_id, selected_program.id, selected_item, settings)
        else:
            selected_item_id = ""
            selected_editor = self._empty_builder_editor(self._builder_workout_name(builder_value, selected_program))

        return WorkoutBuilderDataSchema(
            title="Конструктор тренировок",
            subtitle="Соберите тренировку из упражнений, настройте нагрузку — изменения сохраняются автоматически.",
            programs=[self._builder_program_tab(self._builder_workout_name(self._builder_setting_value(session, user_id, program.id), program), program) for program in programs],
            strength_modes=self.get_strength_modes(),
            selected_program_id=selected_program.id,
            info=self._builder_info(selected_program, self._builder_workout_name(builder_value, selected_program), estimated_duration_minutes),
            groups=groups,
            selected_exercise_id=selected_item_id,
            selected_exercise=selected_editor,
            add_suggestions=[],
            summary_cards=self._builder_summary_cards(groups, estimated_duration_minutes),
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

        groups = self._sanitize_builder_groups(payload.groups, payload.user_id)
        current_value = self._builder_setting_value(session, payload.user_id, program_id)
        editors = current_value.get("editors") if isinstance(current_value.get("editors"), dict) else {}
        workout_name = self._sanitize_builder_workout_name(payload.workout_name, current_value, selected_program)
        if payload.selected_exercise_id and payload.selected_exercise:
            selected_item = next((item for group in groups for item in group.items if item.id == payload.selected_exercise_id), None)
            if selected_item is not None:
                exercise = get_imported_exercise(selected_item.slug)
                load_type = self._builder_load_type(exercise)
                default_target = self._parse_builder_target_value(selected_item.sets, selected_item.load, self._default_builder_target_value(exercise))
                editor = self._normalize_builder_editor(payload.selected_exercise, load_type, default_target)
                groups = self._apply_builder_editor_to_groups(groups, payload.selected_exercise_id, editor)
                editors[str(payload.selected_exercise_id)] = editor.model_dump(mode="json", by_alias=True)
            else:
                editors[str(payload.selected_exercise_id)] = payload.selected_exercise.model_dump(mode="json", by_alias=True)
        self._save_setting(
            session,
            payload.user_id,
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

    def _sanitize_builder_groups(self, groups: list[BuilderWorkoutGroupSchema], user_id: str = "alexey") -> list[BuilderWorkoutGroupSchema]:
        sanitized: list[BuilderWorkoutGroupSchema] = []
        for group in groups:
            items = []
            for item in group.items:
                exercise = get_imported_exercise(item.slug)
                if exercise is None:
                    continue
                load_type = self._builder_load_type(exercise)
                sets = self._parse_builder_set_count(item.sets)
                target_value = self._parse_builder_target_value(item.sets, item.load, self._default_builder_target_value(exercise))
                duration_seconds = self._parse_builder_duration(item.sets)
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
                        "reps": target_value,
                        "weight": int(round(weight)),
                        "restSeconds": rest_seconds,
                        **({"durationSeconds": duration_seconds} if duration_seconds is not None else {}),
                    },
                )

                items.append(
                    item.model_copy(
                        update={
                            "muscles": [self._translate_muscle(muscle) for muscle in exercise.muscles],
                            "affects_fatigue": exercise.equipment != "Recovery",
                            "preview_video_url": self._preview_video_url(exercise, user_id),
                            "load_type": load_type,
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

    def _builder_editor(
        self,
        session: Session,
        user_id: str,
        program_id: str,
        selected_item: BuilderExerciseItemSchema,
        settings: ExerciseLoadSettingsSchema,
    ) -> BuilderExerciseEditorSchema:
        exercise = get_imported_exercise(selected_item.slug)
        load_type = self._builder_load_type(exercise)
        default_target = self._parse_builder_target_value(selected_item.sets, selected_item.load, self._default_builder_target_value(exercise))
        value = self._builder_setting_value(session, user_id, program_id).get("editors")
        raw_editor = value.get(selected_item.id) if isinstance(value, dict) else None
        if isinstance(raw_editor, dict):
            try:
                editor = BuilderExerciseEditorSchema.model_validate(raw_editor)
                return self._normalize_builder_editor(editor, load_type, default_target)
            except ValidationError:
                pass

        state = self._user_state(session, user_id, selected_item.slug)
        set_params = {
            "reps": state.working_reps if state and state.working_reps is not None else default_target,
            "weight": int(round(state.working_weight if load_type == "weighted" and state and state.working_weight is not None else self._default_builder_weight(exercise))),
            "restSeconds": settings.rest_seconds,
        }
        if load_type == "timed":
            set_params["durationSeconds"] = default_target
        editor = BuilderExerciseEditorSchema(
            name=selected_item.name,
            subtitle=selected_item.muscle_group,
            set_params=set_params,
            load_type=load_type,
            load_mode=settings.mode,
            tempo=settings.tempo,
            strength_mode_id=selected_item.strength_mode_id,
            strength_day_type=selected_item.strength_day_type,
            strength_plan=selected_item.strength_plan,
            note=state.notes if state and state.notes else "Следить за техникой и не терять контроль в нижней точке.",
        )
        return self._normalize_builder_editor(editor, load_type, default_target)

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

    def _builder_summary_cards(self, groups: list[BuilderWorkoutGroupSchema], duration_minutes: int) -> list[BuilderSummaryCardSchema]:
        exercise_count = sum(len(group.items) for group in groups)
        set_count = sum(len(item.strength_plan) or self._parse_sets(item.sets) for group in groups for item in group.items)
        tonnage = sum(self._builder_item_tonnage(item) for group in groups for item in group.items)
        return [
            BuilderSummaryCardSchema(label="упражнений", value=str(exercise_count), hint="структура тренировки"),
            BuilderSummaryCardSchema(label="подходов", value=str(set_count), hint="общий объём"),
            BuilderSummaryCardSchema(label="минут", value=str(duration_minutes), hint="оценка длительности"),
            BuilderSummaryCardSchema(label="кг", value=f"{int(round(tonnage)):,}".replace(",", " "), hint="общий тоннаж"),
        ]

    def _builder_estimated_duration_minutes(self, groups: list[BuilderWorkoutGroupSchema], fallback_minutes: int) -> int:
        total_seconds = sum(self._builder_item_duration_seconds(item) for group in groups for item in group.items)
        if total_seconds <= 0:
            return 0
        return max(1, int(round(total_seconds / 60)))

    def _builder_item_duration_seconds(self, item: BuilderExerciseItemSchema) -> int:
        if item.strength_plan:
            work_seconds = sum(self._builder_set_active_seconds(item, set_plan.target_reps_label) for set_plan in item.strength_plan)
            rest_seconds = sum(set_plan.rest_seconds for set_plan in item.strength_plan[:-1])
            return work_seconds + rest_seconds

        set_count = self._parse_sets(item.sets)
        work_seconds = self._builder_set_active_seconds(item, item.sets) * max(set_count, 1)
        rest_seconds = self._parse_builder_rest(item.rest) * max(set_count - 1, 0)
        return work_seconds + rest_seconds

    def _builder_set_active_seconds(self, item: BuilderExerciseItemSchema, source: str) -> int:
        if item.load_type == "timed":
            return self._parse_builder_duration(item.sets) or 45

        reps = self._parse_strength_target_reps(source) if item.strength_plan else self._parse_reps(source)
        return max(20, reps * 4)

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

    def _normalize_builder_editor(self, editor: BuilderExerciseEditorSchema, load_type: str, default_target: int) -> BuilderExerciseEditorSchema:
        set_params = dict(editor.set_params)
        normalized_set_params = {
            "reps": self._coerce_builder_int(set_params.get("reps"), default_target, 1),
            "weight": self._coerce_builder_int(set_params.get("weight"), 0, 0),
            "restSeconds": self._coerce_builder_int(set_params.get("restSeconds"), 60, 15),
        }
        duration_seconds = self._coerce_builder_optional_int(set_params.get("durationSeconds"), 1)
        if duration_seconds is not None:
            normalized_set_params["durationSeconds"] = duration_seconds
        elif load_type == "timed":
            normalized_set_params["durationSeconds"] = default_target

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
        reps = max(1, int(set_params.get("reps", 10)))
        rest_seconds = max(15, int(set_params.get("restSeconds", 90)))
        weight = max(0, int(set_params.get("weight", 0)))

        def weight_label(factor: float) -> str:
            if load_type != "weighted" or weight <= 0:
                return "вес тела"
            return f"{max(0, round(weight * factor)):g} кг"

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

        return [
            item(1, "warmup", "Разминка", target_range(max(8, reps - 2), max(10, reps)), 0.5, 60, "4–5 в запасе", "Лёгкий разминочный подход."),
            item(2, "work", "Рабочий подход", "8–12", 1.0, max(60, min(rest_seconds, 120)), "1–3 в запасе", "Стабильная техника без отказа."),
            item(3, "work", "Рабочий подход", "8–12", 1.0, max(60, min(rest_seconds, 120)), "1–3 в запасе", "Сохранять амплитуду."),
            item(4, "work", "Рабочий подход", "8–12", 1.0, max(60, min(rest_seconds, 120)), "1–3 в запасе", "Остановиться до потери техники."),
        ]

    def _apply_builder_editor_to_groups(self, groups: list[BuilderWorkoutGroupSchema], selected_exercise_id: str, editor: BuilderExerciseEditorSchema) -> list[BuilderWorkoutGroupSchema]:
        updated_groups: list[BuilderWorkoutGroupSchema] = []
        for group in groups:
            updated_items = []
            for item in group.items:
                if item.id != selected_exercise_id:
                    updated_items.append(item)
                    continue

                exercise = get_imported_exercise(item.slug)
                load_type = editor.load_type or self._builder_load_type(exercise)
                effective_set_params = editor.effective_set_params or self._builder_effective_set_params(load_type, editor.set_params, editor.load_mode, editor.tempo)
                strength_mode_id = self._normalize_strength_mode_id(editor.strength_mode_id)
                strength_day_type = self._normalize_strength_day_type(strength_mode_id, editor.strength_day_type)
                strength_plan = self._builder_strength_plan(strength_mode_id, strength_day_type, load_type, effective_set_params)
                updated_items.append(
                    item.model_copy(
                        update={
                            "load_type": load_type,
                            "sets": self._format_builder_sets(load_type, self._parse_builder_set_count(item.sets), effective_set_params["reps"], effective_set_params.get("durationSeconds")),
                            "load": self._format_builder_load(load_type, effective_set_params["weight"]),
                            "rest": f"{effective_set_params['restSeconds']} сек",
                            "strength_mode_id": strength_mode_id,
                            "strength_day_type": strength_day_type,
                            "strength_plan": strength_plan,
                        }
                    )
                )
            updated_groups.append(group.model_copy(update={"items": updated_items}))
        return updated_groups

    def _builder_effective_set_params(self, load_type: str, set_params: dict[str, int], load_mode: str, tempo: str) -> dict[str, int]:
        load_mode_rule = self._builder_load_mode_rule(load_mode)
        tempo_rule = self._builder_tempo_rule(tempo)
        result = {
            "reps": max(1, int(round(set_params.get("reps", 1) * load_mode_rule["reps_factor"] * tempo_rule["reps_factor"]))),
            "weight": max(0, int(round(set_params.get("weight", 0) * load_mode_rule["weight_factor"] * tempo_rule["weight_factor"]))) if load_type == "weighted" else max(0, int(set_params.get("weight", 0))),
            "restSeconds": max(15, int(set_params.get("restSeconds", 60)) + int(load_mode_rule["rest_delta"]) + int(tempo_rule["rest_delta"])),
        }
        duration_seconds = set_params.get("durationSeconds")
        if duration_seconds is not None:
            result["durationSeconds"] = max(1, int(round(duration_seconds * load_mode_rule["duration_factor"] * tempo_rule["duration_factor"])))
        return result

    def _builder_load_mode_rule(self, load_mode: str) -> dict[str, float | int | str]:
        return BUILDER_LOAD_MODE_RULES.get(load_mode, BUILDER_LOAD_MODE_RULES["Обычный вес"])

    def _builder_tempo_rule(self, tempo: str) -> dict[str, float | int | str]:
        return BUILDER_TEMPO_RULES.get(tempo, BUILDER_TEMPO_RULES["Обычный"])

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
        if exercise and exercise.force == "Static":
            return "timed"
        if exercise and exercise.equipment in {"Bodyweight", "Stretches", "Recovery"}:
            return "bodyweight"
        return "weighted"

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

        duration_suffix = f" · {max(1, duration_seconds)} сек" if duration_seconds is not None else ""
        return f"{max(1, sets)}×{max(1, target_value)}{duration_suffix}"

    def _parse_builder_set_count(self, value: str) -> int:
        match = re.search(r"(\d+)", value)
        if match:
            return max(1, int(match.group(1)))
        return 3

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
        state = self._user_state(session, user_id, slug)
        base_weight = 45.0 if exercise and exercise.equipment == "Machine" else (40.0 if exercise and exercise.equipment == "Barbell" else 20.0)
        weight = state.working_weight if state and state.working_weight is not None else base_weight
        sets = state.working_sets if state and state.working_sets is not None else 3
        reps = state.working_reps if state and state.working_reps is not None else 10
        rest_seconds = state.rest_seconds if state and state.rest_seconds is not None else 60
        calibration = state.calibration_status if state and state.calibration_status else ("required" if exercise and exercise.equipment == "Machine" else "recommended")
        return ExerciseLoadSettingsSchema(
            weight=weight,
            sets=sets,
            reps=reps,
            rest_seconds=rest_seconds,
            mode="Обычный вес" if weight > 0 else "Контроль техники",
            tempo="Обычный",
            recommendation="Можно сохранить рабочий вес и контролировать амплитуду движения.",
            safe_range=(max(0.0, weight - 10.0), weight + 5.0),
            calibration=calibration,
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
        return MUSCLE_TRANSLATIONS.get(value, value.replace("_", " ").title())

    def _translate_equipment(self, value: str) -> str:
        return EQUIPMENT_TRANSLATIONS.get(value, value)

    def _translate_grip(self, value: str) -> str:
        return GRIP_TRANSLATIONS.get(value, value)

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

        return sorted(visible_programs, key=lambda program: (not program.recommended_today, program.name.lower(), program.id))

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

    def _schedule_entries(self, session: Session) -> list[WorkoutScheduleEntry]:
        entries = list(session.scalars(select(WorkoutScheduleEntry).order_by(WorkoutScheduleEntry.scheduled_date.asc())))
        if entries:
            return entries
        base_days = [
            (date(2026, 5, 13), "Спина + бицепс", "completed", ["Выполнено"], 45, 5, 18, 78),
            (date(2026, 5, 14), "Спина + бицепс", "today", ["Сегодня"], 45, 5, 18, 78),
            (date(2026, 5, 15), "День отдыха", "rest", ["Восстановление"], None, None, None, None),
            (date(2026, 5, 16), "Грудь + плечи", "planned", ["Запланировано"], 40, 4, 14, 66),
            (date(2026, 5, 17), "Ноги + кор", "planned", ["Запланировано"], 50, 5, 18, 58),
            (date(2026, 5, 18), "Фуллбоди", "completed", ["Выполнено"], 42, 4, 16, 74),
            (date(2026, 5, 19), "Плечи", "planned", ["Запланировано"], 35, 3, 12, 71),
        ]
        return [
            WorkoutScheduleEntry(
                user_id="alexey",
                scheduled_date=scheduled_date,
                title=title,
                subtitle="Сегодня" if status == "today" else None,
                status=status,
                badges=badges,
                duration_minutes=duration_minutes,
                exercise_count=exercise_count,
                set_count=set_count,
                readiness_percent=readiness_percent,
                target_muscles="спина, бицепс, предплечья" if title == "Спина + бицепс" else ("грудь, плечи" if title == "Грудь + плечи" else "ноги, кор"),
                recommendation="Грудь лучше не нагружать до следующей сессии." if title == "Спина + бицепс" else "Держите объём в пределах готовности и корректируйте нагрузку по ощущениям.",
                metadata_json={},
            )
            for scheduled_date, title, status, badges, duration_minutes, exercise_count, set_count, readiness_percent in base_days
        ]

    def _calendar_day(self, entry: WorkoutScheduleEntry, selected: bool, mode: str) -> CalendarDayCardSchema:
        date_label = entry.scheduled_date.strftime("%d") if mode == "month" else entry.scheduled_date.strftime("%a %d")
        return CalendarDayCardSchema(
            id=str(entry.scheduled_date),
            date_label=date_label,
            title=entry.title,
            badges=list(entry.badges),
            status=entry.status,
            readiness_percent=entry.readiness_percent,
            duration=f"{entry.duration_minutes} мин" if entry.duration_minutes is not None else None,
            exercise_count=entry.exercise_count,
            selected=selected,
        )

    def _format_date(self, value: datetime) -> str:
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).strftime("%d.%m.%Y")
