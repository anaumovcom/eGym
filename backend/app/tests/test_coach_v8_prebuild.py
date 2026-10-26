"""V8: result-independent story lines are prepared (text + voice) while the user prepares and played at their moment."""

import asyncio
import json

from app.models.coach import CoachAttempt
from app.schemas.coach_control import CoachPreferences
from app.services.coach import live, scenario
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.voice import decode_frame
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, settle
from app.tests.test_coach_v1_scenarios import PLAN, bible_for


def script(calls):
    def run(body):
        data = json.loads(body["input"][0]["content"])
        calls.append(data)
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": [f["id"] for f in data["allowedFacts"] if f["id"] == "exercise"][:1],
                "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"},
                "text": ("Пилот, на трассу, рёв моторов уже слышен." if len(calls) % 2 else "Держим болид, финиш близко.")}
    return run


async def wait(job):
    for _ in range(500):
        if job is not None and job.done():
            return
        await asyncio.sleep(0.01)


async def test_prebuild_then_play_without_new_paid_requests(session_factory, monkeypatch):
    monkeypatch.setattr(live, "PREBUILD_START_DELAY_S", 0)
    calls = []
    # Story lines only here; plan-only in-set lines (V12) have their own test.
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**{**HYBRID, "during_sets": False}),
                                     fake_text=FakeTextAuthor(script(calls)))
    plan = scenario.parse_plan(PLAN)
    coach.scenario_card = {"title": "Гонка героев", "archetype": "race"}
    coach.scenario_bible = scenario.validate_bible(bible_for({"plan": PLAN}), plan)
    # Before the workout starts the story opening is prepared first.
    assert [t[0] for t in coach._prebuild_targets()] == ["T01:opening", "T67:ex-2", "T68:ex-3", "T69:ex-3"]
    coach.schedule_prebuild()
    await wait(coach.prebuild_job)
    assert set(coach.prebuilt) == {"T01:opening", "T67:ex-2", "T68:ex-3", "T69:ex-3"}
    with session_factory() as db:
        before = db.query(CoachAttempt).filter_by(run_id=run_id).count()
        purposes = {a.purpose for a in db.query(CoachAttempt).filter_by(run_id=run_id)}
    assert purposes == {"prebuild"} and before == 8  # text + voice for four lines
    opening = coach.prebuilt["T01:opening"].text
    await coach.handle(event("workout_started", run_id, exercise="ex-1", context={"exerciseName": "Жим ногами",
                                                                                 "exerciseCount": 3}))
    await settle(coach)
    start = sink.of("speech_start")[-1]
    assert start["triggerId"] == "T01" and start["prebuilt"] is True and start["text"] == opening
    assert [t[0] for t in coach._prebuild_targets()] == ["T67:ex-2", "T68:ex-3", "T69:ex-3"]
    prepared = coach.prebuilt["T67:ex-2"].text
    await coach.handle(event("exercise_ready", run_id, exercise="ex-2", context={"exerciseName": "Тяга сверху"}))
    await settle(coach)
    start = sink.of("speech_start")[-1]
    assert start["triggerId"] == "T67" and start["prebuilt"] is True and start["text"] == prepared
    end = sink.of("speech_end")[-1]
    assert end["status"] == "complete" and end["frames"] > 0
    frames = [decode_frame(b) for b in sink.bytes if decode_frame(b).metadata.generation_id == start["generationId"]]
    assert frames and frames[-1].metadata.final and frames[0].metadata.scope.exercise_id == "ex-2"
    with session_factory() as db:
        assert db.query(CoachAttempt).filter_by(run_id=run_id).count() == before
    assert "T67:ex-2" not in coach.prebuilt
    await coach.close()


async def test_live_moments_wait_behind_a_prebuild_item(session_factory, monkeypatch):
    monkeypatch.setattr(live, "PREBUILD_START_DELAY_S", 0)
    calls = []
    slow = FakeTextAuthor(script(calls), delay_s=0.2)
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=slow)
    plan = scenario.parse_plan(PLAN)
    coach.scenario_card = {"title": "Гонка героев", "archetype": "race"}
    coach.scenario_bible = scenario.validate_bible(bible_for({"plan": PLAN}), plan)
    coach.schedule_prebuild()
    for _ in range(100):
        if coach._prebuild_items:
            break
        await asyncio.sleep(0.01)
    await coach.handle(event("rep_milestone", run_id, exercise="ex-1", set_ordinal=1, phase="active-set",
                             context={"moment": "velocity_drop_hard", "phaseElapsedMs": 30_000,
                                      "telemetry": {"reps": 6, "velocityDropPct": 35}}))
    assert len(coach.queue) == 1 and not any(d.get("reason") == "pipeline_busy" for d in sink.of("decision"))
    await wait(coach.prebuild_job)
    await settle(coach)
    assert any(m["triggerId"] == "T21" for m in sink.of("speech_start")), sink.of("decision")
    await coach.close()
