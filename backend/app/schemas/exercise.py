from typing import Literal

from app.schemas.base import SchemaModel
from app.schemas.muscle import MuscleCardSchema


class ExerciseVideoAssetSchema(SchemaModel):
    url: str
    label: str
    view: Literal["side", "front"]
    gender: Literal["male", "female"]


class ExerciseHistoryEntrySchema(SchemaModel):
    date: str
    weight: str
    reps: str
    sets: int
    volume: str
    rpe: int
    note: str


class ExerciseLoadPointSchema(SchemaModel):
    label: str
    value: float
    caption: str | None = None


class ExerciseAlternativeSchema(SchemaModel):
    slug: str
    name: str
    secondary_name: str
    muscles: list[str]
    equipment: str


class ExerciseCompatibilitySchema(SchemaModel):
    tone: str
    title: str
    description: str
    affected_muscles: list[MuscleCardSchema]


class ExerciseLoadSettingsSchema(SchemaModel):
    weight: float
    sets: int
    reps: int
    rest_seconds: int
    mode: str
    tempo: str
    recommendation: str
    safe_range: tuple[float, float]
    calibration: str


class ExerciseSummarySchema(SchemaModel):
    slug: str
    name: str
    secondary_name: str
    equipment: str
    difficulty: str
    force: str
    grips: str
    mechanic: str
    muscles: list[str]
    favorite: bool
    blacklisted: bool
    recommended: bool
    compatibility_tone: str
    readiness_status: str
    difficulty_label: str
    image_url: str | None = None
    preview_video_url: str | None = None
    badges: list[str]


class ExerciseGuideSchema(SchemaModel):
    setup: list[str]
    how_to_perform: list[str]
    technique: list[str]
    things_to_avoid: list[str]
    key_tips: list[str]


class ExerciseDetailsSchema(ExerciseSummarySchema):
    description: str
    short_steps: list[str]
    guide: ExerciseGuideSchema
    videos: list[ExerciseVideoAssetSchema]
    primary_muscles: list[str]
    secondary_muscles: list[str]
    stabilizers: list[str]
    muscle_role_text: str
    compatibility: ExerciseCompatibilitySchema
    load_settings: ExerciseLoadSettingsSchema
    history: list[ExerciseHistoryEntrySchema]
    load_progress: list[ExerciseLoadPointSchema]
    similar: list[ExerciseAlternativeSchema]
    equipment_alternatives: list[str]
    when_to_choose_alternative: list[str]


class ExerciseCatalogAvailableFiltersSchema(SchemaModel):
    muscles: list[str]
    equipment: list[str]
    difficulty: list[str]
    force: list[str]
    mechanic: list[str]
    grips: list[str]


class ExerciseCatalogResponseSchema(SchemaModel):
    items: list[ExerciseSummarySchema]
    total: int
    available_filters: ExerciseCatalogAvailableFiltersSchema