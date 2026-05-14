from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.training import ExerciseHistoryRecord, UserExerciseState, WorkoutProgram, WorkoutScheduleEntry
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
    BuilderSummaryCardSchema,
    BuilderWorkoutGroupSchema,
    ProgramCompatibilitySchema,
    ProgramDetailsActionsSchema,
    ProgramDetailsSchema,
    ProgramLibraryDataSchema,
    ProgramSummarySchema,
    QuickStartDataSchema,
    QuickStartExerciseListItemSchema,
    QuickStartRecommendationSchema,
    QuickStartSelectedExerciseReadinessSchema,
    QuickStartSelectedExerciseSchema,
    QuickStartSelectedExerciseWarningSchema,
    TodayWorkoutDataSchema,
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
        selected_slug = selected or FEATURED["today"][0]
        machine_scenario = "blocked" if scenario == "blocked" else "ready"
        machine = self.machine_service.get_machine_health(session, machine_scenario)
        readiness_percent = 42 if scenario == "recovery" else 78
        rows = []
        for index, slug in enumerate(FEATURED["today"]):
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
            summary={"exercises": 5, "sets": 18, "duration": "45 мин"},
            main_action="Продолжить тренировку" if scenario == "in-progress" else ("Открыть результат" if scenario == "completed" else ("Старт заблокирован" if scenario == "blocked" else "Начать тренировку")),
            exercise_rows=rows,
            selected_exercise_id=selected_slug,
            selected_exercise=selected_panel,
            warnings=warnings,
            muscles=self._muscle_cards(session, user_id),
            progress=WorkoutProgressSchema(
                completed_exercises=5 if scenario == "completed" else (2 if scenario == "in-progress" else 0),
                total_exercises=5,
                completed_sets=18 if scenario == "completed" else (7 if scenario == "in-progress" else 0),
                total_sets=18,
                minutes_left=0 if scenario == "completed" else (27 if scenario == "in-progress" else 45),
                percent=100 if scenario == "completed" else (39 if scenario == "in-progress" else 0),
                next_step="Тренировка завершена" if scenario == "completed" else "Сгибание рук",
            ),
            quick_actions=["Изменить тренировку", "Заменить упражнение", "Сохранить как программу", "Перенести тренировку"],
        )

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

    def get_builder(self, session: Session, *, selected_exercise_id: str | None) -> WorkoutBuilderDataSchema:
        groups = [
            BuilderWorkoutGroupSchema(
                id="group-a",
                kind="alternating",
                title="Тяга сверху + Присед",
                rounds="3 круга • 8–12 мин",
                between_exercises_rest="30 сек",
                between_rounds_rest="90 сек",
                items=[
                    BuilderExerciseItemSchema(id="group-pullups-1", slug="machine-pulldown", name="Тяга сверху", muscle_group="Спина", sets="3×10", rest="30 сек", load="45 кг"),
                    BuilderExerciseItemSchema(id="group-squat-1", slug="barbell-heels-up-back-squat", name="Присед", muscle_group="Ноги", sets="3×8", rest="30 сек", load="60 кг"),
                ],
            ),
            BuilderWorkoutGroupSchema(
                id="group-b",
                kind="single",
                title="Основной блок",
                items=[
                    BuilderExerciseItemSchema(id="row-1", slug="machine-seated-cable-row", name="Тяга горизонтального блока", muscle_group="Спина", sets="3×10", rest="90 сек", load="45 кг"),
                    BuilderExerciseItemSchema(id="row-2", slug="underhand-pulldown", name="Тяга обратным хватом", muscle_group="Спина", sets="4×12", rest="90 сек", load="40 кг"),
                    BuilderExerciseItemSchema(id="curl-1", slug="barbell-curl", name="Сгибание рук", muscle_group="Бицепс", sets="3×12", rest="75 сек", load="20 кг"),
                    BuilderExerciseItemSchema(id="plank-1", slug="forearm-plank", name="Планка", muscle_group="Кор", sets="3×45 сек", rest="45 сек", load="вес тела"),
                ],
            ),
        ]
        selected_item = next((item for group in groups for item in group.items if item.id == selected_exercise_id), groups[0].items[0])
        exercise = get_imported_exercise(selected_item.slug)
        settings = self._load_settings(session, "alexey", selected_item.slug, exercise)
        return WorkoutBuilderDataSchema(
            title="Конструктор тренировок",
            subtitle="Соберите тренировку из упражнений, настройте нагрузку и сохраните программу.",
            info={
                "name": "День спины",
                "type": "Силовая",
                "duration": "≈ 45 минут",
                "difficulty": "Средняя",
                "description": "Тренировка на спину и бицепс с умеренным объёмом.",
            },
            groups=groups,
            selected_exercise_id=selected_item.id,
            selected_exercise=BuilderExerciseEditorSchema(
                name=selected_item.name,
                subtitle=selected_item.muscle_group,
                set_params={"reps": settings.reps, "weight": int(round(settings.weight)), "restSeconds": settings.rest_seconds},
                load_mode=settings.mode,
                tempo=settings.tempo,
                note="Следить за техникой и не терять контроль в нижней точке.",
            ),
            add_suggestions=[
                {"slug": "machine-pulldown", "name": "Тяга сверху", "muscles": "Спина, бицепс"},
                {"slug": "machine-seated-cable-row", "name": "Тяга к поясу", "muscles": "Спина"},
                {"slug": "underhand-pulldown", "name": "Тяга обратным хватом", "muscles": "Широчайшие"},
                {"slug": "barbell-curl", "name": "Сгибание рук", "muscles": "Бицепс"},
            ],
            summary_cards=[
                BuilderSummaryCardSchema(label="упражнений", value="5", hint="структура тренировки"),
                BuilderSummaryCardSchema(label="подходов", value="18", hint="общий объём"),
                BuilderSummaryCardSchema(label="минут", value="45", hint="оценка длительности"),
                BuilderSummaryCardSchema(label="кг", value="5620", hint="общий тоннаж"),
            ],
            warnings=[
                {"tone": "warning", "title": "Длинная тренировка", "description": "Расчётное время больше целевого. Можно убрать один вспомогательный блок."},
                {"tone": "warning", "title": "Короткий отдых", "description": "Для тяжёлых подходов рекомендуется отдых 60–90 секунд."},
                {"tone": "success", "title": "Упражнения из чёрного списка отсутствуют", "description": "Текущая версия плана безопасна для пользователя."},
            ],
        )

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
        preview_video_url = exercise.videos[0].relative_url if exercise.videos else None
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

    def _programs(self, session: Session) -> list[WorkoutProgram]:
        programs = list(session.scalars(select(WorkoutProgram).where(WorkoutProgram.deleted.is_(False)).order_by(WorkoutProgram.recommended_today.desc(), WorkoutProgram.name.asc())))
        if programs:
            return programs
        return [
            WorkoutProgram(id="back-biceps", owner_user_id=None, source="template", name="Спина + бицепс", subtitle="Силовая тренировка", program_type="strength", difficulty="medium", duration_minutes=45, exercise_count=5, set_count=18, focus_tags=["Спина", "Бицепс", "Предплечья"], recommended_today=True, description="Тяговая силовая тренировка.", structure={"exerciseSlugs": FEATURED["today"]}),
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
