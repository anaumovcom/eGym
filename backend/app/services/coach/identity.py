"""Live speech identity and validation cursors; never rewrite an event's source scope."""

from dataclasses import dataclass, field

from pydantic import Field, StrictBool, StrictInt

from app.schemas.coach import CoachEvent, CoachModel, CoachPhase, CoachScope


class SpeechContext(CoachModel):
    scope: CoachScope | None
    plan_revision: StrictInt = Field(ge=0)
    context_version: StrictInt = Field(ge=0)
    phase: CoachPhase
    blocked: StrictBool

    @property
    def gated(self) -> bool:
        return self.blocked or self.phase in {"disabled", "paused-set", "suspended"} or self.scope is None


def identity(event: CoachEvent) -> dict:
    return {"schemaVersion": 1, "eventId": event.id, "scope": event.scope.model_dump(by_alias=True),
            "planRevision": event.plan_revision, "contextVersion": event.context_version,
            "createdAtMs": event.created_at_ms, "startDeadlineMs": event.start_deadline_ms,
            "factDependencies": list(event.fact_dependencies)}


def matches_identity(value: object, expected: object) -> bool:
    """Known fields only, no coercion (notably bool is not a numeric version)."""
    if isinstance(expected, dict):
        return isinstance(value, dict) and all(k in value and matches_identity(value[k], v)
                                               for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(value, list) and len(value) == len(expected) and all(
            matches_identity(a, b) for a, b in zip(value, expected, strict=True))
    if type(expected) in (int, float):
        return type(value) in (int, float) and value == expected
    return type(value) is type(expected) and value == expected


def same_run(a: CoachScope, b: CoachScope) -> bool:
    return a.user_id == b.user_id and a.run_id == b.run_id


def survives(kind: str, previous: SpeechContext, next_context: SpeechContext, started: bool,
             confirmed_result: bool = False) -> bool:
    a, b = previous.scope, next_context.scope
    if previous.gated or next_context.gated or a is None or b is None or not same_run(a, b):
        return False
    if started:
        return True
    # Plan edits invalidate pending facts, not speech already heard by the user.
    if previous.plan_revision != next_context.plan_revision:
        return False
    path = {"set_persisted": ("active-set", "finalizing-set", "rest"),
            "exercise_finalized": ("active-set", "finalizing-set", "exercise-summary"),
            "workout_finalized": ("workout-summary",)}.get(kind, ())
    if path and previous.phase not in path:
        return False
    if a == b and previous.phase == next_context.phase:
        return True
    if (not confirmed_result or not path or next_context.phase not in path
            or a.exercise_id != b.exercise_id or a.set_ordinal != b.set_ordinal
            or b.scope_epoch < a.scope_epoch):
        return False
    before, after = path.index(previous.phase), path.index(next_context.phase)
    return (after > before or (after == before and next_context.phase in {"exercise-summary", "workout-summary"}
                              and b.scope_epoch > a.scope_epoch))


@dataclass
class WorkState:
    """Mutable, terminal invalidation shared by the task, queue and ACK registry."""

    context: SpeechContext | None = None
    valid: bool = True
    started: bool = False
    confirmed_result: bool = False
    summary_remapped: bool = False
    marks: dict[str, float] = field(default_factory=dict)
    model: str = "unknown"
    connection: str = "unknown"
    lifecycle: str = "pending"
    audible_start_ms: float | None = None
    audible_duration_ms: float = 0

    def transition(self, target: str) -> bool:
        allowed = {
            'pending': {'preparing', 'expired', 'rejected'},
            'preparing': {'ready', 'expired', 'rejected'},
            'ready': {'started', 'expired', 'rejected'},
            'started': {'completed', 'interrupted'},
        }
        if target not in allowed.get(self.lifecycle, set()):
            return False
        self.lifecycle = target
        return True

    def advance(self, kind: str, next_context: SpeechContext) -> None:
        if not self.valid:
            return
        previous = self.context
        if previous is None:
            self.valid = False  # Work admitted without context cannot acquire provenance later.
            return
        exact = previous.scope == next_context.scope and previous.phase == next_context.phase
        remap = not exact and previous.phase == next_context.phase
        if (not survives(kind, previous, next_context, self.started, self.confirmed_result)
                or (not self.started and remap and self.summary_remapped)):
            self.valid = False
        else:
            if remap and not self.started:
                self.summary_remapped = True
            self.context = next_context