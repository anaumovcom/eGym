from datetime import date
from typing import Any, Literal

from pydantic import Field

from app.schemas.base import SchemaModel
from app.schemas.exercise import ExerciseSummarySchema
from app.schemas.machine import MachineHealthSchema
from app.schemas.muscle import MuscleCardSchema

ProgramDifficulty = Literal["novice", "easy", "medium", "advanced"]
CalendarViewMode = Literal["week", "month"]
CalendarDayStatus = Literal["completed", "planned", "skipped", "rest", "overload", "today", "empty"]
BuilderGroupKind = Literal["single", "alternating", "superset", "circuit"]
BuilderLoadType = Literal["weighted", "bodyweight", "timed"]
StrengthSetType = Literal["warmup", "work", "failure"]


class StrengthModeDayOptionSchema(SchemaModel):
    id: str
    label: str
    description: str


class StrengthTrainingModeSchema(SchemaModel):
    id: str
    title: str
    short_description: str
    goal: str
    level: str
    audience: str
    default_day_type: str | None = None
    day_options: list[StrengthModeDayOptionSchema] = Field(default_factory=list)
    safety_note: str | None = None


class BuilderStrengthSetPlanSchema(SchemaModel):
    set_number: int
    set_type: StrengthSetType
    label: str
    target_reps_label: str
    recommended_weight_label: str
    rest_seconds: int
    rir_label: str
    note: str


class QuickStartRecommendationSchema(SchemaModel):
    title: str
    description: str
    cta: str


class QuickStartExerciseListItemSchema(ExerciseSummarySchema):
    reason: str
    last_result: str
    last_performed: str


class QuickStartSelectedExerciseReadinessSchema(SchemaModel):
    label: str
    tone: str
    description: str


class QuickStartSelectedExerciseWarningSchema(SchemaModel):
    tone: Literal["warning", "blocked"]
    title: str
    description: str


class QuickStartSelectedExerciseSchema(SchemaModel):
    exercise: ExerciseSummarySchema
    readiness: list[QuickStartSelectedExerciseReadinessSchema]
    last_result: str
    forma_recommendation: str
    settings: "ExerciseLoadSettingsSchema"
    warnings: list[QuickStartSelectedExerciseWarningSchema]


class QuickStartDataSchema(SchemaModel):
    recommendation: QuickStartRecommendationSchema
    machine: MachineHealthSchema
    filter_groups: dict[str, list[str]]
    recommended: list[QuickStartExerciseListItemSchema]
    recent: list[QuickStartExerciseListItemSchema]
    favorites: list[QuickStartExerciseListItemSchema]
    selected_exercise_slug: str | None
    selected_exercise: QuickStartSelectedExerciseSchema | None


class WorkoutExerciseRowSchema(SchemaModel):
    id: str
    slug: str
    name: str
    muscles: str
    image_url: str | None
    load: str
    rest: str
    status: str
    calibration: str
    note: str | None = None


class WorkoutExercisePanelReadinessSchema(SchemaModel):
    label: str
    value: str
    tone: str


class WorkoutExercisePanelSchema(SchemaModel):
    id: str
    slug: str
    name: str
    muscles: str
    last_result: str
    forma_recommendation: str
    readiness: list[WorkoutExercisePanelReadinessSchema]
    settings: "ExerciseLoadSettingsSchema"
    alerts: list[str]


class WorkoutProgressSchema(SchemaModel):
    completed_exercises: int
    total_exercises: int
    completed_sets: int
    total_sets: int
    minutes_left: int
    percent: int
    next_step: str


class TodayWorkoutWarningSchema(SchemaModel):
    tone: Literal["warning", "blocked"]
    title: str
    description: str


class TodayWorkoutDataSchema(SchemaModel):
    title: str
    subtitle: str
    readiness_percent: int
    machine: MachineHealthSchema
    start_state: Literal["planned", "in-progress", "completed", "blocked", "recovery"]
    summary: dict[str, Any]
    main_action: str
    exercise_rows: list[WorkoutExerciseRowSchema]
    selected_exercise_id: str
    selected_exercise: WorkoutExercisePanelSchema
    warnings: list[TodayWorkoutWarningSchema]
    muscles: list[MuscleCardSchema]
    progress: WorkoutProgressSchema
    quick_actions: list[str]


class ProgramSummarySchema(SchemaModel):
    id: str
    name: str
    subtitle: str
    exercise_count: int
    set_count: int
    duration_minutes: int
    difficulty: ProgramDifficulty
    focus_tags: list[str]
    recommended_today: bool
    image_url: str | None = None


class ProgramCompatibilitySchema(SchemaModel):
    tone: Literal["great", "okay", "caution"]
    title: str
    description: str


class ProgramExerciseLineSchema(SchemaModel):
    order: int
    name: str
    load: str
    rest: str


class ProgramDetailsActionsSchema(SchemaModel):
    primary: str
    secondary: str
    save: str
    calendar: str
    builder: str


class ProgramDetailsSchema(ProgramSummarySchema):
    compatibility: ProgramCompatibilitySchema
    equipment_coverage: str
    blacklist_issues: int
    exercise_lines: list[ProgramExerciseLineSchema]
    actions: ProgramDetailsActionsSchema


