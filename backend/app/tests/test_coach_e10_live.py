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
