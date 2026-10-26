"""E10 live coach: browser event → server facts → Director → text author → voice → tagged PCM frames.

The browser is never a fact source for results: saved sets and summaries are read from the DB by owner.
One pipeline per run (paid single-flight); completion queue is bounded and priority ordered.
"""

import asyncio
import contextlib
import hashlib
import logging
import math
import secrets
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.coach import CoachEvent, CoachScope
from app.schemas.coach_control import CoachPreferences
from app.services.coach import (
    counters,
    episode,
    expressive,
    history,
    journal,
    ledger,
    progress,
    scenario,
    security,
    telemetry,
)
from app.services.coach.completion import LocalCompletion, additional_package, duplicate_local, useful_addition
from app.services.coach.context import CoachContext, build_context
from app.services.coach.director import Candidate, Director
from app.services.coach.facts import (
    AllowedFact,
    Comparison,
    FactPackage,
    memory_key,
    saved_set_facts,
    spoken_quantity,
    target_fact,
    weight_fact,
)
from app.services.coach.identity import SpeechContext, WorkState, identity, matches_identity, same_run
from app.services.coach.luna import LunaTextAdapter, TextAuthor, text_pricing
from app.services.coach.memory import CoachMemory, CrossWorkoutStore, RunMemoryStore, Utterance
from app.services.coach.mood import Mood, MoodTracker, classify
from app.services.coach.personas import persona
from app.services.coach.prompts import DEFAULT_FORBIDDEN, AuthorRequest
from app.services.coach.routing import default_routes
from app.services.coach.speech_actions import SPEECH_ACTIONS, speech_action
from app.services.coach.triggers import TRIGGERS
from app.services.coach.voice import (
    Delivery,
    FishVoiceAdapter,
    PcmFramer,
    RealtimeVoiceAdapter,
    TtsVoiceAdapter,
    VoiceOutcome,
    VoiceStreamer,
    decode_frame,
    encode_frame,
    select_delivery,
    situational_delivery_enabled,
    voice_pricing,
    websocket_connect,
)

logger = logging.getLogger("coach.live")
SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]

MAX_SEEN = 1024
MAX_PENDING_ACKS = 32
MAX_QUEUED = 4
REST_EXTRA_MIN_MS = 35_000
SUMMARY_TRIGGERS = {"T55", "T56", "T58", "T59"}
# Saved-set trigger → P2 task. T38 (skipped) stays a local clip; T41 needs analysis opt-in (not offered).
RESULT_TASKS = {"T36": "rest/full-feedback", "T37": "rest/partial-feedback", "T39": "rest/comparison",
                "T40": "rest/comparison", "T43": "rest/record"}
RESULT_INTENTS = {"T36": ("factual-feedback", "motivation", "humor"), "T37": ("factual-feedback", "motivation"),
                  "T39": ("factual-feedback",), "T40": ("factual-feedback",), "T43": ("factual-feedback", "motivation")}
GAP_SCALE = {"short": 0.7, "normal": 1.0, "long": 1.6}
WORDS_SCALE = {"short": 0.6, "normal": 1.0, "detailed": 1.25}
NAME_FACTS = frozenset({"exercise", "next-exercise", "exercise-names"})
MAX_TELEMETRY_MS = 86_400_000
# V0.3: budget tier is read from the ledger at most this often (one cheap SQLite read per window).
BUDGET_TIER_TTL_MS = 2_000
# From tier 3 only results/summaries are authored live; tier 4 keeps only the reserved summary.
TIER_RESULT_ONLY, TIER_SUMMARY_ONLY = 3, 4
TIER_SHORT_REST, TIER_SHORT_REST_WORDS = 2, 25
# V1 scenarios: one proposal plus up to three regenerations; a job waits this long for the speech pipeline.
SCENARIO_PROPOSALS = 4
SCENARIO_IDLE_WAIT_S = 20.0
SCENARIO_WORDS = 30
# V8: prepared story lines (exercise intros, act starts, the boss, the last-set cheer) built while the user prepares.
PREBUILD_START_DELAY_S = 3.0
PREBUILD_IDLE_WAIT_S = 60.0
PREBUILD_VALID_MS = 2 * 3_600_000
PREBUILD_MAX_LINES = 12
OPENING_KEY = "T01:opening"
SPEECH_TIMING_STAGES = ("receive", "textStart", "textEnd", "firstPcm", "speechEnd", "ackStart", "ackEnd", "ackCancel")
PROGRESS_FACTS = frozenset({"set-position", "sets-left", "exercise-position", "plan-sets", "planned-sets"})
# In-set moments (T21 set support): claim, per-set topic, intents. The browser only says which moment it is;
# the claims are fixed server text, and the Director paces them by the set's real elapsed time.
SET_MOMENTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "start": ("Подход только начался, первые повторения засчитаны", "set-start", ("motivation", "general-tip")),
    "partial": ("Последнее движение не засчитано",
                "set-range", ("general-tip", "motivation")),
    "half": ("Половина подхода уже позади", "set-support", ("motivation", "humor")),
    "finish": ("Идут последние повторения подхода", "set-finish", ("motivation",)),
    "stall": ("В подходе пауза: новое повторение пока не засчитано", "set-stall", ("motivation",)),
    "support": ("Подход продолжается", "set-advice", ("general-tip",)),
    # V2 rep tracker moments; their measured facts come from telemetry.moment_facts.
    "velocity_drop": ("Подход продолжается", "set-velocity", ("motivation",)),
    "velocity_drop_hard": ("Идут последние, самые тяжёлые повторения подхода", "set-velocity", ("motivation",)),
    "tempo": ("Подход продолжается", "set-tempo", ("general-tip", "motivation")),
}
SET_MOMENT_KINDS = {"set_activated": "start", "rep_completed": "partial", "rep_milestone": "half",
                    "last_rep_pending": "finish"}
# V7.1: lines with time to think get variants and a judge (never in-set cues or verbatim tips/catalog).
# Live runs 26.10.2026: a single rest result is voiced 3–4 s after the set, with variants 8–12 s; the quick reaction
# felt more alive at the same quality. Variants stay for prepared story lines, records and the workout summary.
VARIANT_TASKS = frozenset({"setup/opening", "setup/act", "setup/boss", "rest/record", "summary/workout"})
TIER_NO_VARIANTS = 1
# Live run 26.10.2026: every variant adds ~2.5 s of output. A record the listener waits for gets two; prepared or
# unhurried lines (opening, acts, boss, the workout summary) keep three.
THREE_VARIANT_TASKS = frozenset({"setup/opening", "setup/act", "setup/boss", "summary/workout"})
# V10: the co-host speaks at most once per this many lines, never in-set; voice pairs for the two library voices.
CO_HOST_EVERY = 4
CO_HOST_PHASES = frozenset({"rest", "summary", "setup"})
MELLSTROY, EKATERINA = "0a690dbeb3984a9f88cd39353880775f", "6d23d3209d6849e0b24ddae6f734afe9"
# V7.2: a story motif returns no sooner than this many exercises after its last use.
MOTIF_GAP_EXERCISES = 2
# V5 #20: in-set moments that carry a new observation; the rest are generic cheers.
NOVEL_MOMENTS = frozenset({"partial", "velocity_drop", "velocity_drop_hard", "tempo", "stall", "finish"})
# Timed sets (the browser follows the on-screen clock): same moments, claims about time instead of reps.
TIMED_SET_MOMENTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "start": ("Таймер подхода запущен, работа началась", "set-start", ("motivation", "general-tip")),
    "half": ("Половина времени подхода уже позади", "set-support", ("motivation", "humor")),
    "finish": ("До конца подхода остаются последние секунды", "set-finish", ("motivation",)),
    "support": ("Работа по таймеру продолжается", "set-advice", ("general-tip",)),
}


@dataclass(frozen=True)
class PrebuiltLine:
    """A validated story line with its synthesized PCM, played instead of a live request when its moment comes."""
    key: str
    text: str
    used_fact_ids: tuple[str, ...]
    pcm: bytes
    source: str
    intent: str | None
    mood: str | None
    exercise_name: str | None


class _FactsChangedError(Exception):
    """Internal factual invalidation, not task cancellation or provider failure."""


@dataclass(frozen=True)
class Opportunity:
    event_id: str
    candidate: Candidate
    task: str
    intents: tuple[str, ...]
    scope: CoachScope
    package: FactPackage | None = None
    exercise_id: str | None = None
    event: CoachEvent | None = None
    received_ms: float | None = None
    deadline_ms: float | None = None  # Server monotonic, NOT the browser's absolute deadline.
    state: WorkState = field(default_factory=WorkState, compare=False)
    source_refs: tuple[tuple[str, int], ...] = ()
    source_context: tuple[tuple[str, object], ...] = ()
    local_completion: LocalCompletion | None = None
    coach_context: CoachContext | None = None

    @property
    def key(self) -> str:
        if self.candidate.trigger_id == "T21":
            # Code-selected topics already include run/exercise/set and the support slot.
            # Hash to keep the ledger opportunity bounded, including its run prefix;
            # event IDs must never turn a repeated topic into a new paid attempt.
            return f"T21:{hashlib.sha256(self.candidate.topic_key.encode()).hexdigest()}"
        return f"{self.candidate.trigger_id}:{self.candidate.semantic_key}"


