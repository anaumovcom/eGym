"""E10 live coach: DB-backed facts, single-flight pipeline, socket protocol. Synthetic adapters only."""

import asyncio
import copy
import itertools
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.routes.coach import get_live_factory
from app.core.config import get_settings
from app.schemas.coach_control import CoachPreferences, PreferencesSave
from app.schemas.runtime import ExerciseSessionCreateSchema, SetResultSaveSchema, WorkoutSessionCreateSchema
from app.services.coach import history, ledger, live
from app.services.coach.live import LiveCoach, Pipeline
from app.services.coach.luna import FakeTextAuthor, TextAuthor
from app.services.coach.preferences import save_preferences
from app.services.coach.voice import FakeVoiceStream, RealtimeVoiceAdapter, VoiceOutcome, VoiceStreamer
from app.services.runtime_service import RuntimeService
from app.tests.test_coach_control_plane import ORIGIN
from app.tests.test_coach_e07_author import PRICE as TEXT_PRICE
from app.tests.test_coach_e08_voice import PRICE as VOICE_PRICE
from app.tests.test_coach_e08_voice import FakeSocket, realtime_events

HYBRID = {"enabled": True, "consent_version": 1, "network_consent_version": 1, "mode": "hybrid"}
_ids = itertools.count(1)


@pytest.fixture(autouse=True)
def coach_enabled(use_test_emulator, monkeypatch):
    monkeypatch.setenv("COACH_ENABLED", "true")
    get_settings.cache_clear()


def echo(text="Поехали, спокойно и собранно."):
    def script(body):
        data = json.loads(body["input"][0]["content"])
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": list(data["lockedFactIds"]), "silenceReason": None,
                "delivery": {"energy": "warm", "pace": "normal", "emphasis": "result"}, key: text}
    return script


def text_author(session_factory, fake=None):
    return TextAuthor(session_factory, fake or FakeTextAuthor(echo()), TEXT_PRICE, model=TEXT_PRICE.model, timeout_s=2)


def voice(session_factory, fake=None):
    return VoiceStreamer(session_factory, fake or FakeVoiceStream(), VOICE_PRICE)


class Sink:
    def __init__(self):
        self.json: list[dict] = []
        self.bytes: list[bytes] = []

    async def send_json(self, payload):
        self.json.append(payload)

    async def send_bytes(self, data):
        self.bytes.append(data)

    def of(self, kind):
        return [m for m in self.json if m["type"] == kind]


def new_run(session_factory, kind="test"):
    with session_factory() as db:
        row, token = ledger.create_run(db, "alexey", kind, "2.00")
        run_id = row.id
        db.rollback()
        generation = ledger.lease(db, run_id, "tab-a", 0)["generation"]
    return run_id, generation, token


def make_coach(session_factory, prefs=None, *, author=True, streamer=True, fake_text=None):
    run_id, generation, _ = new_run(session_factory)
    sink = Sink()
    coach = LiveCoach(session_factory, run_id=run_id, owner="tab-a", generation=generation, user_id="alexey",
                      settings=prefs or CoachPreferences(**HYBRID),
                      author=text_author(session_factory, fake_text) if author else None,
                      voice=voice(session_factory) if streamer else None,
                      send_json=sink.send_json, send_bytes=sink.send_bytes)
    return coach, sink, run_id


def event(kind, run_id, *, exercise="ex-1", set_ordinal=None, epoch=1, phase="setup", user="alexey", **extra):
    now = time.time() * 1000
    return {"type": "event", "event": {
        "id": f"{kind}-{next(_ids)}", "kind": kind, "phase": phase, "source": "runtime_ack",
        "scope": {"userId": user, "runId": run_id, "exerciseId": exercise, "setOrdinal": set_ordinal, "scopeEpoch": epoch},
        "createdAtMs": now, "startDeadlineMs": now + 20_000}, **extra}


def seed(db, *, days_ago=0, actual=8, planned=10, status="partial", name="Тяга сверху"):
    service = RuntimeService()
    started = datetime.now(UTC) - timedelta(days=days_ago)
    workout = service.save_workout_session(db, WorkoutSessionCreateSchema(
        user_id="alexey", source="catalog", title="Synthetic", started_at=started, status="in_progress"))
    exercise = service.save_exercise_session(db, ExerciseSessionCreateSchema(
        user_id="alexey", workout_session_id=workout.workout_session_id, exercise_slug="machine-pulldown",
        exercise_name=name, kind="machine", status="completed" if status == "completed" else "partial",
        started_at=started, target_sets=1, training_mode="constant")).exercise_session.id
    saved = service.save_set_result(db, SetResultSaveSchema(
        exercise_session_id=exercise, set_number=1, planned_value=planned, actual_value=actual, reps=actual,
        weight_kg=20, tempo_label="unknown", set_type="working",
        machine_metrics={"completionStatus": status, "loadMode": "constant", "rangeId": "fixture-range",
                 "calibrationId": "fixture-calibration", "countMethod": "sensor"}))
    return workout.workout_session_id, exercise, saved.set_id


async def settle(coach):
    for _ in range(100):
        task = coach.task
        if task is not None and not task.done():
            await task
        await asyncio.sleep(0.01)
        if (coach.task is None or coach.task.done()) and coach.queued is None:
            return


# ---------- history ----------

def test_saved_set_history_needs_consent_and_owner(db_session):
    seed(db_session, days_ago=7, actual=8, planned=10, status="partial")
    _, _, set_id = seed(db_session, actual=10, planned=10, status="completed")
    without = history.load_saved_set(db_session, "alexey", set_id, history_consent=False)
    assert without.history == "unavailable" and without.previous is None and without.comparison.status == "unavailable"
    assert without.exercise_name == "Тяга сверху" and without.current.outcome == "completed"
    with_consent = history.load_saved_set(db_session, "alexey", set_id, history_consent=True)
    assert with_consent.history == "available" and with_consent.previous.value == 8
    with pytest.raises(history.HistoryError, match="owner_mismatch"):
        history.load_saved_set(db_session, "somebody-else", set_id, history_consent=True)
    first = history.load_saved_set(db_session, "alexey", set_id - 1, history_consent=True)
    assert first.history == "empty_confirmed"
    assert history.speakable_name("Lat pulldown") is None and history.speakable_name("Жим ногами") == "Жим ногами"


def test_summaries_are_built_from_db_rows(db_session):
    workout_id, exercise_id, _ = seed(db_session, actual=8, planned=10, status="partial")
    package = history.exercise_summary(db_session, "alexey", exercise_id, scope_epoch=1, valid_until_ms=10**13)
    assert package.trigger_id == "T56" and {f.id for f in package.facts} >= {"sets-done", "best-set", "outcome", "exercise"}
    total = history.workout_summary(db_session, "alexey", workout_id, scope_epoch=1, valid_until_ms=10**13)
    assert total.trigger_id == "T59" and total.facts[0].value == 1
    with pytest.raises(history.HistoryError, match="owner_mismatch"):
        history.workout_summary(db_session, "intruder", workout_id, scope_epoch=1, valid_until_ms=10**13)


# ---------- live coach ----------

