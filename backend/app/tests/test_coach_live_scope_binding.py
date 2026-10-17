"""Runtime scope is independent from the ledger; real socket, synthetic providers only."""

import copy
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.api.routes.coach import get_live_factory
from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachLedgerRun
from app.schemas.coach import CoachEvent
from app.schemas.coach_control import LiveConfigure
from app.services.coach import ledger, live
from app.services.coach.identity import identity
from app.services.coach.live import Pipeline
from app.services.coach.memory import RunMemoryStore
from app.services.coach.voice import decode_frame
from app.tests.test_coach_control_plane import ORIGIN
from app.tests.test_coach_e10_live import (
    enable,
    event,
    live_context,
    make_coach,
    settle,
    text_author,
    voice,
    ws_url,
)


@pytest.fixture(autouse=True)
def enabled_coach(use_test_emulator, monkeypatch):
    monkeypatch.setenv("COACH_ENABLED", "true")
    get_settings.cache_clear()
    # Keep retained memory checks independent of other sockets in the safe suite.
    monkeypatch.setattr(live, "_RUN_MEMORY", RunMemoryStore())


@pytest.mark.parametrize("value", ["", "x" * 121, 1, True, [], {}])
def test_runtime_run_id_is_strict_and_bounded(value):
    with pytest.raises(ValidationError):
        LiveConfigure.model_validate({"type": "configure", "runToken": "token", "ownerId": "tab-a",
                                      "runtimeRunId": value})


@pytest.mark.parametrize("value", [None, "runtime:123", "x" * 120])
def test_runtime_run_id_accepts_scope_identifier_bounds(value):
    config = LiveConfigure.model_validate({"type": "configure", "runToken": "token", "ownerId": "tab-a",
                                          "runtimeRunId": value})
    assert config.runtime_run_id == value


def create_browser_run(client, session_factory):
    client.base_url = "http://localhost"
    enable(session_factory)
    response = client.post("/api/coach/runs", headers=ORIGIN, json={"userId": "alexey", "ledger": "workout"})
    assert response.status_code == 200
    run = response.json()
    # Keep the real POST's random ledger identity and token. Synthetic dispatch is deliberately
    # allowed only on the test ledger; change that classification in this isolated fixture DB.
    with session_factory() as db:
        db.get(CoachLedgerRun, run["runId"]).ledger = "test"
        db.commit()
    return run


def install_pipeline(client, session_factory, *, author=True, streamer=True, reason=None):
    text = text_author(session_factory) if author else None
    audio = voice(session_factory) if streamer else None

    async def factory(sessions, prefs):
        return Pipeline(text, audio, reason)

    client.app.dependency_overrides[get_live_factory] = lambda: factory
    return text, audio


@pytest.mark.parametrize("runtime_binding", [True, False])
def test_socket_runtime_scope_streams_without_rewriting_identity_or_billing(client, session_factory, runtime_binding):
    run = create_browser_run(client, session_factory)
    run_id = run["runId"]
    runtime_id = "runtime:training-session-123" if runtime_binding else run_id
    if runtime_binding:
        assert runtime_id != run_id
    install_pipeline(client, session_factory)
    message = event("workout_started", runtime_id)
    message["event"].update(planRevision=1, contextVersion=1)
    original = CoachEvent.model_validate(message["event"])
    configure = {"type": "configure", "runToken": run["runToken"], "ownerId": "tab-a"}
    if runtime_binding:
        configure["runtimeRunId"] = runtime_id
    with client.websocket_connect(ws_url(run_id), headers=ORIGIN) as ws:
        ws.send_json(configure)
        configured = ws.receive_json()
        assert configured["type"] == "configured" and configured["text"] is True and configured["voice"] is True
        assert configured["degraded"] is False and configured["degradedReason"] is None
        ws.send_json(live_context(message))
        ws.send_json(message)
        start = ws.receive_json()
        assert start["type"] == "speech_start" and start["text"] and start["source"] == "fake", start
        assert start["identity"] == identity(original)
        frames = []
        while True:
            chunk = ws.receive()
            if chunk.get("bytes") is not None:
                frames.append(decode_frame(chunk["bytes"]))
            else:
                end = json.loads(chunk["text"])
                break
        assert end["type"] == "speech_end" and end["status"] == "complete"
        assert end["frames"] == len(frames) > 0
        for frame in frames:
            assert frame.metadata.scope == original.scope
            assert frame.metadata.generation_id == frame.metadata.utterance_id == start["generationId"]
        active = next(coach for coach in live._ACTIVE if coach.run_id == run_id)
        assert active.scope_run_id == runtime_id and active.active_op.event == original
        assert ("alexey", run_id) in live._RUN_MEMORY.entries
        if runtime_binding:
            assert ("alexey", runtime_id) not in live._RUN_MEMORY.entries
        ack = {"generationId": start["generationId"], "identity": start["identity"]}
        ws.send_json({"type": "playback_started", **ack})
        ws.send_json({"type": "playback_completed", **ack})
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
        assert start["generationId"] in active.memory.completed
    with session_factory() as db:
        snap = ledger.snapshot(db, run_id)
        attempts = list(db.scalars(select(CoachAttempt)))
        row = db.get(CoachLedgerRun, run_id)
        assert row.owner == "tab-a" and row.generation == configured["generation"]
        if runtime_binding:
            assert db.get(CoachLedgerRun, runtime_id) is None
    assert snap["requests"] == len(attempts) == 2 and snap["settledMicros"] > 0
    assert {attempt.stage for attempt in attempts} == {"text", "voice"}
    assert all(attempt.run_id == run_id and attempt.status == "settled" for attempt in attempts)


