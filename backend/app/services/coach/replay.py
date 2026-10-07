"""Deterministic TEST-ONLY admission harness, never mounted as an API or run by app startup."""

import asyncio
import json
import math
from collections import deque
from dataclasses import dataclass, field

from app.schemas.coach import CoachDecision, CoachEvent, CoachFact, CoachReason, CoachScope, CoachSettings
from app.services.coach.ports import AudioChunk, Clock, TextProvider, VoiceAdapter

MAX_RECEIPTS = 1024
MAX_PENDING = 32
MAX_AUDIO_BYTES = 2_880_000


def canonical_key(event: CoachEvent) -> str:
    scope = event.scope
    workout = event.kind in {"workout_finalized", "workout_started"}
    exercise = event.kind in {"exercise_finalized", "exercise_ready"}
    return json.dumps(
        [scope.user_id, scope.run_id, None if workout else scope.exercise_id,
         None if workout or exercise else scope.set_ordinal, event.kind, event.ordinal],
        ensure_ascii=False, separators=(",", ":"),
    )


def fact_signature(fact: CoachFact) -> tuple[object, ...]:
    return fact.value, fact.unit, fact.source, fact.confidence, fact.scope_epoch


@dataclass
class ReplayContext:
    scope: CoachScope
    settings: CoachSettings = field(default_factory=CoachSettings)
    facts: dict[str, CoachFact] = field(default_factory=dict)
    plan_revision: int = 0
    context_version: int = 0
    safety_blocked: bool = False
    source_fresh: bool = True
    owner: bool = True
    muted: bool = False


@dataclass(frozen=True)
class ReplayResult:
    event_id: str
    reason: CoachReason | None = None
    decision: CoachDecision | None = None
    chunks: tuple[AudioChunk, ...] = ()


class ReplayCoordinator:
    def __init__(self, clock: Clock, text: TextProvider, voice: VoiceAdapter, context: ReplayContext, timeout_seconds: float = 5):
        if not text.test_only or not voice.test_only:
            raise ValueError("Replay accepts only explicit test providers")
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 5:
            raise ValueError("Invalid test provider timeout")
        self.clock, self.text, self.voice, self.context = clock, text, voice, context
        self.timeout_seconds = timeout_seconds
        self.receipts: set[str] = set()
        self.aliases: dict[str, str] = {}
        self.pending: deque[CoachEvent] = deque()
        self.busy = False
        self.generation = 0

    def cancel(self) -> None:
        self.generation += 1
        self.pending.clear()

    def add_alias(self, event: CoachEvent, backend_set_id: int) -> bool:
        if backend_set_id <= 0:
            return False
        key = canonical_key(event)
        alias = json.dumps([event.scope.user_id, "set", backend_set_id])
        if key not in self.receipts or (alias in self.aliases and self.aliases[alias] != key):
            return False
        if alias not in self.aliases and len(self.aliases) >= MAX_RECEIPTS:
            return False
        self.aliases[alias] = key
        return True

    def enqueue(self, event: CoachEvent) -> CoachReason | None:
        if len(self.pending) >= MAX_PENDING:
            return CoachReason.queue_full
        self.pending.append(event)
        return None

    def gate(self, event: CoachEvent, generation: int) -> CoachReason | None:
        ctx, now = self.context, self.clock.now_ms()
        if generation != self.generation:
            return CoachReason.cancelled
        if not ctx.settings.enabled:
            return CoachReason.disabled
        if ctx.settings.consent_version is None:
            return CoachReason.no_consent
        if ctx.safety_blocked:
            return CoachReason.safety
        if ctx.muted:
            return CoachReason.mute
        if not ctx.owner:
            return CoachReason.owner_mismatch
        if event.source not in {"synthetic", "recorded"}:
            return CoachReason.mock_source
        if event.scope != ctx.scope:
            return CoachReason.scope_changed
        if now < event.created_at_ms:
            return CoachReason.no_window
        if now >= event.start_deadline_ms:
            return CoachReason.expired
        if not ctx.source_fresh:
            return CoachReason.stale_source
        facts = {fact.id: fact for fact in event.facts}
        for fact_id in event.fact_dependencies:
            expected, current = facts[fact_id], ctx.facts.get(fact_id)
            if expected.confidence == "unknown" or current is None or current.confidence == "unknown":
                return CoachReason.validation_failed
            if expected.scope_epoch != ctx.scope.scope_epoch or fact_signature(expected) != fact_signature(current):
                return CoachReason.scope_changed
            if now < current.observed_at_ms or now >= min(expected.valid_until_ms, current.valid_until_ms):
                return CoachReason.stale_source
        return None

    async def process(self, event: CoachEvent) -> ReplayResult:
        if self.busy:
            return ReplayResult(event.id, CoachReason.pipeline_busy)
        key = canonical_key(event)
        if key in self.receipts:
            return ReplayResult(event.id, CoachReason.duplicate)
        if len(self.receipts) >= MAX_RECEIPTS:
            return ReplayResult(event.id, CoachReason.queue_full)
        self.receipts.add(key)  # skipped/failed opportunities are consumed; no replay backlog
        generation = self.generation
        reason = self.gate(event, generation)
        if reason:
            return ReplayResult(event.id, reason)
        self.busy = True
        try:
            return await asyncio.wait_for(self._generate(event, generation), timeout=self.timeout_seconds)
        except TimeoutError:
            return ReplayResult(event.id, CoachReason.provider_circuit)
        finally:
            self.busy = False

    async def _generate(self, event: CoachEvent, generation: int) -> ReplayResult:
        try:
            decision = await self.text.generate(event)
            reason = self.gate(event, generation)
            if reason:
                return ReplayResult(event.id, reason)
            if not set(decision.used_fact_ids).issubset(event.fact_dependencies):
                return ReplayResult(event.id, CoachReason.validation_failed)
            if decision.action == "silence":
                return ReplayResult(event.id, decision=decision)
            chunks: list[AudioChunk] = []
            byte_count, duration_ms, next_sequence = 0, 0.0, 0
            generation_id = f"replay-{generation}-{len(self.receipts)}"
            async for chunk in self.voice.stream(decision.text, event.scope, generation_id):
                reason = self.gate(event, generation)
                if reason:
                    return ReplayResult(event.id, reason)
                meta = chunk.metadata
                if (meta.scope != event.scope or meta.generation_id != generation_id or meta.source != "fake"
                        or meta.sequence != next_sequence or meta.byte_length != len(chunk.data)
                        or (chunks and chunks[-1].metadata.final)):
                    return ReplayResult(event.id, CoachReason.validation_failed)
                byte_count += len(chunk.data)
                duration_ms += meta.duration_ms
                if byte_count > MAX_AUDIO_BYTES or duration_ms > 60_000 or next_sequence >= 256:
                    return ReplayResult(event.id, CoachReason.queue_full)
                next_sequence += 1
                chunks.append(chunk)
            reason = self.gate(event, generation)
            if reason:
                return ReplayResult(event.id, reason)
            if not chunks or not chunks[-1].metadata.final:
                return ReplayResult(event.id, CoachReason.validation_failed)
            return ReplayResult(event.id, decision=decision, chunks=tuple(chunks))
        except Exception:
            # A fake failure is bounded and non-retrying; no transport/body logging.
            return ReplayResult(event.id, CoachReason.provider_circuit)

    async def drain(self) -> tuple[ReplayResult, ...]:
        results = []
        while self.pending:
            results.append(await self.process(self.pending.popleft()))
        return tuple(results)