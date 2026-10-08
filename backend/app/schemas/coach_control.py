"""E03/E04 bounded control-plane contracts; never expose secret inputs in responses."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr, model_validator

from app.schemas.coach import CoachModel, CoachSettings


class CoachPreferences(CoachSettings):
    consent_version: Literal[1] | None = None
    network_consent_version: Literal[1] | None = None
    voice_volume: float | None = Field(default=None, ge=0, le=1)
    style: Literal["companion", "calm", "strict", "showman", "stoic"] = "companion"
    humor: Literal["off", "light", "often"] = "light"
    humor_kinds: tuple[Literal["irony", "absurd", "wordplay", "self"], ...] = ("irony", "self")
    # Explicit 18+ dark-humor opt-in; the prompt module still forbids pain/injury/body/protected groups.
    edgy_opt_in: bool = False
    extras: tuple[Literal["callbacks", "pop-culture", "trivia", "breathing"], ...] = ()
    address: Literal["ty", "vy"] = "ty"
    # Letters separated by single spaces/hyphens only: it is sent to the model as data, never as instructions.
    nickname: str = Field(default="", max_length=24, pattern=r"^(?:[^\W\d_]+(?:[ -][^\W\d_]+)*)?$")
    during_sets: bool = True
    during_rest: bool = True

    @model_validator(mode="after")
    def validate_consent(self):
        if len(set(self.humor_kinds)) != len(self.humor_kinds) or len(set(self.extras)) != len(self.extras):
            raise ValueError("Duplicate personality options")
        if self.enabled and self.consent_version != 1:
            raise ValueError("Current consent required")
        if self.mode != "local" and self.network_consent_version != 1:
            raise ValueError("Network consent required")
        if not Decimal("0") < Decimal(self.budget_usd) <= Decimal("2"):
            raise ValueError("Workout budget must be >0 and <=2 USD")
        return self


class PreferencesSave(CoachModel):
    expected_revision: int = Field(ge=0)
    settings: CoachPreferences


class OperatorLogin(CoachModel):
    password: SecretStr = Field(min_length=1, max_length=256)


class CredentialSave(CoachModel):
    key: SecretStr = Field(min_length=8, max_length=512)
    expected_version: int = Field(ge=0)


class CredentialDelete(CoachModel):
    expected_version: int = Field(ge=0)


class RunCreate(CoachModel):
    user_id: str = Field(min_length=1, max_length=120)
    ledger: Literal["workout", "test", "pack"] = "workout"
    cap_usd: str = Field(default="2.00", pattern=r"^\d{1,3}(\.\d{1,6})?$")


class LeaseRequest(CoachModel):
    owner_id: str = Field(min_length=1, max_length=120)
    expected_generation: int = Field(ge=0)


class LiveConfigure(CoachModel):
    """First live-socket message. The run token never travels in the URL/query string."""

    type: Literal["configure"]
    run_token: str = Field(min_length=1, max_length=128)
    owner_id: str = Field(min_length=1, max_length=120)


class RunBind(CoachModel):
    workout_session_id: int = Field(ge=1)


class CapChange(CoachModel):
    cap_usd: str = Field(pattern=r"^\d{1,3}(\.\d{1,6})?$")
    confirm_increase: bool = False


class JobCreate(CoachModel):
    idempotency_key: str = Field(min_length=1, max_length=120)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: tuple[str, ...] = Field(min_length=1, max_length=256)


class JobAction(CoachModel):
    action: Literal["pause", "resume", "cancel"]


class PackJobCreate(CoachModel):
    run_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=120)
    plan_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    clip_ids: tuple[str, ...] = Field(min_length=1, max_length=256)


class Pricing(CoachModel):
    version: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    # Integer micro-USD per million tokens. Pricing pinned on each attempt.
    input_rate: int = Field(ge=0, le=1_000_000_000)
    cached_rate: int = Field(ge=0, le=1_000_000_000)
    output_rate: int = Field(ge=0, le=1_000_000_000)
    audio_input_rate: int = Field(default=0, ge=0, le=1_000_000_000)
    audio_cached_rate: int = Field(default=0, ge=0, le=1_000_000_000)
    audio_output_rate: int = Field(default=0, ge=0, le=1_000_000_000)
    verified: bool = False
    enforceable_bounds: bool = False

    @model_validator(mode="after")
    def validate_cached(self):
        if self.cached_rate > self.input_rate or self.audio_cached_rate > self.audio_input_rate:
            raise ValueError("Invalid cached rate")
        return self


class UsageBounds(CoachModel):
    input_tokens: int = Field(default=0, ge=0, le=1_000_000)
    output_tokens: int = Field(default=0, ge=0, le=1_000_000)
    audio_input_tokens: int = Field(default=0, ge=0, le=1_000_000)
    audio_output_tokens: int = Field(default=0, ge=0, le=1_000_000)


class ReportedUsage(UsageBounds):
    # Complete normalized category totals must be explicit, not unknown coerced to zero.
    input_tokens: int = Field(ge=0, le=1_000_000)
    output_tokens: int = Field(ge=0, le=1_000_000)
    audio_input_tokens: int = Field(ge=0, le=1_000_000)
    audio_output_tokens: int = Field(ge=0, le=1_000_000)
    cached_input_tokens: int = Field(default=0, ge=0, le=1_000_000)
    reasoning_tokens: int = Field(default=0, ge=0, le=1_000_000)
    cached_audio_input_tokens: int = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_subsets(self):
        if self.cached_input_tokens > self.input_tokens or self.reasoning_tokens > self.output_tokens or self.cached_audio_input_tokens > self.audio_input_tokens:
            raise ValueError("Usage subset exceeds total")
        return self


class PartialUsage(CoachModel):
    input_tokens: int | None = Field(default=None, ge=0, le=1_000_000)
    output_tokens: int | None = Field(default=None, ge=0, le=1_000_000)
    audio_input_tokens: int | None = Field(default=None, ge=0, le=1_000_000)
    audio_output_tokens: int | None = Field(default=None, ge=0, le=1_000_000)
    cached_input_tokens: int | None = Field(default=None, ge=0, le=1_000_000)
    reasoning_tokens: int | None = Field(default=None, ge=0, le=1_000_000)
    cached_audio_input_tokens: int | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_subsets(self):
        for total, subset in ((self.input_tokens, self.cached_input_tokens), (self.output_tokens, self.reasoning_tokens), (self.audio_input_tokens, self.cached_audio_input_tokens)):
            if total is not None and subset is not None and subset > total:
                raise ValueError("Usage subset exceeds total")
        return self