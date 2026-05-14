from app.models.enums import NotificationTone
from app.schemas.base import SchemaModel
from app.schemas.machine import MachineHealthSchema


class DashboardWorkoutSchema(SchemaModel):
    title: str
    exercises: int
    sets: int
    duration: str
    list: list[str]


class DashboardRecommendationSchema(SchemaModel):
    name: str
    muscles: str
    status: str


class DashboardQuickStartItemSchema(SchemaModel):
    name: str
    stats: str
    last: str


class DashboardProgressMetricSchema(SchemaModel):
    label: str
    value: str


class DashboardAlertSchema(SchemaModel):
    tone: NotificationTone
    title: str
    description: str


class MuscleCardSchema(SchemaModel):
    name: str
    status: str
    score: int


class DashboardDataSchema(SchemaModel):
    greeting: str
    recommendation_title: str
    recommendation_text: str
    readiness_percent: int
    today_workout: DashboardWorkoutSchema | None
    machine: MachineHealthSchema
    alerts: list[DashboardAlertSchema]
    recommended_exercises: list[DashboardRecommendationSchema]
    quick_start: list[DashboardQuickStartItemSchema]
    progress: list[DashboardProgressMetricSchema]
    muscles: list[MuscleCardSchema]