class ProgramLibraryDataSchema(SchemaModel):
    search_placeholder: str
    category_filters: list[str]
    duration_filters: list[str]
    level_filters: list[str]
    equipment_filters: list[str]
    recommended: list[ProgramSummarySchema]
    all_programs: list[ProgramSummarySchema]
    selected_program: ProgramDetailsSchema


class CalendarDayCardSchema(SchemaModel):
    id: str
    date_label: str
    title: str
    badges: list[str]
    status: CalendarDayStatus
    readiness_percent: int | None = None
    duration: str | None = None
    exercise_count: int | None = None
    selected: bool | None = None


class CalendarDayDetailsSchema(SchemaModel):
    date_label: str
    title: str
    subtitle: str
    exercise_count: int
    set_count: int
    duration: str
    target_muscles: str
    status_text: str
    readiness_percent: int
    recommendation: str


class WorkoutCalendarDataSchema(SchemaModel):
    mode: CalendarViewMode
    title: str
    legend: list[str]
    days: list[CalendarDayCardSchema]
    selected_day_id: str
    selected_day: CalendarDayDetailsSchema
    quick_actions: list[str]
    summary: list[dict[str, str]]
    muscle_balance: list[dict[str, str]]


class BuilderExerciseItemSchema(SchemaModel):
    id: str
    slug: str
    name: str
    muscle_group: str
    muscles: list[str] = Field(default_factory=list)
    affects_fatigue: bool = True
    sets: str
    rest: str
    load: str
    load_type: BuilderLoadType | None = None
    preview_video_url: str | None = None
    strength_mode_id: str = "basic"
    strength_day_type: str | None = None
    strength_plan: list[BuilderStrengthSetPlanSchema] = Field(default_factory=list)


class BuilderProgramTabSchema(SchemaModel):
    id: str
    name: str
    subtitle: str
    recommended_today: bool
    can_delete: bool = False


class BuilderWorkoutGroupSchema(SchemaModel):
    id: str
    kind: BuilderGroupKind
    title: str
    rounds: str | None = None
    between_exercises_rest: str | None = None
    between_rounds_rest: str | None = None
    items: list[BuilderExerciseItemSchema]


class BuilderExerciseEditorSchema(SchemaModel):
    name: str
    subtitle: str
    set_params: dict[str, int]
    effective_set_params: dict[str, int] = Field(default_factory=dict)
    load_type: BuilderLoadType | None = None
    load_mode: str
    load_mode_description: str = ""
    tempo: str
    tempo_description: str = ""
    strength_mode_id: str = "basic"
    strength_day_type: str | None = None
    strength_plan: list[BuilderStrengthSetPlanSchema] = Field(default_factory=list)
    note: str


class BuilderSummaryCardSchema(SchemaModel):
    label: str
    value: str
    hint: str


class WorkoutBuilderWarningSchema(SchemaModel):
    tone: Literal["warning", "blocked", "success"]
    title: str
    description: str


class WorkoutBuilderDataSchema(SchemaModel):
    title: str
    subtitle: str
    programs: list[BuilderProgramTabSchema]
    strength_modes: list[StrengthTrainingModeSchema]
    selected_program_id: str
    info: dict[str, str]
    groups: list[BuilderWorkoutGroupSchema]
    selected_exercise_id: str
    selected_exercise: BuilderExerciseEditorSchema
    add_suggestions: list[dict[str, str]]
    summary_cards: list[BuilderSummaryCardSchema]
    warnings: list[WorkoutBuilderWarningSchema]


class TodayWorkoutPlanMutationSchema(SchemaModel):
    user_id: str = Field(min_length=1)
    slugs: list[str]


class BuilderPlanMutationSchema(SchemaModel):
    user_id: str = Field(min_length=1)
    program_id: str | None = None
    workout_name: str | None = None
    groups: list[BuilderWorkoutGroupSchema]
    selected_exercise_id: str | None = None
    selected_exercise: BuilderExerciseEditorSchema | None = None


class TrainingPlanMutationResultSchema(SchemaModel):
    status: Literal["saved"]


class UserExerciseSlugListSchema(SchemaModel):
    user_id: str
    slugs: list[str]


class UpdateUserExerciseFlagSchema(SchemaModel):
    user_id: str = Field(min_length=1)
    exercise_slug: str = Field(min_length=1)


class ProgramMutationSchema(SchemaModel):
    user_id: str
    name: str
    subtitle: str
    program_type: str
    difficulty: ProgramDifficulty
    duration_minutes: int
    description: str
    focus_tags: list[str]
    structure: dict[str, Any]
    recommended_today: bool = False


class ProgramMutationResultSchema(SchemaModel):
    id: str
    status: str


class ScheduleAssignmentRequestSchema(SchemaModel):
    user_id: str
    program_id: str
    scheduled_date: date
    status: str = "planned"
    title: str | None = None


class ScheduleAssignmentResultSchema(SchemaModel):
    id: int
    status: str
    scheduled_date: date


from app.schemas.exercise import ExerciseLoadSettingsSchema  # noqa: E402