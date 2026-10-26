"""Live T21 continuity through the real author/voice/ledger, with offline fake providers."""

import copy
import json
import time
from collections import Counter
from dataclasses import replace

import pytest

from app.core.config import get_settings
from app.schemas.coach import CoachEvent
from app.schemas.coach_control import CoachPreferences
from app.services.coach import ledger
from app.services.coach.live import Opportunity
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.triggers import TRIGGERS
from app.services.coach.voice import FakeVoiceStream
from app.tests.test_coach_e10_live import HYBRID, echo, event, make_coach, seed, settle, voice
from app.tests.test_coach_u04_context import DECLARATION


@pytest.fixture(autouse=True)
def enabled(use_test_emulator, monkeypatch):
    monkeypatch.setenv("COACH_ENABLED", "true")
    get_settings.cache_clear()


def support(coach, run_id, elapsed, *, kind="rep_milestone"):
    message = event(kind, run_id, set_ordinal=1, phase="active-set", context={
        **DECLARATION, "moment": "support", "phaseElapsedMs": elapsed})
    message["event"].update(exerciseKind="machine", createdAtMs=coach.now_ms(),
                            startDeadlineMs=coach.now_ms() + 20_000)
    return message


async def complete(coach, sink, clock):
    await settle(coach)
    assert sink.of("speech_start") and sink.of("speech_end"), (sink.json, coach.stats.as_dict())
    start, end = sink.of("speech_start")[-1], sink.of("speech_end")[-1]
    assert end["generationId"] == start["generationId"] and end["status"] == "complete"
    assert end["frames"] > 0
    ack = {"generationId": start["generationId"], "identity": start["identity"], "durationMs": 1_000}
    await coach.handle({"type": "playback_started", **ack})
    clock[0] += 1_000
    await coach.handle({"type": "playback_completed", **ack})
    assert start["generationId"] in coach.memory.completed
    assert coach.opportunities[start["eventId"]].state.lifecycle == "completed"
    return start


@pytest.mark.parametrize("second_elapsed", [30_000, 45_000])
async def test_distinct_support_slots_complete_and_semantic_replays_are_free(session_factory, second_elapsed):
    def script(body):
        data = json.loads(body["input"][0]["content"])
        tip = data["coachContext"]["tip"]
        output = echo(tip["text"] if tip else "Спокойно работаем дальше.")(body)
        output["usedFactIds"] = ["reviewed-tip"] if tip else []
        return output

    fake, adapter = FakeTextAuthor(script), FakeVoiceStream()
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, density="talkative"), fake_text=fake)
    coach.voice = voice(session_factory, adapter)
    # TextAuthor also compares its deadline with wall time; retain a current epoch.
    clock = [time.time() * 1000]
    phase_start = clock[0] - 15_000
    coach.now_ms = coach.monotonic_ms = lambda: clock[0]
    try:
        first = support(coach, run_id, 15_000)
        await coach.handle(first)
        start = await complete(coach, sink, clock)
        original = coach.opportunities[first["event"]["id"]]
        tip = original.coach_context.tip
        assert tip is not None and start["text"] == tip.text
        assert coach.memory.tip_completed(tip.tip_id, tip.version)

        clock[0] = phase_start + second_elapsed
        second = support(coach, run_id, second_elapsed)
        await coach.handle(second)
        await complete(coach, sink, clock)
        fallback = coach.opportunities[second["event"]["id"]]
        assert original.key != fallback.key
        assert fallback.task == "active/support" and fallback.intents == ("motivation",)
        assert fallback.coach_context.tip is None
        assert "reviewed-tip" not in fallback.coach_context.fact_ids
        assert len(fake.calls) == len(adapter.calls) == len(sink.of("speech_start")) == 2
        authored = json.loads(fake.calls[1]["input"][0]["content"])
        assert authored["intent"] == ["motivation"] and authored["coachContext"]["tip"] is None
        assert not any(f["id"] == "reviewed-tip" for f in authored["allowedFacts"])
        assert sink.of("speech_start")[1]["text"] == "Спокойно работаем дальше."

        # Retained code-selected opportunities keep their original phase start on
        # redelivery, while semantic replay remains free regardless of pacing.
        for original_message in (first, second):
            clock[0] += 12_000
            replay = copy.deepcopy(original_message)
            replay["event"].update(id=f"{original_message['event']['id']}-redelivered",
                                   createdAtMs=clock[0], startDeadlineMs=clock[0] + 20_000)
            retained = coach.opportunities[original_message["event"]["id"]]
            await coach._admit_and_start(replace(
                retained, event_id=replay["event"]["id"], event=CoachEvent.model_validate(replay["event"]),
                received_ms=clock[0], deadline_ms=clock[0] + 20_000,
                candidate=replace(retained.candidate, created_ms=clock[0], valid_until_ms=clock[0] + 20_000)))
            assert sink.of("decision")[-1]["reason"] in {"topic_repeat", "duplicate"}
        # Unmodified inbound event replay also reaches semantic topic deduplication.
        for original_message in (first, second):
            clock[0] += 12_000
            replay = copy.deepcopy(original_message)
            replay["event"].update(id=f"{original_message['event']['id']}-inbound-replay",
                                   createdAtMs=clock[0], startDeadlineMs=clock[0] + 20_000)
            await coach.handle(replay)
            assert sink.of("decision")[-1]["reason"] == "topic_repeat"
        await settle(coach)
        assert len(fake.calls) == len(adapter.calls) == 2
        assert len(sink.of("speech_start")) == len(sink.of("speech_end")) == 2
        with session_factory() as db:
            attempts = ledger.snapshot(db, run_id)["attempts"]
        assert len(attempts) == 4
        assert Counter(a["stage"] for a in attempts) == {"text": 2, "voice": 2}
        assert all(a["status"] == "settled" for a in attempts)
    finally:
        await coach.close()


