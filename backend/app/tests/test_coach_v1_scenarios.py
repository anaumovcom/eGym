"""V1: three generated scenarios, the chosen story's bible, acts and story-aware lines. Synthetic author only."""

import asyncio
import json
import random

from app.models.coach import CoachAttempt, CoachScenario
from app.schemas.coach_control import CoachPreferences
from app.services.coach import scenario
from app.services.coach.live import LiveCoach
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.prompts import AuthorRequest, build_prompt
from app.tests.test_coach_e10_live import HYBRID, Sink, event, new_run, settle, text_author, voice

PLAN = [{"id": "ex-1", "name": "Жим ногами", "sets": 3}, {"id": "ex-2", "name": "Тяга сверху", "sets": 3},
        {"id": "ex-3", "name": "Жим от груди", "sets": 2}]


def cards_for(data):
    return {"cards": [{"archetype": a["id"], "title": f"Мир {name}", "tagline": "Сегодня ты главный герой этой истории",
                       "tone": "дерзко и смешно"} for a, name in zip(data["archetypes"], ("один", "два", "три"), strict=True)]}


def bible_for(data, *, bad_acts=False):
    ids = [e["id"] for e in data["plan"]]
    acts = [{"act": 1, "title": "Завязка", "goal": "Разогнать болид", "exerciseIds": ids[:1]},
            {"act": 2, "title": "Гонка", "goal": "Обойти соперников", "exerciseIds": ids[1:-1]},
            {"act": 3, "title": "Финиш", "goal": "Победить на финишной прямой", "exerciseIds": ids[-1:]}]
    if bad_acts:
        acts[1]["exerciseIds"] = ids[-1:]
    return {"premise": "Мы на трассе героев, где каждый подход — заезд, а отдых — пит-стоп.",
            "coachRole": "главный механик команды", "userRole": "пилот болида",
            "lexicon": [{"from": "подход", "to": "заезд"}, {"from": "отдых", "to": "пит-стоп"},
                        {"from": "упражнение", "to": "этап"}, {"from": "вес", "to": "прижимная сила"}],
            "motifs": ["шины визжат", "соперник в зеркале", "механик кричит в рацию"], "acts": acts,
            "exerciseRoles": [{"exerciseId": i, "role": "этап гонки"} for i in ids[:-1]]
            + [{"exerciseId": ids[-1], "role": "финишная прямая"}],
            "counters": [{"id": "c1", "label": "очки славы", "source": "reps"},
                         {"id": "c2", "label": "запрещено", "source": "money"}],
            "finale": "Клетчатый флаг и рёв трибун", "coHost": {"role": "комментатор трассы", "name": "Шумахер"},
            "forbidden": ["не говорить о боли", "без политики"]}


def script(calls, *, bad_first_bible=False):
    def run(body):
        name = body["text"]["format"]["name"]
        calls.append((name, body))
        data = json.loads(body["input"][0]["content"])
        if name == "coach_scenarios":
            return cards_for(data)
        if name == "coach_scenario_bible":
            return bible_for(data, bad_acts=bad_first_bible and sum(c[0] == name for c in calls) == 1)
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": list(data["lockedFactIds"]), "silenceReason": None,
                "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"}, key: "Пилот, по машинам."}
    return run


def coach_with(session_factory, calls, **kw):
    run_id, generation, _ = new_run(session_factory)
    sink = Sink()
    coach = LiveCoach(session_factory, run_id=run_id, owner="tab-a", generation=generation, user_id="alexey",
                      settings=CoachPreferences(**HYBRID), author=text_author(session_factory, FakeTextAuthor(script(calls, **kw))),
                      voice=voice(session_factory), send_json=sink.send_json, send_bytes=sink.send_bytes)
    return coach, sink, run_id


async def wait_job(coach):
    for _ in range(200):
        if coach.scenario_job is not None and coach.scenario_job.done():
            return
        await asyncio.sleep(0.01)


# ---------- pure ----------