async def test_opening_streams_tagged_audio_and_acks_update_memory(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    await coach.handle(event("workout_started", run_id))
    await settle(coach)
    assert sink.of("speech_start"), (sink.json, coach.stats.as_dict())
    start, end = sink.of("speech_start")[0], sink.of("speech_end")[0]
    assert start["triggerId"] == "T01" and start["text"] and start["sampleRate"] == 24_000 and start["source"] == "fake"
    assert end["generationId"] == start["generationId"] and end["status"] == "complete" and end["frames"] == len(sink.bytes) > 0
    await coach.handle({"type": "playback_started", "generationId": start["generationId"], "durationMs": 2_000})
    await coach.handle({"type": "playback_completed", "generationId": start["generationId"]})
    assert start["generationId"] in coach.memory.completed
    await coach.handle({"type": "ping"})
    assert sink.of("pong")[0]["stats"]["spoken"] == 1
    await coach.handle({"type": "nope"})
    assert sink.of("error")[-1]["reason"] == "unknown_message"


async def test_foreign_duplicate_and_invalid_events_are_rejected(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    await coach.handle(event("workout_started", run_id, user="intruder"))
    message = event("exercise_ready", run_id, context={"exerciseName": "Тяга сверху"})
    await coach.handle(message)
    await settle(coach)
    await coach.handle(message)
    await coach.handle({"type": "event", "event": {"id": "x"}})
    assert [m["reason"] for m in sink.of("event_rejected")] == ["owner_mismatch", "duplicate", "invalid_event"]


async def test_saved_set_uses_db_comparison_with_locked_clause(session_factory):
    with session_factory() as db:
        seed(db, days_ago=7, actual=8, planned=8, status="completed")
        _, _, set_id = seed(db, actual=10, planned=10, status="completed")
    fake = FakeTextAuthor(echo("Хороший шаг вперёд."))
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, history_consent=True), fake_text=fake)
    await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id},
                             context={"restMs": 90_000, "restElapsedMs": 2_000}))
    await settle(coach)
    start = sink.of("speech_start")[0]
    assert start["triggerId"] in {"T39", "T40"}
    sent = json.loads(fake.calls[0]["input"][0]["content"])
    assert sent["mode"] == "locked_fact" and sent["lockedFactClause"] and sent["comparisonStatus"] == "comparable"
    assert start["text"].startswith(sent["lockedFactClause"])
    # Browser cannot point at another user's rows or invent result IDs.
    await coach.handle(event("set_persisted", run_id, set_ordinal=2, phase="rest", refs={"backendSetId": 999_999}))
    await coach.handle(event("set_persisted", run_id, set_ordinal=3, phase="rest", refs={"backendSetId": "1"}))
    assert [m["reason"] for m in sink.of("decision")[-2:]] == ["owner_mismatch", "no_source"]


async def test_busy_pipeline_skips_ordinary_but_queues_summary(session_factory):
    with session_factory() as db:
        _, exercise_id, _ = seed(db, actual=10, planned=10, status="completed")
    slow = FakeTextAuthor(echo(), delay_s=0.2)
    coach, sink, run_id = make_coach(session_factory, fake_text=slow)
    await coach.handle(event("workout_started", run_id))
    await coach.handle(event("rep_milestone", run_id, set_ordinal=1, phase="active-set"))
    await coach.handle(event("exercise_finalized", run_id, phase="exercise-summary",
                             refs={"backendExerciseId": exercise_id}))
    assert sink.of("decision")[0]["reason"] == "pipeline_busy" and coach.queued is not None
    await settle(coach)
    assert [m["triggerId"] for m in sink.of("speech_start")] == ["T01", "T55"]


async def test_safety_cancels_speech_and_latches(session_factory):
    slow = FakeTextAuthor(echo(), delay_s=1)
    coach, sink, run_id = make_coach(session_factory, fake_text=slow)
    await coach.handle(event("workout_started", run_id))
    await asyncio.sleep(0.05)
    await coach.handle({"type": "safety", "latched": True})
    assert coach.task.done() and coach.stats.reasons["safety"] == 1 and not sink.of("speech_start")
    await coach.handle(event("exercise_ready", run_id, exercise="ex-2"))
    assert sink.of("decision")[-1]["reason"] == "safety"
    with session_factory() as db:
        assert ledger.snapshot(db, run_id)["pendingMicros"] >= 0


@pytest.mark.parametrize("cancel", ["safety", "scope", "close"])
async def test_preconnect_overlaps_blocked_author_and_is_joined_on_cancel(session_factory, cancel):
    coach, sink, run_id = make_coach(session_factory)
    author_started, warmup_started = asyncio.Event(), asyncio.Event()
    author_cleaned, warmup_cleaned = asyncio.Event(), asyncio.Event()
    warmup_tasks = []
    original = coach.author.author

    async def blocked_author(**kwargs):
        outcome = await original(**kwargs)
        author_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass  # Even a broken provider must not publish or dispatch voice after cancellation.
        finally:
            author_cleaned.set()
        return outcome

    class Warmable(FakeVoiceStream):
        async def preconnect(self):
            warmup_tasks.append(asyncio.current_task())
            warmup_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                warmup_cleaned.set()

    adapter = Warmable()
    coach.author.author = blocked_author
    coach.voice = voice(session_factory, adapter)
    message = event("workout_started", run_id)
    message["event"].update(planRevision=1, contextVersion=1)
    await coach.handle(live_context(message))
    try:
        await coach.handle(message)
        await asyncio.wait_for(author_started.wait(), 2)
        await asyncio.wait_for(warmup_started.wait(), 1)
        assert not author_cleaned.is_set() and not warmup_cleaned.is_set()
        assert not adapter.calls and not sink.bytes
        if cancel == "scope":
            await coach.handle(live_context(message, version=2, blocked=True))
        elif cancel == "safety":
            await coach.handle({"type": "safety", "latched": True})
        else:
            await coach.close()
        assert coach.task.done() and author_cleaned.is_set() and warmup_cleaned.is_set()
        assert len(warmup_tasks) == 1 and warmup_tasks[0].done()
        assert not adapter.calls and not sink.of("speech_start") and not sink.bytes
        with session_factory() as db:
            assert not [a for a in ledger.snapshot(db, run_id)["attempts"] if a["stage"] == "voice"]
    finally:
        await coach.close()


@pytest.mark.parametrize("warmup", ["complete", "error", "timeout"])
async def test_preconnect_best_effort_preserves_live_generation(session_factory, warmup):
    coach, sink, run_id = make_coach(session_factory)
    cleaned = asyncio.Event()
    original = coach.author.author

    class Warmable(FakeVoiceStream):
        async def preconnect(self):
            try:
                if warmup == "error":
                    raise OSError("synthetic warmup failure")
                if warmup == "timeout":
                    await asyncio.Event().wait()
            finally:
                cleaned.set()

    async def delayed_author(**kwargs):
        await asyncio.wait_for(cleaned.wait(), 1)
        return await original(**kwargs)

    adapter = Warmable()
    coach.voice = VoiceStreamer(session_factory, adapter, VOICE_PRICE, first_audio_timeout_s=0.01)
    coach.author.author = delayed_author
    try:
        await coach.handle(event("workout_started", run_id))
        await settle(coach)
        assert cleaned.is_set() and adapter.calls and sink.bytes
        assert sink.of("speech_end")[-1]["status"] == "complete"
        assert not coach.stats.reasons["internal_error"]
    finally:
        await coach.close()


@pytest.mark.parametrize("cancel", [False, True])
async def test_completed_live_preconnect_keeps_socket_and_dispatches_only_after_author(session_factory, cancel):
    coach, sink, run_id = make_coach(session_factory)
    connected, author_waiting = asyncio.Event(), asyncio.Event()
    socket = FakeSocket(realtime_events())
    original = coach.author.author

    async def connect(url, headers):
        connected.set()
        return socket

    adapter = RealtimeVoiceAdapter(connect, "synthetic-key", model="mock-realtime", voice="v", keep_alive=True)
    adapter.test_only = True  # Only scripted transport; production dispatch is unchanged.
    coach.voice = voice(session_factory, adapter)

    async def blocked_author(**kwargs):
        outcome = await original(**kwargs)
        await asyncio.wait_for(connected.wait(), 1)
        assert socket.sent == [] and adapter._socket is socket
        with session_factory() as db:
            assert not [a for a in ledger.snapshot(db, run_id)["attempts"] if a["stage"] == "voice"]
        author_waiting.set()
        if cancel:
            await asyncio.Event().wait()
        return outcome

    coach.author.author = blocked_author
    try:
        await coach.handle(event("workout_started", run_id))
        await asyncio.wait_for(author_waiting.wait(), 2)
        if cancel:
            await coach.cancel("cancelled")
            assert not sink.of("speech_start") and socket.sent == []
        else:
            await settle(coach)
            end = sink.of("speech_end")[-1]
            assert end["status"] == "complete" and end["connectionClass"] == "warm"
            assert [frame["type"] for frame in socket.sent] == ["response.create"]
            with session_factory() as db:
                assert [a["status"] for a in ledger.snapshot(db, run_id)["attempts"]
                        if a["stage"] == "voice"] == ["settled"]
        assert coach.task.done() and adapter.connects == 1 and not socket.closed
        assert adapter._socket is socket
    finally:
        await coach.close()
        await adapter.aclose()


