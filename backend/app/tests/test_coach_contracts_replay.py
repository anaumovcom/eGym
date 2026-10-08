import ast
import asyncio
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.coach import (
    COACH_VOICES,
    CoachAudio,
    CoachDecision,
    CoachEvent,
    CoachEventKind,
    CoachFact,
    CoachReason,
    CoachSettings,
    CoachUsage,
)
from app.services.coach.fakes import FakeAudioManager, FakeClock, FakePackStorage, FakeTextProvider, FakeVoiceAdapter
from app.services.coach.replay import MAX_PENDING, MAX_RECEIPTS, ReplayContext, ReplayCoordinator, canonical_key

FIXTURE = Path(__file__).parent / "fixtures" / "coach_e02_replay.json"


def event_fixture() -> CoachEvent:
    return CoachEvent.model_validate(json.loads(FIXTURE.read_text())["events"][0])


def harness():
    event = event_fixture()
    clock, text, voice = FakeClock(1000), FakeTextProvider(), FakeVoiceAdapter()
    context = ReplayContext(
        event.scope, CoachSettings(enabled=True, consent_version=1), {fact.id: fact for fact in event.facts},
    )
    return event, clock, text, voice, context, ReplayCoordinator(clock, text, voice, context)


def test_wire_fixture_roundtrip_and_distinct_events():
    data = json.loads(FIXTURE.read_text())
    assert data["mode"] == "test"
    events = [CoachEvent.model_validate(item) for item in data["events"]]
    assert [event.model_dump(mode="json", by_alias=True) for event in events] == data["events"]
    assert canonical_key(events[0]) != canonical_key(events[1])


def test_typescript_vocabulary_matches_backend():
    from typing import get_args

    path = Path(__file__).resolve().parents[3] / "frontend/src/features/coach/model/contracts.ts"
    source = path.read_text()
    for name, expected in (("COACH_EVENT_KINDS", get_args(CoachEventKind)), ("COACH_REASONS", tuple(CoachReason))):
        block = source.split(f"export const {name} = [", 1)[1].split("] as const", 1)[0]
        assert tuple(re.findall(r"'([^']+)'", block)) == expected
    assert CoachSettings().model_dump(by_alias=True) == {
        "schemaVersion": 1, "enabled": False, "consentVersion": None, "mode": "local",
        "density": "companion", "count": "off", "voiceProfile": "ash", "historyConsent": False,
        "revision": 0, "budgetUsd": "2.00",
    }
    voices = source.split("export const COACH_VOICES = [", 1)[1].split("] as const", 1)[0]
    assert tuple(re.findall(r"'([^']+)'", voices)) == COACH_VOICES
    for legacy in (None, "", "female", "male"):
        assert CoachSettings(voice_profile=legacy).voice_profile == "ash"
    assert CoachSettings(voice_profile="cedar").voice_profile == "cedar"
    with pytest.raises(ValidationError):
        CoachSettings(voice_profile="robot")


@pytest.mark.parametrize("patch", [{"schemaVersion": 2}, {"extra": True}, {"startDeadlineMs": 999}, {"exerciseKind": "isometric"}, {"factDependencies": ["missing"]}])
def test_contract_rejects_bad_event(patch):
    value = event_fixture().model_dump(mode="json", by_alias=True)
    with pytest.raises(ValidationError):
        CoachEvent.model_validate({**value, **patch})


@pytest.mark.parametrize("patch", [{"confidence": "unknown"}, {"value": None}, {"value": float("nan")}, {"value": "x" * 201}])
def test_unknown_is_not_zero_and_fact_bounds(patch):
    fact = event_fixture().facts[0].model_dump()
    with pytest.raises(ValidationError):
        CoachFact.model_validate({**fact, **patch})
    assert CoachFact.model_validate({**fact, "confidence": "unknown", "value": None}).value is None


def test_usage_unknown_subsets_and_audio_bounds():
    usage = CoachUsage(attempt_id="a", ledger="test", stage="text", status="unsettled")
    assert usage.input_tokens is None and usage.cost_usd is None
    with pytest.raises(ValidationError):
        CoachUsage(attempt_id="a", ledger="test", stage="text", status="settled", input_tokens=10, cached_input_tokens=11)
    with pytest.raises(ValidationError):
        CoachDecision(action="silence", text="Not silence")
    with pytest.raises(ValidationError):
        CoachAudio(utterance_id="u", generation_id="g", scope=event_fixture().scope, sequence=0,
                   source="fake", codec="wav", sample_rate=16000, byte_length=2_880_001, duration_ms=1)


