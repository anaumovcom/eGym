from datetime import datetime
from typing import Literal

from app.schemas.base import SchemaModel


class MuscleTargetSchema(SchemaModel):
    muscle_id: str
    name: str
    role: str


class SetResultCreateSchema(SchemaModel):
    occurred_at: datetime | None = None
    set_number: int
    planned_value: int
    actual_value: int
    set_type: str | None = None
    target_min_reps: int | None = None
    target_max_reps: int | None = None
    reps: int | None = None
    weight_kg: float | None = None
    duration_seconds: int | None = None
    tempo_label: str
    amplitude_percent: float | None = None
    rest_duration_seconds: int | None = None
    rir: int | None = None
    subjective_effort: int | None = None
    discomfort_level: int | None = None
    pain: bool = False
    technique_breakdown: bool = False
    comment: str | None = None
    sync_label: str | None = None
    machine_metrics: dict[str, object] = {}


class SetResultSaveSchema(SetResultCreateSchema):
    exercise_session_id: int


class ExerciseSessionCreateSchema(SchemaModel):
    exercise_session_id: int | None = None
    user_id: str
    workout_session_id: int | None = None
    exercise_slug: str
    exercise_name: str
    exercise_secondary_name: str | None = None
    kind: str
    order_index: int = 1
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    calibration_state: str | None = None
    target_sets: int = 0
    training_mode: str | None = None
    training_day_type: str | None = None
    recommendation: str | None = None
    muscles: list[MuscleTargetSchema] = []
    sets: list[SetResultCreateSchema] = []


class WorkoutSessionCreateSchema(SchemaModel):
    workout_session_id: int | None = None
    user_id: str
    source: str
    title: str
    subtitle: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: int = 0
    feeling: str | None = None
    discomfort: str | None = None
    notes: str | None = None
    exercise_session_ids: list[int] = []
    exercises: list[ExerciseSessionCreateSchema] = []


class RuntimeSetResultSchema(SchemaModel):
    set_number: int
    planned_value: int
    actual_value: int
    set_type: str | None = None
    target_min_reps: int | None = None
    target_max_reps: int | None = None
    reps: int | None = None
    weight_kg: float | None = None
    rir: int | None = None
    subjective_effort: int | None = None
    discomfort_level: int | None = None
    pain: bool = False
    technique_breakdown: bool = False
    comment: str | None = None
    volume_kg: float | None = None
    amplitude_percent: float | None = None
    tempo_label: str
    sync_label: str | None = None


class RuntimePlanVsFactSchema(SchemaModel):
    label: str
    plan: str
    fact: str
    delta: str


class RuntimeExerciseTotalsSchema(SchemaModel):
    sets_completed: str
    reps_or_time: str
    volume: str
    best_set: str | None = None
    average_amplitude: str | None = None
    tempo: str


class RuntimeExerciseSummarySchema(SchemaModel):
    exercise_session_id: int
    outcome: str
    exercise_id: str
    title: str
    subtitle: str
    set_results: list[RuntimeSetResultSchema]
    totals: RuntimeExerciseTotalsSchema
    plan_vs_fact: list[RuntimePlanVsFactSchema]
    recommendation: str
    next_step_label: str


class RuntimeWorkoutMetricSchema(SchemaModel):
    label: str
    value: str
    hint: str


class RuntimeWorkoutExerciseRowSchema(SchemaModel):
    exercise_session_id: int | None = None
    exercise_slug: str | None = None
    name: str
    result: str
    status: str
    kind: str | None = None
    current_load: str | None = None
    current_weight_kg: float | None = None
    current_reps: int | None = None
    current_sets: int | None = None
    rest_seconds: int | None = None
    training_mode: str | None = None
    training_day_type: str | None = None


class RuntimeWorkoutMuscleSchema(SchemaModel):
    name: str
    status: str
    score: int


class RuntimeWorkoutSummarySchema(SchemaModel):
    workout_session_id: int
    outcome: str
    title: str
    subtitle: str
    metrics: list[RuntimeWorkoutMetricSchema]
    exercises: list[RuntimeWorkoutExerciseRowSchema]
    muscle_load: list[RuntimeWorkoutMuscleSchema]
    recommendation: str
    next_workout: str
    feeling: str
    discomfort: str


class LoadAdjustmentRequestSchema(SchemaModel):
    user_id: str
    exercise_slug: str
    direction: Literal["increase", "decrease"]
    training_mode: str | None = None
    training_day_type: str | None = None
    kind: str | None = None
    current_weight_kg: float | None = None
    current_reps: int | None = None
    current_sets: int | None = None
    rest_seconds: int | None = None


class LoadAdjustmentResponseSchema(SchemaModel):
    user_id: str
    exercise_slug: str
    direction: str
    load_label: str
    weight_kg: float | None = None
    reps: int | None = None
    sets: int | None = None
    rest_seconds: int | None = None
    training_mode: str | None = None
    training_day_type: str | None = None
    recommendation: str


class SetFatigueDeltaSchema(SchemaModel):
    muscle_id: str
    name: str
    delta: float
    current_score: int
    readiness_percent: int
    status: str


class SavedSetResponseSchema(SchemaModel):
    set_id: int
    exercise_session_id: int
    fatigue: list[SetFatigueDeltaSchema]