@pytest.mark.parametrize("gate", ["text-only", "no-author", "safety"])
async def test_preconnect_only_for_admitted_hybrid_voice_opportunity(session_factory, gate):
    prefs = CoachPreferences(**{**HYBRID, "mode": "text-only" if gate == "text-only" else "hybrid"})
    coach, _, run_id = make_coach(session_factory, prefs, author=gate != "no-author")
    calls = []

    async def preconnect():
        calls.append(True)

    coach.voice.preconnect = preconnect
    try:
        if gate == "safety":
            await coach.handle({"type": "safety", "latched": True})
        await coach.handle(event("workout_started", run_id))
        await settle(coach)
        assert calls == []
    finally:
        await coach.close()


async def test_text_only_and_missing_provider_degrade_honestly(session_factory):
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**{**HYBRID, "mode": "text-only"}))
    await coach.handle(event("workout_started", run_id))
    await settle(coach)
    decision = sink.of("decision")[-1]
    assert decision["action"] == "text" and decision["text"] and not sink.bytes and not sink.of("speech_start")
    silent, sink2, run2 = make_coach(session_factory, author=False, streamer=False)
    await silent.handle(event("workout_started", run2))
    await settle(silent)
    assert sink2.of("decision")[-1]["reason"] == "provider_unavailable"
    pipeline = await live.default_pipeline(session_factory, CoachPreferences(**HYBRID))
    assert pipeline.author is None and pipeline.voice is None and pipeline.reason == "provider_unavailable"


async def test_preferences_shape_opportunities(session_factory):
    quiet = CoachPreferences(**HYBRID, during_sets=False, during_rest=False, humor="off")
    coach, sink, run_id = make_coach(session_factory, quiet)
    await coach.handle(event("rep_milestone", run_id, set_ordinal=1, phase="active-set"))
    await coach.handle(event("rest_long_opportunity", run_id, set_ordinal=1, phase="rest",
                             context={"restMs": 120_000, "restElapsedMs": 10_000}))
    assert [m["reason"] for m in sink.of("decision")] == ["disabled", "disabled"]
    with session_factory() as db:
        planned = coach.plan(db, live.CoachEvent.model_validate(event("workout_started", run_id)["event"]), None, {})
    assert "humor" not in planned.intents
    chatty, sink2, run2 = make_coach(session_factory)
    await chatty.handle(event("rest_long_opportunity", run2, set_ordinal=1, phase="rest",
                              context={"restMs": 60_000, "restElapsedMs": 40_000}))
    assert sink2.of("decision")[-1]["reason"] == "no_window"


def add_set(db, exercise_id, set_number, *, actual=10, planned=10, weight=20.0, low=None, high=None):
    return RuntimeService().save_set_result(db, SetResultSaveSchema(
        exercise_session_id=exercise_id, set_number=set_number, planned_value=planned, actual_value=actual, reps=actual,
        weight_kg=weight, tempo_label="unknown", machine_metrics={"completionStatus": "completed"},
        target_min_reps=low, target_max_reps=high)).set_id


def plan(coach, run_id, kind, **kwargs):
    message = event(kind, run_id, **kwargs)
    with coach.sessions() as db:
        return coach.plan(db, live.CoachEvent.model_validate(message["event"]), message.get("refs"),
                          message.get("context", {}))


@pytest.mark.parametrize("timed", [False, True])
def test_regular_active_advice_has_useful_task_and_bounded_distinct_topics(session_factory, timed):
    coach, _, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, density="talkative"))

    def advice(elapsed):
        message = event("rep_milestone", run_id, set_ordinal=1, phase="active-set",
                        context={"moment": "support", "phaseElapsedMs": elapsed, "exerciseName": "Тяга сверху",
                                 "exerciseSlug": "machine-pulldown", "variant": "machine-pulldown", "controlMode": "constant"})
        message["event"]["exerciseKind"] = "timed" if timed else "machine"
        message["event"]["progressUnit"] = "seconds" if timed else "reps"
        with coach.sessions() as db:
            return coach.plan(db, live.CoachEvent.model_validate(message["event"]), None, message["context"])

    assert advice(14_999) == "no_window"
    first, second = advice(15_000), advice(30_000)
    if timed:
        assert first.task == second.task == "active/support"
        assert first.intents == ("motivation",) and first.coach_context.tip is None
    else:
        assert first.task == "active/general-tip" and first.intents == ("general-tip",)
    assert first.candidate.trigger_id == "T21" and first.candidate.phase == "active"
    assert first.candidate.topic_key != second.candidate.topic_key
    assert advice(60_000).candidate.topic_key == advice(120_000).candidate.topic_key
    assert coach.director.admit(first.candidate, coach.now_ms()).ok
    coach.director.latch_safety(True)
    assert coach.director.admit(second.candidate, coach.now_ms()).reason == "safety"
    coach.settings = CoachPreferences(**HYBRID, during_sets=False)
    assert advice(30_000) == "disabled"


def test_history_skips_shorter_last_session_and_summaries_are_rich(db_session):
    _, old_exercise, _ = seed(db_session, days_ago=14, actual=8, planned=8, status="completed")
    add_set(db_session, old_exercise, 2, actual=7, planned=8)
    seed(db_session, days_ago=7, actual=9, planned=9, status="completed")  # Only set 1 last time.
    workout_id, exercise_id, _ = seed(db_session, actual=10, planned=10, status="completed")
    set_id = add_set(db_session, exercise_id, 2, actual=9, planned=9)
    saved = history.load_saved_set(db_session, "alexey", set_id, history_consent=True)
    assert saved.history == "available" and saved.previous.value == 7
    package = history.exercise_summary(db_session, "alexey", exercise_id, scope_epoch=1, valid_until_ms=10**13)
    facts = {f.id: f for f in package.facts}
    assert facts["total"].value == 19 and facts["weight"].value == 20 and facts["planned-sets"].value == 1
    total = history.workout_summary(db_session, "alexey", workout_id, scope_epoch=1, valid_until_ms=10**13)
    facts = {f.id: f for f in total.facts}
    assert facts["total-reps"].value == 19 and facts["exercise-names"].value == "Тяга сверху"
    assert all(f.ref == f"workout:{workout_id}" for f in total.facts)


async def test_equal_results_of_next_sets_are_not_blocked_as_repeats(session_factory):
    with session_factory() as db:
        _, exercise_id, first = seed(db, actual=10, planned=10, status="completed")
        second = add_set(db, exercise_id, 2)

    lines = iter(["Десять повторений, ровно и собранно.", "Снова десять повторений, стабильно держишь план."])

    def speak(body):
        data = json.loads(body["input"][0]["content"])
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": ["saved-set"],
                "silenceReason": None, "delivery": {"energy": "warm", "pace": "normal", "emphasis": "result"},
                "text": next(lines)}

    coach, sink, run_id = make_coach(session_factory, fake_text=FakeTextAuthor(speak))
    clock = [time.time() * 1000]
    coach.now_ms = lambda: clock[0]
    for ordinal, set_id in ((1, first), (2, second)):
        await coach.handle(event("set_persisted", run_id, set_ordinal=ordinal, phase="rest", refs={"backendSetId": set_id},
                                 context={"restMs": 90_000, "restElapsedMs": 1_000}))
        await settle(coach)
        start = sink.of("speech_start")[-1]
        await coach.handle({"type": "playback_started", "generationId": start["generationId"], "durationMs": 2_000})
        await coach.handle({"type": "playback_completed", "generationId": start["generationId"]})
        clock[0] += 40_000
    assert len(sink.of("speech_start")) == 2, sink.json
    # Only spoken facts are remembered, per saved set.
    assert set(coach.memory.fact_mentions) == {(f"saved-set@set:{first}", "10"), (f"saved-set@set:{second}", "10")}


async def test_saved_set_package_carries_exercise_progress_and_half_kg(session_factory):
    with session_factory() as db:
        _, exercise_id, _ = seed(db, actual=10, planned=10, status="completed")
        set_id = add_set(db, exercise_id, 2, actual=9, planned=12, weight=22.5, low=8, high=12)
    coach, _, run_id = make_coach(session_factory)
    op = plan(coach, run_id, "set_persisted", set_ordinal=2, phase="rest", refs={"backendSetId": set_id},
              context={"nextExerciseName": "Жим ногами"})
    facts = {f.id: f for f in op.package.facts}
    assert facts["weight"].numbers == (22.5, 22) and "с половиной" in facts["weight"].claim
    assert facts["target"].numbers == (8, 12) and facts["exercise"].value == "Тяга сверху"
    assert facts["next-exercise"].value == "Жим ногами" and all(f.ref == f"set:{set_id}" for f in facts.values())
    # target_sets=1 in the seed: set 2 is out of plan, so no position facts are invented.
    assert "set-position" not in facts


