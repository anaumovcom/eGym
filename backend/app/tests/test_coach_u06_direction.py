"""U06 deterministic Russian replay; no extra author/provider calls."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.services.coach.director import Candidate, Coalescer, Director
from app.services.coach.facts import AllowedFact, target_fact
from app.services.coach.prompts import AuthorRequest, build_prompt
from app.services.coach.speech_actions import SCENARIO_EXAMPLES, SPEECH_ACTIONS, speech_action
from app.services.coach.validation import validate

CORPUS = json.loads((Path(__file__).parent / "fixtures/coach_u06_validation.json").read_text())


def corpus_request(profile="full"):
    value, unit, goal = {"full": (10, "reps", 10), "partial": (7, "reps", 12),
                         "range": (7, "reps", 12), "timed": (30, "seconds", 40)}[profile]
    facts = (AllowedFact("saved-set", "Сохранённый результат", "confirmed", value, unit, numbers=(value,),
                         quantity_kind="measured", sufficiency="sufficient"),
             target_fact(8 if profile == "range" else goal, goal, unit),
             AllowedFact("weight", "Плановый вес двадцать килограммов", "confirmed", 20, "kg",
                         numbers=(20,), quantity_kind="declared"))
    return AuthorRequest("T37" if profile == "partial" else "T36", "rest", "rest/partial-feedback"
                         if profile == "partial" else "rest/full-feedback", ("factual-feedback", "humor"),
                         "result", 40, facts, outcome="partial" if profile in {"partial", "range"} else "full")


def payload(req, text, used=(), intent=None):
    return {"action": "speak", "intent": intent or req.intents[0], "topicKey": req.topic_key,
            "usedFactIds": list(used), "text": text, "silenceReason": None,
            "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}


@pytest.mark.parametrize("case", CORPUS, ids=lambda case: case["id"])
def test_russian_validation_replay(case):
    req = corpus_request(case.get("profile", "full"))
    verdict = validate(payload(req, case["text"], case.get("used", ())), req)
    assert verdict.ok is case["ok"], verdict.reason


@pytest.mark.parametrize(("task", "action", "phase"), [
    ("setup/opening", "orient", "setup"), ("active/support", "support", "active"),
    ("rest/full-feedback", "result", "rest"), ("rest/general-tip", "explain", "rest"),
    ("rest/playful", "playful", "rest"), ("summary/workout", "summary", "summary"),
])
def test_explicit_actions_scenario_examples_and_style(task, action, phase):
    req = AuthorRequest("T01", phase, task, ("motivation",), "topic", 20, style="stoic")
    prompt = build_prompt(req)
    assert speech_action(task) == action and phase in SPEECH_ACTIONS[action].phases
    assert json.loads(prompt.data)["speechAction"] == action
    assert "философ-стоик" in prompt.instructions
    assert SCENARIO_EXAMPLES[action] in prompt.instructions
    assert all(example not in prompt.instructions for key, example in SCENARIO_EXAMPLES.items() if key != action)


def candidate(action="support", phase="active", **changes):
    return replace(Candidate("T21" if phase == "active" else "T36", "set-a", phase, 0, 100_000, "new-topic",
                             scopes={"set": "set-a"}, phase_started_ms=0, phase_length_ms=90_000,
                             speech_action=action), **changes)


def test_real_interval_union_not_sum_and_local_count_not_content():
    director = Director()
    director.note_local_playback(0, 4000, content=False)
    director.note_local_playback(2000, 4000, content=False)
    director.note_audible(3000, 2000, content=True)
    assert director.acoustic_ratio(candidate(), 10_000) == .6  # 6 s union, not 10 s sum.
    assert director.last_start_ms == 3000 and not director.slot_counts
    count_only = Director()
    count_only.note_local_playback(0, 6000, content=False)
    assert count_only.last_start_ms is None and count_only._playing(1000) == 0
    assert count_only.admit(candidate(), 6000).reason == "density_cap"
    assert count_only.admit(candidate("result", "rest"), 6000).ok


def test_active_at_most_one_short_live_thought_no_serialization():
    director = Director("talkative", gap_scale=0)
    director.note_audible(0, 10_000, content=True)
    assert director.admit(candidate(), 1).reason == "density_cap"
    director.update_audible("missing", 0)  # Does not create a new interval.
    clean = Director("talkative", words_scale=2)
    assert clean.admit(candidate(), 1).max_words == 16


def test_result_preserves_window_safety_duplicate_and_overlap_limits():
    director = Director()
    c = candidate("result", "rest")
    director.note_local_playback(0, 10_000, content=True)
    assert director.admit(c, 1000).ok  # No arbitrary local cooldown suppression.
    director.note_audible(500, 10_000, content=True)
    assert director.admit(c, 1000).reason == "density_cap"  # Two content intervals already playing.
    assert Director().admit(replace(c, valid_until_ms=3000), 1000).reason == "no_window"
    director.latch_safety(True)
    assert director.admit(c, 1000).reason == "safety"
    director = Director()
    director.note_admitted(c)
    assert director.admit(c, 1000).reason in {"duplicate", "cooldown"}


def test_coalescing_priority_then_freshness_bounded_no_new_paid_queue():
    coalescer = Coalescer()
    older = candidate(priority=30)
    newer = replace(older, created_ms=10)
    coalescer.add(older, 0)
    coalescer.add(newer, 0)
    winners, dropped = coalescer.due(300)
    assert winners == [newer] and dropped == [older]
    for index in range(1000):
        coalescer.add(replace(older, semantic_key=str(index)), 1000)
    assert sum(map(len, coalescer.pending.values())) == 128


@pytest.mark.parametrize("humor", ["off", "light", "often"])
def test_optional_humor_actual_intent_gates_without_style_changes(humor):
    req = replace(corpus_request(), humor=humor, style="strict")
    ordinary = payload(req, "Сделанное записано, спокойно отдыхаем.")
    assert validate(ordinary, req).ok
    funny = payload(req, "У отдыха тоже есть рабочее место.", intent="humor")
    assert validate(funny, req).ok is (humor != "off")


@pytest.fixture
def enabled_coach(use_test_emulator, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("COACH_ENABLED", "true")
    get_settings.cache_clear()


async def test_live_local_observation_is_bounded_untrusted_no_author_or_facts(session_factory, enabled_coach):
    from app.services.coach.identity import SpeechContext
    from app.tests.test_coach_e10_live import make_coach, plan
    coach, sink, run = make_coach(session_factory)
    op = plan(coach, run, "workout_started")
    coach.context = SpeechContext(scope=op.scope, phase="setup", planRevision=1, contextVersion=1, blocked=False)
    base = {"type": "localPlayback", "kind": "count", "action": "count", "durationMs": 750}
    for invalid in [dict(base, durationMs=True), dict(base, durationMs=float("nan")), dict(base, durationMs=60001),
                    dict(base, kind=[]), dict(base, action="ignore"), dict(base, text="private"),
                    dict(base, userId="private"), dict(base, durationMs=None)]:
        await coach.handle(invalid)
    assert not coach.director.local_audible
    for _ in range(200):
        await coach.handle(base)
    assert len(coach.local_observations) == 128 and len(coach.director.local_audible) == 64
    assert not coach.director.audible and not coach.director.slot_counts and not coach.memory.heard()
    assert coach.task is None and not sink.json
    coach.context = coach.context.model_copy(update={"blocked": True})
    before = list(coach.director.local_audible)
    await coach.handle(dict(base, kind="cue", action="support"))
    assert coach.director.local_audible == before
    await coach.close()


async def test_rejected_author_output_is_one_attempt_silence_no_voice(session_factory, enabled_coach):
    from app.services.coach.luna import FakeTextAuthor
    from app.tests.test_coach_e10_live import echo, event, make_coach, settle
    calls = []
    def script(body):
        calls.append(body)
        return echo("Сегодня лучше, чем раньше.")(body)
    coach, sink, run = make_coach(session_factory, fake_text=FakeTextAuthor(script))
    await coach.handle(event("workout_started", run))
    await settle(coach)
    assert len(calls) == 1 and not sink.of("speech_start") and not sink.bytes
    assert sink.of("decision")[-1]["action"] == "silence"
    await coach.close()


async def test_local_start_during_authoring_rechecks_budget_before_voice(session_factory, enabled_coach):
    from app.services.coach.luna import FakeTextAuthor
    from app.tests.test_coach_e10_live import echo, event, make_coach, settle
    def script(body):
        coach.director.note_local_playback(coach.now_ms(), 8000, content=True)
        return echo()(body)
    coach, sink, run = make_coach(session_factory, fake_text=FakeTextAuthor(script))
    await coach.handle(event("last_rep_pending", run, set_ordinal=1, phase="active-set",
                             context={"phaseElapsedMs": 20_000}))
    await settle(coach)
    assert sink.of("decision")[-1]["reason"] == "density_cap"
    assert not sink.of("speech_start") and not sink.bytes
    await coach.close()


@pytest.mark.parametrize(("text", "expected"), [
    ("Сильнее не значит лучше, сейчас отдых.", True),
    ("Больше не значит лучше, спокойно отдыхаем.", True),
    ("Сильнее не значит лучше, но сегодня ты сильнее вчерашнего.", False),
    ("Сегодня десять повторений, вчера десять.", False),
    ("Работаем любой ценой.", False),
    ("Ну ты и тряпка.", False),
    ("План выполнен частично.", True),
    ("План выполнен частично, но весь план закрыт.", False),
])
def test_additional_conversational_negation_and_pressure_pairs(text, expected):
    req = corpus_request("partial")
    assert validate(payload(req, text), req).ok is expected


@pytest.mark.parametrize("text", ["Осталось сорок секунд.", "На таймере тридцать секунд.",
                                  "Прошло тридцать секунд.", "До конца сорок секунд."])
def test_stored_duration_or_target_is_not_a_live_clock(text):
    req = corpus_request("timed")
    assert validate(payload(req, text, ("saved-set", "target")), req).reason == "number"


@pytest.mark.parametrize(("text", "unit", "numbers", "kind", "expected"), [
    ("По плану двадцать с половиной килограмма.", "kg", (20.5, 20), "declared", True),
    ("По плану 20,5 килограмма.", "kg", (20.5, 20), "declared", True),
    ("По плану двадцать с половиной повторений.", "kg", (20.5, 20), "declared", False),
    ("Две тысячи повторений записано.", "reps", (2000,), "measured", True),
    ("По плану восемь секунд. Выполнено двенадцать секунд.", "seconds", (8, 12), "declared", False),
])
def test_fraction_compound_and_plan_observation_bindings(text, unit, numbers, kind, expected):
    fact = AllowedFact("quantity", "Разрешённая величина", "confirmed", numbers[0], unit,
                       numbers=numbers, quantity_kind=kind)
    req = replace(corpus_request(), facts=(fact,))
    assert validate(payload(req, text, ("quantity",)), req).ok is expected