"""V0 task routing: which text model, reasoning effort and output budget each kind of line gets.

Classes, not individual tasks: in-set cues must stay fast, rest/setup/summary lines can think longer, and
whole-workout generation (scenario, bible, episode) gets the strongest settings. Budget tiers only ever
make a route cheaper (V0.3), never richer.
"""

from dataclasses import dataclass, replace
from typing import Literal

from app.core.coach_limits import (
    COACH_JUDGE_OUTPUT_TOKENS,
    COACH_MAX_TEXT_OUTPUT_TOKENS,
    COACH_NARRATIVE_OUTPUT_TOKENS,
    COACH_PLAN_OUTPUT_TOKENS,
    COACH_TEXT_OUTPUT_TOKENS,
)
from app.core.config import get_settings
from app.schemas.coach_control import Pricing

TaskClass = Literal["plan", "narrative", "live", "judge"]
TASK_CLASSES: tuple[TaskClass, ...] = ("plan", "narrative", "live", "judge")
# Budget tier (ledger.budget_tier) from which reasoning is forced down to "low".
TIER_LOW_REASONING = 2


@dataclass(frozen=True, slots=True)
class Route:
    task_class: TaskClass
    model: str
    pricing: Pricing
    reasoning_effort: str | None
    max_output_tokens: int
    timeout_s: float

    def __post_init__(self):
        if not COACH_TEXT_OUTPUT_TOKENS // 2 <= self.max_output_tokens <= COACH_MAX_TEXT_OUTPUT_TOKENS:
            raise ValueError("Route output budget out of bounds")
        # Whole-workout generation (plan) may think for up to 40 s; spoken lines stay within 15 s.
        if not 0 < self.timeout_s <= (40 if self.task_class == "plan" else 15):
            raise ValueError("Bounded route timeout required")


def task_class(task: str) -> TaskClass:
    """In-set and paused cues are latency-critical; everything spoken outside effort may think longer."""
    if task.startswith(("plan/", "scenario/", "episode/")):
        return "plan"
    if task.startswith("judge/"):
        return "judge"
    if task.startswith(("active/", "paused")):
        return "live"
    return "narrative"


def strong_pricing() -> Pricing:
    cfg = get_settings()
    return Pricing(version=cfg.coach_text_strong_pricing_version, model=cfg.coach_text_model_strong,
                   input_rate=cfg.coach_text_strong_input_rate, cached_rate=cfg.coach_text_strong_cached_rate,
                   output_rate=cfg.coach_text_strong_output_rate,
                   verified=cfg.coach_text_strong_pricing_verified and cfg.coach_text_pricing_verified,
                   enforceable_bounds=True)


def default_routes(fast: Pricing) -> dict[TaskClass, Route]:
    """Strong model only with verified pricing; otherwise fail closed onto the fast model (never unpriced)."""
    cfg = get_settings()
    strong = strong_pricing()
    if not strong.verified:
        strong = fast
    live_tokens = max(COACH_TEXT_OUTPUT_TOKENS, cfg.coach_text_max_output_tokens)
    return {
        "plan": Route("plan", strong.model, strong, cfg.coach_text_strong_reasoning_effort,
                      COACH_PLAN_OUTPUT_TOKENS, 40),
        "narrative": Route("narrative", strong.model, strong, cfg.coach_text_strong_reasoning_effort,
                           COACH_NARRATIVE_OUTPUT_TOKENS, 12),
        "live": Route("live", fast.model, fast, cfg.coach_text_reasoning_effort, live_tokens, 8),
        "judge": Route("judge", fast.model, fast, "low", COACH_JUDGE_OUTPUT_TOKENS, 6),
    }


def degrade(route: Route, tier: int) -> Route:
    """Lower tiers keep the same model (priced already) but stop paying for long reasoning."""
    if tier >= TIER_LOW_REASONING and route.reasoning_effort not in {None, "none", "low"}:
        return replace(route, reasoning_effort="low")
    return route