async def test_context_facts_and_content_switches(session_factory):
    context = {"exerciseName": "Тяга сверху", "exerciseIndex": 2, "exerciseCount": 4, "totalSets": 3,
               "targetReps": 10, "weightKg": 30}
    coach, _, run_id = make_coach(session_factory)
    ready = plan(coach, run_id, "exercise_ready", context=context)
    assert {f.id for f in ready.package.facts} == {"exercise", "exercise-position", "plan-sets", "target", "weight"}
    opening = plan(coach, run_id, "workout_started", context={"exerciseCount": 4, "exerciseName": "Тяга сверху"})
    assert {f.id for f in opening.package.facts} == {"exercise-count", "exercise"}
    rest = plan(coach, run_id, "rest_long_opportunity", set_ordinal=3, phase="rest",
                context={"restMs": 120_000, "restElapsedMs": 10_000, "totalSets": 3, "exerciseName": "Тяга сверху",
                         "nextExerciseName": "Жим ногами"})
    assert {f.id for f in rest.package.facts} == {"exercise", "set-position", "sets-left", "next-exercise"}
    bad = plan(coach, run_id, "exercise_ready", exercise="ex-9",
               context={"exerciseName": "Lat pulldown", "totalSets": 99, "weightKg": 20.3, "targetReps": True})
    assert bad.package is None

    picky = CoachPreferences(**HYBRID, say_numbers=False, say_exercise_name=False, greeting=False, set_feedback=False)
    coach2, _, run2 = make_coach(session_factory, picky)
    assert plan(coach2, run2, "exercise_ready", context=context).package is None
    assert plan(coach2, run2, "workout_started") == "disabled"
    assert plan(coach2, run2, "set_persisted", set_ordinal=1, phase="rest", refs={"backendSetId": 1}) == "disabled"
    request = coach2._request(plan(coach2, run2, "rep_milestone", set_ordinal=1, phase="active-set"), 10)
    assert request.say_numbers is False and [f.id for f in request.facts] == ["milestone"]


def test_assistant_context_persists_per_user_and_reaches_live_author(session_factory):
    from pydantic import ValidationError

    from app.services.coach.preferences import load_preferences
    from app.services.coach.prompts import build_prompt

    context = "Идёт трансляция тренировки на стриме, тренер комментирует и подбадривает спортсмена."
    with session_factory() as db:
        assert load_preferences(db, "alexey").assistant_context == ""
        saved = save_preferences(db, "alexey", PreferencesSave(expected_revision=0,
                                 settings=CoachPreferences(**HYBRID, assistant_context=context)))
        loaded = load_preferences(db, "alexey")
        assert loaded.assistant_context == context and loaded.revision == saved.revision == 1
    coach, _, run_id = make_coach(session_factory, loaded)
    request = coach._request(plan(coach, run_id, "workout_started"), 20)
    assert request.assistant_context == context
    assert context in build_prompt(request).data
    assert context not in build_prompt(request).instructions
    with pytest.raises(ValidationError):
        CoachPreferences(assistant_context="я" * 501)


def test_in_set_moments_get_own_topics_and_follow_real_set_time(session_factory):
    coach, _, run_id = make_coach(session_factory)
    context = {"exerciseName": "Жим в Смите", "totalSets": 3, "targetReps": 10, "phaseElapsedMs": 40_000}
    ops = {kind if moment is None else moment: plan(coach, run_id, kind, set_ordinal=2, phase="active-set",
                                                    context={**context, **({"moment": moment} if moment else {})})
           for kind, moment in (("set_activated", None), ("rep_completed", None), ("rep_milestone", None),
                                ("rep_milestone", "stall"), ("last_rep_pending", None))}
    topics = {key: op.candidate.topic_key.split(":", 1)[0] for key, op in ops.items()}
    assert topics == {"set_activated": "set-start", "rep_completed": "set-range", "rep_milestone": "set-support",
                      "stall": "set-stall", "last_rep_pending": "set-finish"}
    assert all(op.candidate.trigger_id == "T21" and op.task == "active/support" for op in ops.values())
    claims = {key: next(f.claim for f in op.package.facts if f.id == "milestone") for key, op in ops.items()}
    assert claims["rep_completed"] == "Последнее движение не засчитано"
    assert "Половина" in claims["rep_milestone"]
    assert "target" in {f.id for f in ops["set_activated"].package.facts}
    assert "target" not in {f.id for f in ops["last_rep_pending"].package.facts}  # no stale "N left" during effort
    started = ops["set_activated"].candidate.phase_started_ms
    assert started is not None and coach.now_ms() - started >= 39_000  # 30–60 s slot cap, not the first-30 s cap
    assert plan(coach, run_id, "rep_completed", set_ordinal=2, phase="rest") is None
    assert plan(coach, run_id, "rep_milestone", set_ordinal=2, phase="active-set",
                context={"moment": ["stall"]}).candidate.topic_key.startswith("set-support:")


def test_timed_set_moments_speak_about_time(session_factory):
    coach, _, run_id = make_coach(session_factory)

    def timed(kind, moment=None, **context):
        message = event(kind, run_id, set_ordinal=1, phase="active-set")
        message["event"]["exerciseKind"] = "timed"
        with coach.sessions() as db:
            return coach.plan(db, live.CoachEvent.model_validate(message["event"]), None,
                              {"exerciseName": "Планка", "totalSets": 2, "phaseElapsedMs": 4_000,
                               **({"moment": moment} if moment else {}), **context})

    start = timed("set_activated", targetSeconds=60)
    claims = {key: next(f.claim for f in op.package.facts if f.id == "milestone")
              for key, op in {"start": start, "half": timed("rep_milestone"),
                              "finish": timed("last_rep_pending")}.items()}
    assert "Таймер" in claims["start"] and "времени" in claims["half"] and "секунды" in claims["finish"]
    assert not any("повторени" in claim for claim in claims.values())
    assert start.candidate.topic_key.startswith("set-start:") and "target" in {f.id for f in start.package.facts}
    assert timed("rep_completed") is None  # no partial-rep moment on a clock


async def test_comparison_switch_and_voice_overrides(session_factory):
    with session_factory() as db:
        seed(db, days_ago=7, actual=8, planned=8, status="completed")
        _, _, set_id = seed(db, actual=10, planned=10, status="completed")
    prefs = CoachPreferences(**HYBRID, history_consent=True, comparisons=False, voice_energy="calm", voice_pace="brisk",
                             pause_gap="long", verbosity="short")
    coach, sink, run_id = make_coach(session_factory, prefs)
    op = plan(coach, run_id, "set_persisted", set_ordinal=1, phase="rest", refs={"backendSetId": set_id})
    assert op.candidate.trigger_id == "T36" and op.package.locked_clause is None
    assert coach.director.gap_scale == 1.6 and coach.director.words_scale == 0.6

    deliveries = []

    class Recording(FakeVoiceStream):
        def stream(self, text, scope, generation_id, delivery, **kwargs):
            deliveries.append(delivery)
            return super().stream(text, scope, generation_id, delivery, **kwargs)

    coach.voice = voice(session_factory, Recording())
    await coach.handle(event("workout_started", run_id))
    await settle(coach)
    assert sink.of("speech_start") and (deliveries[0].energy, deliveries[0].pace) == ("calm", "brisk")


async def test_forget_user_clears_live_memory(session_factory):
    coach, _, run_id = make_coach(session_factory)
    coach.memory.note_attempted("set-result")
    live.register(coach)
    try:
        assert live.forget_user("alexey") == 1 and not coach.memory.attempted_topics
        assert coach.director.memory is coach.memory
    finally:
        live.unregister(coach)


# ---------- socket ----------

def ws_url(run_id):
    return f"ws://localhost/api/coach/runs/{run_id}/live"


def enable(session_factory, **fields):
    with session_factory() as db:
        save_preferences(db, "alexey", PreferencesSave(expected_revision=0, settings=CoachPreferences(**{**HYBRID, **fields})))


