"""V4: story counters computed from saved results only; boss health on the last exercise; voiced as facts."""

import json

from app.schemas.coach_control import CoachPreferences
from app.services.coach import counters
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.prompts import AuthorRequest
from app.services.coach.validation import validate
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, settle
from app.tests.test_coach_v3_progress import workout

BIBLE = {"plan": [{"id": "ex-1", "name": "Тяга", "sets": 2}, {"id": "ex-2", "name": "Жим", "sets": 4}],
         "counters": [{"id": "c1", "label": "Очки славы", "source": "reps"},
                      {"id": "c2", "label": "Пройдено пути", "source": "plan"}],
         "acts": [{"act": 1, "title": "Старт", "goal": "Разогнаться", "exerciseIds": ["ex-1"]},
                  {"act": 2, "title": "Босс", "goal": "Победить", "exerciseIds": ["ex-2"]}],
         "exerciseRoles": {}, "lexicon": [], "motifs": [], "premise": "", "coachRole": "", "userRole": "", "finale": ""}
COMMON = {"scope_epoch": 1, "valid_until_ms": 10**13, "ref": "x"}


def test_values_follow_fixed_formulas():
    found = counters.values(BIBLE, counters.Totals(reps=24, tonnage=480, sets=3), records=1, steady=2)
    assert found == [{"id": "c1", "label": "Очки славы", "source": "reps", "value": 240},
                     {"id": "c2", "label": "Пройдено пути", "source": "plan", "value": 50}]


def test_raw_counter_labels_and_units_cannot_be_replaced_by_legacy_story_names():
    bible = {**BIBLE, "counters": [
        {"id": "c1", "label": "Пройдено заездов", "source": "sets"},
        {"id": "c2", "label": "Кристаллы силы", "source": "tonnage"},
        {"id": "c3", "label": "Ровные круги", "source": "steady"}]}
    found = counters.values(bible, counters.Totals(reps=24, tonnage=480, sets=3), records=0, steady=2)
    assert [c["label"] for c in found] == ["Завершённые подходы", "Поднятый тоннаж", "Подходы в ровном темпе"]
    assert [f.claim for f in counters.facts(found, COMMON)] == [
        "Завершённые подходы: три подхода", "Поднятый тоннаж: четыреста восемьдесят килограммов",
        "Подходы в ровном темпе: два подхода"]
    # facts() is also a boundary: callers may supply old counter state directly.
    legacy = [{**c, "label": "Заезды"} for c in found]
    assert counters.facts(legacy, COMMON) == counters.facts(found, COMMON)


def test_boss_health_only_on_the_boss_exercise_of_boss_worlds():
    assert counters.boss_health(BIBLE, "rpg", "ex-2", 1) == {"id": "boss", "label": "Здоровье босса", "source": "boss",
                                                              "value": 75}
    assert counters.boss_health(BIBLE, "rpg", "ex-2", 4)["value"] == 0
    assert counters.boss_health(BIBLE, "rpg", "ex-1", 1) is None
    assert counters.boss_health(BIBLE, "race", "ex-2", 1) is None
    [dead] = counters.facts([{"id": "boss", "label": "Здоровье босса", "source": "boss", "value": 0}], COMMON)
    assert dead.claim == "Здоровье босса на нуле: босс повержен" and not dead.numbers


def test_counter_facts_are_speakable_and_validated():
    [glory] = counters.facts([{"id": "c1", "label": "Очки славы", "source": "reps", "value": 240}], COMMON)
    assert glory.claim == "Очки славы: двести сорок" and glory.numbers == (240,) and glory.provenance == "scenario-counter"
    request = AuthorRequest("T36", "rest", "rest/full-feedback", ("motivation",), "t", 30, facts=(glory,))
    output = {"action": "speak", "intent": "motivation", "topicKey": "t", "usedFactIds": ["counter-c1"],
              "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"},
              "text": "Чат ревёт: очки славы уже двести сорок!"}
    assert validate(output, request).ok
    invented = {**output, "text": "Чат ревёт: очки славы уже тысяча!"}
    assert validate(invented, request).reason == "number"


async def test_live_counters_reach_the_line_and_the_browser(session_factory):
    seen = []

    def script(body):
        data = json.loads(body["input"][0]["content"])
        seen.append(data)
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": list(data["lockedFactIds"]) or ["counter-c1"], "silenceReason": None,
                "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"}, key: "Очки славы: сто."}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    coach.scenario_card, coach.scenario_bible = {"title": "Боссфайт", "archetype": "rpg"}, BIBLE
    with session_factory() as db:
        _, _, [set_id] = workout(db, sets=((20, 10),))
    await coach.handle(event("set_persisted", run_id, exercise="ex-1", set_ordinal=1, phase="rest",
                             refs={"backendSetId": set_id}, context={"restMs": 90_000}))
    await settle(coach)
    state = sink.of("scenario_state")[-1]
    assert state["counters"][0] == {"id": "c1", "label": "Очки славы", "source": "reps", "value": 100}
    assert any(f["id"] == "counter-c1" for f in seen[-1]["allowedFacts"])
    assert sink.of("speech_start"), sink.of("decision")
    assert coach.scenario_state()["counters"][0]["value"] == 100
    await coach.close()
