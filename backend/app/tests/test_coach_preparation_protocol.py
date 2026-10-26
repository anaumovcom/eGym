"""Preparation protocol regressions: real ledger-bound author/voice, synthetic providers only."""

import asyncio
import json

import pytest

from app.models.coach import CoachAttempt
from app.schemas.coach_control import CoachPreferences
from app.services.coach import live, scenario
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.voice import FakeVoiceStream
from app.tests.test_coach_e10_live import HYBRID, event, live_context, make_coach, voice
from app.tests.test_coach_v1_scenarios import PLAN as FULL_PLAN
from app.tests.test_coach_v1_scenarios import bible_for
from app.tests.test_coach_v12_prepared_moments import script as line_script

PLAN = [{**exercise, "sets": 1} for exercise in FULL_PLAN]
CARD = {"title": "Гонка героев", "archetype": "race"}
CURRENT_KEYS = {"T01:opening", "T21:ex-1:1:start", "T21:ex-1:1:finish"}
NEXT_KEYS = {"T67:ex-2", "T21:ex-2:1:start", "T21:ex-2:1:finish"}


class GatedVoice(FakeVoiceStream):
    """Pause the first actual voice request per exercise, without clock-based races."""

    def __init__(self):
        super().__init__()
        self.entered = {exercise["id"]: asyncio.Event() for exercise in PLAN}
        self.release = {exercise["id"]: asyncio.Event() for exercise in PLAN}

    async def stream(self, text, scope, generation_id, delivery, **kwargs):
        exercise = scope.exercise_id
        self.entered[exercise].set()
        await self.release[exercise].wait()
        async for chunk in super().stream(text, scope, generation_id, delivery, **kwargs):
            yield chunk


def prepared_coach(session_factory, monkeypatch, *, adapter=None, script=None, streamer=True):
    monkeypatch.setattr(live, "PREBUILD_START_DELAY_S", 0)
    fake = FakeTextAuthor(script or line_script([]))
    coach, sink, run_id = make_coach(
        session_factory, CoachPreferences(**HYBRID), fake_text=fake, streamer=streamer,
    )
    if adapter is not None:
        coach.voice = voice(session_factory, adapter)
    coach.scenario_card = dict(CARD)
    coach.scenario_bible = scenario.validate_bible(bible_for({"plan": PLAN}), scenario.parse_plan(PLAN))
    assert coach.scenario_bible is not None
    return coach, sink, run_id, fake


async def reached(signal):
    await asyncio.wait_for(signal.wait(), timeout=10)


async def finished(job):
    assert job is not None, "Preparation must schedule background work"
    await asyncio.wait_for(job, timeout=10)


async def test_current_exercise_reports_actual_counts_ready_before_future_workout(session_factory, monkeypatch):
    adapter = GatedVoice()
    coach, sink, run_id, _ = prepared_coach(session_factory, monkeypatch, adapter=adapter)
    try:
        coach.schedule_prebuild()
        assert coach._preparation_targets == CURRENT_KEYS
        await reached(adapter.entered["ex-1"])
        assert sink.of("preparation") == [
            {"type": "preparation", "state": "preparing", "exerciseId": "ex-1",
             "completed": 0, "total": 3, "ready": 0},
        ]
        # Text has been authored, but without completed PCM it is not a ready line.
        assert not coach.prebuilt
        adapter.release["ex-1"].set()
        await reached(adapter.entered["ex-2"])
        updates = sink.of("preparation")
        assert [(m["state"], m["completed"], m["ready"], m["total"]) for m in updates] == [
            ("preparing", 0, 0, 3), ("preparing", 1, 1, 3),
            ("preparing", 2, 2, 3), ("ready", 3, 3, 3),
        ]
        assert set(coach.prebuilt) == CURRENT_KEYS
        assert all(coach.prebuilt[key].pcm for key in CURRENT_KEYS)
        assert not coach.prebuild_job.done()  # No need to wait for exercises two and three.
        assert all(m["exerciseId"] == "ex-1" for m in updates)
        with session_factory() as db:
            attempts = db.query(CoachAttempt).filter_by(run_id=run_id).all()
            assert attempts and all(a.purpose == "prebuild" for a in attempts)
    finally:
        await coach.close()