def use_factory(client, session_factory, *, author=True, streamer=True):
    async def factory(sessions, prefs):
        return Pipeline(text_author(session_factory) if author else None,
                        voice(session_factory) if streamer else None, None if author else "provider_unavailable")
    client.app.dependency_overrides[get_live_factory] = lambda: factory


def test_socket_rejects_foreign_origin_and_bad_configure(client, session_factory):
    client.base_url = "http://localhost"
    enable(session_factory)
    run_id, _, token = new_run(session_factory)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(ws_url(run_id), headers={"Origin": "http://evil.example"}):
            pass
    assert closed.value.code == 1008
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "configure", "runToken": "wrong", "ownerId": "tab-b"}))
        assert ws.receive_json() == {"type": "error", "reason": "run_not_found"}
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "configure", "runToken": token, "ownerId": "tab-b"}))
        assert ws.receive_json()["reason"] == "owner_mismatch"  # tab-a still holds the lease


def test_socket_refuses_when_coach_disabled(client, session_factory, monkeypatch):
    client.base_url = "http://localhost"
    monkeypatch.setenv("COACH_ENABLED", "false")
    get_settings.cache_clear()
    enable(session_factory)
    run_id, _, token = new_run(session_factory)
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "configure", "runToken": token, "ownerId": "tab-a"}))
        assert ws.receive_json() == {"type": "error", "reason": "coach_disabled"}


def test_socket_refuses_local_mode(client, session_factory):
    client.base_url = "http://localhost"
    enable(session_factory, mode="local", network_consent_version=None)
    run_id, _, token = new_run(session_factory)
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "configure", "runToken": token, "ownerId": "tab-a"}))
        assert ws.receive_json()["reason"] == "local_mode"


def test_socket_end_to_end_speech_frames(client, session_factory):
    client.base_url = "http://localhost"
    enable(session_factory)
    use_factory(client, session_factory)
    run_id, _, token = new_run(session_factory)
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "configure", "runToken": token, "ownerId": "tab-a"}))
        configured = ws.receive_json()
        assert configured["type"] == "configured" and configured["voice"] and configured["voiceId"] == "ash"
        assert ws.receive_json() == {"type": "scenario", "state": "none"}  # V1 announce
        ws.send_text(json.dumps(event("workout_started", run_id)))
        start = ws.receive_json()
        assert start["type"] == "speech_start" and start["triggerId"] == "T01"
        frames = []
        while True:
            message = ws.receive()
            if message.get("bytes") is not None:
                frames.append(message["bytes"])
                continue
            end = json.loads(message["text"])
            break
        assert end["type"] == "speech_end" and end["status"] == "complete" and len(frames) == end["frames"] > 0
        ws.send_text("not json")
        assert ws.receive_json() == {"type": "error", "reason": "invalid_message"}
    with session_factory() as db:
        snap = ledger.snapshot(db, run_id)
    assert snap["requests"] == 2 and snap["settledMicros"] > 0  # one text + one voice attempt


def test_settings_change_ends_socket_generation(client, session_factory, monkeypatch):
    from app.api.routes import coach as routes
    monkeypatch.setattr(routes, "LEASE_RENEW_S", 0.05)
    client.base_url = "http://localhost"
    enable(session_factory)
    use_factory(client, session_factory)
    run_id, _, token = new_run(session_factory)
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "configure", "runToken": token, "ownerId": "tab-a"}))
        assert ws.receive_json()["type"] == "configured"
        assert ws.receive_json() == {"type": "scenario", "state": "none"}  # V1 announce
        with session_factory() as db:
            save_preferences(db, "alexey", PreferencesSave(expected_revision=1, settings=CoachPreferences(**HYBRID, humor="off")))
        assert ws.receive_json() == {"type": "error", "reason": "stale_run"}  # client reconnects with fresh settings


def test_socket_degraded_without_provider_and_memory_endpoint(client, session_factory):
    client.base_url = "http://localhost"
    enable(session_factory)
    use_factory(client, session_factory, author=False, streamer=False)
    run_id, _, token = new_run(session_factory)
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_text(json.dumps({"type": "configure", "runToken": token, "ownerId": "tab-a"}))
        configured = ws.receive_json()
        assert configured["text"] is False and configured["degraded"] is True
        assert configured["degradedReason"] == "provider_unavailable"
        assert ws.receive_json() == {"type": "scenario", "state": "none"}  # V1 announce
        ws.send_text(json.dumps(event("workout_started", run_id)))
        assert ws.receive_json()["reason"] == "provider_unavailable"
        response = client.delete("/api/coach/users/alexey/memory", headers=ORIGIN)
        assert response.status_code == 200 and response.json() == {"cleared": 1, "persistentMemory": False}
    # U00 legacy baseline: socket close discarded all state, so this count was 0.
    # U05 keeps bounded same-run state: deletion must include disconnected cached runs too.
    assert client.delete("/api/coach/users/alexey/memory", headers=ORIGIN).json()["cleared"] == 1
    assert client.delete("/api/coach/users/alexey/memory").status_code == 403


# ---------- U01 identity, context, clocks and terminal ACKs ----------

def live_context(message, *, version=1, revision=1, **changes):
    return {"type": "context", "scope": copy.deepcopy(message["event"]["scope"]),
            "phase": message["event"]["phase"], "planRevision": revision, "contextVersion": version,
            "blocked": False, **changes}


async def contextual_opening(coach, run_id):
    message = event("workout_started", run_id)
    message["event"].update(planRevision=1, contextVersion=1, createdAtMs=123, startDeadlineMs=20_123)
    await coach.handle(live_context(message))
    await coach.handle(message)
    await settle(coach)
    return message


async def test_u01_original_identity_and_pcm_scope_are_preserved(session_factory):
    from app.services.coach.identity import identity
    from app.services.coach.voice import decode_frame

    coach, sink, run_id = make_coach(session_factory)
    message = await contextual_opening(coach, run_id)
    start = sink.of("speech_start")[0]
    original = live.CoachEvent.model_validate(message["event"])
    assert start["identity"] == identity(original)
    assert coach.active_op.event == original
    assert start["identity"]["createdAtMs"] == 123  # Never replaced by server wall time.
    for frame in sink.bytes:
        chunk = decode_frame(frame)
        assert chunk.metadata.scope == original.scope
        assert chunk.metadata.generation_id == chunk.metadata.utterance_id == start["generationId"]
        assert "identity" not in chunk.metadata.model_dump(by_alias=True)  # PCM wire remains E08.


