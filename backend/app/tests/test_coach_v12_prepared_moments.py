"""V12: plan-only moments (set start/finish, tempo and «hardest reps» cues, «what it works») are prepared one
exercise ahead and play only while the live moment still carries the same facts and mood."""

import asyncio
import itertools
import json

from app.schemas.coach_control import CoachPreferences
from app.services.coach import live, scenario
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.memory import opening
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, settle
from app.tests.test_coach_v1_scenarios import bible_for

PLAN = [{"id": "ex-1", "name": "Тяга сверху", "sets": 2, "slug": "machine-pulldown", "targets": [10, 10]},
        {"id": "ex-2", "name": "Жим от груди", "sets": 2, "slug": "machine-chest-press", "targets": [10, 8]},
        {"id": "ex-3", "name": "Разгибание ног", "sets": 2, "kind": "machine", "targets": [10, 10]}]
OPENERS = ("Поехали", "Держим", "Ракета", "Мотор", "Трасса", "Рывок", "Пилот", "Болид", "Финиш", "Газуем", "Вираж",
           "Рация", "Шины", "Свет", "Гонка", "Старт", "Круг", "Флаг", "Рёв", "Зеркало", "Пит", "Механик")


def script(calls):
    serial = itertools.count()

    def run(body):
        data = json.loads(body["input"][0]["content"])
        calls.append(data)
        facts = {f["id"] for f in data["allowedFacts"]}
        used = ["target"] if "target" in facts else ["exercise"] if "exercise" in facts else []
        opener = OPENERS[next(serial) % len(OPENERS)]
        text = f"{opener}, цель — десять повторений." if used == ["target"] else f"{opener}, этап идёт по плану."
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": used,
                "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"},
                "text": text}
    return run


async def prepared_coach(session_factory, monkeypatch, prefs=None):
    monkeypatch.setattr(live, "PREBUILD_START_DELAY_S", 0)
    calls = []
    coach, sink, run_id = make_coach(session_factory, prefs or CoachPreferences(**HYBRID),
                                     fake_text=FakeTextAuthor(script(calls)))
    coach.scenario_card = {"title": "Гонка героев", "archetype": "race"}
    coach.scenario_bible = scenario.validate_bible(bible_for({"plan": PLAN}), scenario.parse_plan(PLAN))
    coach.workout_started = True  # The opening is covered elsewhere; here the workout is under way.
    return coach, sink, run_id, calls


async def wait(job):
    for _ in range(1000):
        if job is not None and job.done():
            return
        await asyncio.sleep(0.01)


def test_plan_keeps_slug_and_set_goals_for_prepared_lines():
    parsed = scenario.parse_plan([{"id": "a", "name": "Жим", "sets": 2, "slug": "machine-chest-press", "targets": [10, None]},
                                  {"id": "b", "name": "Тяга", "sets": 2, "slug": "Bad Slug!", "targets": [10]}])
    assert parsed[0].slug == "machine-chest-press" and parsed[0].targets == (10, None)
    assert parsed[1].slug is None and parsed[1].targets == ()  # a malformed slug or a wrong-length goal list is dropped


async def test_targets_cover_the_current_and_next_exercise_and_story_lines_later(session_factory, monkeypatch):
    coach, _, _, _ = await prepared_coach(session_factory, monkeypatch, CoachPreferences(**{**HYBRID, "density": "show"}))
    keys = [t.key for t in coach._prebuild_targets()]
    assert keys[:7] == ["T21:ex-1:1:start", "T19:ex-1:fast-descent", "T21:ex-1:velocity_drop_hard",
                        "T21:ex-1:1:finish", "T70:ex-1", "T21:ex-1:2:start", "T21:ex-1:2:finish"]
    assert "T67:ex-2" in keys and "T70:ex-2" in keys and "T21:ex-2:2:finish" in keys
    # The third exercise is beyond the lookahead: only its story lines (boss, last set) are prepared now.
    assert keys[-2:] == ["T68:ex-3", "T69:ex-3"] and not [k for k in keys if k.startswith(("T21:ex-3", "T19:ex-3"))]
    await coach.close()
    quiet, _, _, _ = await prepared_coach(session_factory, monkeypatch,
                                          CoachPreferences(**{**HYBRID, "density": "quiet"}))
    assert not [t for t in quiet._prebuild_targets() if t.trigger in {"T19", "T21"}]
    await quiet.close()
    calm, _, _, _ = await prepared_coach(session_factory, monkeypatch,
                                         CoachPreferences(**{**HYBRID, "density": "companion"}))
    keys = [t.key for t in calm._prebuild_targets()]
    assert "T21:ex-1:1:start" in keys and not [k for k in keys if k.startswith("T19") or "velocity" in k]
    await calm.close()


async def test_prepared_set_lines_play_only_when_facts_and_mood_still_match(session_factory, monkeypatch):
    coach, sink, run_id, calls = await prepared_coach(session_factory, monkeypatch,
                                                      CoachPreferences(**{**HYBRID, "density": "show"}))
    try:
        coach.schedule_prebuild()
        await wait(coach.prebuild_job)
        assert {"T21:ex-1:1:start", "T21:ex-1:1:finish", "T70:ex-1", "T21:ex-1:2:start"} <= set(coach.prebuilt)
        assert coach.moods.current is None  # preparing moments never moved the live mood
        prepared = [c for c in calls if "preparedLines" in c]
        assert prepared and all(len(c["preparedLines"]) <= 10 for c in prepared)  # each line saw the earlier ones
        # ...and their first words are taken: neither a later prepared line nor a live one may open the same way.
        assert opening(prepared[-1]["preparedLines"][-1]) in prepared[-1]["recentOpenings"]
        upcoming = coach.prebuilt["T21:ex-1:1:finish"].text
        live_op = type("Op", (), {"exercise_id": "ex-1"})()
        assert opening(upcoming) in coach._openings_to_avoid(live_op)
        context = {"exerciseName": "Тяга сверху", "totalSets": 2}

        async def moment(kind, set_ordinal, **extra):
            coach.director.last_start_ms = None
            await coach.handle(event(kind, run_id, exercise="ex-1", set_ordinal=set_ordinal, phase="active-set",
                                     context={**context, **extra}))
            await settle(coach)
            return sink.of("speech_start")[-1]

        start = await moment("set_activated", 1, moment="start", phaseElapsedMs=3_000, targetReps=10)
        assert start["triggerId"] == "T21" and start["prebuilt"] is True and "десять" in start["text"]
        # After a partial set the cheerful prepared finish is not played: the moment is written live, with care.
        coach.moods.exercise_outcomes["ex-1"] = "partial"
        before = len(calls)
        finish = await moment("last_rep_pending", 1, moment="finish", phaseElapsedMs=30_000, targetReps=10)
        assert finish["triggerId"] == "T21" and not finish.get("prebuilt") and len(calls) == before + 1
        coach.moods.exercise_outcomes["ex-1"] = "full"
        # The plan changed under the prepared line (twelve, not ten): its claim no longer holds, so it is live.
        before = len(calls)
        second = await moment("set_activated", 2, moment="start", phaseElapsedMs=3_000, targetReps=12)
        assert second["triggerId"] == "T21" and not second.get("prebuilt") and len(calls) == before + 1
        # Moments strictly behind the workout are dropped: the first rest's «what it works» is gone in set two.
        assert "T70:ex-1" not in coach.prebuilt and "T21:ex-1:1:finish" not in coach.prebuilt
    finally:
        await coach.close()
