from datetime import datetime

from app.schemas.base import SchemaModel
from app.schemas.machine import MachineHealthSchema
from app.schemas.user import BodyMeasurementSchema


class MetricCardSchema(SchemaModel):
    label: str
    value: str
    hint: str | None = None
    tone: str | None = None


class ChartPointSchema(SchemaModel):
    label: str
    value: float
    accent: bool | None = None


class ProgressExerciseHistoryRowSchema(SchemaModel):
    date: str
    weight: str
    sets: str
    reps: str
    volume: str
    amplitude: str


class ProgressExerciseOptionSchema(SchemaModel):
    slug: str
    name: str


class MuscleCardSchema(SchemaModel):
    name: str
    status: str
    score: int


class ProgressExerciseDetailsSchema(SchemaModel):
    slug: str
    last_result: str
    best_result: str
    best_volume: str
    completed_times: str
    average_amplitude: str
    tempo_trend: str
    work_weight_series: list[ChartPointSchema]
    volume_series: list[ChartPointSchema]
    history: list[ProgressExerciseHistoryRowSchema]
    affected_muscles: list[MuscleCardSchema]
    recommendation: str


class ProgressPhotoViewSchema(SchemaModel):
    id: str
    label: str


class ProgressPhotoEntrySchema(SchemaModel):
    id: str
    date: str
    year: str
    views: list[ProgressPhotoViewSchema]
    is_latest: bool | None = None


class ProgressBodyMeasurementRowSchema(SchemaModel):
    label: str
    current: str
    delta: str
    tone: str


class ProgressDataSchema(SchemaModel):
    machine: MachineHealthSchema
    updated_at: str
    period_label: str
    title: str
    subtitle: str
    summary_cards: list[MetricCardSchema]
    summary_volume_series: list[ChartPointSchema]
    main_progress: dict[str, object]
    improvements: list[str]
    period_summary: list[MetricCardSchema]
    recommendation: str
    exercise_options: list[ProgressExerciseOptionSchema]
    selected_exercise: ProgressExerciseDetailsSchema
    strength_cards: list[MetricCardSchema]
    volume_top_exercises: list[dict[str, object]]
    regularity_cards: list[MetricCardSchema]
    activity_calendar: list[dict[str, object]]
    weekly_training_series: list[ChartPointSchema]
    weekly_minute_series: list[ChartPointSchema]
    day_distribution: list[ChartPointSchema]
    recent_weeks: list[dict[str, object]]
    muscle_load: list[MuscleCardSchema]
    muscle_split: list[dict[str, object]]
    muscle_coverage: list[dict[str, object]]
    muscle_recommendation: str
    body_cards: list[MetricCardSchema]
    body_weight_series: list[ChartPointSchema]
    body_measurements: list[ProgressBodyMeasurementRowSchema]
    smart_scale: dict[str, object]
    photo_entries: list[ProgressPhotoEntrySchema]
    photo_stats: list[MetricCardSchema]
    photo_recommendation: str
    empty_state: dict[str, str] | None = None


class FatigueImpactSchema(SchemaModel):
    exercise: str
    date: str
    share: str
    status: str


class FatigueExerciseSuggestionSchema(SchemaModel):
    name: str
    note: str
    status: str


class FatigueMuscleSchema(SchemaModel):
    id: str
    name: str
    short_name: str
    group: str
    area: str
    score: int
    readiness_percent: int
    status: str
    recovery_hours: int
    last_load_at: str
    impact: list[FatigueImpactSchema]
    recommendation: str
    recommended_exercises: list[FatigueExerciseSuggestionSchema]
    avoid_exercises: list[FatigueExerciseSuggestionSchema]


class FatigueDataSchema(SchemaModel):
    machine: MachineHealthSchema
    updated_at: str
    readiness_percent: int
    overview: list[MetricCardSchema]
    muscles: list[FatigueMuscleSchema]
    recommended_plan: str
    recovery_note: str


class FatigueResetSchema(SchemaModel):
    user_id: str


class FatigueResetResultSchema(SchemaModel):
    status: str
    user_id: str
    reset_at: str
    reset_count: int


class FatigueHistoryPointSchema(SchemaModel):
    label: str
    score: int
    readiness_percent: int


class FatigueHistoryResponseSchema(SchemaModel):
    muscle_id: str
    points: list[FatigueHistoryPointSchema]


class ProgressPhotoAssetSchema(SchemaModel):
    id: int
    mode: str
    view: str
    taken_at: str
    image_url: str
    thumbnail_url: str
    width: int
    height: int
    note: str | None = None


class ProgressPhotoListResponseSchema(SchemaModel):
    photos: list[ProgressPhotoAssetSchema]


class AchievementSchema(SchemaModel):
    id: str
    title: str
    description: str
    unlocked: bool
    unlocked_at: str | None = None


class AchievementsResponseSchema(SchemaModel):
    achievements: list[AchievementSchema]


class BodyMeasurementListResponseSchema(SchemaModel):
    measurements: list[BodyMeasurementSchema]


class BodyMeasurementCreateSchema(SchemaModel):
    user_id: str
    measured_at: datetime
    weight_kg: float | None = None
    body_fat_percent: float | None = None
    chest_cm: float | None = None
    waist_cm: float | None = None
    hips_cm: float | None = None