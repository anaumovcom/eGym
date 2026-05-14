from datetime import date, datetime

from pydantic import Field

from app.models.enums import AccessRole, UserAccent
from app.schemas.base import SchemaModel


class UserSummarySchema(SchemaModel):
    id: str
    name: str
    readiness_percent: int
    last_workout: str
    today_focus: str
    week_progress: str
    accent: UserAccent


class UsersResponseSchema(SchemaModel):
    users: list[UserSummarySchema]


class UserGoalSchema(SchemaModel):
    id: int
    goal_type: str
    label: str
    target_value: float | None
    target_unit: str | None
    is_primary: bool


class BodyMeasurementSchema(SchemaModel):
    id: int
    measured_at: datetime
    weight_kg: float | None
    body_fat_percent: float | None
    chest_cm: float | None
    waist_cm: float | None
    hips_cm: float | None


class UserProfileSchema(SchemaModel):
    birth_date: date | None
    height_cm: int | None
    weight_kg: float | None
    photo_url: str | None
    notes: str | None


class CurrentUserSchema(SchemaModel):
    id: str
    name: str
    role: AccessRole
    readiness_percent: int
    accent: UserAccent
    profile: UserProfileSchema | None
    goals: list[UserGoalSchema]


class SelectUserRequestSchema(SchemaModel):
    user_id: str = Field(min_length=1)


class SelectUserResponseSchema(SchemaModel):
    current_user: CurrentUserSchema