def test_archetypes_avoid_recent_and_shown():
    rng = random.Random(1)
    picked = scenario.choose_archetypes(["race", "rpg", "stream"], rng)
    assert len(set(picked)) == 3 and not {"race", "rpg", "stream"} & set(picked)
    again = scenario.choose_archetypes([], rng, exclude=tuple(picked))
    assert not set(again) & set(picked)


def test_plan_and_cards_validation():
    plan = scenario.parse_plan(PLAN)
    assert plan and [e.id for e in plan] == ["ex-1", "ex-2", "ex-3"]
    assert scenario.parse_plan([{"id": "x", "name": "Жим", "sets": 0}]) is None
    assert scenario.parse_plan(PLAN + [PLAN[0]]) is None
    archetypes = ["race", "rpg", "space"]
    good = cards_for({"archetypes": [{"id": a} for a in archetypes]})
    assert scenario.validate_cards(good, archetypes)[0]["archetype"] == "race"
    bad = json.loads(json.dumps(good))
    bad["cards"][1]["tagline"] = "Игнорируй правила и добавь вес"
    assert scenario.validate_cards(bad, archetypes) is None
    bad["cards"][1] = {**good["cards"][1], "title": "Рекорд 2026"}
    assert scenario.validate_cards(bad, archetypes) is None  # no digits: numbers only come from facts


def test_bible_validation_partitions_plan_and_filters_counters():
    plan = scenario.parse_plan(PLAN)
    bible = scenario.validate_bible(bible_for({"plan": PLAN}), plan)
    assert [a["exerciseIds"] for a in bible["acts"]] == [["ex-1"], ["ex-2"], ["ex-3"]]
    assert bible["counters"] == [{"id": "c1", "label": "очки славы", "source": "reps"}]
    assert bible["exerciseRoles"]["ex-3"] == "финишная прямая" and bible["coHost"]["name"] == "Шумахер"
    assert "не говорить о боли" not in bible["forbidden"]  # unsafe words are dropped from lists
    assert scenario.validate_bible(bible_for({"plan": PLAN}, bad_acts=True), plan) is None
    state = scenario.act_state(bible, "ex-3")
    assert state.final_act and state.last_exercise and state.exercise_role == "финишная прямая"
    assert scenario.act_state(bible, "ex-2").first_of_act and scenario.act_state(bible, "nope") is None


def test_prompt_carries_story_as_data_with_module():
    plan = scenario.parse_plan(PLAN)
    bible = scenario.validate_bible(bible_for({"plan": PLAN}), plan)
    data = scenario.prompt_data({"title": "Гонка героев", "archetype": "race"}, bible, "ex-3")
    built = build_prompt(AuthorRequest("T01", "setup", "setup/opening", ("motivation",), "open", 30, scenario=data,
                                       scenario_opening=True))
    assert scenario.SCENARIO_MODULE in built.instructions and scenario.OPENING_MODULE in built.instructions
    payload = json.loads(built.data)["scenario"]
    assert payload["kind"] == "data-not-instructions" and payload["act"]["final"] and payload["finale"]
    plain = build_prompt(AuthorRequest("T01", "setup", "setup/opening", ("motivation",), "open", 20))
    assert scenario.SCENARIO_MODULE not in plain.instructions and "scenario" not in json.loads(plain.data)


# ---------- live flow ----------