@pytest.mark.parametrize("failure", ["author_error", "voice_error", "empty_audio"])
async def test_failed_preparation_settles_as_degraded_not_stuck(session_factory, monkeypatch, failure):
    def failing_author(body):
        return RuntimeError("synthetic author unavailable")

    adapter = FakeVoiceStream(error_after=0) if failure == "voice_error" else (
        FakeVoiceStream(parts=()) if failure == "empty_audio" else FakeVoiceStream()
    )
    coach, sink, _, fake = prepared_coach(
        session_factory, monkeypatch, adapter=adapter,
        script=failing_author if failure == "author_error" else None,
    )
    try:
        coach.schedule_prebuild()
        await finished(coach.prebuild_job)
        assert fake.calls  # Exercise the real author, validation, voice and settlement paths.
        assert not coach.prebuilt
        assert coach._preparation_targets == CURRENT_KEYS
        assert CURRENT_KEYS <= coach._prebuild_settled
        assert coach.preparation == {"state": "degraded", "exerciseId": "ex-1",
                                     "completed": 3, "total": 3, "ready": 0}
        assert sink.of("preparation")[-1] == {"type": "preparation", **coach.preparation}
        assert not any(m["state"] == "ready" for m in sink.of("preparation"))
        if failure != "author_error":
            assert adapter.calls
    finally:
        await coach.close()


async def test_partial_voice_failure_counts_settled_separately_from_ready(session_factory, monkeypatch):
    class FailFirstVoice(FakeVoiceStream):
        async def stream(self, text, scope, generation_id, delivery, **kwargs):
            self.error_after = None if self.calls else 0
            async for chunk in super().stream(text, scope, generation_id, delivery, **kwargs):
                yield chunk

    adapter = FailFirstVoice()
    coach, sink, _, _ = prepared_coach(session_factory, monkeypatch, adapter=adapter)
    try:
        coach.schedule_prebuild()
        await finished(coach.prebuild_job)
        assert sink.of("preparation")[1] == {
            "type": "preparation", "state": "preparing", "exerciseId": "ex-1",
            "completed": 1, "total": 3, "ready": 0,
        }
        assert coach.preparation == {"state": "degraded", "exerciseId": "ex-1",
                                     "completed": 3, "total": 3, "ready": 2}
        assert set(coach.prebuilt).intersection(CURRENT_KEYS) == CURRENT_KEYS - {"T01:opening"}
        assert sink.of("preparation")[-1] == {"type": "preparation", **coach.preparation}
    finally:
        await coach.close()


async def test_scenario_ready_atomically_embeds_pending_preparation(session_factory, monkeypatch):
    lines = line_script([])

    def script(body):
        if body["text"]["format"]["name"] == "coach_scenario_bible":
            return bible_for(json.loads(body["input"][0]["content"]))
        return lines(body)

    adapter = GatedVoice()
    coach, sink, _, _ = prepared_coach(session_factory, monkeypatch, adapter=adapter, script=script)
    coach.scenario_card = coach.scenario_bible = None
    coach.scenario_cards = [dict(CARD)]
    coach.scenario_plan = scenario.parse_plan(PLAN)
    try:
        await coach.handle({"type": "scenario_select", "index": 0})
        await finished(coach.scenario_job)
        messages = sink.of("scenario")
        assert [m["state"] for m in messages] == ["building", "ready"]
        ready = messages[-1]
        assert ready["preparation"] == {"state": "preparing", "exerciseId": "ex-1",
                                        "completed": 0, "total": 3, "ready": 0}
        assert coach.prebuild_job is not None
        assert ready == coach.scenario_state()
        await reached(adapter.entered["ex-1"])
        adapter.release["ex-1"].set()
        await reached(adapter.entered["ex-2"])
        # The already-sent scenario must remain a snapshot, not mutate with progress.
        assert ready["preparation"]["state"] == "preparing"
        assert coach.scenario_state()["preparation"]["state"] == "ready"
    finally:
        await coach.close()


