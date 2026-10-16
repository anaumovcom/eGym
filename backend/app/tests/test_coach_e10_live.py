"""E10 live coach: DB-backed facts, single-flight pipeline, socket protocol. Synthetic adapters only."""

import asyncio
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
from app.services.coach.voice import FakeVoiceStream, VoiceStreamer
from app.services.runtime_service import RuntimeService
from app.tests.test_coach_control_plane import ORIGIN
from app.tests.test_coach_e07_author import PRICE as TEXT_PRICE
from app.tests.test_coach_e08_voice import PRICE as VOICE_PRICE

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
        exercise_name=name, kind="machine", status="in_progress", started_at=started, target_sets=1)).exercise_session.id
    saved = service.save_set_result(db, SetResultSaveSchema(
        exercise_session_id=exercise, set_number=1, planned_value=planned, actual_value=actual, reps=actual,
        weight_kg=20, tempo_label="unknown", machine_metrics={"completionStatus": status}))
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
                        context={"moment": "support", "phaseElapsedMs": elapsed, "exerciseName": "Жим ногами"})
        message["event"]["exerciseKind"] = "timed" if timed else "machine"
        message["event"]["progressUnit"] = "seconds" if timed else "reps"
        with coach.sessions() as db:
            return coach.plan(db, live.CoachEvent.model_validate(message["event"]), None, message["context"])

    assert advice(14_999) == "no_window"
    first, second = advice(15_000), advice(30_000)
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
    assert "амплитуду" in claims["rep_completed"] and "Половина" in claims["rep_milestone"]
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
        assert configured["text"] is False and configured["degraded"] == "provider_unavailable"
        ws.send_text(json.dumps(event("workout_started", run_id)))
        assert ws.receive_json()["reason"] == "provider_unavailable"
        response = client.delete("/api/coach/users/alexey/memory", headers=ORIGIN)
        assert response.status_code == 200 and response.json() == {"cleared": 1, "persistentMemory": False}
    assert client.delete("/api/coach/users/alexey/memory", headers=ORIGIN).json()["cleared"] == 0
    assert client.delete("/api/coach/users/alexey/memory").status_code == 403