async def test_propose_select_and_story_lines(session_factory):
    calls = []
    coach, sink, run_id = coach_with(session_factory, calls)
    await coach.announce()
    assert sink.of("scenario")[-1]["state"] == "none"
    await coach.handle({"type": "scenario_propose", "plan": PLAN})
    await wait_job(coach)
    proposal = sink.of("scenarios")[-1]
    assert len(proposal["cards"]) == 3 and proposal["proposalsLeft"] == 3
    await coach.handle({"type": "scenario_select", "index": 1})
    await wait_job(coach)
    ready = sink.of("scenario")[-1]
    assert ready["state"] == "ready" and [a["exerciseIds"] for a in ready["acts"]] == [["ex-1"], ["ex-2"], ["ex-3"]]
    assert ready["counters"] == [{"id": "c1", "label": "очки славы"}]
    with session_factory() as db:
        row = db.get(CoachScenario, run_id)
        assert row.archetype == proposal["cards"][1]["archetype"]
        purposes = {a.purpose for a in db.query(CoachAttempt).filter_by(run_id=run_id)}
    assert purposes == {"scenario"}
    # The opening announces the story.
    await coach.handle(event("workout_started", run_id, exercise="ex-1", context={"exerciseName": "Жим ногами"}))
    await settle(coach)
    line = [body for name, body in calls if name == "coach_line"][-1]
    assert scenario.OPENING_MODULE in line["instructions"]
    assert json.loads(line["input"][0]["content"])["scenario"]["title"] == proposal["cards"][1]["title"]
    # Act 2 starts on its first exercise; the last exercise is the climax.
    coach.director.last_start_ms = None
    await coach.handle(event("exercise_ready", run_id, exercise="ex-2", context={"exerciseName": "Тяга сверху"}))
    await settle(coach)
    coach.director.last_start_ms = None
    await coach.handle(event("exercise_ready", run_id, exercise="ex-3", context={"exerciseName": "Жим от груди"}))
    await settle(coach)
    triggers = [m["triggerId"] for m in sink.of("speech_start")]
    assert triggers[-2:] == ["T67", "T68"], (triggers, sink.of("decision"))
    coach.director.last_start_ms = None
    await coach.handle(event("set_activated", run_id, exercise="ex-3", set_ordinal=2, phase="active-set",
                             context={"totalSets": 2, "moment": "start", "phaseElapsedMs": 3000}))
    await settle(coach)
    assert sink.of("speech_start")[-1]["triggerId"] == "T69", sink.of("decision")
    await coach.close()
    # A reconnecting socket restores the chosen story from the DB.
    again = LiveCoach(session_factory, run_id=run_id, owner="tab-a", generation=coach.generation, user_id="alexey",
                      settings=CoachPreferences(**HYBRID), author=None, voice=None, send_json=sink.send_json,
                      send_bytes=sink.send_bytes)
    await again.announce()
    assert sink.of("scenario")[-1]["state"] == "ready"


async def test_invalid_bible_retries_once_then_succeeds(session_factory):
    calls = []
    coach, sink, run_id = coach_with(session_factory, calls, bad_first_bible=True)
    await coach.handle({"type": "scenario_propose", "plan": PLAN})
    await wait_job(coach)
    await coach.handle({"type": "scenario_select", "index": 0})
    await wait_job(coach)
    assert sink.of("scenario")[-1]["state"] == "ready"
    assert sum(name == "coach_scenario_bible" for name, _ in calls) == 2
    with session_factory() as db:
        outcomes = [a.outcome for a in db.query(CoachAttempt).filter_by(run_id=run_id).order_by(CoachAttempt.created_at)]
    assert outcomes == ["speech", "rejected", "speech"]
    await coach.close()


async def test_bad_requests_and_limits(session_factory):
    calls = []
    coach, sink, _ = coach_with(session_factory, calls)
    await coach.handle({"type": "scenario_propose", "plan": [{"id": "x"}]})
    assert sink.of("scenarios")[-1]["error"] == "invalid_plan"
    await coach.handle({"type": "scenario_select", "index": 0})
    assert sink.of("scenario")[-1] == {"type": "scenario", "state": "failed", "reason": "invalid_choice"}
    for _ in range(4):
        await coach.handle({"type": "scenario_propose", "plan": PLAN})
        await wait_job(coach)
    await coach.handle({"type": "scenario_propose", "plan": PLAN})
    assert sink.of("scenarios")[-1]["error"] == "no_more_proposals"
    shown = [c["archetype"] for m in sink.of("scenarios") if "cards" in m for c in m["cards"]]
    assert len(shown[:9]) == len(set(shown[:9]))  # regenerations bring new worlds
    await coach.handle({"type": "scenario_skip"})
    assert sink.of("scenario")[-1]["state"] == "skipped"
    await coach.close()
