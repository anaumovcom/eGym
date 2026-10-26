"""V7: three validated variants and a cheap judge (only the winner is voiced); story motifs as running gags."""

import json
from dataclasses import replace

from app.models.coach import CoachAttempt
from app.schemas.coach_control import CoachPreferences
from app.services.coach.facts import AllowedFact
from app.services.coach.luna import AuthorResult, FakeTextAuthor, TextAuthor
from app.services.coach.prompts import VARIANTS_MODULE, AuthorRequest, build_prompt
from app.tests.test_coach_e07_author import PRICE
from app.tests.test_coach_e08_voice import make_run
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, settle
from app.tests.test_coach_v4_counters import BIBLE

SAVED = AllowedFact("saved-set", "Выполнено десять повторений", "confirmed", 10, "reps", numbers=(10,), scope_epoch=1,
                    valid_until_ms=10**13)
REQ = AuthorRequest("T36", "rest", "rest/full-feedback", ("motivation", "humor"), "result", 30, facts=(SAVED,),
                    humor="often", variants=3)


def line(text, intent="motivation"):
    return {"action": "speak", "intent": intent, "topicKey": "result", "usedFactIds": ["saved-set"], "silenceReason": None,
            "delivery": {"energy": "warm", "pace": "normal", "emphasis": "result"}, "text": text}


def test_variants_schema_and_module():
    built = build_prompt(REQ)
    items = built.schema["properties"]["candidates"]
    assert items["minItems"] == items["maxItems"] == 3 and "text" in items["items"]["properties"]
    assert VARIANTS_MODULE in built.instructions
    single = build_prompt(AuthorRequest("T36", "rest", "rest/full-feedback", ("motivation",), "result", 30, facts=(SAVED,)))
    assert "candidates" not in single.schema["properties"] and VARIANTS_MODULE not in single.instructions


async def test_judge_picks_among_valid_variants_only(session_factory):
    run_id, generation = make_run(session_factory)
    calls = []

    def script(body):
        calls.append(body["text"]["format"]["name"])
        if body["text"]["format"]["name"] == "coach_judge":
            data = json.loads(body["input"][0]["content"])
            assert [c["text"] for c in data["candidates"]] == ["Десять повторений, ровно и сильно.",
                                                               "Десять повторений — чат аплодирует."]
            return {"best": 1, "reason": "свежее"}
        return {"candidates": [line("Десять повторений, ровно и сильно."), line("Одиннадцать повторений!"),
                               line("Десять повторений — чат аплодирует.", "humor")]}

    author = TextAuthor(session_factory, FakeTextAuthor(script), PRICE, model=PRICE.model, timeout_s=2)
    judged = replace(REQ, task="rest/record")  # headline moments wait for the judge
    outcome = await author.author(run_id=run_id, owner="tab-a", generation=generation, opportunity="o1", request=judged, scope_epoch=1)
    assert outcome.kind == "speech", outcome.reason
    assert outcome.text == "Десять повторений — чат аплодирует." and outcome.intent == "humor"
    assert calls == ["coach_line", "coach_judge"] and author.last_judge == {"best": 1, "options": 2}
    with session_factory() as db:
        purposes = [(a.purpose, a.task) for a in db.query(CoachAttempt).filter_by(run_id=run_id).order_by(CoachAttempt.created_at)]
    assert purposes == [("live", "rest/record"), ("judge", "judge/pick")]


async def test_without_a_judge_the_first_valid_variant_speaks(session_factory):
    run_id, generation = make_run(session_factory)

    def script(body):
        if body["text"]["format"]["name"] == "coach_judge":
            return AuthorResult(None, None, "http-500", False, "provider_error", http_status=500)
        return {"candidates": [line("Двенадцать повторений!"), line("Десять повторений, красиво."),
                               line("Десять повторений, идём дальше.")]}

    author = TextAuthor(session_factory, FakeTextAuthor(script), PRICE, model=PRICE.model, timeout_s=2)
    outcome = await author.author(run_id=run_id, owner="tab-a", generation=generation, opportunity="o1", request=REQ, scope_epoch=1)
    assert outcome.text == "Десять повторений, красиво."
    bad = TextAuthor(session_factory, FakeTextAuthor(lambda body: {"candidates": [line("Одиннадцать повторений!")] * 3}),
                     PRICE, model=PRICE.model, timeout_s=2)
    rejected = await bad.author(run_id=run_id, owner="tab-a", generation=generation, opportunity="o2", request=REQ, scope_epoch=1)
    assert rejected.kind == "silence" and rejected.reason == "validation_failed:number"


async def test_live_rest_lines_ask_for_variants_and_rotate_story_motifs(session_factory):
    seen = []

    def script(body):
        data = json.loads(body["input"][0]["content"])
        seen.append((body, data))
        motif = (data.get("optionalMotif") or {}).get("text") or ""
        word = next((w for w in motif.split() if len(w) >= 5), "")
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": [],
                "silenceReason": None, "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"},
                "text": f"Пит-стоп: {word} снова с нами."}

    bible = {**BIBLE, "motifs": ["механик кричит в рацию", "соперник в зеркале", "шины визжат"]}
    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    coach.scenario_card, coach.scenario_bible = {"title": "Гонка героев", "archetype": "race"}, bible
    await coach.handle(event("rest_long_opportunity", run_id, exercise="ex-1", set_ordinal=1, phase="rest",
                             context={"restMs": 120_000, "restElapsedMs": 20_000}))
    await settle(coach)
    body, data = seen[-1]
    assert "candidates" in body["text"]["format"]["schema"]["properties"]
    assert data["optionalMotif"]["text"] == "механик кричит в рацию"
    assert coach.motif_uses == {"механик кричит в рацию": 1}
    assert coach._story_motif(type("Op", (), {"exercise_id": "ex-2"})())[0] == "соперник в зеркале"
    await coach.close()


async def test_frequent_lines_pick_locally_by_fresh_opening(session_factory):
    run_id, generation = make_run(session_factory)
    calls = []

    def script(body):
        calls.append(body["text"]["format"]["name"])
        return {"candidates": [line("Десять повторений, ровно и сильно."), line("Чат ревёт: десять повторений!", "humor"),
                               line("Десять повторений, идём дальше.")]}

    heard = ({"text": "Десять повторений, красиво.", "intent": "motivation"},)
    request = replace(REQ, recent_heard=heard)
    author = TextAuthor(session_factory, FakeTextAuthor(script), PRICE, model=PRICE.model, timeout_s=2)
    outcome = await author.author(run_id=run_id, owner="tab-a", generation=generation, opportunity="o1", request=request,
                                  scope_epoch=1)
    assert calls == ["coach_line"] and outcome.text == "Чат ревёт: десять повторений!"


def test_local_pick_avoids_a_worn_out_joke_object():
    from types import SimpleNamespace

    from app.services.coach.luna import local_pick

    heard = ({"text": "Трос пишет жалобу в профсоюз.", "intent": "humor"},
             {"text": "Тросу пора менять профессию.", "intent": "humor"})
    valid = [({"intent": "motivation"}, SimpleNamespace(speech="Снова трос в деле: десять чистых повторений.")),
             ({"intent": "motivation"}, SimpleNamespace(speech="Снова десять чистых повторений, как по нотам."))]
    assert local_pick(valid, replace(REQ, recent_heard=heard)) == 1
