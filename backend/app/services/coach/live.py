"""E10 live coach: browser event → server facts → Director → text author → voice → tagged PCM frames.

The browser is never a fact source for results: saved sets and summaries are read from the DB by owner.
One pipeline per run (paid single-flight); a summary arriving while busy waits in a 1-slot queue.
"""

import asyncio
import contextlib
import secrets
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.coach import CoachEvent, CoachScope
from app.schemas.coach_control import CoachPreferences
from app.services.coach import history, security
from app.services.coach.director import Candidate, Director
from app.services.coach.facts import AllowedFact, Comparison, FactPackage, saved_set_facts
from app.services.coach.luna import LunaTextAdapter, TextAuthor, text_pricing
from app.services.coach.memory import CoachMemory, Utterance
from app.services.coach.prompts import AuthorRequest
from app.services.coach.triggers import TRIGGERS
from app.services.coach.voice import (
    Delivery,
    RealtimeVoiceAdapter,
    VoiceOutcome,
    VoiceStreamer,
    voice_pricing,
    websocket_connect,
)

SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]

MAX_SEEN = 1024
MAX_PENDING_ACKS = 32
REST_EXTRA_MIN_MS = 35_000
SUMMARY_TRIGGERS = {"T55", "T56", "T58", "T59"}
# Saved-set trigger → P2 task. T38 (skipped) stays a local clip; T41 needs analysis opt-in (not offered).
RESULT_TASKS = {"T36": "rest/full-feedback", "T37": "rest/partial-feedback", "T39": "rest/comparison",
                "T40": "rest/comparison"}
RESULT_INTENTS = {"T36": ("factual-feedback", "motivation", "humor"), "T37": ("factual-feedback", "motivation"),
                  "T39": ("factual-feedback",), "T40": ("factual-feedback",)}


@dataclass(frozen=True)
class Opportunity:
    event_id: str
    candidate: Candidate
    task: str
    intents: tuple[str, ...]
    scope: CoachScope
    package: FactPackage | None = None
    exercise_id: str | None = None

    @property
    def key(self) -> str:
        return f"{self.candidate.trigger_id}:{self.candidate.semantic_key}"