@pytest.mark.asyncio
async def test_happy_path_dedup_and_backend_aliases():
    event, _, text, voice, _, coordinator = harness()
    result = await coordinator.process(event)
    assert result.reason is None and result.decision.action == "speak"
    assert result.chunks[0].metadata.source == "fake"
    assert result.chunks[0].metadata.final
    assert coordinator.add_alias(event, 11) and coordinator.add_alias(event, 12)
    duplicate = event.model_copy(update={"id": "different-response-id", "context_version": 100})
    assert (await coordinator.process(duplicate)).reason == CoachReason.duplicate
    assert text.calls == voice.calls == 1
    assert not coordinator.add_alias(event, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("gate,reason", [
    ("disabled", CoachReason.disabled), ("consent", CoachReason.no_consent),
    ("safety", CoachReason.safety), ("muted", CoachReason.mute), ("owner", CoachReason.owner_mismatch),
    ("stale", CoachReason.stale_source), ("scope", CoachReason.scope_changed),
    ("expired", CoachReason.expired), ("live", CoachReason.mock_source),
])
async def test_hard_gates_never_call_providers(gate, reason):
    event, clock, text, voice, context, coordinator = harness()
    if gate == "disabled":
        context.settings = CoachSettings()
    if gate == "consent":
        context.settings = CoachSettings(enabled=True)
    if gate == "safety":
        context.safety_blocked = True
    if gate == "muted":
        context.muted = True
    if gate == "owner":
        context.owner = False
    if gate == "stale":
        context.source_fresh = False
    if gate == "scope":
        context.scope = context.scope.model_copy(update={"user_id": "another-user"})
    if gate == "expired":
        clock.advance(2000)
    if gate == "live":
        event = event.model_copy(update={"source": "hardware"})
    assert (await coordinator.process(event)).reason == reason
    assert (await coordinator.process(event)).reason == CoachReason.duplicate
    assert text.calls == voice.calls == 0


@pytest.mark.asyncio
async def test_context_ticks_do_not_invalidate_semantic_facts():
    event, _, _, _, context, coordinator = harness()
    context.context_version = 999
    context.plan_revision = 99  # unchanged dependencies, not global tick/revision equality
    assert (await coordinator.process(event)).reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["cancel", "scope", "fact", "deadline", "safety"])
async def test_guard_after_text_await(change):
    event, clock, text, voice, context, coordinator = harness()

    def mutate():
        if change == "cancel":
            coordinator.cancel()
        if change == "scope":
            context.scope = context.scope.model_copy(update={"scope_epoch": 2})
        if change == "fact":
            context.facts[event.facts[0].id] = event.facts[0].model_copy(update={"value": 9})
        if change == "deadline":
            clock.advance(2000)
        if change == "safety":
            context.safety_blocked = True

    text.after_generate = mutate
    assert (await coordinator.process(event)).reason is not None
    assert voice.calls == 0
    assert not coordinator.busy


@pytest.mark.asyncio
async def test_late_pcm_is_rejected_without_playback():
    event, _, _, voice, _, coordinator = harness()
    voice.before_chunk = coordinator.cancel
    result = await coordinator.process(event)
    assert result.reason == CoachReason.cancelled and result.chunks == ()


@pytest.mark.asyncio
async def test_silence_and_undeclared_claim_do_not_create_voice():
    event, _, text, voice, _, coordinator = harness()
    text.decision = CoachDecision(action="silence")
    assert (await coordinator.process(event)).decision.action == "silence"
    assert voice.calls == 0
    event2 = event.model_copy(update={"ordinal": 2})
    text.decision = CoachDecision(action="speak", text="Тест", used_fact_ids=("fake-record",))
    assert (await coordinator.process(event2)).reason == CoachReason.validation_failed
    assert voice.calls == 0


@pytest.mark.asyncio
async def test_bounded_queue_receipts_and_fake_storage():
    event, clock, text, voice, context, coordinator = harness()
    for _ in range(MAX_PENDING):
        assert coordinator.enqueue(event) is None
    assert coordinator.enqueue(event) == CoachReason.queue_full
    results = await coordinator.drain()
    assert len(results) == MAX_PENDING and sum(item.reason is None for item in results) == 1
    coordinator.receipts = {str(i) for i in range(MAX_RECEIPTS)}
    assert (await coordinator.process(event)).reason == CoachReason.queue_full
    text.test_only = False
    with pytest.raises(ValueError):
        ReplayCoordinator(clock, text, voice, context)
    with pytest.raises(ValueError):
        clock.advance(-1)
    packs, audio = FakePackStorage(), FakeAudioManager()
    assert packs.get_verified("version", "missing") is None
    audio.enqueue(results[0].chunks[0])
    audio.cancel_scope(event.scope)
    assert not audio.received


@pytest.mark.asyncio
async def test_single_flight_during_await_and_external_cancel():
    event, clock, _, voice, context, _ = harness()
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingFake:
        test_only = True

        async def generate(self, event):
            entered.set()
            await release.wait()
            return CoachDecision(action="speak", text="Тест")

    coordinator = ReplayCoordinator(clock, BlockingFake(), voice, context)
    task = asyncio.create_task(coordinator.process(event))
    await entered.wait()
    assert (await coordinator.process(event.model_copy(update={"ordinal": 1}))).reason == CoachReason.pipeline_busy
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not coordinator.busy


@pytest.mark.asyncio
async def test_stalled_fake_provider_is_bounded_and_consumed():
    event, clock, _, voice, context, _ = harness()

    class StalledFake:
        test_only = True

        async def generate(self, event):
            await asyncio.Event().wait()

    coordinator = ReplayCoordinator(clock, StalledFake(), voice, context, timeout_seconds=0.01)
    assert (await coordinator.process(event)).reason == CoachReason.provider_circuit
    assert not coordinator.busy
    assert (await coordinator.process(event)).reason == CoachReason.duplicate
    assert voice.calls == 0


def test_coach_foundation_has_no_transport_or_motor_imports():
    root = Path(__file__).resolve().parents[1]
    # E03 introduces deliberate fixed-URL metadata auth in security.py, not inference.
    files = [root / "services/coach" / name for name in ("ports.py", "fakes.py", "replay.py", "lifecycle.py")] + [root / "schemas/coach.py"]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(any(word in name for word in ("hardware", "modbus", "serial", "httpx", "requests", "socket")) for name in imports), path