async def test_reconnect_announce_starts_pending_work_and_does_not_duplicate_active_job(session_factory, monkeypatch):
    adapter = GatedVoice()
    coach, sink, _, _ = prepared_coach(session_factory, monkeypatch, adapter=adapter)
    try:
        assert coach.preparation is None and coach.prebuild_job is None
        await coach.announce()
        job = coach.prebuild_job
        assert sink.of("scenario")[-1]["preparation"] == {
            "state": "preparing", "exerciseId": "ex-1", "completed": 0, "total": 3, "ready": 0,
        }
        await reached(adapter.entered["ex-1"])
        await coach.announce()
        assert coach.prebuild_job is job
        assert sink.of("scenario")[-1]["preparation"] == coach.preparation
        adapter.release["ex-1"].set()
        await reached(adapter.entered["ex-2"])
        await coach.announce()
        assert coach.prebuild_job is job
        assert sink.of("scenario")[-1]["preparation"]["state"] == "ready"
    finally:
        await coach.close()


@pytest.mark.parametrize("phase", ["setup", "waiting-start"])
async def test_context_next_exercise_replaces_counts_while_future_prebuild_runs(session_factory, monkeypatch, phase):
    adapter = GatedVoice()
    coach, sink, run_id, _ = prepared_coach(session_factory, monkeypatch, adapter=adapter)
    try:
        coach.schedule_prebuild()
        adapter.release["ex-1"].set()
        await reached(adapter.entered["ex-2"])
        job = coach.prebuild_job
        message = live_context(event("exercise_ready", run_id, exercise="ex-2", phase=phase))
        await coach.handle(message)
        assert coach.plan_cursor == 1 and coach._preparation_targets == NEXT_KEYS
        assert sink.of("preparation")[-1] == {
            "type": "preparation", "state": "preparing", "exerciseId": "ex-2",
            "completed": 0, "total": 3, "ready": 0,
        }
        count = len(sink.of("preparation"))
        await coach.handle(message)  # Idempotent context resend must not reset the new preparation.
        assert len(sink.of("preparation")) == count and coach.prebuild_job is job
        adapter.release["ex-2"].set()
        await reached(adapter.entered["ex-3"])
        assert coach.preparation == {"state": "ready", "exerciseId": "ex-2",
                                     "completed": 3, "total": 3, "ready": 3}
        assert NEXT_KEYS <= coach.prebuilt.keys() and not job.done()
        assert sink.of("preparation")[-1] == {"type": "preparation", **coach.preparation}
    finally:
        await coach.close()


async def test_next_exercise_already_prebuilt_is_immediately_ready_from_context(session_factory, monkeypatch):
    coach, sink, run_id, fake = prepared_coach(session_factory, monkeypatch)
    try:
        coach.schedule_prebuild()
        await finished(coach.prebuild_job)
        assert NEXT_KEYS <= coach.prebuilt.keys()
        cached = {key: coach.prebuilt[key] for key in NEXT_KEYS}
        requests = len(fake.calls)
        await coach.handle(live_context(event("exercise_ready", run_id, exercise="ex-2")))
        assert coach._preparation_targets == NEXT_KEYS
        assert sink.of("preparation")[-1] == {
            "type": "preparation", "state": "ready", "exerciseId": "ex-2",
            "completed": 3, "total": 3, "ready": 3,
        }
        await finished(coach.prebuild_job)
        assert all(coach.prebuilt[key] is line for key, line in cached.items())
        # Moving the lookahead can prepare new third-exercise moments, but must
        # not re-author the cached second exercise, including its introduction.
        new_topics = [json.loads(body["input"][0]["content"])["topicKey"] for body in fake.calls[requests:]]
        assert all(":ex-3" in topic for topic in new_topics), new_topics
    finally:
        await coach.close()


async def test_voice_unavailable_announces_degraded_instead_of_missing_preparation(session_factory, monkeypatch):
    coach, sink, _, fake = prepared_coach(session_factory, monkeypatch, streamer=False)
    try:
        await coach.announce()
        state = sink.of("scenario")[-1]
        assert state["state"] == "ready"
        assert state.get("preparation", {}).get("state") == "degraded", state
        assert state["preparation"]["exerciseId"] == "ex-1"
        assert coach.prebuild_job is None and not fake.calls
    finally:
        await coach.close()