@pytest.mark.parametrize("density", ["quiet", "companion", "talkative", "show"])
async def test_short_set_distinct_dense_events_are_admitted_for_all_profiles(session_factory, density):
    lines = iter(("Спокойно работаем дальше.", "Этот участок проходим в своём ритме."))
    fake = FakeTextAuthor(lambda body: echo(next(lines))(body))
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(
        **HYBRID, density=density, pause_gap="short"), fake_text=fake)
    adapter = FakeVoiceStream()
    coach.voice = voice(session_factory, adapter)
    clock = [time.time() * 1000]
    phase_start = clock[0] - 15_000
    coach.now_ms = coach.monotonic_ms = lambda: clock[0]
    try:
        first = support(coach, run_id, 15_000)
        first["context"]["exerciseSlug"] = "unknown"  # Support only, without a reviewed tip.
        await coach.handle(first)
        await complete(coach, sink, clock)
        # Still within the old cooldown and <30 s slot cap.
        clock[0] = phase_start + 17_000
        second = support(coach, run_id, 17_000)
        second["context"]["moment"] = "half"
        await coach.handle(second)
        await complete(coach, sink, clock)
        assert len(fake.calls) == len(adapter.calls) == 2
    finally:
        await coach.close()


def test_keys_partition_only_t21_topics_and_keep_saved_results_canonical(session_factory):
    coach, _, run_id = make_coach(session_factory)
    with session_factory() as db:
        message = support(coach, run_id, 15_000)
        op = coach.plan(db, CoachEvent.model_validate(message["event"]), None, message["context"])
        _, _, set_id = seed(db, actual=10, planned=10, status="completed")
        saved = event("set_persisted", run_id, set_ordinal=1, phase="rest")
        result = coach.plan(db, CoachEvent.model_validate(saved["event"]), {"backendSetId": set_id}, {})
    assert isinstance(op, Opportunity) and isinstance(result, Opportunity)
    assert TRIGGERS["T21"].max_per_scope is None
    assert replace(op, event_id="new-client-event").key == op.key
    assert replace(op, candidate=replace(op.candidate, topic_key=op.candidate.topic_key + ":other")).key != op.key
    # Even a very long scoped topic produces a bounded ledger key, run prefix included.
    long = replace(op, candidate=replace(op.candidate, topic_key="run:set:" + "текст" * 2_000))
    assert len(f"{'r' * 120}:{long.key}") <= 1024
    assert result.key == f"{result.candidate.trigger_id}:{result.candidate.semantic_key}"
    assert replace(result, event_id="redelivery", candidate=replace(
        result.candidate, topic_key="changed-client-topic")).key == result.key
    for trigger in TRIGGERS.keys() - {"T21"}:
        other = replace(op, candidate=replace(op.candidate, trigger_id=trigger))
        assert other.key == f"{trigger}:{op.candidate.semantic_key}"


def test_real_pilot_result_quantity_before_full_outcome_is_not_a_plan_quantity(session_factory):
    from app.services.coach.prompts import build_prompt
    from app.services.coach.validation import validate
    from app.tests.test_coach_e10_live import plan

    with session_factory() as db:
        _, _, sid = seed(db, actual=10, planned=10, status="completed")
    coach, _, run_id = make_coach(session_factory)
    op = plan(coach, run_id, "set_persisted", set_ordinal=1, phase="rest", refs={"backendSetId": sid})
    req = coach._request(op, 30)
    payload = echo("Десять повторений — план подхода выполнен. Хорошая точка.")(
        {"input": [{"content": build_prompt(req).data}]})
    payload["usedFactIds"] = ["saved-set", "outcome"]
    assert validate(payload, req).ok
    for text in ("Десять повторений — план миссии выполнен.", "Десять повторений — и план выполнен!"):
        assert validate({**payload, "text": text}, req).ok, text  # a world word for the plan (live run 26.10.2026)
    assert not validate({**payload, "text": "Десять повторений — план на завтра выполнен заранее."}, req).ok
    assert not validate(payload, replace(req, outcome="partial")).ok
    assert not validate({**payload, "text": "Десять килограммов — план подхода выполнен."}, req).ok
    assert not validate({**payload, "usedFactIds": ["target", "outcome"]}, req).ok


def test_later_support_prompt_does_not_offer_an_already_heard_fact(session_factory):
    from app.services.coach.facts import memory_key

    coach, _, run_id = make_coach(session_factory)
    message = support(coach, run_id, 30_000)
    message["context"]["exerciseSlug"] = "unknown"
    with session_factory() as db:
        op = coach.plan(db, CoachEvent.model_validate(message["event"]), None, message["context"])
    milestone = next(f for f in op.package.facts if f.id == "milestone")
    coach.memory.fact_mentions[(memory_key(milestone), repr(milestone.value))] = 1
    request = coach._request(op, 16)
    assert "milestone" not in {f.id for f in request.facts}
    assert op.package.facts  # Persisted semantic source revalidation was not mutated.
    assert request.task == "active/support" and request.intents == ("motivation",)