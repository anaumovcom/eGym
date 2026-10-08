"""Versioned Coach contracts. No provider, credential or hardware dependencies."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, field_validator, model_validator
from pydantic.alias_generators import to_camel


class CoachModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True, allow_inf_nan=False,
    )
    schema_version: Literal[1] = 1


class CoachReason(StrEnum):
    disabled = "disabled"
    no_consent = "no_consent"
    mute = "mute"
    audio_locked = "audio_locked"
    hidden = "hidden"
    safety = "safety"
    stale_source = "stale_source"
    mock_source = "mock_source"
    owner_mismatch = "owner_mismatch"
    scope_changed = "scope_changed"
    no_window = "no_window"
    cooldown = "cooldown"
    density_cap = "density_cap"
    topic_repeat = "topic_repeat"
    pipeline_busy = "pipeline_busy"
    budget = "budget"
    provider_circuit = "provider_circuit"
    validation_failed = "validation_failed"
    missing_clip = "missing_clip"
    decode_failed = "decode_failed"
    expired = "expired"
    duplicate = "duplicate"
    cancelled = "cancelled"
    queue_full = "queue_full"


CoachPhase = Literal[
    "disabled", "setup", "waiting-start", "active-set", "paused-set", "finalizing-set",
    "rest", "exercise-summary", "workout-summary", "suspended",
]
CoachEventKind = Literal[
    "workout_started", "exercise_ready", "set_activated", "rep_completed", "rep_milestone",
    "last_rep_pending", "set_paused", "set_resumed", "set_stopped", "set_persisted",
    "rest_entered", "rest_long_opportunity", "rest_ending", "exercise_finalized", "workout_finalized",
    "pain_reported", "safety_changed",
]
CoachExerciseKind = Literal["machine", "bodyweight", "timed", "stretch", "group"]
CoachSource = Literal["hardware", "runtime_ack", "user_input", "synthetic", "recorded"]
CoachOutcome = Literal["completed", "partial", "skipped", "aborted"]


# Built-in voices of the Realtime model (live speech and packs share one timbre). Ash is the default.
COACH_VOICES = ("ash", "alloy", "ballad", "cedar", "coral", "echo", "marin", "sage", "shimmer", "verse")
DEFAULT_COACH_VOICE = "ash"
CoachVoice = Literal["ash", "alloy", "ballad", "cedar", "coral", "echo", "marin", "sage", "shimmer", "verse"]


class CoachSettings(CoachModel):
    enabled: bool = False
    consent_version: int | None = Field(default=None, ge=1)
    mode: Literal["local", "hybrid", "text-only"] = "local"
    density: Literal["quiet", "companion", "talkative"] = "companion"
    count: Literal["every", "last-three", "milestones", "off"] = "off"
    # Provider voice ID. Legacy E09 slots ("female"/"male") and unset values migrate to the default voice.
    voice_profile: CoachVoice = DEFAULT_COACH_VOICE
    history_consent: bool = False
    revision: int = Field(default=0, ge=0)
    budget_usd: str = Field(default="2.00", pattern=r"^\d{1,3}(\.\d{1,4})?$")

    @field_validator("voice_profile", mode="before")
    @classmethod
    def migrate_voice(cls, value: object) -> object:
        return DEFAULT_COACH_VOICE if value in (None, "", "female", "male") else value


class CoachScope(CoachModel):
    user_id: str = Field(min_length=1, max_length=120)
    run_id: str = Field(min_length=1, max_length=120)
    exercise_id: str | None = Field(default=None, min_length=1, max_length=160)
    set_ordinal: int | None = Field(default=None, ge=1)
    scope_epoch: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def set_requires_exercise(self) -> "CoachScope":
        if self.set_ordinal is not None and self.exercise_id is None:
            raise ValueError("Set scope requires exercise identity")
        return self


class CoachRun(CoachModel):
    scope: CoachScope
    workout_session_id: int | None = Field(default=None, ge=1)
    mode: Literal["live", "test"] = "live"
    state: Literal["idle", "active", "closed"] = "idle"
    pricing_version: str | None = Field(default=None, max_length=80)


class CoachFact(CoachModel):
    id: str = Field(min_length=1, max_length=120)
    value: StrictBool | StrictInt | StrictFloat | str | None = None
    unit: Literal["reps", "seconds", "kg", "mm", "percent", "text", "boolean"]
    source: CoachSource
    confidence: Literal["confirmed", "derived-validated", "unknown"]
    observed_at_ms: float = Field(ge=0)
    valid_until_ms: float = Field(ge=0)
    scope_epoch: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_value(self) -> "CoachFact":
        if (self.confidence == "unknown") != (self.value is None):
            raise ValueError("Unknown must be null; confirmed facts need a value")
        if isinstance(self.value, str) and len(self.value) > 200:
            raise ValueError("Fact text exceeds bound")
        if self.value is not None:
            if self.unit == "text" and not isinstance(self.value, str):
                raise ValueError("Text unit requires string")
            if self.unit == "boolean" and type(self.value) is not bool:
                raise ValueError("Boolean unit requires bool")
            if self.unit not in {"text", "boolean"} and type(self.value) not in {int, float}:
                raise ValueError("Numeric unit requires numeric value")
        if self.valid_until_ms < self.observed_at_ms:
            raise ValueError("Invalid fact validity interval")
        return self


class CoachEvent(CoachModel):
    id: str = Field(min_length=1, max_length=120)
    scope: CoachScope
    kind: CoachEventKind
    phase: CoachPhase
    source: CoachSource
    exercise_kind: CoachExerciseKind | None = None
    control_mode: str | None = Field(default=None, max_length=40)
    progress_unit: Literal["reps", "seconds"] | None = None
    ordinal: int = Field(default=0, ge=0)
    plan_revision: int = Field(default=0, ge=0)
    context_version: int = Field(default=0, ge=0)
    created_at_ms: float = Field(ge=0)
    start_deadline_ms: float = Field(ge=0)
    facts: tuple[CoachFact, ...] = Field(default=(), max_length=12)
    fact_dependencies: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def validate_dependencies(self) -> "CoachEvent":
        ids = [fact.id for fact in self.facts]
        if len(ids) != len(set(ids)) or len(self.fact_dependencies) != len(set(self.fact_dependencies)):
            raise ValueError("Duplicate facts/dependencies")
        if not set(self.fact_dependencies).issubset(ids):
            raise ValueError("Missing dependency fact")
        if self.start_deadline_ms < self.created_at_ms:
            raise ValueError("Deadline precedes event")
        if self.kind.startswith("set_") or self.kind in {"rep_completed", "rep_milestone", "last_rep_pending"}:
            if self.scope.set_ordinal is None:
                raise ValueError("Set event requires set ordinal")
        return self


class CoachDecision(CoachModel):
    action: Literal["speak", "silence"]
    text: str = Field(default="", max_length=600)
    intent: Literal["motivation", "humor", "factual-feedback", "general-tip", "summary"] = "motivation"
    used_fact_ids: tuple[str, ...] = Field(default=(), max_length=12)
    topic_key: str = Field(default="", max_length=80)
    delivery: Literal["neutral", "energetic", "calm"] = "neutral"

    @model_validator(mode="after")
    def validate_action(self) -> "CoachDecision":
        if self.action == "speak" and not self.text.strip():
            raise ValueError("Speech must have text")
        if self.action == "silence" and (self.text or self.used_fact_ids):
            raise ValueError("Silence must not carry speech")
        return self


class CoachAudio(CoachModel):
    utterance_id: str = Field(min_length=1, max_length=120)
    generation_id: str = Field(min_length=1, max_length=120)
    scope: CoachScope
    sequence: int = Field(ge=0)
    source: Literal["local", "cache", "realtime", "tts", "fake"]
    codec: Literal["pcm_s16le", "wav"]
    sample_rate: int = Field(ge=8000, le=96000)
    channels: Literal[1, 2] = 1
    byte_length: int = Field(ge=0, le=2_880_000)
    duration_ms: float = Field(ge=0, le=60_000)
    final: bool = False


class CoachUsage(CoachModel):
    attempt_id: str = Field(min_length=1, max_length=120)
    ledger: Literal["workout", "test", "pack"]
    stage: Literal["text", "voice"]
    status: Literal["reserved", "sent", "settled", "unsettled", "cancelled"]
    completeness: Literal["complete", "partial", "unavailable"] = "unavailable"
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    audio_input_tokens: int | None = Field(default=None, ge=0)
    audio_output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: str | None = Field(default=None, pattern=r"^\d+(\.\d+)?$")
    pricing_version: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_subsets(self) -> "CoachUsage":
        for total, subset in ((self.input_tokens, self.cached_input_tokens), (self.output_tokens, self.reasoning_tokens)):
            if total is not None and subset is not None and subset > total:
                raise ValueError("Usage subset exceeds total")
        return self


class CoachRuntimeNotice(CoachModel):
    """After-commit server observation, not an instruction and not a browser event."""

    kind: Literal["set_persisted", "exercise_finalized", "workout_finalized"]
    user_id: str = Field(min_length=1, max_length=120)
    workout_session_id: int | None = Field(default=None, ge=1)
    exercise_session_id: int | None = Field(default=None, ge=1)
    set_id: int | None = Field(default=None, ge=1)
    set_ordinal: int | None = Field(default=None, ge=1)
    actual_value: int | None = Field(default=None, ge=0)
    outcome: CoachOutcome | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> "CoachRuntimeNotice":
        if self.kind == "set_persisted" and (self.set_id is None or self.set_ordinal is None or self.exercise_session_id is None):
            raise ValueError("Persisted set requires captured identities")
        if self.kind == "exercise_finalized" and (self.exercise_session_id is None or self.outcome is None):
            raise ValueError("Finalized exercise requires identity and outcome")
        if self.kind == "workout_finalized" and (self.workout_session_id is None or self.outcome is None):
            raise ValueError("Finalized workout requires identity and outcome")
        return self


class CoachCapabilities(CoachModel):
    enabled: bool = False
    implementation: Literal["control-plane"] = "control-plane"
    paid_dispatch: Literal[False] = False
    lifecycle_observation: bool = False
    replay: Literal["test-only"] = "test-only"