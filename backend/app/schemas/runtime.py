from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

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


class SetFeedbackSchema(SchemaModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=120)
    subjective_effort: int | None = Field(default=None, strict=True, ge=0, le=10)
    discomfort_level: int | None = Field(default=None, strict=True, ge=0, le=10)

    @model_validator(mode="after")
    def explicit_value(self):
        if self.subjective_effort is None and self.discomfort_level is None:
            raise ValueError("Explicit feedback required")
        return self


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
    per_side: bool = False
    planned_total: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    training_mode: str | None = None
    training_day_type: str | None = None
    recommendation: str | None = None
    muscles: list[MuscleTargetSchema] = []
    sets: list[SetResultCreateSchema] = []
    # an exercise done again: the earlier sets (and their fatigue) are dropped
    reset_sets: bool = False


class ExerciseSessionsResetRequestSchema(SchemaModel):
    exercises: list[ExerciseSessionCreateSchema] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def valid_resets(self):
        for exercise in self.exercises:
            if exercise.exercise_session_id is None:
                raise ValueError("Reset requires an exercise session ID")
            if not exercise.reset_sets or exercise.status != "in_progress" or exercise.sets:
                raise ValueError("Reset requires reset_sets=true, status=in_progress and empty sets")
        if len({exercise.user_id for exercise in self.exercises}) != 1:
            raise ValueError("All resets must belong to the same user")
        if len({exercise.exercise_session_id for exercise in self.exercises}) != len(self.exercises):
            raise ValueError("Exercise session IDs must be unique")
        return self


class ExerciseSessionsResetResponseSchema(SchemaModel):
    missing_exercise_session_ids: list[int]


class CoachPlanModel(SchemaModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class CoachPlanSetSchema(CoachPlanModel):
    ordinal: int = Field(ge=1, le=100)
    side: Literal["left", "right"] | None = None
    round_number: int | None = Field(default=None, ge=1, le=100)
    set_type: Literal["warmup", "working"] | None = None
    target_type: Literal["exact", "range", "open", "unknown"]
    unit: Literal["reps", "seconds"]
    minimum: int | None = Field(default=None, ge=1, le=86400)
    maximum: int | None = Field(default=None, ge=1, le=86400)
    planned_weight_kg: float | None = Field(default=None, ge=0, le=2000)
    rest_seconds: int = Field(ge=0, le=86400)

    @model_validator(mode="after")
    def valid_target(self):
        if self.target_type == "exact" and not (self.minimum is not None and self.minimum == self.maximum):
            raise ValueError("Exact target requires equal bounds")
        if self.target_type == "range" and not (self.minimum is not None and self.maximum is not None
                                                 and self.minimum <= self.maximum):
            raise ValueError("Range target requires ordered bounds")
        if self.target_type in {"open", "unknown"} and (self.minimum is not None or self.maximum is not None):
            raise ValueError("Open/unknown targets have no bounds")
        return self


class CoachPlanExerciseSchema(CoachPlanModel):
    exercise_id: str = Field(min_length=1, max_length=160)
    order_index: int = Field(ge=1, le=100)
    slug: str = Field(min_length=1, max_length=160)
    kind: Literal["machine", "bodyweight", "timed", "stretch", "group"]
    per_side: bool = False
    training_mode: str | None = Field(default=None, max_length=64)
    training_day_type: str | None = Field(default=None, max_length=32)
    sets: list[CoachPlanSetSchema] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_sets(self):
        if [s.ordinal for s in self.sets] != list(range(1, len(self.sets) + 1)):
            raise ValueError("Physical set ordinals must be unique and contiguous")
        if self.per_side and (len(self.sets) % 2 or any(
                s.side != ("left" if index % 2 == 0 else "right") or s.round_number != index // 2 + 1
                for index, s in enumerate(self.sets))):
            raise ValueError("Per-side plan requires paired physical left/right steps and logical rounds")
        if not self.per_side and any(s.side is not None for s in self.sets):
            raise ValueError("Side-specific steps require per-side mode")
        return self


class CoachWorkoutPlanSchema(CoachPlanModel):
    schema_version: Literal[1] = 1
    # Declared client intent, persisted by server; NOT verified hardware telemetry.
    origin: Literal["declared-client-plan"] = "declared-client-plan"
    exercises: list[CoachPlanExerciseSchema] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounded_plan(self):
        if [e.order_index for e in self.exercises] != list(range(1, len(self.exercises) + 1)):
            raise ValueError("Exercise order must be unique and contiguous")
        if len({e.exercise_id for e in self.exercises}) != len(self.exercises):
            raise ValueError("Exercise identities must be unique")
        if sum(len(e.sets) for e in self.exercises) > 2000 or len(self.model_dump_json()) > 500_000:
            raise ValueError("Workout plan exceeds snapshot budget")
        return self


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
    coach_plan: CoachWorkoutPlanSchema | None = None


class RuntimeSetResultSchema(SchemaModel):
    set_number: int
    side: Literal["left", "right"] | None = None
    round_number: int | None = None
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