@dataclass
class LiveStats:
    reasons: Counter = field(default_factory=Counter)
    triggers: Counter = field(default_factory=Counter)
    spoken: int = 0
    opportunities: Counter = field(default_factory=Counter)
    first_audio_ms: deque = field(default_factory=lambda: deque(maxlen=32))
    latencies: dict[str, deque] = field(default_factory=dict)
    budget_tier: int = 0

    def measure(self, metric: str, op: Opportunity, elapsed: float) -> None:
        if not math.isfinite(elapsed):
            return
        key = f"{metric}:{op.candidate.trigger_id}:{op.state.model}:{op.state.connection}"
        if key not in self.latencies:
            if len(self.latencies) >= 256:
                return
            self.latencies[key] = deque(maxlen=128)
        self.latencies[key].append(round(min(MAX_TELEMETRY_MS, max(0, elapsed)), 2))

    def as_dict(self) -> dict:
        audio = sorted(self.first_audio_ms)
        return {"spoken": self.spoken, "reasons": dict(self.reasons), "triggers": dict(self.triggers),
                "budgetTier": self.budget_tier,
            "opportunities": dict(self.opportunities),
                "firstAudioMs": {"count": len(audio), "median": audio[len(audio) // 2] if audio else None,
                     "max": audio[-1] if audio else None}, "firstAudioMsLabel": "voice-only",
            "latencies": {key: {"count": len(values), "p50": sorted(values)[math.ceil(len(values) * .5) - 1],
                         "p95": sorted(values)[math.ceil(len(values) * .95) - 1]}
                      for key, values in self.latencies.items()}}


def _bounded_ms(value: object, upper: float) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= upper else None


def _ref(refs: object, name: str) -> int | None:
    value = refs.get(name) if isinstance(refs, dict) else None
    return value if type(value) is int and 0 < value < 2**53 else None


def _count(context: dict, name: str, upper: int = 50) -> int | None:
    value = context.get(name)
    return value if type(value) is int and 0 < value <= upper else None


def _name(context: dict, name: str) -> str | None:
    value = context.get(name)
    return history.speakable_name(value if isinstance(value, str) and len(value) <= 120 else None)


def _kg(context: dict, name: str) -> float | None:
    value = context.get(name)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def progress_facts(ordinal: int | None, total: int | None, *, next_exercise: str | None = None,
                   **common) -> list[AllowedFact]:
    """Where the user is inside the exercise: set N of M, sets left, what comes next."""
    found = []
    if ordinal and total and 0 < ordinal <= total <= 50:
        found.append(AllowedFact("set-position", f"Подход {ordinal} из {total}", "confirmed", f"{ordinal}/{total}",
                                 numbers=(ordinal, total), **common))
        left = total - ordinal
        found.append(AllowedFact("sets-left", f"Осталось {spoken_quantity(left, 'sets')}", "confirmed", left, "sets",
                                 numbers=(left,), **common) if left else
                     AllowedFact("sets-left", "Это был последний подход упражнения", "confirmed", 0, **common))
    if next_exercise:
        found.append(AllowedFact("next-exercise", f"Дальше по плану — {next_exercise}", "confirmed", next_exercise,
                                 **common))
    return found


class LiveCoach:
    def __init__(self, sessions: Callable[[], Session], *, run_id: str, owner: str, generation: int, user_id: str,
                 settings: CoachPreferences, author: TextAuthor | None, voice: VoiceStreamer | None,
                 send_json: SendJson, send_bytes: SendBytes, now_ms: Callable[[], float] = lambda: time.time() * 1000,
                 monotonic_ms: Callable[[], float] = lambda: time.monotonic() * 1000,
                 feedback_ttl_ms: float = 300_000, scope_run_id: str | None = None):
        self.sessions, self.run_id, self.owner, self.generation = sessions, run_id, owner, generation
        # Billing, leases and retained memory use run_id; source identities remain runtime-scoped.
        self.scope_run_id = run_id if scope_run_id is None else scope_run_id
        self.user_id, self.settings, self.author, self.voice = user_id, settings, author, voice
        self.send_json, self.send_bytes, self.now_ms = send_json, send_bytes, now_ms
        self.monotonic_ms = monotonic_ms
        self.feedback_ttl_ms = min(300_000, max(0, feedback_ttl_ms))
        self.memory = CoachMemory(enabled=settings.memory_enabled)
        self.cross_preferences: dict[str, str] = {}
        self.memory_epoch = 0
        self.line_metadata: dict[str, dict] = {}
        self.director = Director(settings.density, self.memory, gap_scale=GAP_SCALE[settings.pause_gap],
                                 words_scale=WORDS_SCALE[settings.verbosity])
        self.task: asyncio.Task | None = None
        self.queue: list[Opportunity] = []
        self.opportunities: dict[str, Opportunity] = {}
        self.seen: set[str] = set()
        self.acks: dict[str, tuple[Opportunity, str, tuple[str, ...]]] = {}
        self.terminal: deque[str] = deque(maxlen=32)
        self.context: SpeechContext | None = None
        self.contexts: deque[SpeechContext] = deque(maxlen=1024)
        self.active_op: Opportunity | None = None
        self.stats = LiveStats()
        self.closed = False
        self.local_observations: deque[float] = deque(maxlen=128)
        self._tier_cache: tuple[float, int] | None = None
        # V1: the chosen story (card + validated bible), restored from the DB after a reconnect.
        self.scenario_card: dict | None = None
        self.scenario_bible: dict | None = None
        self.scenario_cards: list[dict] = []
        self.scenario_plan: tuple[scenario.PlanExercise, ...] | None = None
        self.scenario_proposals = 0
        self.scenario_shown: list[str] = []
        self.scenario_job: asyncio.Task | None = None
        # V4: per saved set, whether it was a record / a steady set (stable across revalidation re-plans).
        self.record_sets: dict[int, bool] = {}
        self.steady_sets: dict[int, bool] = {}
        self.counter_state: list[dict] = []
        self.moods = MoodTracker()
        self.voice_history = expressive.VoiceHistory()
        self.motif_uses: dict[str, int] = {}
        self.why_done: set[str] = set()
        self.lines_since_co_host = CO_HOST_EVERY
        self.prebuilt: dict[str, PrebuiltLine] = {}
        self.workout_started = False
        self.episode_job: asyncio.Task | None = None
        self.prebuild_job: asyncio.Task | None = None
        self._prebuild_items: set[asyncio.Task] = set()
        self._sent_counters: list[dict] = []
        self._load_scenario()

    def budget_tier(self) -> int:
        """V0.3 degradation tier of this run's ledger; an unreadable ledger never degrades by itself."""
        now = self.monotonic_ms()
        if self._tier_cache is not None and now - self._tier_cache[0] < BUDGET_TIER_TTL_MS:
            self.stats.budget_tier = self._tier_cache[1]
            return self._tier_cache[1]
        try:
            with self.sessions() as db:
                tier = ledger.run_budget(db, self.run_id)["tier"]
        except HTTPException:
            tier = 0
        self._tier_cache = (now, tier)
        self.stats.budget_tier = tier
        return tier

    @property
    def queued(self) -> Opportunity | None:
        return self.queue[0] if self.queue else None

    def _transition(self, op: Opportunity, target: str) -> None:
        if op.state.transition(target):
            self.stats.opportunities[target] += 1

    def _end_state(self, op: Opportunity, reason: str) -> None:
        self._transition(op, 'interrupted' if op.state.started else 'expired' if reason == 'expired' else 'rejected')
        if op.state.lifecycle in {'interrupted', 'expired', 'rejected'}:
            op.state.valid = False

    @staticmethod
    def _priority(op: Opportunity) -> int:
        return 3 if op.event and op.event.kind == 'workout_finalized' else 2 if (
            op.event and op.event.kind == 'exercise_finalized') else 1

    async def _enqueue(self, op: Opportunity) -> None:
        await self._expire_queue()
        if len(self.queue) >= MAX_QUEUED:
            lowest = min(self.queue, key=lambda item: (self._priority(item), -(item.received_ms or 0)))
            if self._priority(op) <= self._priority(lowest):
                await self._decision(op.event_id, op.candidate.trigger_id, 'silence', 'queue_full')
                return
            self.queue.remove(lowest)
            await self._decision(lowest.event_id, lowest.candidate.trigger_id, 'silence', 'queue_preempted')
        self.queue.append(op)
        self.queue.sort(key=lambda item: (-self._priority(item),
                 self.memory.topic_blocked(item.candidate.topic_key),
                 -(item.received_ms or 0), item.deadline_ms or float("inf")))

    async def _expire_queue(self) -> None:
        for op in list(self.queue):
            if not self._current(op):
                self.queue.remove(op)
                reason = 'expired' if op.deadline_ms is not None and self.monotonic_ms() > op.deadline_ms else 'scope_changed'
                await self._decision(op.event_id, op.candidate.trigger_id, 'silence', reason)

    async def _drain(self) -> None:
        await self._expire_queue()
        while self.queue and not self.closed and (self.task is None or self.task.done()):
            await self._admit_and_start(self.queue.pop(0))

    def _duration(self, message: dict, op: Opportunity, *, interrupted: bool = False) -> None:
        if not op.state.started:
            return
        duration = _bounded_ms(message.get('durationMs'), 60_000)
        if interrupted:
            duration = min(duration if duration is not None else op.state.audible_duration_ms,
                           max(0, self.monotonic_ms() - op.state.marks['ackStart']))
        if duration is not None:
            op.state.audible_duration_ms = duration
            self.director.update_audible(message['generationId'], duration)
            self.memory.update_duration(message['generationId'], duration)

    # ---------- inbound ----------

    async def handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "event":
            await self._event(message)
        elif kind == "localPlayback":
            self._local_playback(message)
        elif kind == "context":
            await self._context(message)
        elif kind == "playback_started":
            self._started(message)
        elif kind == "playback_completed":
            entry = self._ack(message)
            if entry is not None and entry[0].state.started:
                gid = message["generationId"]
                self._duration(message, entry[0])
                self._transition(entry[0], 'completed')
                self.memory.note_completed(gid)
                self._mark(entry[0], "ackEnd")
                self._finish(gid)
        elif kind == "playback_failed":
            entry = self._ack(message, check_current=False)
            if entry is not None:
                self._duration(message, entry[0], interrupted=True)
                self._end_state(entry[0], 'playback_failed')
                self.memory.note_interrupted(message['generationId'])
                entry[0].state.valid = False
                self._mark(entry[0], "ackCancel")
                self._finish(message["generationId"])
                self._note("playback_failed")
        elif kind == "cancel":
            await self.cancel("cancelled")
        elif kind == "safety":
            latched = message.get("latched") is True
            self.director.latch_safety(latched)
            if latched:
                await self.cancel("safety")
        elif kind == "ping":
            await self._expire_queue()
            await self.send_json({"type": "pong", "stats": self.stats.as_dict()})
        elif kind in {"scenario_propose", "scenario_select", "scenario_skip"}:
            await self._scenario_message(kind, message)
        else:
            await self.send_json({"type": "error", "reason": "unknown_message"})

    def _local_playback(self, message: dict) -> None:
        # Observation only: no fact, identity, free text, or paid generation path.
        if set(message) != {"type", "kind", "action", "durationMs"} or self.context is None or self.context.blocked:
            return
        local_kind, action = message["kind"], message["action"]
        pairs = {"count": {"count"}, "cue": {"orient", "support", "result", "summary", "safety"}}
        if not isinstance(local_kind, str) or not isinstance(action, str) or action not in pairs.get(local_kind, set()):
            return
        duration = _bounded_ms(message["durationMs"], 60_000)
        now = self.now_ms()
        if duration is None or duration <= 0:
            return
        if len(self.local_observations) == 128 and now - self.local_observations[0] < 60_000:
            return
        self.local_observations.append(now)
        self.director.note_local_playback(now, duration, content=action not in {"count", "safety"})

    async def _context(self, message: dict) -> None:
        try:
            next_context = SpeechContext.model_validate({k: v for k, v in message.items() if k != "type"})
        except ValidationError:
            await self._reject(None, "invalid_context")
            return
        if next_context.scope is not None and (next_context.scope.user_id != self.user_id
                                               or next_context.scope.run_id != self.scope_run_id):
            await self._reject(None, "owner_mismatch")
            return
        previous = self.context
        if previous is not None:
            if next_context == previous:
                return  # Idempotent resend, not a new transition.
            if (next_context.context_version <= previous.context_version
                    or next_context.plan_revision < previous.plan_revision):
                await self._reject(None, "context_reordered")
                return
        self.context = next_context
        self.contexts.append(next_context)
        ops = [entry[0] for entry in self.acks.values()]
        ops += [op for op in [self.active_op, *self.queue] if op is not None]
        # One opportunity may be both active and waiting for its playback ACK.
        unique = {id(op): op for op in ops}
        for op in unique.values():
            op.state.advance(op.event.kind if op.event else "", next_context)
        await self._expire_queue()
        for gid, (op, _, _) in list(self.acks.items()):
            if not op.state.valid:
                self._mark(op, "ackCancel")
                self._finish(gid)
        if self.active_op is not None and not self.active_op.state.valid:
            await self._cancel_task("scope_changed")

    def _event_state(self, event: CoachEvent, *, confirmed_result: bool = False) -> WorkState:
        state = WorkState(confirmed_result=confirmed_result)
        if self.context is None:
            return state  # Legacy direct callers; production sends context before events.
        origin = next((c for c in self.contexts if c.context_version == event.context_version
                       and c.plan_revision == event.plan_revision), None)
        if origin is None or origin.scope is None:
            state.valid = False
            return state
        scope_matches = event.scope == origin.scope or (
            event.kind == "workout_finalized" and event.scope.exercise_id is None
            and event.scope.set_ordinal is None and same_run(event.scope, origin.scope)
            and event.scope.scope_epoch == origin.scope.scope_epoch)
        capture_phases = {
            "set_persisted": {"active-set", "finalizing-set"},
            "exercise_finalized": {"active-set", "finalizing-set", "exercise-summary"},
            "workout_finalized": {"workout-summary"},
        }
        # Keep the authoritative origin as the cursor; workout-only null fields
        # belong to the event identity, not a fabricated runtime transition.
        state.valid = (scope_matches and not origin.gated and origin.phase == event.phase
                       and event.phase in capture_phases.get(event.kind, {event.phase}))
        state.context = origin
        for context in self.contexts:
            if context.context_version >= origin.context_version:
                state.advance(event.kind, context)
        return state

    def _current(self, op: Opportunity) -> bool:
        task = asyncio.current_task()
        return (not self.closed and op.state.valid and not (task is not None and task.cancelling())
                and (op.state.started or op.deadline_ms is None or self.monotonic_ms() <= op.deadline_ms))

    def _mark(self, op: Opportunity, stage: str) -> None:
        if stage in op.state.marks:
            return
        now = op.received_ms if stage == "receive" and op.received_ms is not None else self.monotonic_ms()
        op.state.marks[stage] = now
        if op.received_ms is not None:
            self.stats.measure(stage, op, now - op.received_ms)
        if stage == "textEnd" and "textStart" in op.state.marks:
            self.stats.measure("textDuration", op, now - op.state.marks["textStart"])

    def _voice_state(self, op: Opportunity, voice: VoiceOutcome) -> None:
        op.state.connection = voice.connection_class
        if voice.model != "unknown":
            op.state.model = f"{str(getattr(self.author, 'model', 'unknown'))[:96]}/{voice.model}"

    def _speech_metadata(self, op: Opportunity, voice: VoiceOutcome) -> dict:
        # Only bounded durations from this server's monotonic receipt clock cross
        # the wire. Never serialize arbitrary marks, absolute clocks or provider data.
        timings = {}
        if op.received_ms is not None:
            for stage in SPEECH_TIMING_STAGES:
                if stage in op.state.marks:
                    elapsed = op.state.marks[stage] - op.received_ms
                    if math.isfinite(elapsed):
                        timings[stage] = round(min(MAX_TELEMETRY_MS, max(0, elapsed)), 2)
        if "textStart" in op.state.marks and "textEnd" in op.state.marks:
            elapsed = op.state.marks["textEnd"] - op.state.marks["textStart"]
            if math.isfinite(elapsed):
                timings["textDuration"] = round(min(MAX_TELEMETRY_MS, max(0, elapsed)), 2)
        return {"voiceModel": voice.model, "textModel": str(getattr(self.author, "model", "unknown"))[:96],
                "source": voice.source, "connectionClass": voice.connection_class, "timingsMs": timings,
                "firstAudioMs": voice.first_audio_ms}

    def _finish(self, gid: str) -> None:
        entry = self.acks.pop(gid, None)
        self.line_metadata.pop(gid, None)
        if entry is not None and entry[0].state.lifecycle not in {'completed', 'interrupted', 'expired', 'rejected'}:
            self._end_state(entry[0], 'playback_failed')
        if entry is not None and entry[0].state.lifecycle == 'interrupted':
            self._duration({'generationId': gid}, entry[0], interrupted=True)
            self.memory.note_interrupted(gid)
        if gid not in self.terminal:
            self.terminal.append(gid)

    def _ack(self, message: dict, *, check_current: bool = True):
        gid = message.get("generationId")
        entry = self.acks.get(gid) if isinstance(gid, str) else None
        if entry is None:
            return None
        op = entry[0]
        if "identity" in message and (op.event is None or not matches_identity(message["identity"], identity(op.event))):
            self._note("identity_mismatch")
            return None
        if check_current and not self._current(op):
            self._end_state(op, 'expired' if op.deadline_ms is not None and self.monotonic_ms() > op.deadline_ms else 'scope_changed')
            op.state.valid = False
            self._mark(op, "ackCancel")
            self._finish(gid)
            return None
        return entry

    async def _event(self, message: dict) -> None:
        received = self.monotonic_ms()
        try:
            event = CoachEvent.model_validate(message.get("event"))
        except ValidationError:
            await self._reject(None, "invalid_event")
            return
        if event.scope.user_id != self.user_id or event.scope.run_id != self.scope_run_id:
            await self._reject(event.id, "owner_mismatch")
            return
        if event.id in self.seen or len(self.seen) >= MAX_SEEN:
            await self._reject(event.id, "duplicate" if event.id in self.seen else "queue_full")
            return
        self.seen.add(event.id)
        if event.kind in {"pain_reported", "safety_changed"}:
            self.director.latch_safety(True)
            await self.cancel("safety")
            return
        # Browser and server absolute times are unrelated. Only the original interval
        # and optional browser elapsed-at-send budget cross the clock boundary. Network
        # transit time is unknowable here; the client rechecks its ORIGINAL deadline.
        ttl = event.start_deadline_ms - event.created_at_ms
        elapsed = _bounded_ms(message.get("elapsedAtSendMs", 0), 86_400_000)
        if elapsed is None:
            await self._reject(event.id, "invalid_elapsed")
            return
        budget = max(0, min(ttl, ttl - elapsed))
        if budget <= 0:
            await self._reject(event.id, "expired")
            return
        context = message.get("context") if isinstance(message.get("context"), dict) else {}
        local = None
        if 'localCompletion' in context:
            try:
                local = LocalCompletion.model_validate(context['localCompletion'])
                if not local.applies(event.kind):
                    raise ValueError('Wrong completion scope')
            except (ValidationError, ValueError):
                await self._reject(event.id, 'invalid_local_completion')
                return
        try:
            with self.sessions() as db:
                opportunity = self.plan(db, event, message.get("refs"), context)
        except history.HistoryError as error:
            await self._decision(event.id, None, "silence", error.reason)
            return
        if event.kind == "workout_finalized" and isinstance(opportunity, Opportunity) and (
                self.episode_job is None or self.episode_job.done()):
            self.episode_job = asyncio.create_task(self._episode(opportunity))
        if self.counter_state != self._sent_counters:
            self._sent_counters = list(self.counter_state)
            await self.send_json({"type": "scenario_state", "counters": self.counter_state})
        if opportunity is None:
            return  # Not a live opportunity (local cue or unmapped event): nothing to say.
        if isinstance(opportunity, str):
            await self._decision(event.id, None, "silence", opportunity)
            return
        # plan() has verified result refs against persisted rows and their owner.
        # Only those confirmed opportunities may traverse the result phase table.
        state = self._event_state(event, confirmed_result=event.kind in {
            "set_persisted", "exercise_finalized", "workout_finalized"})
        if not state.valid:
            await self._reject(event.id, "scope_changed")
            return
        opportunity = replace(opportunity, received_ms=received, deadline_ms=received + budget, state=state,
                              local_completion=local, package=additional_package(opportunity.package, local),
                              candidate=replace(opportunity.candidate,
                                                valid_until_ms=min(opportunity.candidate.valid_until_ms,
                                                                   self.now_ms() + budget)))
        state.model = str(getattr(self.author, "model", "unknown"))[:96]
        if self.voice is not None and self.settings.mode != "text-only":
            capability = getattr(self.voice.adapter, "capability", None)
            state.model += "/" + str(getattr(capability, "model", "unknown"))[:96]
        # Classification stays unknown until the actual voice request reports it.
        self._mark(opportunity, "receive")
        self.opportunities[event.id] = opportunity
        self.stats.opportunities['pending'] += 1
        if self.task and not self.task.done():
            # A prebuild item takes a few seconds: live moments wait for it instead of being lost (V8).
            if event.kind in {'set_persisted', 'exercise_finalized', 'workout_finalized'} or self.task in self._prebuild_items:
                await self._enqueue(opportunity)
                return
            await self._decision(event.id, opportunity.candidate.trigger_id, "silence", "pipeline_busy")
            return
        await self._admit_and_start(opportunity)

    async def _admit_and_start(self, op: Opportunity) -> None:
        if not self._current(op):
            reason = 'expired' if op.deadline_ms is not None and self.monotonic_ms() > op.deadline_ms else 'scope_changed'
            await self._decision(op.event_id, op.candidate.trigger_id, "silence", reason)
            return
        if op.local_completion and not useful_addition(op.package, tuple(f.id for f in (
            op.package.facts if op.package else ())), op.local_completion):
            await self._decision(op.event_id, op.candidate.trigger_id, 'silence', 'no_useful_content')
            return
        # A queued callback can race an inbound event after the previous task ends.
        if self.task is not None and not self.task.done():
            if (op.event and op.event.kind in {'set_persisted', 'exercise_finalized', 'workout_finalized'}) or (
                    self.task in self._prebuild_items):
                await self._enqueue(op)
            else:
                await self._decision(op.event_id, op.candidate.trigger_id, "silence", "pipeline_busy")
            return
        tier = self.budget_tier()
        action = op.candidate.speech_action
        if self.settings.density == "show":
            # V0.3: from tier 1 the show is toned down to «talkative» (and back once money allows).
            self.director.set_profile("talkative" if tier >= 1 else "show")
        if (tier >= TIER_SUMMARY_ONLY and action != "summary") or (
                tier >= TIER_RESULT_ONLY and action not in {"result", "summary"}):
            # Local clips keep counting/confirming; the remaining money is kept for results and the summary.
            await self._decision(op.event_id, op.candidate.trigger_id, "silence", "budget_tier")
            return
        admission = self.director.admit(op.candidate, self.now_ms())
        if not admission.ok:
            await self._decision(op.event_id, op.candidate.trigger_id, "silence", admission.reason or "no_window")
            return
        self.director.note_admitted(op.candidate)
        self._transition(op, 'preparing')
        self.stats.triggers[op.candidate.trigger_id] += 1
        self.active_op = op
        max_words = admission.max_words
        if tier >= TIER_SHORT_REST and op.candidate.phase in {"rest", "setup"} and action != "summary":
            max_words = min(max_words, TIER_SHORT_REST_WORDS)
        self.task = asyncio.create_task(self._pipeline(op, max_words))
        self.task.add_done_callback(self._after)

    def _after(self, task: asyncio.Task) -> None:
        if self.closed or task is not self.task or not self.queue:
            return
        asyncio.get_running_loop().create_task(self._drain())

    def _started(self, message: dict) -> None:
        gid, duration = message.get("generationId"), _bounded_ms(message.get("durationMs"), 60_000)
        entry = self._ack(message)
        if entry is None:
            return
        op, text, used_ids = entry
        if op.state.started:
            self._duration(message, op)
            return
        if op.state.lifecycle != 'ready':
            return
        op.state.started = True
        self._transition(op, 'started')
        if op.candidate.trigger_id == "T70":
            self.why_done.add(op.scope.exercise_id or "-")  # V9.1: explained once it is actually heard.
        self._mark(op, "ackStart")
        now = self.now_ms()
        op.state.audible_duration_ms = duration if duration is not None else 2_500
        self.director.note_audible(now, op.state.audible_duration_ms, content=True, utterance_id=gid)
        # Only facts the line actually spoke are "mentioned"; keys are per source record, so the same
        # value in the next set (10 reps again) is a new fact, not a repeat.
        used = {memory_key(f): f.value for f in (op.package.facts if op.package else ()) if f.id in used_ids}
        metadata = self.line_metadata.get(gid, {})
        intent = metadata.get("intent")
        tip = op.coach_context.tip if op.coach_context and "reviewed-tip" in used_ids else None
        discussed = tuple((f.id, f.ref or "", f.provenance) for f in (
            op.package.facts if op.package else ()) if f.id in used_ids)
        self.memory.note_started(Utterance(gid, op.candidate.trigger_id, op.candidate.topic_key, text, now,
                                           op.state.audible_duration_ms, exercise_id=op.exercise_id,
                                           topic_family=op.candidate.topic_family,
                                           form=intent or "", energy=metadata.get("energy", ""), intent=intent,
                                           humor=intent == "humor", tip_id=tip.tip_id if tip else None,
                                           tip_version=tip.version if tip else None, discussed_facts=discussed,
                                           motif=metadata.get("motif"), callback=metadata.get("callback", False),
                                           phase_key=op.candidate.semantic_key), used,
                                 callback=metadata.get("callback", False))

    async def cancel(self, reason: str) -> None:
        ops = [entry[0] for entry in self.acks.values()]
        ops += [op for op in [self.active_op, *self.queue] if op is not None]
        for op in {id(op): op for op in ops}.values():
            self._end_state(op, reason)
            op.state.valid = False
            self._mark(op, "ackCancel")
        for op in list(self.queue):
            await self._decision(op.event_id, op.candidate.trigger_id, 'silence', reason)
        self.queue.clear()
        for gid in list(self.acks):
            self._duration({'generationId': gid}, self.acks[gid][0], interrupted=True)
            self.memory.note_interrupted(gid)
            self._finish(gid)
        await self._cancel_task(reason)

    async def _cancel_task(self, reason: str) -> None:
        task = self.task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            self._note(reason)

    async def close(self) -> None:
        self.closed = True
        for job in (self.scenario_job, self.prebuild_job, self.episode_job, *self._prebuild_items):
            if job is not None and not job.done():
                job.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await job
        await self.cancel("cancelled")

    # ---------- V1 scenarios ----------

    def _load_scenario(self) -> None:
        try:
            with self.sessions() as db:
                found = scenario.load(db, self.run_id, self.user_id)
        except Exception:  # noqa: BLE001 - a broken optional story must never stop the coach
            found = None
        if found:
            self.scenario_card, self.scenario_bible = found

    def story_counters(self, db: Session, workout_id: int | None, *, exercise_id: str | None = None,
                       exercise_session_id: int | None = None) -> list[dict]:
        """V4: the chosen story's counters for this workout, plus boss health on the boss exercise."""
        if not (self.scenario_card and self.scenario_bible):
            return []
        totals = counters.workout_totals(db, workout_id, self.user_id)
        found = counters.values(self.scenario_bible, totals, records=sum(self.record_sets.values()),
                                steady=sum(self.steady_sets.values()))
        boss = counters.boss_health(self.scenario_bible, self.scenario_card.get("archetype", ""), exercise_id,
                                    counters.boss_sets_done(db, exercise_session_id))
        return [*found, *([boss] if boss else [])]

    def scenario_state(self) -> dict:
        if not (self.scenario_card and self.scenario_bible):
            return {"type": "scenario", "state": "none"}
        bible = self.scenario_bible
        return {"type": "scenario", "state": "ready", "title": self.scenario_card["title"],
                "tagline": self.scenario_card.get("tagline"), "archetype": self.scenario_card["archetype"],
                "acts": [{"act": a["act"], "title": a["title"], "exerciseIds": a["exerciseIds"]} for a in bible["acts"]],
                "counters": [{"id": c["id"], "label": c["label"],
                              "value": next((v["value"] for v in self.counter_state if v["id"] == c["id"]), None)}
                             for c in bible.get("counters", [])],
                "coHost": bible.get("coHost")}

    async def announce(self) -> None:
        """After `configured`: tell a (re)connected browser whether a story is already chosen."""
        await self.send_json(self.scenario_state())

    async def _scenario_message(self, kind: str, message: dict) -> None:
        if self.author is None:
            await self.send_json({"type": "scenarios", "error": "provider_unavailable"})
            return
        if self.scenario_job is not None and not self.scenario_job.done():
            await self.send_json({"type": "scenarios", "error": "scenario_busy"})
            return
        if kind == "scenario_skip":
            self.scenario_cards = []
            await self.send_json({"type": "scenario", "state": "skipped"})
            return
        if kind == "scenario_propose":
            plan = scenario.parse_plan(message.get("plan"))
            if plan is None:
                await self.send_json({"type": "scenarios", "error": "invalid_plan"})
                return
            if self.scenario_proposals >= SCENARIO_PROPOSALS:
                await self.send_json({"type": "scenarios", "error": "no_more_proposals"})
                return
            self.scenario_plan = plan
            self.scenario_job = asyncio.create_task(self._scenario_propose(plan))
            return
        index = message.get("index")
        if type(index) is not int or not 0 <= index < len(self.scenario_cards) or self.scenario_plan is None:
            await self.send_json({"type": "scenario", "state": "failed", "reason": "invalid_choice"})
            return
        self.scenario_job = asyncio.create_task(self._scenario_build(self.scenario_cards[index], self.scenario_plan))

    async def _hold_pipeline(self) -> bool:
        """Scenario generation shares the run's single paid flight: wait for speech, then occupy the slot."""
        deadline = time.monotonic() + SCENARIO_IDLE_WAIT_S
        while self.task is not None and not self.task.done():
            if time.monotonic() > deadline:
                return False
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(asyncio.shield(self.task), max(0.05, deadline - time.monotonic()))
        if self.closed:
            return False
        self.task = asyncio.current_task()
        self.task.add_done_callback(self._after)
        return True

    async def _scenario_propose(self, plan: tuple[scenario.PlanExercise, ...]) -> None:
        if not await self._hold_pipeline():
            await self.send_json({"type": "scenarios", "error": "pipeline_busy"})
            return
        self.scenario_proposals += 1
        with self.sessions() as db:
            recent = scenario.recent_archetypes(db, self.user_id)
        archetypes = scenario.choose_archetypes(recent, exclude=tuple(self.scenario_shown))
        s = self.settings
        output, error = await self.author.generate(
            run_id=self.run_id, owner=self.owner, generation=self.generation,
            opportunity=f"{self.run_id}:scenario:propose:{self.scenario_proposals}", task="scenario/propose",
            name="coach_scenarios", instructions=scenario.PROPOSE_INSTRUCTIONS,
            data=scenario.propose_data(plan, archetypes, character=s.persona, style=s.style, goal=s.goal,
                                       experience=s.experience, assistant_context=s.assistant_context),
            schema=scenario.propose_schema(archetypes), purpose="scenario", reasoning_effort="low",
            tier=self.budget_tier())
        cards = scenario.validate_cards(output, archetypes) if output is not None else None
        if cards is None:
            if output is not None:
                self.author.reject_generation("scenario_cards")
            await self.send_json({"type": "scenarios", "error": error or "invalid_scenarios"})
            return
        self.scenario_cards = cards
        self.scenario_shown.extend(archetypes)
        await self.send_json({"type": "scenarios", "cards": cards,
                              "proposalsLeft": max(0, SCENARIO_PROPOSALS - self.scenario_proposals)})

    async def _scenario_build(self, card: dict, plan: tuple[scenario.PlanExercise, ...]) -> None:
        await self.send_json({"type": "scenario", "state": "building", "title": card["title"]})
        if not await self._hold_pipeline():
            await self.send_json({"type": "scenario", "state": "failed", "reason": "pipeline_busy"})
            return
        s = self.settings
        bible, error = None, None
        for attempt in (1, 2):  # One more try for a malformed bible; then the workout simply has no story.
            output, error = await self.author.generate(
                run_id=self.run_id, owner=self.owner, generation=self.generation,
                opportunity=f"{self.run_id}:scenario:bible:{card['archetype']}:{attempt}", task="scenario/bible",
                name="coach_scenario_bible", instructions=scenario.BIBLE_INSTRUCTIONS,
                data=scenario.bible_data(card, plan, character=s.persona, profanity=s.profanity, humor=s.humor),
                schema=scenario.bible_schema(plan), purpose="scenario", tier=self.budget_tier())
            if output is None:
                break
            bible = scenario.validate_bible(output, plan)
            if bible is not None:
                break
            self.author.reject_generation("scenario_bible")
            error = "invalid_bible"
        if bible is None:
            await self.send_json({"type": "scenario", "state": "failed", "reason": error or "invalid_bible"})
            return
        with self.sessions() as db:
            scenario.save(db, self.run_id, self.user_id, card, bible)
        self.scenario_card, self.scenario_bible = card, bible
        await self.send_json(self.scenario_state())
        self.schedule_prebuild()

    # ---------- V11 episode ----------

    def episode_input(self, db: Session, workout_id: int, package: FactPackage | None) -> episode.EpisodeInput:
        facts = list(package.facts if package else ())
        if self.settings.history_consent:
            found, _ = progress.regularity(db, self.user_id, current_workout_id=workout_id, scope_epoch=0,
                                           valid_until_ms=float("inf"))
            facts += found
        values = {f.id: f.value for f in facts}
        boss = next((c["value"] for c in self.counter_state if c["id"] == "boss"), None)
        earned = episode.achievements(fact_ids=set(values), fact_values=values, records=sum(self.record_sets.values()),
                                      steady_sets=sum(self.steady_sets.values()), boss_defeated=boss == 0)
        bible = self.scenario_bible or {}
        return episode.EpisodeInput(tuple((f.id, f.claim, tuple(f.numbers)) for f in facts), earned,
                                    (self.scenario_card or {}).get("title"), bible.get("finale"))

    async def _episode(self, op: Opportunity) -> None:
        """After the workout summary line: write the recap on the reserved budget, or keep the local template."""
        workout_id = dict(op.source_refs).get("backendWorkoutId")
        if workout_id is None:
            return
        deadline = time.monotonic() + PREBUILD_IDLE_WAIT_S
        await asyncio.sleep(0.1)  # Let the summary line take the paid slot first.
        while self.task is not None and not self.task.done() and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
        with self.sessions() as db:
            source = self.episode_input(db, workout_id, op.package)
        payload, kind = episode.local(source), "local"
        if self.author is not None and not self.closed and (self.task is None or self.task.done()):
            self.task = asyncio.current_task()
            self.task.add_done_callback(self._after)
            output, _ = await self.author.generate(
                run_id=self.run_id, owner=self.owner, generation=self.generation,
                opportunity=f"{self.run_id}:episode:{workout_id}", task="episode/workout", name="coach_episode",
                instructions=episode.INSTRUCTIONS, data=episode.data(source), schema=episode.SCHEMA, purpose="episode",
                meta={"trigger_id": op.candidate.trigger_id})
            written = episode.validate(output, source) if output is not None else None
            if written is not None:
                payload, kind = written, "generated"
            elif output is not None:
                self.author.reject_generation("episode")
        with self.sessions() as db:
            saved = episode.save(db, workout_id=workout_id, user_id=self.user_id, run_id=self.run_id, payload=payload,
                                 source=kind, achievement_ids=source.achievements)
        with contextlib.suppress(Exception):
            await self.send_json({"type": "episode", "workoutId": workout_id, "title": saved["title"]})

    # ---------- V8 prebuild ----------

    def schedule_prebuild(self) -> None:
        if (self.prebuild_job is None or self.prebuild_job.done()) and self.scenario_bible and self.author is not None \
                and self.voice is not None and self.settings.mode == "hybrid":
            self.prebuild_job = asyncio.create_task(self._prebuild_all())

    def _prebuild_targets(self) -> list[tuple[str, str, str, dict, int]]:
        """(key, trigger, task, plan exercise, position) for result-independent story moments."""
        plan = self.scenario_bible.get("plan", []) if self.scenario_bible else []
        targets = []
        for position, exercise in enumerate(plan, 1):
            act = scenario.act_state(self.scenario_bible, exercise["id"])
            if position > 1 and act is not None:
                trigger, task = (("T68", "setup/boss") if act.last_exercise else
                                 ("T67", "setup/act") if act.first_of_act and act.act > 1 else ("T04", "setup/opening"))
                targets.append((f"{trigger}:{exercise['id']}", trigger, task, exercise, position))
        if plan:
            targets.append((f"T69:{plan[-1]['id']}", "T69", "active/finale", plan[-1], len(plan)))
            if not self.workout_started:
                # Live run 26.10.2026: on a slow API the story opening (variants + judge) expired before the voice.
                targets.insert(0, (OPENING_KEY, "T01", "setup/opening", plan[0], 1))
        return targets[:PREBUILD_MAX_LINES]

    def _prebuild_op(self, trigger: str, task: str, exercise: dict, position: int) -> Opportunity:
        now = self.now_ms()
        total = len(self.scenario_bible.get("plan", []))
        common = {"scope_epoch": 0, "valid_until_ms": now + PREBUILD_VALID_MS, "ref": f"prebuild:{exercise['id']}",
                  "provenance": "runtime-event-declaration", "quantity_kind": "declared", "sufficiency": "limited"}
        name = history.speakable_name(exercise.get("name"))
        found = [AllowedFact("exercise", f"Упражнение — {name}", "confirmed", name, **common) if name else None]
        if trigger == "T01":
            found = [AllowedFact("exercise-count", f"В тренировке {spoken_quantity(total, 'exercises')}", "confirmed",
                                 total, "exercises", numbers=(total,), **common) if total else None,
                     AllowedFact("exercise", f"Первое упражнение — {name}", "confirmed", name, **common) if name else None]
            if self.settings.history_consent:
                with self.sessions() as db:  # The same jubilee/streak/first-workout facts as the live opening.
                    regular, _ = progress.regularity(db, self.user_id, current_workout_id=None, scope_epoch=0,
                                                     valid_until_ms=now + PREBUILD_VALID_MS)
                found += regular
        elif trigger == "T69":
            found.append(AllowedFact("milestone", "Идёт последний подход всей тренировки", "confirmed", "finale", **common))
        else:
            found.append(AllowedFact("exercise-position", "Это последнее упражнение тренировки", "confirmed", position,
                                     **common) if position == total else
                         AllowedFact("exercise-position", f"Упражнение {position} из {total}", "confirmed",
                                     f"{position}/{total}", numbers=(position, total), **common))
            sets = exercise.get("sets")
            if type(sets) is int and 0 < sets <= 50:
                found.append(AllowedFact("plan-sets", f"По плану {spoken_quantity(sets, 'sets')}", "confirmed", sets,
                                         "sets", numbers=(sets,), **common))
        package = FactPackage(trigger, tuple(f for f in found if f is not None), Comparison("unavailable"), "none")
        phase = "active" if trigger == "T69" else "setup"
        scope = CoachScope(user_id=self.user_id, run_id=self.scope_run_id, exercise_id=exercise["id"])
        candidate = Candidate(trigger, f"prebuild:{exercise['id']}", phase, now, now + PREBUILD_VALID_MS,
                              f"prebuild:{trigger}:{exercise['id']}", {}, words_cap=None if trigger == "T69" else SCENARIO_WORDS,
                              topic_family=TRIGGERS[trigger].family, speech_action=speech_action(task))
        return Opportunity(f"prebuild-{trigger}-{exercise['id']}", candidate, task, ("motivation", "humor"), scope,
                           self._shape(package), exercise["id"])

    async def _prebuild_all(self) -> None:
        if self.workout_started:
            await asyncio.sleep(PREBUILD_START_DELAY_S)  # Let the story's live opening line go first.
        for key, trigger, task, exercise, position in self._prebuild_targets():
            if self.closed or not self.scenario_bible:
                return
            if key in self.prebuilt:
                continue
            deadline = time.monotonic() + PREBUILD_IDLE_WAIT_S
            while time.monotonic() < deadline and not self.closed:
                while self.task is not None and not self.task.done() and time.monotonic() < deadline:
                    await asyncio.sleep(0.2)
                item = asyncio.create_task(self._prebuild_one(key, trigger, task, exercise, position))
                self._prebuild_items.add(item)
                item.add_done_callback(self._prebuild_items.discard)
                try:
                    started = await item
                except asyncio.CancelledError:
                    raise
                except Exception:  # A failed preparation only means this moment is authored live.
                    self._note("prebuild_error")
                    logger.exception("coach prebuild failed key=%s", key)
                    break
                if started is not False:
                    break  # Built, or skipped for budget/silence: either way this moment is settled.
                # A live line took the slot between our check and the start: wait for it and retry.

    async def _prebuild_one(self, key: str, trigger: str, task: str, exercise: dict, position: int) -> bool | None:
        if self.task is not None and not self.task.done():
            return False  # A live line took the slot first; the caller waits and retries.
        self.task = asyncio.current_task()
        self.task.add_done_callback(self._after)
        op = self._prebuild_op(trigger, task, exercise, position)
        if self.budget_tier() >= 1:
            return  # Economy: prepared lines are a luxury, live results and summaries come first.
        request = self._request(op, 14 if trigger == "T69" else SCENARIO_WORDS)
        outcome = await self.author.author(run_id=self.run_id, owner=self.owner, generation=self.generation,
                                           opportunity=f"{self.run_id}:prebuild:{key}", request=request, memory=None,
                                           scope_epoch=0, purpose="prebuild", timeout_s=15,
                                           meta={**self._journal_meta(op), "task": f"prebuild/{task}"[:40]})
        if outcome.kind != "speech":
            return
        delivery = Delivery(**(outcome.delivery or {})) if outcome.delivery else Delivery()
        delivery = select_delivery(delivery, intent=outcome.intent, action=op.candidate.speech_action, outcome=None,
                                   enabled=getattr(self.voice.adapter, "emotive", False))
        if getattr(self.voice.adapter, "emotive", False) and request.mood:
            delivery = replace(delivery, mood=request.mood["name"], phase="rest", sounds=self.settings.voice_sounds)
        voice = VoiceOutcome()
        pcm = bytearray()
        async with contextlib.aclosing(self.voice.stream(
                run_id=self.run_id, owner=self.owner, generation=self.generation,
                opportunity=f"{self.run_id}:prebuild:{key}", text=outcome.text, scope=op.scope,
                generation_id=f"prebuild-{secrets.token_hex(6)}", outcome=voice, delivery=delivery, purpose="prebuild",
                meta={**self._journal_meta(op), "task": f"prebuild/{task}"[:40]})) as frames:
            async for frame in frames:
                pcm += decode_frame(frame).data
        if voice.status == "complete" and pcm:
            self.prebuilt[key] = PrebuiltLine(key, outcome.text, outcome.used_fact_ids, bytes(pcm), voice.source,
                                              outcome.intent, (request.mood or {}).get("name"),
                                              history.speakable_name(exercise.get("name")))

    async def _play_prebuilt(self, op: Opportunity, line: PrebuiltLine) -> None:
        """Speak a prepared line for this live moment: same ACK/memory path, re-framed for the live scope."""
        trigger, gid = op.candidate.trigger_id, secrets.token_hex(12)
        valid_for = op.candidate.valid_until_ms - self.now_ms()
        if op.deadline_ms is not None:
            valid_for = min(valid_for, op.deadline_ms - self.monotonic_ms())
        if valid_for < 1_000 or not self._current(op):
            await self._decision(op.event_id, trigger, "silence", "expired")
            return
        self._transition(op, 'ready')
        self._remember(gid, op, line.text, line.used_fact_ids)
        if gid in self.acks:
            self.line_metadata[gid] = {"intent": line.intent, "energy": "", "motif": None, "callback": False,
                                       "mood": line.mood}
        source = line.source if line.source in {"realtime", "tts", "fish", "fake"} else "fish"
        await self.send_json({"type": "speech_start", "eventId": op.event_id, "triggerId": trigger, "generationId": gid,
                              "text": line.text, "validForMs": round(valid_for), "sampleRate": 24_000, "source": source,
                              "prebuilt": True, **({"identity": identity(op.event)} if op.event else {})})
        framer = PcmFramer(gid, gid, op.scope, source)
        frames = 0
        for chunk in [*framer.push(line.pcm), framer.finish()]:
            if not self._current(op):
                self._finish(gid)
                await self.send_json({"type": "speech_end", "generationId": gid, "status": "cancelled",
                                      "reason": "cancelled", "frames": frames})
                return
            await self.send_bytes(encode_frame(chunk))
            frames += 1
        self.stats.spoken += 1
        self._mark(op, "speechEnd")
        await self.send_json({"type": "speech_end", "generationId": gid, "status": "complete", "reason": None,
                              "frames": frames, "voiceModel": "prebuilt", "source": source, "timingsMs": {},
                              "firstAudioMs": 0, "connectionClass": "not-applicable"})

    # ---------- event → opportunity ----------

    def plan(self, db: Session, event: CoachEvent, refs: object, context: dict) -> Opportunity | str | None:
        now, scope = self.now_ms(), event.scope
        run, exercise = scope.run_id, scope.exercise_id or "-"
        set_key = f"{run}:{exercise}:{scope.set_ordinal or 0}"
        scopes = {"workout": run, "exercise": f"{run}:{exercise}", "set": set_key, "rest": f"rest:{set_key}",
                  "slot": f"slot:{set_key}"}
        rest_ms = _bounded_ms(context.get("restMs"), 3_600_000)
        rest_elapsed = _bounded_ms(context.get("restElapsedMs"), 3_600_000) or 0
        phase_elapsed = _bounded_ms(context.get("phaseElapsedMs"), 3_600_000) or 0

        def candidate(trigger: str, phase: str, topic: str, *, until: float | None = None, hint: float = 2_500,
                      started: float | None = None, length: float | None = None) -> Candidate:
            window = TRIGGERS[trigger].window_ms or 20_000
            return Candidate(trigger, f"{scopes.get(TRIGGERS[trigger].scope, set_key)}", phase, now,
                             min(now + window, until) if until else now + window, topic, scopes,
                             duration_hint_ms=hint, phase_started_ms=started, phase_length_ms=length,
                             topic_family=TRIGGERS[trigger].family)

        def op(c: Candidate, task: str, intents: tuple[str, ...], package: FactPackage | None = None) -> Opportunity | str:
            saved, feedback = None, None
            set_ref = _ref(refs, "backendSetId")
            if set_ref and event.kind in {"set_persisted", "rest_long_opportunity"}:
                saved = history.load_saved_set(db, self.user_id, set_ref, history_consent=False)
                if saved.current.ordinal != scope.set_ordinal:
                    return "no_source"
                feedback = history.explicit_feedback(db, self.user_id, set_ref, now_ms=now,
                                                     ttl_ms=self.feedback_ttl_ms)
            cc = build_context(event, context, c.phase, saved=saved, feedback=feedback)
            # Story moments (act start, the boss) keep their scenario intro; plain intros become a technique memo.
            if c.phase == "setup" and self.settings.exercise_intro and cc.setup_guidance and c.trigger_id not in {"T67", "T68"}:
                task, intents = "setup/technique", ("general-tip",)
                package = FactPackage(c.trigger_id, tuple(
                    AllowedFact(key, text, "confirmed", text, scope_epoch=scope.scope_epoch,
                                valid_until_ms=c.valid_until_ms, provenance="exercise-catalog-instructions",
                                ref=f"catalog:{cc.exercise_slug}:{key}", sufficiency="limited")
                    for key, text in cc.setup_guidance), Comparison("unavailable"), "none")
                # One source-backed explanation replaces the motivational opening.
                c = replace(c, duration_hint_ms=10_000)
            if event.kind == "workout_started" and not self.settings.greeting and task != "setup/technique":
                return "disabled"
            if cc.tip and self.memory.tip_completed(cc.tip.tip_id, cc.tip.version):
                cc = replace(cc, tip=None)
            # Missing or fully explained guidance is not a reason to lose the
            # support window. Keep the ordinary active safety/claim validator;
            # strip the tip before constructing facts or author metadata.
            if task == "active/general-tip" and cc.tip is None:
                task, intents = "active/support", ("motivation",)
            if cc.risk:
                intents = tuple(i for i in intents if i != "humor") or ("motivation",)
            if cc.tip and task in {"active/general-tip", "setup/opening", "rest/playful"}:
                tip_fact = AllowedFact("reviewed-tip", cc.tip.text, "confirmed", cc.tip.tip_id,
                                       scope_epoch=scope.scope_epoch, valid_until_ms=c.valid_until_ms,
                                       provenance=cc.tip.source, ref=f"tip:{cc.tip.tip_id}:{cc.tip.version}",
                                       sufficiency="sufficient")
                package = replace(package, facts=(*package.facts, tip_fact)) if package else FactPackage(
                    c.trigger_id, (tip_fact,), Comparison("unavailable"), "none")
                if task == "rest/playful":
                    task, intents = "rest/general-tip", ("general-tip",)
            else:
                if task != "setup/technique":
                    intents = tuple(i for i in intents if i != "general-tip") or ("motivation",)
            if self.settings.humor == "off" or not self.memory.humor_allowed():
                intents = tuple(i for i in intents if i != "humor") or ("motivation",)
            if package:
                locked = [f for f in package.facts if f.id in package.locked_fact_ids]
                if (not self.settings.say_weight and package.locked_clause and "вес" in package.locked_clause.lower()) or any((not self.settings.say_numbers and f.numbers)
                       or (not self.settings.say_weight and f.id == "weight")
                       or (not self.settings.say_exercise_name and f.id in NAME_FACTS)
                       or (not self.settings.say_set_progress and f.id in PROGRESS_FACTS) for f in locked):
                    return "restricted_content"
            source_refs = tuple((key, value) for key in ("backendSetId", "backendExerciseId", "backendWorkoutId")
                                if (value := _ref(refs, key)) is not None)
            source_context = tuple((key, context[key]) for key in ("restMs", "restElapsedMs", "nextExerciseName",
                                    "exerciseSlug", "variant", "controlMode", "moment", "phaseElapsedMs")
                                   if key in context and isinstance(context[key], int | float | str)
                                   and len(str(context[key])) <= 120)
            # Telemetry summaries travel as canonical JSON so revalidation rebuilds the same measured facts.
            source_context += tuple((key, value) for key in ("setMetrics", "telemetry")
                                    if (value := telemetry.wire(context.get(key))) is not None)
            shaped = self._shape(package)
            cc = replace(cc, fact_ids=tuple(f.id for f in shaped.facts) if shaped else (),
                         goal=self.settings.goal, experience=self.settings.experience)
            action = speech_action(task)
            c = replace(c, speech_action=action, priority=SPEECH_ACTIONS[action].priority)
            return Opportunity(event.id, c, task, intents, scope, shaped, scope.exercise_id, event=event,
                               source_refs=source_refs, source_context=source_context, coach_context=cc)

        def plan_package(trigger: str, found: list[AllowedFact | None]) -> FactPackage | None:
            kept = tuple(f for f in found if f is not None)
            return FactPackage(trigger, kept, Comparison("unavailable"), "none") if kept else None

        s = self.settings
        epoch, valid = scope.scope_epoch, now + 60_000
        common = {"scope_epoch": epoch, "valid_until_ms": valid, "ref": f"{event.kind}:{set_key}",
              "provenance": "runtime-event-declaration", "quantity_kind": "declared",
              "sufficiency": "limited"}
        unit = "seconds" if event.exercise_kind in history.TIMED_KINDS else "reps"
        name = _name(context, "exerciseName")
        named = AllowedFact("exercise", f"Упражнение — {name}", "confirmed", name, **common) if name else None
        if event.kind == "workout_started":
            self.workout_started = True
            if not s.greeting and not s.exercise_intro:
                return "disabled"
            count = _count(context, "exerciseCount")
            package = plan_package("T01", [
                AllowedFact("exercise-count", f"В тренировке {spoken_quantity(count, 'exercises')}", "confirmed", count,
                            "exercises", numbers=(count,), **common) if count else None,
                AllowedFact("exercise", f"Первое упражнение — {name}", "confirmed", name, **common) if name else None])
            if s.history_consent:
                # V3 #17: jubilee, weekly streak, a long gap or the very first workout.
                found, status = progress.regularity(db, self.user_id, current_workout_id=None, scope_epoch=epoch,
                                                    valid_until_ms=valid)
                if found:
                    package = replace(package, facts=(*package.facts, *found), history=status) if package else \
                        FactPackage("T01", tuple(found), Comparison("unavailable"), "none", history=status)
            opening = candidate("T01", "setup", "workout-opening", hint=3_000)
            if self.scenario_bible:
                opening = replace(opening, words_cap=SCENARIO_WORDS, duration_hint_ms=5_000)
            return op(opening, "setup/opening", ("motivation", "humor"), package)
        if event.kind == "exercise_ready":
            if not s.exercise_intro:
                return "disabled"
            index, count, sets = _count(context, "exerciseIndex"), _count(context, "exerciseCount"), _count(context, "totalSets")
            position = None
            if index and count and index <= count and count > 1:
                position = (AllowedFact("exercise-position", "Это последнее упражнение тренировки", "confirmed", index,
                                        **common) if index == count else
                            AllowedFact("exercise-position", f"Упражнение {index} из {count}", "confirmed", f"{index}/{count}",
                                        numbers=(index, count), **common))
            exact = _count(context, "targetReps", 1000)
            low, high = _count(context, "targetMin", 1000), _count(context, "targetMax", 1000)
            target = (target_fact(exact, exact, unit, prefix="План на подход —", **common) if exact else
                      target_fact(low, high, unit, prefix="План на подход —", **common) if low and high else None)
            body = progress.muscle_facts(db, self.user_id, context.get("exerciseSlug") if isinstance(
                context.get("exerciseSlug"), str) else None, scope_epoch=epoch, valid_until_ms=valid) if s.history_consent else []
            package = plan_package("T04", [
                named, position,
                AllowedFact("plan-sets", f"По плану {spoken_quantity(sets, 'sets')}", "confirmed", sets, "sets",
                            numbers=(sets,), **common) if sets else None,
                target, weight_fact(_kg(context, "weightKg"), prefix="Плановый вес", **common), *body])
            act = scenario.act_state(self.scenario_bible, scope.exercise_id) if self.scenario_bible else None
            if act and (act.last_exercise or (act.first_of_act and act.act > 1)):
                # The story's act boundary or climax replaces the plain introduction of this exercise.
                trigger, task = ("T68", "setup/boss") if act.last_exercise else ("T67", "setup/act")
                story = replace(candidate(trigger, "setup", f"exercise-intro:{exercise}", hint=5_000),
                                words_cap=SCENARIO_WORDS)
                return op(story, task, ("motivation", "humor"), package and replace(package, trigger_id=trigger))
            return op(candidate("T04", "setup", f"exercise-intro:{exercise}", hint=3_000), "setup/opening",
                      ("motivation",), package)
        if event.kind in SET_MOMENT_KINDS and event.phase == "active-set":
            if not s.during_sets:
                return "disabled"
            moment = SET_MOMENT_KINDS[event.kind]
            if event.kind == "rep_milestone" and context.get("moment") in (
                    "stall", "support", "velocity_drop", "velocity_drop_hard", "tempo"):
                moment = context["moment"]
            moments = TIMED_SET_MOMENTS if unit == "seconds" else SET_MOMENTS
            if moment not in moments:
                return None
            claim, topic, intents = moments[moment]
            total_sets = _count(context, "totalSets")
            act = scenario.act_state(self.scenario_bible, scope.exercise_id) if self.scenario_bible else None
            if (moment == "start" and act and act.last_exercise and total_sets and scope.set_ordinal == total_sets):
                package = plan_package("T69", [named, AllowedFact("milestone", "Идёт последний подход всей тренировки",
                                                                  "confirmed", "finale", **common)])
                return op(candidate("T69", "active", f"finale:{set_key}", started=now - phase_elapsed),
                          "active/finale", ("motivation",), package)
            measured = telemetry.moment_facts(moment, telemetry.parse(context.get("telemetry")), common)
            if moment in {"velocity_drop", "velocity_drop_hard", "tempo"} and not measured:
                return "insufficient_facts"
            if moment == "tempo":
                package = plan_package("T19", [named, *measured])
                return op(candidate("T19", "active", f"set-tempo:{set_key}", started=now - phase_elapsed),
                          "active/tempo", intents, package)
            if moment == "support":
                slot = min(4, int(phase_elapsed // 15_000))
                if slot < 1:
                    return "no_window"
                topic = f"{topic}:{slot}"
            exact = _count(context, "targetSeconds" if unit == "seconds" else "targetReps", 3600) if moment == "start" else None
            package = plan_package("T21", [
                named, *progress_facts(scope.set_ordinal, _count(context, "totalSets"), **common)[:1],
                target_fact(exact, exact, unit, prefix="Цель подхода —", **common) if exact else None,
                AllowedFact("milestone", claim, "confirmed", moment, **common), *measured])
            # Topic stays per set: "half" keeps the historical key so one comment per moment per set.
            moment_candidate = replace(candidate("T21", "active", f"{topic}:{set_key}", started=now - phase_elapsed),
                                       novelty=moment in NOVEL_MOMENTS)
            return op(moment_candidate, "active/general-tip" if moment == "support" else "active/support", intents, package)
        if event.kind == "set_persisted":
            if not s.set_feedback:
                return "disabled"
            set_id = _ref(refs, "backendSetId")
            if set_id is None:
                return "no_source"
            saved = history.load_saved_set(db, self.user_id, set_id, history_consent=s.history_consent)
            if saved.current.ordinal != scope.set_ordinal:
                return "no_source"
            comparison = saved.comparison if s.comparisons and s.say_numbers else Comparison("unavailable")
            package = saved_set_facts(saved.current, comparison, scope_epoch=epoch, valid_until_ms=valid,
                                      history=saved.history, ref=f"set:{set_id}")
            if package.trigger_id not in RESULT_TASKS:
                return None  # Skipped set: local clip territory.
            set_common = {**common, "ref": f"set:{set_id}", "provenance": "persisted-plan",
                          "observed_at_ms": saved.current.observed_at_ms, "quantity_kind": "derived"}
            extra = [AllowedFact("exercise", f"Упражнение — {saved.exercise_name}", "confirmed", saved.exercise_name,
                                 **set_common)] if saved.exercise_name else []
            extra += progress_facts(saved.current.ordinal, saved.target_sets or None,
                                    next_exercise=_name(context, "nextExerciseName"), **set_common)
            extra += telemetry.set_facts(telemetry.parse(context.get("setMetrics")), {**common, "ref": f"set:{set_id}"})
            records = []
            if s.history_consent and s.comparisons:
                # V3 #15/#16 (both are comparisons with the past): a confirmed personal record leads the line —
                # T43, or the locked comparison clause framed as a record — and tonnage marks join as a fact.
                records = progress.personal_records(db, self.user_id, set_id, scope_epoch=epoch, valid_until_ms=valid)
                if records and package.outcome == "full":
                    extra = [*records, *extra]
                    if package.trigger_id == "T36":
                        package = replace(package, trigger_id="T43")
                else:
                    records = []
                workout_id = getattr(db.get(history.ExerciseSession, saved.exercise_id), "workout_session_id", None)
                if workout_id is not None and (mark := progress.tonnage_mark(
                        getattr(progress.tonnage(db, self.user_id, workout_id), "share", None))):
                    extra.append(progress.tonnage_fact(mark, ref=f"tonnage:{workout_id}:{mark}", scope_epoch=epoch,
                                                       valid_until_ms=valid))
            self.record_sets[set_id] = bool(records)
            self.steady_sets[set_id] = (telemetry.parse(context.get("setMetrics")) or {}).get("steady") is True
            if self.scenario_bible:
                exercise_row = db.get(history.ExerciseSession, saved.exercise_id)
                self.counter_state = self.story_counters(
                    db, getattr(exercise_row, "workout_session_id", None), exercise_id=scope.exercise_id,
                    exercise_session_id=saved.exercise_id)
                extra.extend(counters.facts(self.counter_state, {**common, "ref": f"counters:{set_id}"}))
            package = replace(package, facts=(package.facts + tuple(extra))[:12], source_signature=saved.source_signature)
            until = now - rest_elapsed + rest_ms - 3_000 if rest_ms else None
            c = candidate(package.trigger_id, "rest", f"set-result:{set_key}", until=until, hint=4_000,
                          started=now - rest_elapsed, length=rest_ms)
            return op(c, "rest/record" if records else RESULT_TASKS[package.trigger_id], RESULT_INTENTS[package.trigger_id],
                      package)
        if event.kind == "rest_long_opportunity":
            if not s.during_rest:
                return "disabled"
            if rest_ms is None or rest_ms - rest_elapsed < REST_EXTRA_MIN_MS:
                return "no_window"
            # Another line of this rest still playing; this event's own line (seen again on revalidation) does not count.
            if any(gid not in self.memory.completed for gid in self.acks
                   if self.acks[gid][0].scope == scope and self.acks[gid][0].event_id != event.id):
                return "utterance_pending"
            slug = context.get("exerciseSlug") if isinstance(context.get("exerciseSlug"), str) else None
            if scope.set_ordinal == 1 and slug and exercise not in self.why_done and (why := progress.why_facts(
                    slug, scope_epoch=epoch, valid_until_ms=valid)):
                # V9.1: the first rest of an exercise says what it is for — once per exercise (marked when spoken).
                package = plan_package("T70", [named, *why])
                c = candidate("T70", "rest", f"why:{exercise}", until=now - rest_elapsed + rest_ms - 5_000,
                              hint=5_000, started=now - rest_elapsed, length=rest_ms)
                return op(c, "rest/why", ("general-tip", "motivation"), package)
            story = counters.facts(self.counter_state, {**common, "ref": f"counters-rest:{set_key}"}) if (
                self.scenario_bible and self.counter_state) else []
            package = plan_package("T46", [
                named, *progress_facts(scope.set_ordinal, _count(context, "totalSets"),
                                       next_exercise=_name(context, "nextExerciseName"), **common), *story])
            c = candidate("T46", "rest", f"rest-playful:{set_key}", until=now - rest_elapsed + rest_ms - 5_000,
                          hint=4_000, started=now - rest_elapsed, length=rest_ms)
            return op(c, "rest/playful", ("humor", "motivation"), package)
        if event.kind == "exercise_finalized":
            if not s.exercise_summary:
                return "disabled"
            exercise_ref = _ref(refs, "backendExerciseId")
            if exercise_ref is None:
                return "no_source"
            package = history.exercise_summary(db, self.user_id, exercise_ref, scope_epoch=epoch, valid_until_ms=valid)
            if s.history_consent and s.comparisons and (record := progress.exercise_volume_record(
                    db, self.user_id, exercise_ref, scope_epoch=epoch, valid_until_ms=valid)):
                package = replace(package, facts=(*package.facts, record)[:12])
            return op(candidate(package.trigger_id, "summary", f"exercise-summary:{exercise}", hint=4_000),
                      "summary/exercise", ("summary",), package)
        if event.kind == "workout_finalized":
            if not s.workout_summary:
                return "disabled"
            workout_ref = _ref(refs, "backendWorkoutId")
            if workout_ref is None:
                return "no_source"
            package = history.workout_summary(db, self.user_id, workout_ref, scope_epoch=epoch, valid_until_ms=valid)
            if self.scenario_bible:
                final = [c for c in self.story_counters(db, workout_ref) if c["id"] != "boss"]
                package = replace(package, facts=(*package.facts, *counters.facts(
                    final, {**common, "ref": f"counters-final:{workout_ref}"}))[:12])
            if s.history_consent and s.comparisons and (mark := progress.tonnage_mark(
                    getattr(progress.tonnage(db, self.user_id, workout_ref), "share", None))):
                package = replace(package, facts=(*package.facts, progress.tonnage_fact(
                    mark, ref=f"tonnage:{workout_ref}:{mark}", scope_epoch=epoch, valid_until_ms=valid))[:12])
            return op(candidate(package.trigger_id, "summary", "workout-summary", hint=6_000),
                      "summary/workout", ("summary",), package)
        return None

    def _shape(self, package: FactPackage | None) -> FactPackage | None:
        """User 'what to mention' switches drop facts before the model sees them; locked clauses stay intact."""
        if package is None:
            return None
        s = self.settings

        def keep(f: AllowedFact) -> bool:
            if f.id in package.locked_fact_ids:
                return True
            return not ((not s.say_numbers and f.numbers) or (not s.say_exercise_name and f.id in NAME_FACTS)
                        or (not s.say_set_progress and f.id in PROGRESS_FACTS) or (not s.say_weight and f.id == "weight"))

        kept = tuple(f for f in package.facts if keep(f))
        if not kept and package.outcome == "none":
            return None  # Plan-only package with nothing left to say about.
        return replace(package, facts=kept)

    # ---------- pipeline ----------

    def _sources_current(self, op: Opportunity) -> bool:
        """Fresh sessions at the two async handoffs, never a DB query per chunk.

        Rebuild the bounded semantic package as well as its persisted-source
        revision. This catches deleted/updated results, changed plan/conditions,
        ownership, and newly available or edited comparison history.
        """
        if (op.package is None or not op.package.source_signature) and not (
            op.coach_context and (op.coach_context.tip or op.coach_context.feedback or op.coach_context.setup_guidance)):
            return True  # Non-persisted declarations are governed by U01 context versions.
        if op.event is None:
            return False
        try:
            with self.sessions() as db:
                fresh = self.plan(db, op.event, dict(op.source_refs), dict(op.source_context))
        except history.HistoryError:
            fresh = None
        if not isinstance(fresh, Opportunity) or fresh.package is None:
            op.state.valid = False
            return False
        if replace(fresh.coach_context, fact_ids=()) != replace(op.coach_context, fact_ids=()):
            op.state.valid = False
            return False
        if not op.package or not op.package.source_signature:
            return True  # Event declarations are versioned by U01; only tip/feedback is revalidated here.

        def semantic(package: FactPackage) -> FactPackage:
            return replace(package, facts=tuple(replace(f, valid_until_ms=0) for f in package.facts))

        if semantic(additional_package(fresh.package, op.local_completion)) != semantic(op.package):
            op.state.valid = False
            return False
        return True

    def _request(self, op: Opportunity, max_words: int) -> AuthorRequest:
        p = op.package
        s = self.settings
        # Do not invite the model to choose a fact that the heard-content guard
        # will inevitably reject (notably the shared milestone in later support slots).
        summary = op.candidate.trigger_id in SUMMARY_TRIGGERS
        request_facts = tuple(f for f in p.facts if f.id in p.locked_fact_ids or
                              self.memory.fact_allowed(memory_key(f), f.value, summary=summary)) if p else ()
        _RUN_MEMORY.prune()
        if self.cross_preferences:
            self.cross_preferences = _CROSS_MEMORY.current(self.user_id)
        risk = bool(op.coach_context and op.coach_context.risk)
        dark = s.edgy_opt_in and s.humor != "off" and not risk
        intents = op.intents
        if s.humor == "off" or risk or not self.memory.humor_allowed():
            intents = tuple(i for i in intents if i != "humor") or ("motivation",)
        motif, callback = None, False
        story_motif = self._story_motif(op) if (s.memory_enabled and not risk and op.candidate.phase in {"rest", "setup"}) else None
        if story_motif:
            motif, callback = story_motif
        elif (s.memory_enabled and "callbacks" in s.extras and "humor" in intents and not risk
                and op.task == "rest/playful" and op.candidate.phase == "rest"):
            if self.memory.motif is None:
                motif = "спокойный ритм"
            elif self.memory.callback_allowed(self.memory.motif, now_ms=self.now_ms(),
                                              phase_key=op.candidate.semantic_key):
                motif, callback = self.memory.motif, True
        record = any("record" in f.permits for f in request_facts)
        mood = self._mood(op, request_facts, risk)
        if mood.name == "recover":
            dark = False
        return AuthorRequest(
            op.candidate.trigger_id, op.candidate.phase, op.task, intents, op.candidate.topic_key, max(1, max_words),
            request_facts, p.comparison.status if p else "unavailable", p.history if p else "unavailable",
            p.outcome if p and p.outcome != "none" else None, p.locked_clause if p else None,
            p.locked_fact_ids if p else (), recent_topics=tuple(self.memory.recent_topics()),
            recent_openings=tuple(self.memory.recent_openings()),
            forbidden_claims=tuple(c for c in DEFAULT_FORBIDDEN if not (record and c == "личный рекорд")),
            summary=op.candidate.trigger_id in SUMMARY_TRIGGERS,
            name_allowed=bool(s.nickname), user_name=s.nickname or None, persona="sharp" if dark else "default",
            style=s.style, humor="off" if risk else s.humor, humor_kinds=() if risk else tuple(s.humor_kinds), dark_humor=dark,
            extras=() if risk else tuple(s.extras), address=s.address, verbosity=s.verbosity, praise=s.praise, goal=s.goal,
            experience=s.experience, user_gender=s.user_gender, coach_gender=s.coach_gender, slang=s.slang,
            say_numbers=s.say_numbers, local_completion=op.local_completion.acknowledged if op.local_completion else (),
            coach_context=op.coach_context, say_exercise_name=s.say_exercise_name,
            recent_heard=self.memory.heard(), discussed_tips=tuple(self.memory.completed_tips)[-32:],
            cross_workout_preferences=tuple(self.cross_preferences.items()) if s.memory_enabled else (),
            optional_motif=motif, motif_callback=callback, category=op.candidate.topic_family,
            character=s.persona, profanity=s.profanity and not risk, assistant_context=s.assistant_context,
            voice_markup=self.voice is not None and s.mode == "hybrid" and getattr(self.voice.adapter, "emotive", False),
            scenario=scenario.prompt_data(self.scenario_card, self.scenario_bible, op.exercise_id,
                                          finale=op.candidate.trigger_id in {"T58", "T59", "T69"},
                                          spoken=[u.text for u in self.memory.started.values()])
            if self.scenario_card and self.scenario_bible else None,
            scenario_opening=op.candidate.trigger_id == "T01" and self.scenario_bible is not None,
            mood=mood.data(), no_roast=mood.name == "recover",
            variants=(3 if op.task in THREE_VARIANT_TASKS else 2)
            if op.task in VARIANT_TASKS and self.budget_tier() < TIER_NO_VARIANTS and not self._author_slow() else 1,
            co_host=self._co_host(op, mood))

    async def _pipeline(self, op: Opportunity, max_words: int) -> None:
        warmup = None
        try:
            # Admission has already succeeded. Overlap only the transport handshake with text;
            # voice reserve/dispatch and all generation remain in the existing _run path.
            if self.settings.mode == "hybrid" and self.voice is not None and self.author is not None and self._current(op):
                warmup = asyncio.create_task(self.voice.preconnect())
            await self._run(op, max_words)
        except asyncio.CancelledError:
            self._end_state(op, 'cancelled')
            raise
        except Exception:  # A closed socket or provider bug must not leave an unobserved task error.
            self._end_state(op, 'internal_error')
            self._note("internal_error")
        finally:
            if warmup is not None:
                if not warmup.done():
                    warmup.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await warmup
            if op.state.lifecycle in {'pending', 'preparing'}:
                self._end_state(op, 'expired' if op.deadline_ms is not None and self.monotonic_ms() > op.deadline_ms else 'cancelled')

    async def _run(self, op: Opportunity, max_words: int) -> None:
        trigger, gid = op.candidate.trigger_id, secrets.token_hex(12)
        opportunity = f"{self.run_id}:{op.key}"
        if not self._current(op):
            return
        key = OPENING_KEY if trigger == "T01" else f"{trigger}:{op.exercise_id}" if op.exercise_id else None
        line = self.prebuilt.pop(key, None) if key else None
        if line is not None and self.voice is not None and self.settings.mode == "hybrid" and (
                line.exercise_name is None or line.exercise_name in {
                    f.value for f in (op.package.facts if op.package else ()) if f.id == "exercise"} or not op.package):
            await self._play_prebuilt(op, line)
            return
        if self.author is None:
            await self._decision(op.event_id, trigger, "silence", "provider_unavailable")
            return
        self._mark(op, "textStart")
        memory_epoch = self.memory_epoch
        request = self._request(op, max_words)
        try:
            outcome = await self.author.author(run_id=self.run_id, owner=self.owner, generation=self.generation,
                                               opportunity=opportunity, request=request,
                                               memory=self.memory, scope_epoch=op.scope.scope_epoch,
                                               deadline_ms=op.candidate.valid_until_ms, tier=self.budget_tier(),
                                               purpose=self._purpose(op), meta=self._journal_meta(op))
        finally:
            self._mark(op, "textEnd")
        # Some providers swallow CancelledError. Task cancellation and terminal work
        # invalidation are checked independently of the provider's returned outcome.
        if not self._current(op) or memory_epoch != self.memory_epoch:
            self._mark(op, "ackCancel")
            return
        if outcome.kind != "speech":
            await self._decision(op.event_id, trigger, "silence", outcome.reason or "no_useful_content")
            return
        co_host_text = (outcome.delivery or {}).get("co_host_text") or ""
        self.lines_since_co_host = 0 if co_host_text else self.lines_since_co_host + 1
        if self.settings.memory_enabled and outcome.attempt_ids:
            # VD.6: the spoken text joins the journal only under conversation memory, and expires with it.
            with contextlib.suppress(Exception), self.sessions() as db:
                journal.annotate(db, outcome.attempt_ids[-1], text_preview=outcome.text)
        if duplicate_local(outcome.text, op.local_completion):
            await self._decision(op.event_id, trigger, 'silence', 'no_useful_content')
            return
        # Local full/closure is not evidence that the persisted plan was met. Keep
        # partial/limited honesty even when the author chose a numeric highlight.
        if op.local_completion and op.package and op.package.outcome in {'partial', 'limited'}:
            honesty = next((f for f in op.package.facts if f.id == 'outcome'), None)
            if honesty is not None and 'outcome' not in outcome.used_fact_ids:
                outcome = replace(outcome, text=f'{honesty.claim}. {outcome.text}',
                                  used_fact_ids=(*outcome.used_fact_ids, 'outcome'))
        if not useful_addition(op.package, outcome.used_fact_ids, op.local_completion, outcome.text):
            await self._decision(op.event_id, trigger, 'silence', 'no_useful_content')
            return
        if not self._sources_current(op):
            self._mark(op, "ackCancel")
            await self._decision(op.event_id, trigger, "silence", "facts_changed")
            return
        # A local clip/another playback ACK may start while text is being authored.
        # Recheck occupancy only, not the already-consumed attempt/slot counters.
        if not self.director.playback_fits(op.candidate, self.now_ms()):
            await self._decision(op.event_id, trigger, "silence", "density_cap")
            return
        valid_for = op.candidate.valid_until_ms - self.now_ms()
        if op.deadline_ms is not None:
            valid_for = min(valid_for, op.deadline_ms - self.monotonic_ms())
        if valid_for < 1_000:
            await self._decision(op.event_id, trigger, "silence", "expired")
            return
        if self.voice is None or self.settings.mode == "text-only":
            self.stats.spoken += 1
            self._transition(op, 'ready')
            await self._decision(op.event_id, trigger, "text", None, outcome.text, event=op.event)
            return
        try:
            delivery = Delivery(**(outcome.delivery or {}))
        except (TypeError, ValueError):
            delivery = Delivery()
        s = self.settings
        # Emotive adapters (Fish drama-3) colour speech by profile through markup, not by a generative prompt.
        delivery = select_delivery(delivery, intent=outcome.intent, action=op.candidate.speech_action,
                       outcome=op.package.outcome if op.package else None,
                       enabled=situational_delivery_enabled() or getattr(self.voice.adapter, "emotive", False),
                       energy=s.voice_energy, pace=s.voice_pace)
        if getattr(self.voice.adapter, "emotive", False) and request.mood:
            # V6: mood → voice defaults, the user's sound/crowd switches and the curve between lines.
            crowd = s.crowd_effects and (self.scenario_card or {}).get("archetype") in expressive.CROWD_ARCHETYPES
            context = expressive.VoiceContext(humor=outcome.intent == "humor", roast=request.roast,
                                              mood=request.mood["name"], sounds=s.voice_sounds, crowd=crowd)
            segments = tuple(expressive.allowed(seg, context) for seg in delivery.segments)
            segments = self.voice_history.shape(segments, now_ms=self.now_ms(), exercise=op.exercise_id)
            delivery = replace(delivery, segments=segments, mood=request.mood["name"], phase=op.candidate.phase,
                               sounds=s.voice_sounds, crowd=bool(crowd))
            self.voice_history.note(segments or (expressive.base_segment(delivery.mood),), now_ms=self.now_ms(),
                                    exercise=op.exercise_id)
        voice = VoiceOutcome()
        self._transition(op, 'ready')
        self._remember(gid, op, outcome.text, outcome.used_fact_ids)
        story_motif = self._note_motif(request.optional_motif, outcome.text, op.exercise_id)
        if gid in self.acks:
            actual_motif = (request.optional_motif if request.optional_motif and (story_motif or (
                outcome.intent == "humor" and request.optional_motif.casefold() in outcome.text.casefold())) else None)
            self.line_metadata[gid] = {"intent": outcome.intent, "energy": delivery.energy,
                                       "motif": actual_motif, "callback": bool(actual_motif and request.motif_callback),
                                       "mood": (request.mood or {}).get("name")}
        checked_first_pcm = False
        try:
            await self.send_json({"type": "speech_start", "eventId": op.event_id, "triggerId": trigger,
                                  "generationId": gid, "text": outcome.text, "validForMs": round(valid_for),
                                  **({"coHostText": delivery.co_host_text} if delivery.co_host_text else {}),
                                  "sampleRate": 24_000, "source": self.voice.adapter.name,
                                  **({"identity": identity(op.event)} if op.event else {})})
            if not self._current(op):
                raise asyncio.CancelledError
            async with contextlib.aclosing(self.voice.stream(
                    run_id=self.run_id, owner=self.owner, generation=self.generation, opportunity=opportunity,
                    text=outcome.text, scope=op.scope, generation_id=gid, outcome=voice, delivery=delivery,
                    purpose=self._purpose(op), meta=self._journal_meta(op))) as frames:
                async for frame in frames:
                    self._voice_state(op, voice)
                    if not self._current(op):
                        raise asyncio.CancelledError
                    if not checked_first_pcm and decode_frame(frame).data:
                        checked_first_pcm = True
                        if not self._sources_current(op):
                            await self._decision(op.event_id, trigger, "silence", "facts_changed")
                            raise _FactsChangedError
                        self._mark(op, "firstPcm")
                    await self.send_bytes(frame)
            if not self._current(op):
                raise asyncio.CancelledError
        except _FactsChangedError:
            self._voice_state(op, voice)
            op.state.valid = False
            self._mark(op, "ackCancel")
            self._mark(op, "speechEnd")
            self._finish(gid)
            await self.send_json({"type": "speech_end", "generationId": gid, "status": "cancelled",
                                  "reason": "facts_changed", "frames": voice.frames, **self._speech_metadata(op, voice)})
            return
        except asyncio.CancelledError:
            self._voice_state(op, voice)
            op.state.valid = False
            self._mark(op, "ackCancel")
            self._mark(op, "speechEnd")
            self._finish(gid)
            with contextlib.suppress(Exception):
                await self.send_json({"type": "speech_end", "generationId": gid, "status": "cancelled",
                                      "reason": "cancelled", "frames": voice.frames, **self._speech_metadata(op, voice)})
            raise
        except Exception:
            self._voice_state(op, voice)
            op.state.valid = False
            self._mark(op, "ackCancel")
            self._mark(op, "speechEnd")
            self._finish(gid)
            with contextlib.suppress(Exception):
                await self.send_json({"type": "speech_end", "generationId": gid, "status": "failed",
                                      "reason": "internal_error", "frames": voice.frames,
                                      **self._speech_metadata(op, voice)})
            raise
        self._voice_state(op, voice)
        if voice.status == "complete":
            self.stats.spoken += 1
            if voice.first_audio_ms is not None:
                self.stats.first_audio_ms.append(voice.first_audio_ms)
        else:
            op.state.valid = False
            self._mark(op, "ackCancel")
            self._finish(gid)
            self._note(voice.reason or voice.status)
        self._mark(op, "speechEnd")
        await self.send_json({"type": "speech_end", "generationId": gid, "status": voice.status,
                              "reason": voice.reason or None, "frames": voice.frames, **self._speech_metadata(op, voice)})

    def _co_host(self, op: Opportunity, mood: Mood) -> dict | None:
        """V10: offer the co-host field only when the story has one, the user allows it and the voice can do it."""
        co = (self.scenario_bible or {}).get("coHost")
        adapter = getattr(self.voice, "adapter", None)
        if (not co or not self.settings.co_host or self.settings.mode != "hybrid" or mood.name == "recover"
                or op.candidate.phase not in CO_HOST_PHASES or self.lines_since_co_host < CO_HOST_EVERY
                or not getattr(adapter, "co_host_reference_id", "")):
            return None
        return {"role": co["role"], "name": co["name"]}

    def _author_slow(self) -> bool:
        """A degraded provider: single lines (prepared ones too, they share the 15 s bound) until it recovers."""
        return bool(self.author is not None and getattr(self.author, "slow", lambda: False)())

    def _story_motif(self, op: Opportunity) -> tuple[str, bool] | None:
        """V7.2: the next bible motif that has rested at least MOTIF_GAP_EXERCISES exercises (a running gag)."""
        if not self.scenario_bible:
            return None
        act = scenario.act_state(self.scenario_bible, op.exercise_id)
        position = act.exercise_index if act else 0
        for motif in self.scenario_bible.get("motifs", []):
            last = self.motif_uses.get(motif)
            if last is None or position - last >= MOTIF_GAP_EXERCISES:
                return motif, last is not None
        return None

    def _note_motif(self, motif: str | None, text: str, exercise_id: str | None) -> bool:
        """A motif counts as used when the line shares one of its distinctive words (≥ 5 letters)."""
        if not motif or not self.scenario_bible or motif not in self.scenario_bible.get("motifs", []):
            return False
        words = {w for w in motif.casefold().replace("ё", "е").split() if len(w) >= 5}
        spoken = text.casefold().replace("ё", "е")
        if not any(word[:-2] in spoken for word in words):
            return False
        act = scenario.act_state(self.scenario_bible, exercise_id)
        self.motif_uses[motif] = act.exercise_index if act else 0
        return True

    def _mood(self, op: Opportunity, request_facts: tuple, risk: bool) -> Mood:
        """V5: classify the moment from facts and context, then apply hysteresis."""
        context = dict(op.source_context)
        values = {f.id: f.value for f in request_facts}
        outcome = op.package.outcome if op.package and op.package.outcome != "none" else None
        previous = self.moods.note_outcome(op.exercise_id, outcome) if op.candidate.phase == "rest" and outcome else None
        act = scenario.act_state(self.scenario_bible, op.exercise_id) if self.scenario_bible else None
        total = context.get("totalSets") if isinstance(context.get("totalSets"), int) else None
        if total is None:
            total = next((f.numbers[1] for f in request_facts if f.id == "set-position" and len(f.numbers) == 2), None)
        mood = classify(trigger=op.candidate.trigger_id, task=op.task, phase=op.candidate.phase, outcome=outcome,
                        fact_ids=set(values), fact_values=values, moment=context.get("moment"),
                        last_exercise=bool(act and act.last_exercise), set_ordinal=op.scope.set_ordinal,
                        total_sets=total, previous_outcome=previous, risk=risk)
        return self.moods.update(mood, self.now_ms())

    @staticmethod
    def _journal_meta(op: Opportunity) -> dict:
        """What the panel shows next to a request: the exercise and set, never facts or prompts."""
        name = next((f.value for f in (op.package.facts if op.package else ()) if f.id == "exercise"
                     and isinstance(f.value, str)), None)
        return {"trigger_id": op.candidate.trigger_id, "task": op.task, "exercise_label": name,
                "set_ordinal": op.scope.set_ordinal}

    @staticmethod
    def _purpose(op: Opportunity) -> str:
        """Summaries may spend the reserved tail of the budget; every other line is ordinary live speech."""
        return "summary" if op.candidate.trigger_id in SUMMARY_TRIGGERS else "live"

    def _remember(self, gid: str, op: Opportunity, text: str, used: tuple[str, ...] = ()) -> None:
        if gid in self.terminal or gid in self.acks or not op.state.valid:
            return
        self.acks[gid] = (op, text, tuple(used))
        while len(self.acks) > MAX_PENDING_ACKS:
            oldest = next(iter(self.acks))
            self.acks[oldest][0].state.valid = False
            self._mark(self.acks[oldest][0], "ackCancel")
            self._finish(oldest)

    # ---------- outbound ----------

    def _note(self, reason: str) -> None:
        self.stats.reasons[reason.split(":", 1)[0]] += 1

    async def _reject(self, event_id: str | None, reason: str) -> None:
        self._note(reason)
        await self.send_json({"type": "event_rejected", "eventId": event_id, "reason": reason})

    async def _decision(self, event_id: str, trigger: str | None, action: str, reason: str | None, text: str = "", *,
                        event: CoachEvent | None = None) -> None:
        op = self.opportunities.get(event_id)
        if op is not None and action == 'silence':
            self._end_state(op, reason or 'no_useful_content')
        if reason:
            self._note(reason)
        await self.send_json({"type": "decision", "eventId": event_id, "triggerId": trigger, "action": action,
                              "reason": reason, **({"text": text} if text else {}),
                              **({"identity": identity(event)} if event else {})})


# ---------- process-local bounded memory; sockets never replay old events ----------

_ACTIVE: set[LiveCoach] = set()
_RUN_MEMORY = RunMemoryStore()
_CROSS_MEMORY = CrossWorkoutStore()


def register(coach: LiveCoach) -> None:
    coach.memory, previous_director, coach.seen = _RUN_MEMORY.attach(
        coach.user_id, coach.run_id, coach.memory, coach.director, coach.seen)
    coach.director = previous_director
    coach.director.memory = coach.memory
    coach.director.set_profile(coach.settings.density)
    coach.director.gap_scale = GAP_SCALE[coach.settings.pause_gap]
    coach.director.words_scale = WORDS_SCALE[coach.settings.verbosity]
    if not coach.settings.memory_enabled:
        coach.memory.clear()
    coach.memory.enabled = coach.settings.memory_enabled
    coach.cross_preferences = _CROSS_MEMORY.exchange(coach.user_id, coach.run_id, coach.settings)
    _ACTIVE.add(coach)


def unregister(coach: LiveCoach) -> None:
    _ACTIVE.discard(coach)


def forget_user(user_id: str) -> int:
    """Clear live AND cached runs, including in-flight publication, without resetting safety/pacing."""
    cached = _RUN_MEMORY.forget(user_id)
    _CROSS_MEMORY.forget(user_id)
    cleared = 0
    for coach in list(_ACTIVE):
        if coach.user_id == user_id:
            coach.memory.clear()
            coach.cross_preferences.clear()
            coach.memory_epoch += 1
            for op in [coach.active_op, *coach.queue, *(entry[0] for entry in coach.acks.values())]:
                if op is not None:
                    op.state.valid = False
            coach.queue.clear()
            for gid in list(coach.acks):
                coach._finish(gid)
            _RUN_MEMORY.attach(user_id, coach.run_id, coach.memory, coach.director, coach.seen)
            cleared += 1
    return max(cached, cleared)


def update_memory_preferences(user_id: str, settings: CoachPreferences) -> None:
    # Preference changes invalidate old drafts; withdrawal deletes retained data immediately.
    forget_user(user_id)
    for coach in list(_ACTIVE):
        if coach.user_id == user_id:
            coach.settings = settings
            coach.memory.enabled = settings.memory_enabled


# ---------- provider pipeline (paid only behind operator flags + verified pricing + vault key) ----------

@dataclass
class Pipeline:
    author: TextAuthor | None
    voice: VoiceStreamer | None
    reason: str | None
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def close(self) -> None:
        for close in self.closers:
            with contextlib.suppress(Exception):
                await close()


PipelineFactory = Callable[[Callable[[], Session], CoachPreferences], Awaitable[Pipeline]]


async def default_pipeline(sessions: Callable[[], Session], prefs: CoachPreferences) -> Pipeline:
    cfg = get_settings()
    pricing = text_pricing()
    if not cfg.coach_paid_text_enabled or not pricing.verified:
        return Pipeline(None, None, "provider_unavailable")
    try:
        with sessions() as db:
            key, _ = security.read_credential(db)
    except HTTPException:
        return Pipeline(None, None, "credential_unavailable")
    # Read timeout covers the slowest route (plan reasoning); TextAuthor enforces each route's own bound.
    client = httpx.AsyncClient(timeout=41, follow_redirects=False, trust_env=False)
    pipeline = Pipeline(TextAuthor(sessions, LunaTextAdapter(client, key, model=cfg.coach_text_model), pricing,
                                   model=cfg.coach_text_model, max_output_tokens=cfg.coach_text_max_output_tokens,
                                   reasoning_effort=cfg.coach_text_reasoning_effort, routes=default_routes(pricing)),
                        None, None, [client.aclose])
    if prefs.mode != "hybrid":
        return pipeline
    kind = {"openai-realtime": "realtime", "openai-tts": "tts", "fish-drama-3": "fish"}[prefs.voice_model]
    fish_key = None
    if kind == "fish":
        try:
            with sessions() as db:
                fish_key, _ = security.read_credential(db, "fish")
        except HTTPException:
            # Fish is the default voice: without its key keep speaking with the OpenAI voice, flagged.
            kind, pipeline.reason = "realtime", "voice_fallback"
    voice_price = voice_pricing(kind)
    if not (cfg.coach_paid_voice_enabled and voice_price.verified):
        pipeline.reason = "voice_unavailable"
        return pipeline
    if kind == "realtime":
        # Live speech and prepared packs share the Realtime voice timbre (decision D-E08.7).
        adapter = RealtimeVoiceAdapter(websocket_connect, key, model=cfg.coach_voice_realtime_model,
                                       voice=prefs.voice_profile,
                                       reasoning_effort=cfg.coach_voice_realtime_reasoning_effort, keep_alive=True,
                                       situational_enabled=situational_delivery_enabled())
        pipeline.closers.insert(0, adapter.aclose)
    elif kind == "tts":
        adapter = TtsVoiceAdapter(client, key, model=cfg.coach_voice_tts_model, voice=prefs.voice_profile,
                                  situational_enabled=situational_delivery_enabled())
    else:
        voice_id = prefs.fish_voice_id or persona(prefs.persona).fish_voice_id or cfg.coach_voice_fish_reference_id
        adapter = FishVoiceAdapter(client, fish_key, model=cfg.coach_voice_fish_model, reference_id=voice_id,
                                   emotion=prefs.voice_emotion,
                                   co_host_reference_id=(EKATERINA if voice_id != EKATERINA else MELLSTROY) if prefs.co_host else "")
    pipeline.voice = VoiceStreamer(sessions, adapter, voice_price)
    return pipeline