async def test_u01_ack_wrong_duplicate_reordered_and_failed(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    await contextual_opening(coach, run_id)
    start = sink.of("speech_start")[0]
    gid, original = start["generationId"], start["identity"]
    ack = {"generationId": gid, "identity": original}
    await coach.handle({"type": "playback_completed", **ack})
    assert gid not in coach.memory.completed and gid in coach.acks
    for field, wrong in (("eventId", "wrong"), ("planRevision", 2), ("contextVersion", 2),
                         ("createdAtMs", 124), ("startDeadlineMs", 99_999), ("factDependencies", ["invented"]),
                         ("schemaVersion", True), ("planRevision", "1")):
        bad = {**original, field: wrong}
        await coach.handle({"type": "playback_started", **ack, "identity": bad})
        await coach.handle({"type": "playback_failed", **ack, "identity": bad})
        assert not coach.memory.started and gid in coach.acks
    bad = copy.deepcopy(original)
    bad["scope"]["scopeEpoch"] += 1
    await coach.handle({"type": "playback_started", **ack, "identity": bad})
    assert not coach.memory.started
    # JSON property order does not matter.
    ack["identity"] = dict(reversed(list(original.items())))
    await coach.handle({"type": "playback_started", **ack, "durationMs": 1234})
    audible = list(coach.director.audible)
    first_started = coach.memory.started[gid]
    await coach.handle({"type": "playback_started", **ack, "durationMs": 60_000})
    assert coach.memory.started[gid].duration_ms == 60_000
    assert coach.memory.started[gid].text == first_started.text
    assert len(coach.director.audible) == len(audible) == 1
    assert coach.director.audible[0][1] == 60_000
    assert coach.stats.opportunities['started'] == 1
    await coach.handle({"type": "playback_completed", **ack})
    await coach.handle({"type": "playback_completed", **ack})
    assert gid in coach.memory.completed and gid not in coach.acks and list(coach.terminal) == [gid]
    await coach.handle({"type": "playback_started", **ack})
    assert coach.memory.started[gid].duration_ms == 60_000
    assert coach.memory.started[gid].text == first_started.text


async def test_u01_failed_ack_removes_entry_and_cannot_complete(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    await contextual_opening(coach, run_id)
    start = sink.of("speech_start")[0]
    ack = {"generationId": start["generationId"], "identity": start["identity"]}
    await coach.handle({"type": "playback_failed", **ack})
    await coach.handle({"type": "playback_started", **ack})
    await coach.handle({"type": "playback_completed", **ack})
    assert not coach.acks and not coach.memory.started and not coach.memory.completed


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("change", ["ordinary", "blocked", "plan", "pause"])
async def test_u01_context_transitions_pending_vs_started(session_factory, started, change):
    coach, sink, run_id = make_coach(session_factory)
    message = await contextual_opening(coach, run_id)
    start = sink.of("speech_start")[0]
    ack = {"generationId": start["generationId"], "identity": start["identity"]}
    if started:
        await coach.handle({"type": "playback_started", **ack})
    scope = {**message["event"]["scope"], "scopeEpoch": 2, "exerciseId": "next"}
    changes = {"scope": scope, "phase": "waiting-start"}
    if change == "blocked":
        changes["blocked"] = True
    elif change == "plan":
        changes["planRevision"] = 2
    elif change == "pause":
        changes["phase"] = "paused-set"  # Even a malformed caller forgetting blocked must fail closed.
    await coach.handle(live_context(message, version=2, **changes))
    survives = started and change in {"ordinary", "plan"}
    assert (ack["generationId"] in coach.acks) == survives
    # Returning to the old scope is not resurrection.
    await coach.handle(live_context(message, version=3, revision=2 if change == "plan" else 1))
    await coach.handle({"type": "playback_started", **ack})
    await coach.handle({"type": "playback_completed", **ack})
    assert (ack["generationId"] in coach.memory.completed) == survives


async def test_started_stream_finishes_after_parameter_edit_with_original_identity(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    ready, release = asyncio.Event(), asyncio.Event()
    original = coach.voice.stream

    async def held_voice(**kwargs):
        async with live.contextlib.aclosing(original(**kwargs)) as frames:
            async for frame in frames:
                yield frame
                if not ready.is_set():
                    ready.set()
                    await release.wait()

    coach.voice.stream = held_voice
    message = event("workout_started", run_id)
    message["event"].update(planRevision=1, contextVersion=1)
    try:
        await coach.handle(live_context(message))
        await coach.handle(message)
        await asyncio.wait_for(ready.wait(), 2)
        start = sink.of("speech_start")[0]
        ack = {"generationId": start["generationId"], "identity": start["identity"]}
        await coach.handle({"type": "playback_started", **ack})
        await coach.handle(live_context(message, version=2, revision=2))
        assert coach.active_op.state.valid and coach.active_op.state.started
        assert coach.active_op.event.plan_revision == 1  # Source provenance is immutable.
        release.set()
        await settle(coach)
        assert sink.of("speech_end")[-1]["status"] == "complete"
        assert len(sink.bytes) > 1
        await coach.handle({"type": "playback_completed", **ack})
        assert ack["generationId"] in coach.memory.completed
    finally:
        release.set()
        await coach.close()


async def test_u01_context_reordering_is_rejected_without_invalidating_current(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    message = await contextual_opening(coach, run_id)
    original = coach.context
    await coach.handle(live_context(message))  # Identical resend is harmless.
    for changes in ({"version": 0}, {"version": 1, "blocked": True}, {"version": 2, "revision": 0}):
        await coach.handle(live_context(message, **changes))
        assert coach.context == original and coach.acks
    assert [m["reason"] for m in sink.of("event_rejected")] == ["context_reordered"] * 3


@pytest.mark.parametrize("mode", ["hybrid", "text-only"])
async def test_u01_delayed_author_cannot_resurrect_after_context_cancel(session_factory, mode):
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**{**HYBRID, "mode": mode}))
    ready, release = asyncio.Event(), asyncio.Event()
    original = coach.author.author

    async def swallowing_author(**kwargs):
        outcome = await original(**kwargs)  # Real TextAuthor with FakeTextAuthor, no paid adapter.
        ready.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            pass  # Deliberately broken provider ignores cancellation.
        return outcome

    coach.author.author = swallowing_author
    message = event("workout_started", run_id)
    message["event"].update(planRevision=1, contextVersion=1)
    await coach.handle(live_context(message))
    await coach.handle(message)
    await asyncio.wait_for(ready.wait(), 2)
    await coach.handle(live_context(message, version=2, blocked=True))
    await settle(coach)
    assert coach.task.done() and not sink.of("speech_start") and not sink.bytes
    assert not [m for m in sink.of("decision") if m.get("text")]


async def test_u01_stale_pcm_is_rejected_even_if_voice_swallows_cancel(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    ready, release = asyncio.Event(), asyncio.Event()
    original = coach.voice.stream

    async def swallowing_voice(**kwargs):
        async with live.contextlib.aclosing(original(**kwargs)) as frames:
            async for frame in frames:
                ready.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass
                yield frame
                return

    coach.voice.stream = swallowing_voice
    message = event("workout_started", run_id)
    message["event"].update(planRevision=1, contextVersion=1)
    await coach.handle(live_context(message))
    await coach.handle(message)
    await asyncio.wait_for(ready.wait(), 2)
    await coach.handle(live_context(message, version=2, blocked=True))
    assert sink.of("speech_start") and not sink.bytes and not coach.acks
    assert sink.of("speech_end")[-1]["status"] == "cancelled"


@pytest.mark.parametrize("browser_origin", [10, 1_900_000_000_000])
async def test_u01_elapsed_ttl_uses_local_monotonic_budget_not_clock_skew(session_factory, browser_origin):
    coach, sink, run_id = make_coach(session_factory)
    clock = [500.0]
    coach.monotonic_ms = lambda: clock[0]
    original = coach.author.author

    async def delayed_author(**kwargs):
        assert kwargs["deadline_ms"] > 1_000_000_000_000  # TextAuthor's wall-clock contract is retained.
        outcome = await original(**kwargs)
        clock[0] += 8_001
        return outcome

    coach.author.author = delayed_author
    message = event("workout_started", run_id, elapsedAtSendMs=12_000)
    message["event"].update(createdAtMs=browser_origin, startDeadlineMs=browser_origin + 20_000)
    await coach.handle(message)
    await settle(coach)
    assert coach.active_op.deadline_ms == 8500 and not sink.of("speech_start") and not sink.bytes
    expired = event("exercise_ready", run_id, elapsedAtSendMs=20_000)
    await coach.handle(expired)
    assert sink.of("event_rejected")[-1]["reason"] == "expired"


async def test_u01_ack_deadline_is_fixed_but_started_completion_can_be_late(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    clock = [100.0]
    coach.monotonic_ms = lambda: clock[0]
    await contextual_opening(coach, run_id)
    start = sink.of("speech_start")[0]
    ack = {"generationId": start["generationId"], "identity": start["identity"]}
    await coach.handle({"type": "playback_started", **ack})
    clock[0] += 60_000
    await coach.handle({"type": "playback_completed", **ack})
    assert ack["generationId"] in coach.memory.completed
    late, late_sink, late_run = make_coach(session_factory)
    clock[0] = 100
    late.monotonic_ms = lambda: clock[0]
    await contextual_opening(late, late_run)
    last = late_sink.of("speech_start")[0]
    clock[0] = 20_101
    await late.handle({"type": "playback_started", "generationId": last["generationId"], "identity": last["identity"]})
    assert not late.memory.started and not late.acks


@pytest.mark.parametrize("kind,phase,next_phase", [("set_persisted", "finalizing-set", "rest"),
    ("exercise_finalized", "exercise-summary", "exercise-summary"),
    ("workout_finalized", "workout-summary", "workout-summary")])
async def test_u01_designated_handoff_keeps_original_capture_identity(session_factory, kind, phase, next_phase):
    with session_factory() as db:
        workout_id, exercise_id, set_id = seed(db, actual=10, planned=10, status="completed")
    coach, sink, run_id = make_coach(session_factory)
    refs = {"backendSetId": set_id, "backendExerciseId": exercise_id, "backendWorkoutId": workout_id}
    message = event(kind, run_id, phase=phase, set_ordinal=1, refs=refs,
                    context={"restMs": 90_000, "restElapsedMs": 0})
    message["event"].update(planRevision=1, contextVersion=1)
    await coach.handle(live_context(message))
    # Browser publishes the lifecycle event after the designated context handoff.
    next_scope = {**message["event"]["scope"], "scopeEpoch": 2}
    await coach.handle(live_context(message, version=2, phase=next_phase, scope=next_scope))
    await coach.handle(message)
    await settle(coach)
    start = sink.of("speech_start")[0]
    assert start["identity"]["contextVersion"] == start["identity"]["planRevision"] == 1
    assert start["identity"]["scope"]["scopeEpoch"] == 1
    await coach.handle({"type": "playback_started", "generationId": start["generationId"], "identity": start["identity"]})
    assert start["generationId"] in coach.memory.started


async def test_u01_text_identity_and_bounded_redacted_monotonic_telemetry(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    clock = [100.0]
    coach.monotonic_ms = lambda: clock[0]
    original = coach.author.author

    async def measured_author(**kwargs):
        outcome = await original(**kwargs)
        clock[0] += 125
        return outcome

    coach.author.author = measured_author
    await contextual_opening(coach, run_id)
    start = sink.of("speech_start")[0]
    ack = {"generationId": start["generationId"], "identity": start["identity"]}
    clock[0] = 400
    await coach.handle({"type": "playback_started", **ack})
    clock[0] = 900
    await coach.handle({"type": "playback_completed", **ack})
    stats = coach.stats.as_dict()
    for stage, elapsed in (("receive", 0), ("textStart", 0), ("textEnd", 125), ("textDuration", 125),
                           ("firstPcm", 125), ("speechEnd", 125), ("ackStart", 300), ("ackEnd", 800)):
        metric = next(v for k, v in stats["latencies"].items() if k.startswith(stage + ":"))
        assert metric == {"count": 1, "p50": elapsed, "p95": elapsed}
    assert stats["firstAudioMsLabel"] == "voice-only" and stats["firstAudioMs"]["count"] == 1
    redacted = json.dumps(stats)
    assert "alexey" not in redacted and run_id not in redacted and start["text"] not in redacted
    for key in stats["latencies"]:
        assert key.endswith(":fake" if key.split(":")[0] in {"firstPcm", "speechEnd", "ackStart", "ackEnd"} else ":unknown")
    end = sink.of("speech_end")[0]
    assert end["connectionClass"] == "fake" and end["voiceModel"] == "fake-voice" and end["textModel"] == TEXT_PRICE.model
    assert end["source"] == "fake"
    assert end["timingsMs"] == {"receive": 0, "textStart": 0, "textEnd": 125,
                                "firstPcm": 125, "speechEnd": 125, "textDuration": 125}
    assert "connectionClass" not in start  # The actual voice request has not happened yet.
    for i in range(200):
        coach.stats.measure("bounded", coach.active_op, i)
        coach._finish(f"terminal-{i}")
    metric = next(v for k, v in coach.stats.as_dict()["latencies"].items() if k.startswith("bounded:"))
    assert metric == {"count": 128, "p50": 135, "p95": 193}
    assert len(coach.terminal) == 32
    text_coach, text_sink, text_run = make_coach(session_factory, CoachPreferences(**{**HYBRID, "mode": "text-only"}))
    await contextual_opening(text_coach, text_run)
    decision = text_sink.of("decision")[-1]
    assert decision["action"] == "text" and decision["identity"]["createdAtMs"] == 123


async def test_u01_live_authoritative_cold_warm_metadata_and_metric_groups(session_factory):
    async def connect(url, headers):
        return FakeSocket([*realtime_events(), *realtime_events()])

    adapter = RealtimeVoiceAdapter(connect, "k", model="mock-realtime", voice="v", keep_alive=True)
    adapter.test_only = True
    streamer = VoiceStreamer(session_factory, adapter, VOICE_PRICE)
    for expected in ("cold", "warm"):
        coach, sink, run_id = make_coach(session_factory)
        coach.voice = streamer
        await contextual_opening(coach, run_id)
        start, end = sink.of("speech_start")[0], sink.of("speech_end")[0]
        assert "connectionClass" not in start
        assert end["connectionClass"] == expected and end["voiceModel"] == "mock-realtime"
        assert end["textModel"] == TEXT_PRICE.model and end["source"] == "realtime"
        for metric in ("firstPcm", "speechEnd"):
            key = f"{metric}:T01:{TEXT_PRICE.model}/mock-realtime:{expected}"
            assert coach.stats.as_dict()["latencies"][key]["count"] == 1
        assert set(end) == {"type", "generationId", "status", "reason", "frames", "firstAudioMs",
                            "voiceModel", "textModel", "source", "connectionClass", "timingsMs"}
    await adapter.aclose()


@pytest.mark.parametrize("kind", ["empty", "error-before", "error-after", "cancel"])
async def test_u01_voice_terminal_telemetry_retains_failure_denominators(session_factory, kind):
    coach, sink, run_id = make_coach(session_factory)
    ready = asyncio.Event()

    class HeldFake(FakeVoiceStream):
        async def stream(self, *args, **kwargs):
            async for frame in super().stream(*args, **kwargs):
                yield frame
                ready.set()
                await asyncio.Event().wait()

    adapter = HeldFake() if kind == "cancel" else FakeVoiceStream(
        parts=() if kind == "empty" else (bytes(4800), bytes(4800)),
        error_after={"error-before": 0, "error-after": 1}.get(kind))
    coach.voice = voice(session_factory, adapter)
    await coach.handle(event("workout_started", run_id))
    if kind == "cancel":
        await asyncio.wait_for(ready.wait(), 2)
        await coach.cancel("cancelled")
    else:
        await settle(coach)
    end = sink.of("speech_end")[-1]
    assert end["status"] == ("complete" if kind == "empty" else "cancelled" if kind == "cancel" else "failed")
    assert end["connectionClass"] == "fake" and end["voiceModel"] == "fake-voice"
    metrics = coach.stats.as_dict()["latencies"]
    assert sum(v["count"] for k, v in metrics.items() if k.startswith("speechEnd:")) == 1
    has_pcm = kind in {"error-after", "cancel"}
    assert ("firstPcm" in end["timingsMs"]) == has_pcm
    assert sum(v["count"] for k, v in metrics.items() if k.startswith("firstPcm:")) == int(has_pcm)
    assert all(k.endswith(":fake") for k in metrics if k.startswith(("firstPcm:", "speechEnd:", "ackCancel:")))
    if kind != "empty":
        assert sum(v["count"] for k, v in metrics.items() if k.startswith("ackCancel:")) == 1
        assert coach.stats.reasons["cancelled" if kind == "cancel" else "provider_error"] == 1
    else:
        assert end["firstAudioMs"] is None


async def test_u01_speech_timing_wire_allowlist_bounds_and_no_absolute_clocks(session_factory):
    coach, _, run_id = make_coach(session_factory)
    await contextual_opening(coach, run_id)
    op = coach.active_op
    op.state.marks.update({"providerSecret": 1234, "firstPcm": op.received_ms - 5,
                           "speechEnd": op.received_ms + 2 * live.MAX_TELEMETRY_MS,
                           "ackEnd": float("nan"), "ackStart": float("inf")})
    result = coach._speech_metadata(op, VoiceOutcome())
    timings = result["timingsMs"]
    assert timings["firstPcm"] == 0 and timings["speechEnd"] == live.MAX_TELEMETRY_MS
    assert not {"providerSecret", "ackEnd", "ackStart"} & timings.keys()
    assert all(0 <= value <= live.MAX_TELEMETRY_MS for value in timings.values())
    coach.stats.measure("nonfinite", op, float("nan"))
    assert not any(k.startswith("nonfinite:") for k in coach.stats.as_dict()["latencies"])


@pytest.mark.parametrize("plan_change", [False, True])
async def test_u01_block_or_plan_change_drops_queued_summary(session_factory, plan_change):
    with session_factory() as db:
        _, exercise_id, _ = seed(db, actual=10, planned=10, status="completed")
    coach, sink, run_id = make_coach(session_factory)
    ready, release = asyncio.Event(), asyncio.Event()
    original = coach.voice.stream

    async def held_voice(**kwargs):
        async with live.contextlib.aclosing(original(**kwargs)) as frames:
            async for frame in frames:
                yield frame
                ready.set()
                await release.wait()

    coach.voice.stream = held_voice
    opening = event("workout_started", run_id)
    opening["event"].update(planRevision=1, contextVersion=1)
    await coach.handle(live_context(opening))
    await coach.handle(opening)
    await asyncio.wait_for(ready.wait(), 2)
    start = sink.of("speech_start")[0]
    await coach.handle({"type": "playback_started", "generationId": start["generationId"], "identity": start["identity"]})
    summary = event("exercise_finalized", run_id, phase="exercise-summary", refs={"backendExerciseId": exercise_id})
    summary["event"].update(planRevision=1, contextVersion=2)
    await coach.handle(live_context(summary, version=2))
    await coach.handle(summary)
    queued = coach.queued
    assert queued is not None
    await coach.handle(live_context(summary, version=3, revision=2 if plan_change else 1, blocked=not plan_change))
    assert coach.queued is None and not queued.state.valid
    if plan_change:
        # The queued stale summary is rejected, but the already audible opening finishes.
        assert start["generationId"] in coach.acks and not coach.task.done()
        release.set()
        await settle(coach)
        assert sink.of("speech_end")[-1]["status"] == "complete"
    else:
        assert not coach.acks and coach.task.done()
    assert len(sink.of("speech_start")) == 1
    await coach.close()


async def test_u01_versioned_delayed_event_cannot_cross_blocked_context_history(session_factory):
    coach, sink, run_id = make_coach(session_factory)
    message = event("workout_started", run_id)
    message["event"].update(planRevision=1, contextVersion=1)
    await coach.handle(live_context(message))
    await coach.handle(live_context(message, version=2, blocked=True))
    await coach.handle(live_context(message, version=3))
    await coach.handle(message)
    assert sink.of("event_rejected")[-1]["reason"] == "scope_changed"
    assert not sink.of("speech_start") and not coach.task


async def test_u01_dependency_identity_is_retained_in_text_decision(session_factory):
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**{**HYBRID, "mode": "text-only"}))
    message = event("workout_started", run_id)
    message["event"].update(facts=[{"id": "original-fact", "value": 1, "unit": "reps", "source": "runtime_ack",
                                  "confidence": "confirmed", "observedAtMs": 1, "validUntilMs": 20_001,
                                  "scopeEpoch": 1}], factDependencies=["original-fact"])
    await coach.handle(message)
    await settle(coach)
    assert sink.of("decision")[-1]["identity"]["factDependencies"] == ["original-fact"]


@pytest.mark.parametrize("kind,phase,destination", [
    ("set_persisted", "active-set", "rest"), ("set_persisted", "finalizing-set", "rest"),
    ("exercise_finalized", "active-set", "exercise-summary"),
    ("exercise_finalized", "finalizing-set", "exercise-summary"),
    ("exercise_finalized", "exercise-summary", "exercise-summary"),
    ("workout_finalized", "workout-summary", "workout-summary"),
])
async def test_result_capture_publish_after_save_real_phase_path(session_factory, kind, phase, destination):
    with session_factory() as db:
        workout_id, exercise_id, set_id = seed(db, actual=10, planned=10, status="completed")
    coach, sink, run_id = make_coach(session_factory)
    message = event(kind, run_id, phase=phase, set_ordinal=1,
                    refs={"backendSetId": set_id, "backendExerciseId": exercise_id, "backendWorkoutId": workout_id},
                    context={"restMs": 90_000, "restElapsedMs": 0})
    message["event"].update(planRevision=1, contextVersion=1)
    origin = live_context(message)
    if kind == "workout_finalized":
        message["event"]["scope"].update(exerciseId=None, setOrdinal=None)
    await coach.handle(origin)
    if phase == "active-set":
        await coach.handle({**origin, "contextVersion": 2, "phase": "finalizing-set",
                            "scope": {**origin["scope"], "scopeEpoch": 2}})
    await coach.handle({**origin, "contextVersion": 3, "phase": destination,
                        "scope": {**origin["scope"], "scopeEpoch": 3}})
    await coach.handle(message)
    await settle(coach)
    start = sink.of("speech_start")[0]
    assert start["identity"]["scope"] == live.CoachEvent.model_validate(message["event"]).scope.model_dump(by_alias=True)
    assert start["identity"]["contextVersion"] == 1
    await coach.handle({"type": "playback_started", "generationId": start["generationId"], "identity": start["identity"]})
    assert start["generationId"] in coach.memory.started


@pytest.mark.parametrize("change", ["plan", "pause", "gate", "exercise", "set", "run", "epoch", "reverse",
                                  "zero", "origin-scope", "origin-phase", "unverified-ref", "capture-rest"])
async def test_result_save_cannot_bypass_origin_or_resurrect(session_factory, change):
    with session_factory() as db:
        _, _, set_id = seed(db, actual=10, planned=10, status="completed")
    coach, sink, run_id = make_coach(session_factory)
    message = event("set_persisted", run_id, phase="active-set", set_ordinal=1, refs={"backendSetId": set_id},
                    context={"restMs": 90_000, "restElapsedMs": 0})
    message["event"].update(planRevision=1, contextVersion=1)
    origin = live_context(message)
    await coach.handle(origin)
    middle = {**origin, "contextVersion": 2, "phase": "finalizing-set"}
    await coach.handle(middle)
    bad = {**middle, "contextVersion": 3}
    if change == "plan":
        bad["planRevision"] = 2
    elif change == "pause":
        bad["phase"] = "paused-set"
    elif change == "gate":
        bad["blocked"] = True
    elif change in {"exercise", "set", "run", "epoch"}:
        field, value = {"exercise": ("exerciseId", "other"), "set": ("setOrdinal", 2),
                        "run": ("runId", "other"), "epoch": ("scopeEpoch", 2)}[change]
        bad["scope"] = {**origin["scope"], field: value}
    elif change == "reverse":
        bad["phase"] = "active-set"
    elif change == "zero":
        message["event"].update(planRevision=0, contextVersion=0)
    elif change == "origin-scope":
        message["event"]["scope"]["setOrdinal"] = 2
    elif change == "origin-phase":
        message["event"]["phase"] = "finalizing-set"
    elif change == "unverified-ref":
        message["refs"] = {"backendExerciseId": 99}
    elif change == "capture-rest":
        message["event"].update(phase="rest", contextVersion=4)
    await coach.handle(bad)
    if change == "run":
        # A foreign context is rejected, not an accepted transition invalidating owned work.
        assert sink.of("event_rejected")[-1]["reason"] == "owner_mismatch"
        assert coach.context.context_version == 2
    await coach.handle({**origin, "contextVersion": 4, "phase": "rest",
                        "planRevision": 2 if change == "plan" else 1})
    await coach.handle(message)
    await settle(coach)
    if change == "run":
        assert sink.of("speech_start") and sink.bytes
    else:
        assert not sink.of("speech_start") and not sink.bytes
    assert sink.of("event_rejected") or sink.of("decision")


def test_confirmed_result_cursors_progress_monotonically_and_summary_remaps_once():
    from app.services.coach.identity import SpeechContext, WorkState

    origin = SpeechContext.model_validate({"scope": {"userId": "u", "runId": "r", "exerciseId": "e",
                                                   "setOrdinal": 1, "scopeEpoch": 1},
                                          "phase": "active-set", "planRevision": 1, "contextVersion": 1,
                                          "blocked": False})
    for confirmed in (False, True):
        state = WorkState(context=origin, confirmed_result=confirmed)
        for phase, epoch in (("finalizing-set", 2), ("exercise-summary", 3)):
            state.advance("exercise_finalized", origin.model_copy(update={"phase": phase,
                          "scope": origin.scope.model_copy(update={"scope_epoch": epoch})}))
        assert state.valid is confirmed
        summary = state.context
        if confirmed:
            state.advance("exercise_finalized", summary.model_copy(update={
                "scope": summary.scope.model_copy(update={"scope_epoch": 4})}))
            assert state.valid
            state.advance("exercise_finalized", summary.model_copy(update={
                "scope": summary.scope.model_copy(update={"scope_epoch": 5})}))
            assert not state.valid
        state.advance("exercise_finalized", origin)
        assert not state.valid
