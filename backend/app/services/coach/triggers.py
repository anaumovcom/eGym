"""T01–T66 registry. Missing or unsupported sources produce skipped reasons, never synthetic observations."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Source = Literal["LOCAL", "LIVE", "FACT", "UI"]
Intent = Literal["motivation", "humor", "factual-feedback", "general-tip", "summary"]

# Data the application cannot currently prove. A trigger depending on them is always skipped.
UNSUPPORTED_SOURCES: dict[str, str] = {
    "rep.start": "no_rep_start_source",
    "tempo.validated": "tempo_metric_policy_unverified",
    "mechanics.phase": "unknown_movement_mechanics",
    "history.personal_best": "no_personal_best_detector",
    "schedule.next": "no_workout_schedule",
    "workout.highlight": "no_workout_achievement_detector",
    "circuit.round": "no_circuit_round_source",
}


@dataclass(frozen=True, slots=True)
class TriggerSpec:
    id: str
    family: str
    sources: tuple[Source, ...]
    group: str | None
    scope: str
    max_per_scope: int | None
    window_ms: int | None
    intents: tuple[Intent, ...]
    requires: tuple[str, ...]
    replaces: tuple[str, ...] = ()
    merge_into: tuple[str, ...] = ()

    @property
    def live(self) -> bool:
        return "LIVE" in self.sources

    @property
    def deterministic(self) -> bool:
        return not self.live


@dataclass(frozen=True, slots=True)
class Eligibility:
    trigger_id: str
    ok: bool
    reason: str | None = None


M, H, F, G, S = "motivation", "humor", "factual-feedback", "general-tip", "summary"


def _t(id_, family, sources, group, scope, limit, window, intents, requires, replaces=(), merge_into=()):
    return TriggerSpec(id_, family, tuple(sources.split("/")), group, scope, limit, window, intents, requires,
                       replaces, merge_into)


_ROWS = (
    _t("T01", "intro", "LIVE", "opening", "workout", 1, 20_000, (M, H), ("workout.real", "setup.ready")),
    _t("T02", "intro", "LIVE", "opening", "workout", 1, 20_000, (M,),
       ("workout.real", "setup.ready", "history.complete", "history.gap_14d"), ("T01",)),
    _t("T03", "intro", "LIVE", "opening", "workout", 1, 20_000, (M,),
       ("workout.real", "setup.ready", "history.empty_confirmed"), ("T01",)),
    _t("T04", "intro", "LIVE", "exercise-intro", "exercise", 1, 30_000, (G, M), ("exercise.metadata",)),
    _t("T05", "intro", "LIVE", "exercise-intro", "exercise", 1, 30_000, (M, H),
       ("exercise.metadata", "history.exercise"), ("T04",)),
    _t("T06", "intro", "LOCAL/LIVE", "set-intro", "set", 1, 10_000, (M,), ("plan.warmup",)),
    _t("T07", "intro", "LIVE", None, "exercise", 1, 10_000, (M,), ("plan.first_working", "set.warmup_done")),
    _t("T08", "intro", "FACT", None, "plan", 1, 10_000, (F,), ("config.weight_confirmed",)),
    _t("T09", "intro", "LIVE", None, "mode", 1, 15_000, (G,), ("config.mode_changed",)),
    _t("T10", "intro", "LOCAL", None, "setup", 1, 5_000, (F,), ("calibration.applied", "setup.ready")),
    _t("T11", "intro", "LIVE", "exercise-intro", "exercise", 1, 30_000, (M, G),
       ("exercise.metadata", "plan.muscle_switch"), ("T04",)),
    _t("T12", "intro", "LOCAL/FACT", None, "round", 1, 5_000, (F,), ("circuit.round",)),
    _t("T13", "set", "LOCAL", None, "set", 1, 1_500, (M,), ("set.active",)),
    _t("T14", "set", "LOCAL", None, "rep", 1, None, (F,), ("rep.confirmed",)),
    _t("T15", "set", "LIVE", "milestone", "set", 1, 4_000, (M, H), ("set.active", "rep.confirmed")),
    _t("T16", "set", "LOCAL/FACT", "milestone", "set", 1, 3_000, (F,), ("rep.confirmed", "target.exact")),
    _t("T17", "set", "LOCAL", "milestone", "set", 1, 1_500, (F,), ("rep.confirmed", "target.exact")),
    _t("T18", "set", "LOCAL", "milestone", "set", 1, 1_000, (F,), ("rep.start", "target.exact")),
    _t("T19", "set", "LIVE", None, "set", 1, 20_000, (M,), ("tempo.validated",)),
    _t("T20", "set", "FACT/LIVE", None, "set", 1, 20_000, (F,), ("tempo.validated",)),
    _t("T21", "set", "LIVE", "set-support", "set", None, 6_000, (M, H), ("set.active", "rep.confirmed")),
    _t("T22", "set", "LOCAL", None, "set", None, 1_000, (M,), ("mechanics.phase",)),
    _t("T23", "set", "LOCAL/FACT", None, "set", 1, 2_000, (F,), ("rep.confirmed", "partial.previous")),
    _t("T24", "set", "LOCAL", None, "episode", 1, 2_000, (F,), ("set.paused",)),
    _t("T25", "set", "LOCAL", None, "episode", 1, 2_000, (F,), ("set.resumed",)),
    _t("T26", "set", "LOCAL/FACT", None, "set", 1, 2_000, (F,), ("target.reached",)),
    _t("T27", "timed", "LOCAL", None, "set", 1, 1_500, (M,), ("timer.running",)),
    _t("T28", "timed", "LOCAL/FACT", None, "set", 1, 3_000, (F,), ("timer.running", "timer.half")),
    _t("T29", "timed", "LOCAL", None, "set", 1, 2_000, (F,), ("timer.running", "timer.remaining")),
    _t("T30", "timed", "LOCAL", None, "second", 1, 900, (F,), ("timer.running", "timer.remaining")),
    _t("T31", "timed", "LIVE", "set-support", "set", None, 6_000, (M,), ("timer.running",)),
    _t("T32", "timed", "LIVE", None, "step", 1, 10_000, (G, M), ("stretch.metadata",)),
    _t("T33", "timed", "LOCAL", None, "rep", 1, None, (F,), ("bodyweight.input",)),
    _t("T34", "timed", "FACT/LIVE", None, "step", 1, 8_000, (F, M), ("group.next",)),
    _t("T35", "result", "LOCAL", None, "set", 1, 2_000, (F,), ("set.closed",)),
    _t("T36", "result", "LIVE/FACT", "set-feedback", "set", 1, 20_000, (F, M, H), ("save.ack", "result.full")),
    _t("T37", "result", "LIVE/FACT", "set-feedback", "set", 1, 20_000, (F, M),
       ("save.ack", "result.partial"), ("T36",)),
    _t("T38", "result", "LOCAL", "set-feedback", "set", 1, 5_000, (F,), ("save.ack", "result.skipped"), ("T36",)),
    _t("T39", "result", "FACT/LIVE", "set-feedback", "set", 1, 20_000, (F,),
       ("save.ack", "history.comparable", "comparison.improved"), ("T36",)),
    _t("T40", "result", "FACT/LIVE", "set-feedback", "set", 1, 20_000, (F,),
       ("save.ack", "history.comparable", "comparison.equal"), ("T36",)),
    _t("T41", "result", "LIVE/FACT", "set-feedback", "set", 1, 20_000, (F,),
       ("save.ack", "history.comparable", "comparison.lower", "analysis.opt_in"), ("T36",)),
    _t("T42", "result", "FACT/LIVE", "set-feedback", "exercise", 1, 20_000, (F,), ("save.ack", "today.best")),
    _t("T43", "result", "FACT/LIVE", "set-feedback", "achievement", 1, 20_000, (F,),
       ("save.ack", "history.personal_best")),
    _t("T44", "result", "FACT/LIVE", "set-feedback", "set", 1, 20_000, (F,), ("save.ack", "tempo.validated")),
    _t("T45", "rest", "LIVE", "set-feedback", "rest", 1, 20_000, (F, M, H), ("rest.entered", "save.ack")),
    _t("T46", "rest", "LIVE", "rest-extra", "slot", 1, 15_000, (H, M),
       ("rest.entered", "rest.remaining_35s", "utterance.completed")),
    _t("T47", "rest", "LIVE", "rest-extra", "exercise", 1, 15_000, (G,),
       ("rest.entered", "tips.enabled", "guide.tip"), ("T46",)),
    _t("T48", "rest", "LIVE", "rest-extra", "motif", 1, 15_000, (H,), ("rest.entered", "motif.completed"), ("T46",)),
    _t("T49", "rest", "LOCAL/FACT", None, "exercise", 1, 5_000, (F,), ("plan.last_set",)),
    _t("T50", "rest", "LOCAL", None, "rest", 1, 1_500, (F,), ("rest.timer",)),
    _t("T51", "rest", "LOCAL", None, "rest", 1, 2_000, (F,), ("rest.ready",)),
    _t("T52", "rest", "UI/LOCAL", None, "episode", 1, 2_000, (F,), ("rest.extended",)),
    _t("T53", "rest", "UI/LOCAL", None, "episode", 1, 2_000, (F,), ("rest.paused",)),
    _t("T54", "rest", "LIVE", "exercise-intro", "exercise", 1, 20_000, (M, G), ("exercise.next",)),
    _t("T55", "summary", "LIVE/FACT", "exercise-end", "exercise", 1, 30_000, (S,),
       ("exercise.finalized", "result.full")),
    _t("T56", "summary", "LIVE/FACT", "exercise-end", "exercise", 1, 30_000, (S,),
       ("exercise.finalized", "result.partial"), ("T55",)),
    _t("T57", "summary", "LOCAL/FACT", None, "round", 1, 5_000, (F,), ("circuit.round",)),
    _t("T58", "summary", "LIVE/FACT", "workout-end", "workout", 1, 60_000, (S,),
       ("workout.finalized", "result.full")),
    _t("T59", "summary", "LIVE/FACT", "workout-end", "workout", 1, 60_000, (S,),
       ("workout.finalized", "result.partial"), ("T58",)),
    _t("T60", "summary", "FACT", "workout-end", "workout", 1, None, (S,), ("schedule.next",), (), ("T58", "T59")),
    _t("T61", "summary", "FACT", "workout-end", "workout", 1, None, (S,), ("workout.highlight",), (), ("T58", "T59")),
    _t("T62", "service", "UI", None, "episode", 1, None, (F,), ("service.error",)),
    _t("T63", "service", "UI", None, "recovery", 1, None, (F,), ("service.recovered",)),
    _t("T64", "service", "UI", None, "episode", 1, None, (F,), ("source.stale",)),
    _t("T65", "service", "LOCAL", "safety", "latch", 1, 2_000, (F,), ("safety.latch",)),
    _t("T66", "service", "LOCAL", "safety", "latch", 1, 2_000, (F,), ("pain.latch",)),
)

TRIGGERS: dict[str, TriggerSpec] = {row.id: row for row in _ROWS}
assert list(TRIGGERS) == [f"T{i:02d}" for i in range(1, 67)]


def evaluate(trigger_id: str, observed: Iterable[str]) -> Eligibility:
    spec = TRIGGERS.get(trigger_id)
    if spec is None:
        return Eligibility(trigger_id, False, "unknown_trigger")
    present = frozenset(observed)
    for key in spec.requires:
        if key in UNSUPPORTED_SOURCES:
            return Eligibility(trigger_id, False, f"unsupported:{UNSUPPORTED_SOURCES[key]}")
    missing = [key for key in spec.requires if key not in present]
    if missing:
        return Eligibility(trigger_id, False, f"no_source:{missing[0]}")
    return Eligibility(trigger_id, True)


def unsupported_triggers() -> dict[str, str]:
    return {spec.id: reason.split(":", 1)[1] for spec in _ROWS
            if (reason := evaluate(spec.id, spec.requires).reason) and reason.startswith("unsupported:")}
