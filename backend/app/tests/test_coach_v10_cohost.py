"""V10: the story's co-host adds a rare short line in a second Fish voice — one multi-speaker request, same rules."""

import json

import httpx

from app.schemas.coach_control import CoachPreferences
from app.services.coach.facts import AllowedFact
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.prompts import CO_HOST_MODULE, AuthorRequest, build_prompt
from app.services.coach.validation import validate
from app.services.coach.voice import Delivery, FishVoiceAdapter, VoiceStreamer
from app.tests.test_coach_e08_voice import PRICE as VOICE_PRICE
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, settle
from app.tests.test_coach_v4_counters import BIBLE

MAIN, SECOND = "0a690dbeb3984a9f88cd39353880775f", "6d23d3209d6849e0b24ddae6f734afe9"
SAVED = AllowedFact("saved-set", "Выполнено десять повторений", "confirmed", 10, "reps", numbers=(10,), scope_epoch=1,
                    valid_until_ms=10**13)
CO = {"role": "комментатор трассы", "name": "Шумахер"}


def output(co_host, text="Десять повторений, болид летит."):
    return {"action": "speak", "intent": "motivation", "topicKey": "t", "usedFactIds": ["saved-set"],
            "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"},
            "text": text, "coHost": co_host}


def test_schema_module_and_validation():
    request = AuthorRequest("T36", "rest", "rest/full-feedback", ("motivation",), "t", 30, facts=(SAVED,), co_host=CO)
    built = build_prompt(request)
    assert "coHost" in built.schema["required"] and CO_HOST_MODULE in built.instructions
    assert json.loads(built.data)["coHost"]["name"] == "Шумахер"
    assert validate(output("Шумахер в восторге, трибуны ревут!"), request).delivery["co_host_text"] == "Шумахер в восторге, трибуны ревут!"
    for dropped in ("", "Одиннадцать повторений!", "Раз два три четыре пять шесть семь восемь девять десять одиннадцать"):
        verdict = validate(output(dropped), request)
        assert verdict.ok and "co_host_text" not in verdict.delivery  # the main line still speaks
    recover = AuthorRequest("T36", "rest", "rest/full-feedback", ("motivation",), "t", 30, facts=(SAVED,), co_host=CO,
                            mood={"name": "recover", "intensity": 1})
    assert "co_host_text" not in validate(output("Шумахер в восторге!"), recover).delivery
    plain = AuthorRequest("T36", "rest", "rest/full-feedback", ("motivation",), "t", 30, facts=(SAVED,))
    assert "coHost" not in build_prompt(plain).schema["properties"]


def test_multi_speaker_fish_request():
    adapter = FishVoiceAdapter(httpx.AsyncClient(), "k", model="drama-3", reference_id=MAIN, co_host_reference_id=SECOND)
    body = adapter.request("Десять повторений.", Delivery(mood="triumph", co_host_text="Трибуны <|speaker:0|> ревут!"))
    assert body["reference_id"] == [MAIN, SECOND]
    assert body["text"].startswith("<|speaker:0|>") and body["text"].count("<|speaker:") == 2
    second = body["text"].split("<|speaker:1|>", 1)[1]
    assert "Трибуны" in second and "ревут" in second and "|" not in second
    solo = FishVoiceAdapter(httpx.AsyncClient(), "k", model="drama-3", reference_id=MAIN, co_host_reference_id=MAIN)
    assert solo.co_host_reference_id == "" and solo.request("Да.", Delivery(co_host_text="Ок."))["reference_id"] == MAIN


async def test_live_co_host_is_rare(session_factory):
    offered = []
    bodies = []

    def script(body):
        data = json.loads(body["input"][0]["content"])
        offered.append("coHost" in data)
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"], "usedFactIds": [],
                "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "none"},
                "text": "Пит-стоп, механики работают.", **({"coHost": "Шумахер одобряет."} if "coHost" in data else {}),
                "voice": {"direction": "", "sound": "none", "stress": "none", "segments": []}}

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=bytes(4800), headers={"content-type": "audio/pcm"})

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID, co_host=True), fake_text=FakeTextAuthor(script))
    coach.scenario_card = {"title": "Гонка героев", "archetype": "race"}
    coach.scenario_bible = {**BIBLE, "coHost": CO, "motifs": []}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fish = FishVoiceAdapter(client, "k", model="drama-3", reference_id=MAIN, co_host_reference_id=SECOND)
        fish.test_only = True
        coach.voice = VoiceStreamer(session_factory, fish, VOICE_PRICE.model_copy(update={"model": "drama-3"}))
        for index in range(2):
            coach.director.last_start_ms = None
            await coach.handle(event("rest_long_opportunity", run_id, exercise=f"ex-{index + 1}", set_ordinal=2, phase="rest",
                                     context={"restMs": 120_000, "restElapsedMs": 20_000}))
            await settle(coach)
    assert offered[:2] == [True, False], (offered, sink.of("decision"), coach.lines_since_co_host, [m.get("coHostText") for m in sink.of("speech_start")])
    assert bodies[0]["reference_id"] == [MAIN, SECOND] and bodies[1]["reference_id"] == MAIN
    assert sink.of("speech_start")[0]["coHostText"] == "Шумахер одобряет."
    await coach.close()
