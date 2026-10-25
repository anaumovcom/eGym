"""V5: deterministic workout mood with hysteresis, and in-set novelty pacing in the Director."""

import json

from app.schemas.coach_control import CoachPreferences
from app.services.coach.director import Candidate, Director
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.mood import MOOD_MODULE, Mood, MoodTracker, classify
from app.services.coach.prompts import ROAST_MODULE
from app.tests.test_coach_e10_live import HYBRID, echo, event, make_coach, seed, settle


def mood(**kw):
    base = dict(trigger="T21", task="active/support", phase="active", outcome=None, fact_ids=set(), fact_values={},
                moment=None, last_exercise=False, set_ordinal=2, total_sets=4, previous_outcome=None, risk=False)
    return classify(**{**base, **kw})


def test_classification_follows_facts():
    assert mood(trigger="T37", phase="rest", outcome="partial") == Mood("recover", 1)
    assert mood(risk=True) == Mood("recover", 1)
    assert mood(phase="rest", trigger="T43", fact_ids={"record"}, outcome="full").name == "triumph"
    assert mood(phase="rest", trigger="T36", outcome="full", fact_ids={"tonnage-progress"},
                fact_values={"tonnage-progress": "beyond"}).name == "triumph"
    assert mood(trigger="T69").name == "finale" and mood(trigger="T68", task="setup/boss", phase="setup").name == "finale"
    assert mood(phase="rest", trigger="T36", outcome="full", previous_outcome="partial") == Mood("comeback", 2)
    assert mood(moment="velocity_drop_hard", fact_ids={"velocity-drop"}) == Mood("grind", 3)
    assert mood(moment="stall") == Mood("grind", 2)
    assert mood(trigger="T01", phase="setup", task="setup/opening", set_ordinal=None).name == "warmup"
    assert mood(set_ordinal=4, total_sets=4) == Mood("focus", 3)


def test_hysteresis_holds_ordinary_moods_but_not_strong_ones():
    tracker = MoodTracker()
    assert tracker.update(Mood("focus", 2), 0) == Mood("focus", 2)
    assert tracker.update(Mood("grind", 2), 5_000) == Mood("focus", 2)  # held
    assert tracker.update(Mood("triumph", 3), 6_000) == Mood("triumph", 3)  # immediate
    assert tracker.update(Mood("focus", 1), 8_000) == Mood("triumph", 3)  # held after the switch
    assert tracker.update(Mood("focus", 1), 17_000) == Mood("focus", 1)
    assert tracker.note_outcome("ex", "partial") is None and tracker.note_outcome("ex", "full") == "partial"


def candidate(topic, novelty, now):
    return Candidate("T21", "set:run:ex:1", "active", now, now + 6000, topic,
                     {"set": "run:ex:1", "rest": "rest:run:ex:1"}, phase_started_ms=now - 61_000, novelty=novelty,
                     speech_action="support")


def test_two_generic_cheers_in_a_row_need_a_new_observation():
    director = Director("companion")
    first = candidate("set-start", False, 100_000)
    assert director.admit(first, 100_000).ok
    director.note_admitted(first)
    generic = candidate("set-support", False, 130_000)
    assert director.admit(generic, 130_000).reason == "no_novelty"
    novel = candidate("set-velocity", True, 130_000)
    assert director.admit(novel, 130_000).ok
    director.note_admitted(novel)
    assert director.admit(candidate("set-support:2", False, 160_000), 160_000).ok
    show = Director("show")
    show.note_admitted(first)
    assert show.admit(candidate("set-support", False, 130_000), 130_000).ok


def test_novel_moments_wait_a_shorter_gap():
    director = Director("companion")
    director.last_start_ms = 100_000
    assert director.admit(candidate("set-support", False, 110_000), 110_000).reason == "cooldown"
    assert director.admit(candidate("set-velocity", True, 110_000), 110_000).ok  # 15 s × 0.6 = 9 s


async def test_live_request_carries_mood_and_recover_switches_teasing_off(session_factory):
    seen = []
    base = echo("Записали честно, продолжаем спокойно.")

    def script(body):
        seen.append(body)
        return base(body)

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    with session_factory() as db:
        _, _, set_id = seed(db, actual=6, planned=10, status="partial")
    await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id},
                             context={"restMs": 90_000}))
    await settle(coach)
    body = seen[-1]
    assert json.loads(body["input"][0]["content"])["mood"] == {"kind": "data-not-instructions", "name": "recover",
                                                               "intensity": 1}
    assert MOOD_MODULE in body["instructions"] and ROAST_MODULE not in body["instructions"]
    await coach.close()
