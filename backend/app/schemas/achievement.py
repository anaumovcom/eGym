"""Public achievement contracts. No private notes, prompts or provider credentials."""

from typing import Literal

from app.schemas.base import SchemaModel


class AchievementTierSchema(SchemaModel):
    id: str
    tier: int
    tier_name: str
    threshold: int
    minimum_evidence_days: int = 0
    title: str
    phrase: str
    rarity: Literal["common", "rare", "epic", "legendary"]
    image_url: str | None = None
    thumbnail_url: str | None = None
    audio_url: str | None = None
    image_state: str
    audio_state: str
    earned: bool = False
    earned_at: str | None = None
    awarded_at: str | None = None
    status: str


class AchievementLineSchema(SchemaModel):
    id: str
    group: str
    group_name: str
    metric: str
    unit: str
    description: str
    thresholds: list[int]
    applicability: str
    current_value: float
    evidence_days: float = 0
    highest_tier: int
    state: str
    updated_at: str | None = None
    is_new: bool = False
    next_tier_id: str | None = None
    progress_percent: float
    tiers: list[AchievementTierSchema]


class AchievementReceiptSchema(SchemaModel):
    definition_id: str
    tier: int
    surface: Literal["detail", "audio"]
    viewed_at: str
    is_new: bool


class AchievementGroupSchema(SchemaModel):
    id: str
    name: str


class AchievementMediaSummarySchema(SchemaModel):
    lines: int
    tiers: int
    images: int
    audio: int


class AchievementCatalogResponseSchema(SchemaModel):
    lines: list[AchievementLineSchema]
    total: int
    next_cursor: int | None = None
    computed_through: str | None = None
    is_rebuilding: bool
    groups: list[AchievementGroupSchema]
    media: AchievementMediaSummarySchema


class AchievementAwardSchema(SchemaModel):
    grant_id: int
    definition_id: str
    group: str
    source_workout_id: int | None = None
    status: str
    is_new: bool = False
    earned_at: str | None = None
    awarded_at: str
    tier: AchievementTierSchema
    unit: str
    description: str


class AchievementOverviewResponseSchema(SchemaModel):
    earned_tiers: int
    total_tiers: int
    completed_lines: int
    total_lines: int
    active_days: float
    recent: list[AchievementAwardSchema]
    upcoming: list[AchievementLineSchema]
    computed_through: str | None = None
    is_rebuilding: bool
    media: AchievementMediaSummarySchema


class WorkoutAwardsResponseSchema(SchemaModel):
    workout_id: int
    awards: list[AchievementAwardSchema]
    is_rebuilding: bool
