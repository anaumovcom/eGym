from datetime import datetime

from app.models.enums import NotificationTone
from app.schemas.base import SchemaModel
from app.schemas.machine import MachineHealthSchema


class DashboardWorkoutSchema(SchemaModel):
    title: str
    exercises: int
    sets: int
    duration: str


class DashboardWorkoutSnapshotSchema(SchemaModel):
    label: str
    primary: str
    secondary: str
    meta: str | None = None


class DashboardWorkoutExerciseSchema(SchemaModel):
    slug: str
    name: str
    previous: DashboardWorkoutSnapshotSchema
    planned: DashboardWorkoutSnapshotSchema
    preview_video_url: str | None = None


class DashboardWorkoutSchema(SchemaModel):
    title: str
    exercises: int
    sets: int
    duration: str
    list: list[DashboardWorkoutExerciseSchema]
class DashboardBuilderWorkoutExerciseSchema(SchemaModel):
    slug: str
    name: str
    status: str = "idle"
    completed_sets: int = 0
    target_sets: int = 0
    progress_percent: int = 0


class DashboardBuilderWorkoutSchema(SchemaModel):
    id: str
    title: str
    exercises: list[DashboardBuilderWorkoutExerciseSchema]
    duration: str
    today_status: str = "idle"
    today_progress_percent: int = 0
    today_completed_exercises: int = 0
    today_total_exercises: int = 0
    resume_available: bool = False


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
    workouts: list[DashboardBuilderWorkoutSchema]
    machine: MachineHealthSchema
    alerts: list[DashboardAlertSchema]
    recommended_exercises: list[DashboardRecommendationSchema]
    quick_start: list[DashboardQuickStartItemSchema]
    progress: list[DashboardProgressMetricSchema]
    muscles: list[MuscleCardSchema]


class DashboardDayProgressResetSchema(SchemaModel):
    user_id: str


class DashboardDayProgressResetResultSchema(SchemaModel):
    status: str
    user_id: str
    effective_from: datetime
