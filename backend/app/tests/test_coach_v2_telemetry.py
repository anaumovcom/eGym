"""V2: rep tracker telemetry → measured machine facts, tempo cue (T19), set summary facts that survive revalidation."""

import json

from app.schemas.coach_control import CoachPreferences
from app.services.coach import telemetry
from app.services.coach.facts import AllowedFact
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.prompts import AuthorRequest
from app.services.coach.triggers import evaluate
from app.services.coach.validation import validate
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, seed, settle

COMMON = {"scope_epoch": 1, "valid_until_ms": 10**13, "ref": "x"}


def test_parse_bounds_and_wire_form():
    assert telemetry.parse({"reps": 5, "velocityDropPct": 31, "eccentricS": 0.6, "concentricS": 1.2, "steady": True,
                            "longestPauseS": 999, "evil": "x"}) == {
        "reps": 5.0, "velocityDropPct": 31.0, "eccentricS": 0.6, "concentricS": 1.2, "steady": True}
    assert telemetry.parse({"velocityDropPct": -3}) is None and telemetry.parse("not json") is None
    assert telemetry.parse(telemetry.wire({"reps": 4, "steady": False})) == {"reps": 4.0, "steady": False}


def test_moment_and_set_facts_are_relative_machine_observations():
    hard = telemetry.moment_facts("velocity_drop_hard", {}, COMMON)[0]
    assert hard.provenance == "machine-telemetry" and hard.quantity_kind == "measured" and not hard.numbers
    assert "tempo" in hard.permits and "датчикам тренажёра" in hard.claim
    fast = telemetry.moment_facts("tempo", {"eccentricS": 0.5, "concentricS": 1.2}, COMMON)[0]
    assert fast.value == "fast-descent" and "movement-cue" in fast.permits
    even = telemetry.moment_facts("tempo", {"eccentricS": 1.1, "concentricS": 1.0}, COMMON)[0]
    assert even.value == "even" and "movement-cue" not in even.permits
    assert telemetry.moment_facts("tempo", {}, COMMON) == []
    summary = telemetry.set_facts({"reps": 8, "velocityDropPct": 20, "eccentricS": 2, "concentricS": 1, "steady": True,
                                   "longestPauseS": 6}, COMMON)
    assert [f.id for f in summary] == ["set-velocity", "set-tempo", "set-steady", "set-pause"]
    assert telemetry.set_facts({"reps": 2, "steady": True}, COMMON) == []


def test_tempo_trigger_is_now_supported():
    assert evaluate("T19", ["tempo.validated"]).ok


def test_validator_allows_a_descent_cue_only_with_a_measured_fact():
    from app.services.coach.context import CoachContext
    cue = telemetry.moment_facts("tempo", {"eccentricS": 0.5, "concentricS": 1.2}, COMMON)[0]
    context = CoachContext(event="rep_milestone", phase="active", set_ordinal=1, exercise_slug="leg-press", kind="machine",
                           variant="leg-press", mode="constant", exercise_source="catalog", plan_source="declared")
    base = dict(trigger_id="T19", phase="active", task="active/tempo", intents=("general-tip",), topic_key="t",
                max_words=14, coach_context=context)
    output = {"action": "speak", "intent": "general-tip", "topicKey": "t", "usedFactIds": ["tempo-ratio"],
              "silenceReason": None, "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"},
              "text": "Опускай чуть медленнее, гриф сейчас падает быстрее подъёма."}
    assert validate(output, AuthorRequest(**base, facts=(cue,))).ok
    plain = AllowedFact("milestone", "Подход продолжается", "confirmed", "support", **COMMON)
    rejected = validate({**output, "usedFactIds": ["milestone"]}, AuthorRequest(**{**base, "task": "active/support"}, facts=(plain,)))
    assert not rejected.ok and rejected.reason in {"unreviewed_tip", "comparison"}


async def test_live_tempo_and_velocity_moments(session_factory):
    seen = []

    def script(body):
        data = json.loads(body["input"][0]["content"])
        seen.append(data)
        used = [f["id"] for f in data["allowedFacts"] if f["id"] in {"tempo-ratio", "velocity-drop"}][:1]
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": used,
                "silenceReason": None, "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"},
                "text": "Держим, гриф идёт тяжелее, но ты в деле." if "velocity-drop" in used else "Опускай подконтрольнее."}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    await coach.handle(event("rep_milestone", run_id, set_ordinal=1, phase="active-set", context={
        "moment": "tempo", "phaseElapsedMs": 20_000, "telemetry": {"reps": 5, "eccentricS": 0.5, "concentricS": 1.2}}))
    await settle(coach)
    assert sink.of("speech_start")[-1]["triggerId"] == "T19", sink.of("decision")
    tempo_facts = {f["id"]: f for f in seen[-1]["allowedFacts"]}
    assert tempo_facts["tempo-ratio"]["provenance"] == "machine-telemetry"
    coach.director.last_start_ms = None
    await coach.handle(event("rep_milestone", run_id, set_ordinal=2, phase="active-set", context={
        "moment": "velocity_drop_hard", "phaseElapsedMs": 30_000, "telemetry": {"reps": 6, "velocityDropPct": 35}}))
    await settle(coach)
    assert sink.of("speech_start")[-1]["triggerId"] == "T21"
    assert "velocity-drop" in {f["id"] for f in seen[-1]["allowedFacts"]}
    # A tempo moment without the measurement is not authored at all.
    await coach.handle(event("rep_milestone", run_id, set_ordinal=3, phase="active-set",
                             context={"moment": "tempo", "phaseElapsedMs": 20_000}))
    assert sink.of("decision")[-1]["reason"] == "insufficient_facts"
    await coach.close()


async def test_set_summary_facts_survive_revalidation(session_factory):
    seen = []

    def script(body):
        data = json.loads(body["input"][0]["content"])
        seen.append(data)
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": list(data["lockedFactIds"]) or ["set-steady"], "silenceReason": None,
                "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}, key: "Ровно прошёл, как по метроному."}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    with session_factory() as db:
        _, _, set_id = seed(db, actual=10, planned=10, status="completed")
    await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id},
                             context={"restMs": 90_000, "setMetrics": {"reps": 10, "velocityDropPct": 8, "steady": True,
                                                                        "eccentricS": 1.5, "concentricS": 1.0}}))
    await settle(coach)
    ids = {f["id"] for f in seen[-1]["allowedFacts"]}
    assert {"set-velocity", "set-tempo", "set-steady"} <= ids
    assert sink.of("speech_start"), sink.of("decision")  # not dropped as facts_changed by revalidation
    await coach.close()