@dataclass
class LiveStats:
    reasons: Counter = field(default_factory=Counter)
    triggers: Counter = field(default_factory=Counter)
    spoken: int = 0
    first_audio_ms: deque = field(default_factory=lambda: deque(maxlen=32))

    def as_dict(self) -> dict:
        audio = sorted(self.first_audio_ms)
        return {"spoken": self.spoken, "reasons": dict(self.reasons), "triggers": dict(self.triggers),
                "firstAudioMs": {"count": len(audio), "median": audio[len(audio) // 2] if audio else None,
                                 "max": audio[-1] if audio else None}}


def _bounded_ms(value: object, upper: float) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= upper else None


def _ref(refs: object, name: str) -> int | None:
    value = refs.get(name) if isinstance(refs, dict) else None
    return value if type(value) is int and 0 < value < 2**53 else None


class LiveCoach:
    def __init__(self, sessions: Callable[[], Session], *, run_id: str, owner: str, generation: int, user_id: str,
                 settings: CoachPreferences, author: TextAuthor | None, voice: VoiceStreamer | None,
                 send_json: SendJson, send_bytes: SendBytes, now_ms: Callable[[], float] = lambda: time.time() * 1000):
        self.sessions, self.run_id, self.owner, self.generation = sessions, run_id, owner, generation
        self.user_id, self.settings, self.author, self.voice = user_id, settings, author, voice
        self.send_json, self.send_bytes, self.now_ms = send_json, send_bytes, now_ms
        self.memory = CoachMemory()
        self.director = Director(settings.density, self.memory)
        self.task: asyncio.Task | None = None
        self.queued: Opportunity | None = None
        self.seen: set[str] = set()
        self.acks: dict[str, tuple[Opportunity, str]] = {}
        self.stats = LiveStats()
        self.closed = False

    # ---------- inbound ----------

    async def handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "event":
            await self._event(message)
        elif kind == "playback_started":
            self._started(message)
        elif kind == "playback_completed":
            gid = message.get("generationId")
            if isinstance(gid, str) and gid in self.acks:
                self.memory.note_completed(gid)
        elif kind == "playback_failed":
            self._note("playback_failed")
        elif kind == "cancel":
            await self.cancel("cancelled")
        elif kind == "safety":
            latched = message.get("latched") is True
            self.director.latch_safety(latched)
            if latched:
                self.queued = None
                await self.cancel("safety")
        elif kind == "ping":
            await self.send_json({"type": "pong", "stats": self.stats.as_dict()})
        else:
            await self.send_json({"type": "error", "reason": "unknown_message"})

    async def _event(self, message: dict) -> None:
        try:
            event = CoachEvent.model_validate(message.get("event"))
        except ValidationError:
            await self._reject(None, "invalid_event")
            return
        if event.scope.user_id != self.user_id:
            await self._reject(event.id, "owner_mismatch")
            return
        if event.id in self.seen or len(self.seen) >= MAX_SEEN:
            await self._reject(event.id, "duplicate" if event.id in self.seen else "queue_full")
            return
        self.seen.add(event.id)
        if event.kind in {"pain_reported", "safety_changed"}:
            self.director.latch_safety(True)
            self.queued = None
            await self.cancel("safety")
            return
        context = message.get("context") if isinstance(message.get("context"), dict) else {}
        try:
            with self.sessions() as db:
                opportunity = self.plan(db, event, message.get("refs"), context)
        except history.HistoryError as error:
            await self._decision(event.id, None, "silence", error.reason)
            return
        if opportunity is None:
            return  # Not a live opportunity (local cue or unmapped event): nothing to say.
        if isinstance(opportunity, str):
            await self._decision(event.id, None, "silence", opportunity)
            return
        if self.task and not self.task.done():
            if opportunity.candidate.trigger_id in SUMMARY_TRIGGERS:
                self.queued = opportunity  # Latest summary only; it is re-admitted when the pipeline frees up.
                return
            await self._decision(event.id, opportunity.candidate.trigger_id, "silence", "pipeline_busy")
            return
        await self._admit_and_start(opportunity)

    async def _admit_and_start(self, op: Opportunity) -> None:
        admission = self.director.admit(op.candidate, self.now_ms())
        if not admission.ok:
            await self._decision(op.event_id, op.candidate.trigger_id, "silence", admission.reason or "no_window")
            return
        self.director.note_admitted(op.candidate)
        self.stats.triggers[op.candidate.trigger_id] += 1
        self.task = asyncio.create_task(self._pipeline(op, admission.max_words))
        self.task.add_done_callback(self._after)

    def _after(self, task: asyncio.Task) -> None:
        if self.closed or task.cancelled() or self.queued is None:
            return
        op, self.queued = self.queued, None
        asyncio.get_running_loop().create_task(self._admit_and_start(op))

    def _started(self, message: dict) -> None:
        gid, duration = message.get("generationId"), _bounded_ms(message.get("durationMs"), 60_000)
        entry = self.acks.get(gid) if isinstance(gid, str) else None
        if entry is None:
            return
        op, text = entry
        now = self.now_ms()
        self.director.note_audible(now, duration or 2_500, content=True)
        used = {f.id: f.value for f in (op.package.facts if op.package else ())}
        self.memory.note_started(Utterance(gid, op.candidate.trigger_id, op.candidate.topic_key, text, now,
                                           duration or 2_500, exercise_id=op.exercise_id,
                                           topic_family=op.candidate.topic_family,
                                           humor="humor" in op.intents and op.candidate.trigger_id == "T46"), used)

    async def cancel(self, reason: str) -> None:
        task = self.task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            self._note(reason)

    async def close(self) -> None:
        self.closed = True
        self.queued = None
        await self.cancel("cancelled")

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

        def op(c: Candidate, task: str, intents: tuple[str, ...], package: FactPackage | None = None) -> Opportunity:
            if self.settings.humor == "off":
                intents = tuple(i for i in intents if i != "humor") or ("motivation",)
            return Opportunity(event.id, c, task, intents, scope, package, scope.exercise_id)

        epoch, valid = scope.scope_epoch, now + 60_000
        if event.kind == "workout_started":
            return op(candidate("T01", "setup", "workout-opening", hint=3_000), "setup/opening", ("motivation", "humor"))
        if event.kind == "exercise_ready":
            name = history.speakable_name(context.get("exerciseName") if isinstance(context.get("exerciseName"), str) else None)
            package = None
            if name:
                fact = AllowedFact("exercise", f"Упражнение — {name}", "confirmed", name, scope_epoch=epoch,
                                   valid_until_ms=valid)
                package = FactPackage("T04", (fact,), Comparison("unavailable"), "none")
            return op(candidate("T04", "setup", f"exercise-intro:{exercise}", hint=3_000), "setup/opening",
                      ("motivation",), package)
        if event.kind == "rep_milestone":
            if not self.settings.during_sets:
                return "disabled"
            return op(candidate("T21", "active", f"set-support:{set_key}", started=now - phase_elapsed),
                      "active/support", ("motivation", "humor"))
        if event.kind == "set_persisted":
            set_id = _ref(refs, "backendSetId")
            if set_id is None:
                return "no_source"
            saved = history.load_saved_set(db, self.user_id, set_id, history_consent=self.settings.history_consent)
            package = saved_set_facts(saved.current, saved.comparison, scope_epoch=epoch, valid_until_ms=valid,
                                      history=saved.history)
            if package.trigger_id not in RESULT_TASKS:
                return None  # Skipped set: local clip territory.
            until = now - rest_elapsed + rest_ms - 3_000 if rest_ms else None
            c = candidate(package.trigger_id, "rest", f"set-result:{set_key}", until=until, hint=4_000,
                          started=now - rest_elapsed, length=rest_ms)
            return op(c, RESULT_TASKS[package.trigger_id], RESULT_INTENTS[package.trigger_id], package)
        if event.kind == "rest_long_opportunity":
            if not self.settings.during_rest:
                return "disabled"
            if rest_ms is None or rest_ms - rest_elapsed < REST_EXTRA_MIN_MS:
                return "no_window"
            if any(gid not in self.memory.completed for gid in self.acks if self.acks[gid][0].scope == scope):
                return "utterance_pending"
            c = candidate("T46", "rest", f"rest-playful:{set_key}", until=now - rest_elapsed + rest_ms - 5_000,
                          hint=4_000, started=now - rest_elapsed, length=rest_ms)
            return op(c, "rest/playful", ("humor", "motivation"))
        if event.kind == "exercise_finalized":
            exercise_ref = _ref(refs, "backendExerciseId")
            if exercise_ref is None:
                return "no_source"
            package = history.exercise_summary(db, self.user_id, exercise_ref, scope_epoch=epoch, valid_until_ms=valid)
            return op(candidate(package.trigger_id, "summary", f"exercise-summary:{exercise}", hint=4_000),
                      "summary/exercise", ("summary",), package)
        if event.kind == "workout_finalized":
            workout_ref = _ref(refs, "backendWorkoutId")
            if workout_ref is None:
                return "no_source"
            package = history.workout_summary(db, self.user_id, workout_ref, scope_epoch=epoch, valid_until_ms=valid)
            return op(candidate(package.trigger_id, "summary", "workout-summary", hint=6_000),
                      "summary/workout", ("summary",), package)
        return None

    # ---------- pipeline ----------

    def _request(self, op: Opportunity, max_words: int) -> AuthorRequest:
        p = op.package
        s = self.settings
        dark = s.edgy_opt_in and s.humor != "off"
        return AuthorRequest(
            op.candidate.trigger_id, op.candidate.phase, op.task, op.intents, op.candidate.topic_key, max(1, max_words),
            p.facts if p else (), p.comparison.status if p else "unavailable", p.history if p else "unavailable",
            p.outcome if p and p.outcome != "none" else None, p.locked_clause if p else None,
            p.locked_fact_ids if p else (), recent_topics=tuple(self.memory.recent_topics()),
            recent_openings=tuple(self.memory.recent_openings()),
            summary=op.candidate.trigger_id in SUMMARY_TRIGGERS,
            name_allowed=bool(s.nickname), user_name=s.nickname or None, persona="sharp" if dark else "default",
            style=s.style, humor=s.humor, humor_kinds=tuple(s.humor_kinds), dark_humor=dark,
            extras=tuple(s.extras), address=s.address)

    async def _pipeline(self, op: Opportunity, max_words: int) -> None:
        try:
            await self._run(op, max_words)
        except asyncio.CancelledError:
            raise
        except Exception:  # A closed socket or provider bug must not leave an unobserved task error.
            self._note("internal_error")

    async def _run(self, op: Opportunity, max_words: int) -> None:
        trigger, gid = op.candidate.trigger_id, secrets.token_hex(12)
        opportunity = f"{self.run_id}:{op.key}"
        if self.author is None:
            await self._decision(op.event_id, trigger, "silence", "provider_unavailable")
            return
        outcome = await self.author.author(run_id=self.run_id, owner=self.owner, generation=self.generation,
                                           opportunity=opportunity, request=self._request(op, max_words),
                                           memory=self.memory, scope_epoch=op.scope.scope_epoch,
                                           deadline_ms=op.candidate.valid_until_ms)
        if outcome.kind != "speech":
            await self._decision(op.event_id, trigger, "silence", outcome.reason or "no_useful_content")
            return
        valid_for = op.candidate.valid_until_ms - self.now_ms()
        if valid_for < 1_000:
            await self._decision(op.event_id, trigger, "silence", "expired")
            return
        if self.voice is None or self.settings.mode == "text-only":
            self.stats.spoken += 1
            await self._decision(op.event_id, trigger, "text", None, outcome.text)
            return
        try:
            delivery = Delivery(**(outcome.delivery or {}))
        except (TypeError, ValueError):
            delivery = Delivery()
        voice = VoiceOutcome()
        await self.send_json({"type": "speech_start", "eventId": op.event_id, "triggerId": trigger, "generationId": gid,
                              "text": outcome.text, "validForMs": round(valid_for), "sampleRate": 24_000,
                              "source": self.voice.adapter.name})
        self._remember(gid, op, outcome.text)
        try:
            async with contextlib.aclosing(self.voice.stream(
                    run_id=self.run_id, owner=self.owner, generation=self.generation, opportunity=opportunity,
                    text=outcome.text, scope=op.scope, generation_id=gid, outcome=voice, delivery=delivery)) as frames:
                async for frame in frames:
                    await self.send_bytes(frame)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await self.send_json({"type": "speech_end", "generationId": gid, "status": "cancelled",
                                      "reason": "cancelled", "frames": voice.frames})
            raise
        if voice.status == "complete":
            self.stats.spoken += 1
            if voice.first_audio_ms is not None:
                self.stats.first_audio_ms.append(voice.first_audio_ms)
        else:
            self._note(voice.reason or voice.status)
        await self.send_json({"type": "speech_end", "generationId": gid, "status": voice.status,
                              "reason": voice.reason or None, "frames": voice.frames, "firstAudioMs": voice.first_audio_ms})

    def _remember(self, gid: str, op: Opportunity, text: str) -> None:
        self.acks[gid] = (op, text)
        while len(self.acks) > MAX_PENDING_ACKS:
            self.acks.pop(next(iter(self.acks)))

    # ---------- outbound ----------

    def _note(self, reason: str) -> None:
        self.stats.reasons[reason.split(":", 1)[0]] += 1

    async def _reject(self, event_id: str | None, reason: str) -> None:
        self._note(reason)
        await self.send_json({"type": "event_rejected", "eventId": event_id, "reason": reason})

    async def _decision(self, event_id: str, trigger: str | None, action: str, reason: str | None, text: str = "") -> None:
        if reason:
            self._note(reason)
        await self.send_json({"type": "decision", "eventId": event_id, "triggerId": trigger, "action": action,
                              "reason": reason, **({"text": text} if text else {})})


# ---------- active sockets (session-only memory lives here) ----------

_ACTIVE: set[LiveCoach] = set()


def register(coach: LiveCoach) -> None:
    _ACTIVE.add(coach)


def unregister(coach: LiveCoach) -> None:
    _ACTIVE.discard(coach)


def forget_user(user_id: str) -> int:
    """Delete memory: drop remembered phrases/topics/callbacks of every live socket of this user."""
    cleared = 0
    for coach in list(_ACTIVE):
        if coach.user_id == user_id:
            coach.memory = CoachMemory()
            coach.director.memory = coach.memory  # Pacing/safety latch stay: they are not personal memory.
            coach.acks.clear()
            cleared += 1
    return cleared


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
    client = httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False)
    pipeline = Pipeline(TextAuthor(sessions, LunaTextAdapter(client, key, model=cfg.coach_text_model), pricing,
                                   model=cfg.coach_text_model, max_output_tokens=cfg.coach_text_max_output_tokens,
                                   reasoning_effort=cfg.coach_text_reasoning_effort), None, None, [client.aclose])
    voice_price = voice_pricing("realtime")
    if prefs.mode == "hybrid":
        if cfg.coach_paid_voice_enabled and voice_price.verified:
            # Live speech and prepared packs share the Realtime voice timbre (decision D-E08.7).
            adapter = RealtimeVoiceAdapter(websocket_connect, key, model=cfg.coach_voice_realtime_model,
                                           voice=prefs.voice_profile,
                                           reasoning_effort=cfg.coach_voice_realtime_reasoning_effort, keep_alive=True)
            pipeline.voice = VoiceStreamer(sessions, adapter, voice_price)
            pipeline.closers.insert(0, adapter.aclose)
        else:
            pipeline.reason = "voice_unavailable"
    return pipeline