def test_socket_wrong_runtime_scope_or_user_rejected_before_provider_calls(client, session_factory):
    run = create_browser_run(client, session_factory)
    author, audio = install_pipeline(client, session_factory)
    runtime_id = "runtime:training-session-123"
    valid = event("workout_started", runtime_id)
    valid["event"].update(planRevision=1, contextVersion=1)
    with client.websocket_connect(ws_url(run["runId"]), headers=ORIGIN) as ws:
        ws.send_json({"type": "configure", "runToken": run["runToken"], "ownerId": "tab-a",
                      "runtimeRunId": runtime_id})
        assert ws.receive_json()["type"] == "configured"
        ws.send_json(live_context(valid))
        for field, wrong in (("runId", run["runId"]), ("runId", "another-runtime"), ("userId", "intruder")):
            invalid = copy.deepcopy(valid)
            invalid["event"]["scope"][field] = wrong
            ws.send_json(live_context(invalid, version=2))
            assert ws.receive_json() == {"type": "event_rejected", "eventId": None, "reason": "owner_mismatch"}
            ws.send_json(invalid)
            assert ws.receive_json() == {"type": "event_rejected", "eventId": valid["event"]["id"],
                                         "reason": "owner_mismatch"}
        active = next(coach for coach in live._ACTIVE if coach.run_id == run["runId"])
        assert active.context.scope.run_id == runtime_id and active.context.context_version == 1
        assert not active.seen and not author.adapter.calls and not audio.adapter.calls
    with session_factory() as db:
        assert ledger.snapshot(db, run["runId"])["attempts"] == []


@pytest.mark.parametrize("bad_auth", ["token", "owner"])
def test_runtime_binding_does_not_bypass_token_or_lease_owner(client, session_factory, bad_auth):
    run = create_browser_run(client, session_factory)
    with session_factory() as db:
        ledger.lease(db, run["runId"], "tab-a", 0)
    factory_calls = []

    async def forbidden_factory(sessions, prefs):
        factory_calls.append(True)
        raise AssertionError("Unauthorized configure must not initialize providers")

    client.app.dependency_overrides[get_live_factory] = lambda: forbidden_factory
    with client.websocket_connect(ws_url(run["runId"]), headers=ORIGIN) as ws:
        ws.send_json({"type": "configure", "runToken": "wrong" if bad_auth == "token" else run["runToken"],
                      "ownerId": "tab-b", "runtimeRunId": "runtime:training-session-123"})
        assert ws.receive_json() == {"type": "error", "reason": "run_not_found" if bad_auth == "token" else "owner_mismatch"}
    assert not factory_calls


@pytest.mark.parametrize("started", [False, True])
async def test_foreign_context_cannot_invalidate_current_speech(session_factory, started):
    coach, sink, run_id = make_coach(session_factory)
    message = event("workout_started", run_id)
    message["event"].update(planRevision=1, contextVersion=1)
    await coach.handle(live_context(message))
    await coach.handle(message)
    await settle(coach)
    start = sink.of("speech_start")[0]
    ack = {"generationId": start["generationId"], "identity": start["identity"]}
    if started:
        await coach.handle({"type": "playback_started", **ack})
    previous = coach.context
    for field, wrong in (("runId", "foreign-run"), ("userId", "intruder")):
        scope = {**message["event"]["scope"], field: wrong}
        await coach.handle(live_context(message, version=2, scope=scope))
        assert sink.of("event_rejected")[-1]["reason"] == "owner_mismatch"
        assert coach.context == previous and ack["generationId"] in coach.acks
    await coach.handle({"type": "playback_started", **ack})
    await coach.handle({"type": "playback_completed", **ack})
    assert ack["generationId"] in coach.memory.completed
    await coach.close()


@pytest.mark.parametrize("author,streamer,reason", [
    (False, False, "provider_unavailable"),
    (True, False, "voice_unavailable"),
])
def test_socket_unhealthy_configured_is_truthful(client, session_factory, author, streamer, reason):
    run = create_browser_run(client, session_factory)
    install_pipeline(client, session_factory, author=author, streamer=streamer, reason=reason)
    with client.websocket_connect(ws_url(run["runId"]), headers=ORIGIN) as ws:
        ws.send_json({"type": "configure", "runToken": run["runToken"], "ownerId": "tab-a",
                      "runtimeRunId": "runtime:training-session-123"})
        configured = ws.receive_json()
        assert configured["text"] is author and configured["voice"] is streamer
        assert configured["degraded"] is True and configured["degradedReason"] == reason
    with session_factory() as db:
        assert ledger.snapshot(db, run["runId"])["requests"] == 0


def test_socket_configure_contract_is_not_an_openapi_component(client):
    assert "LiveConfigure" not in client.app.openapi()["components"]["schemas"]