"""V9: «why this exercise» on its first rest (catalog facts + goal) and the set review from machine telemetry."""

import json

from app.schemas.coach_control import CoachPreferences
from app.services.coach import progress
from app.services.coach.facts import AllowedFact
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.prompts import REVIEW_MODULE, AuthorRequest, build_prompt
from app.services.coach.validation import validate
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, seed, settle

EPOCH = {"scope_epoch": 1, "valid_until_ms": 10**13}


def test_why_facts_come_from_the_catalog():
    found = {f.id: f for f in progress.why_facts("machine-pulldown", **EPOCH)}
    assert found["muscles"].claim == "Работают бицепс и широчайшие"
    assert "многосуставное" in found["mechanic"].claim and found["force"].claim == "Движение тянущее"
    assert all(f.provenance == "exercise-catalog" for f in found.values())
    assert progress.why_facts("no-such-exercise", **EPOCH) == []


async def test_first_rest_explains_the_exercise_once(session_factory):
    seen = []

    def script(body):
        data = json.loads(body["input"][0]["content"])
        seen.append((body, data))
        used = [f["id"] for f in data["allowedFacts"] if f["id"] == "muscles"][:1]
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": used,
                "silenceReason": None, "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"},
                "text": "Здесь работают бицепс и широчайшие: это база для сильной спины."}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, goal="strength"),
                                     fake_text=FakeTextAuthor(script))
    rest = {"restMs": 120_000, "restElapsedMs": 20_000, "exerciseSlug": "machine-pulldown", "exerciseName": "Тяга сверху"}
    await coach.handle(event("rest_long_opportunity", run_id, exercise="ex-1", set_ordinal=1, phase="rest", context=rest))
    await settle(coach)
    assert sink.of("speech_start"), (sink.of("decision"), sink.of("event_rejected"))
    assert sink.of("speech_start")[-1]["triggerId"] == "T70"
    body, data = seen[-1]
    assert {"muscles", "mechanic"} <= {f["id"] for f in data["allowedFacts"]}
    assert "Цель пользователя — сила" in body["instructions"]
    assert "ex-1" in coach.why_done
    coach.director.last_start_ms = None
    await coach.handle(event("rest_long_opportunity", run_id, exercise="ex-1", set_ordinal=1, phase="rest", epoch=2,
                             context=rest))
    await settle(coach)
    assert all(m["triggerId"] != "T70" for m in sink.of("speech_start")[1:])
    await coach.close()


def test_review_module_and_a_rest_cue_from_measured_facts():
    tempo = AllowedFact("set-tempo", "По датчикам тренажёра опускание шло заметно быстрее подъёма", "derived-validated",
                        "fast-descent", permits=("tempo", "movement-cue"), scope_epoch=1, valid_until_ms=10**13)
    saved = AllowedFact("saved-set", "Выполнено десять повторений", "confirmed", 10, "reps", numbers=(10,), scope_epoch=1,
                        valid_until_ms=10**13)
    request = AuthorRequest("T36", "rest", "rest/full-feedback", ("factual-feedback",), "result", 30, facts=(saved, tempo))
    assert REVIEW_MODULE in build_prompt(request).instructions
    output = {"action": "speak", "intent": "factual-feedback", "topicKey": "result", "usedFactIds": ["saved-set", "set-tempo"],
              "silenceReason": None, "delivery": {"energy": "warm", "pace": "normal", "emphasis": "result"},
              "text": "Десять повторений. Опускание шло быстрее подъёма — в следующем подходе опускай медленнее."}
    assert validate(output, request).ok
    plain = AuthorRequest("T36", "rest", "rest/full-feedback", ("factual-feedback",), "result", 30, facts=(saved,))
    assert REVIEW_MODULE not in build_prompt(plain).instructions
    assert not validate({**output, "usedFactIds": ["saved-set"]}, plain).ok


async def test_saved_set_with_metrics_gets_the_review_module(session_factory):
    seen = []

    def script(body):
        seen.append(body)
        data = json.loads(body["input"][0]["content"])
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": list(data["lockedFactIds"]) or ["saved-set"], "silenceReason": None,
                "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}, key: "Десять повторений, ровно."}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    with session_factory() as db:
        _, _, set_id = seed(db, actual=10, planned=10, status="completed")
    await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id},
                             context={"restMs": 90_000, "setMetrics": {"reps": 10, "eccentricS": 0.5, "concentricS": 1.2}}))
    await settle(coach)
    assert REVIEW_MODULE in seen[-1]["instructions"]
    await coach.close()
