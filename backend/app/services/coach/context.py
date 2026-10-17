"""Bounded context assembled by code; no free-form catalog instructions or inferred feelings."""

import re
from dataclasses import asdict, dataclass

from app.schemas.coach import CoachEvent
from app.services.coach.tips import ReviewedTip, select_tip
from app.services.exercise_library import get_imported_exercise

_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
MODES = frozenset({"constant", "eccentric", "isokinetic", "adaptive", "bodyweight", "unloaded", "stretch"})


def identifier(value: object) -> str | None:
    return value if isinstance(value, str) and len(value) <= 100 and _IDENTIFIER.fullmatch(value) else None


@dataclass(frozen=True, slots=True)
class ExplicitFeedback:
    set_id: int
    effort: int | None
    discomfort: int | None
    observed_at_ms: float
    expires_at_ms: float
    source: str = "persisted-explicit-set-feedback"


@dataclass(frozen=True, slots=True)
class CoachContext:
    event: str
    phase: str
    set_ordinal: int | None
    exercise_slug: str | None
    kind: str | None
    variant: str | None
    mode: str | None
    exercise_source: str
    plan_source: str
    feedback: ExplicitFeedback | None = None
    tip: ReviewedTip | None = None
    fact_ids: tuple[str, ...] = ()
    goal: str = "none"
    experience: str = "intermediate"
    profile_source: str = "saved-coach-preferences"
    setup_guidance: tuple[tuple[str, str], ...] = ()

    @property
    def risk(self) -> bool:
        return self.feedback is not None and self.feedback.discomfort is not None and self.feedback.discomfort > 0

    def data(self, *, say_numbers: bool, say_name: bool) -> dict:
        data = asdict(self)
        # Selection may use the identifier privately; do not disclose it to the author on opt-out.
        if not say_name:
            data["exercise_slug"] = data["variant"] = None
        if not say_numbers:
            data["set_ordinal"] = None
        if self.tip:
            # Applicability metadata stays server-side on name opt-out.
            data["tip"] = {"tipId": self.tip.tip_id, "version": self.tip.version,
                           "source": self.tip.source, "review": self.tip.review, "text": self.tip.text}
        if self.feedback:
            data["feedback"] = {"source": self.feedback.source, "explicit": True,
                                "effort": self.feedback.effort if say_numbers else None,
                                "discomfort": self.feedback.discomfort if say_numbers else None,
                                "discomfortReported": self.risk,
                                "observedAtMs": self.feedback.observed_at_ms,
                                "expiresAtMs": self.feedback.expires_at_ms}
        return data


def build_context(event: CoachEvent, declaration: dict, phase: str, *, saved=None,
                  feedback: ExplicitFeedback | None = None) -> CoachContext:
    if saved is not None:
        slug, kind, mode = saved.current.exercise_slug, saved.current.exercise_kind, saved.current.load_mode
        # Only generic machine identity, never a claim of cable/handle equivalence.
        variant = slug
        source, plan = "persisted-result", "persisted-declared-plan"
    else:
        slug, variant = identifier(declaration.get("exerciseSlug")), identifier(declaration.get("variant"))
        kind, mode = event.exercise_kind, declaration.get("controlMode")
        source, plan = "runtime-event-declaration", "declared-client-plan"
    slug = identifier(slug)
    try:
        loaded = get_imported_exercise(slug) if slug else None
    except (OSError, ValueError, TypeError, KeyError):
        loaded = None
    if loaded is None:
        slug = variant = None
    if not isinstance(mode, str) or mode not in MODES or (event.control_mode is not None and event.control_mode != mode):
        mode = None
    tip = select_tip(slug, kind, variant, mode, phase,
                     discomfort=feedback.discomfort if feedback else None)
    guidance = ()
    if phase == "setup" and loaded and variant in {None, slug}:
        # Catalog instructions already shown in exercise details, not certified
        # active-set tips. Never expand this permission into live form correction.
        groups = (
            ("catalog-technique", (*loaded.guide.technique, *loaded.guide.how_to_perform) or loaded.steps),
            ("catalog-avoid", loaded.guide.things_to_avoid),
            ("catalog-setup", loaded.guide.setup),
        )
        # Keep complete bounded instructions: truncation can drop a negation or
        # movement qualifier. Each item must also fit AllowedFact's 200-char cap.
        guidance = tuple((f"{key}-{index}", text) for key, lines in groups
                 for index, line in enumerate(lines[:4], 1)
                 if (text := " ".join(line.split())) and len(text) <= 200)[:12]
    return CoachContext(event.kind, phase, event.scope.set_ordinal, identifier(slug), kind,
                        identifier(variant), mode, source, plan, feedback, tip, setup_guidance=guidance)