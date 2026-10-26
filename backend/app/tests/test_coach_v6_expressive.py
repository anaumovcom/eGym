"""V6: Fish drama-3 per-sentence segments, palette, mood → voice, markup budget, curve and synthesis params."""

import json

import httpx
import pytest

from app.schemas.coach_control import CoachPreferences
from app.services.coach import expressive
from app.services.coach.expressive import Segment, VoiceContext, VoiceHistory
from app.services.coach.facts import AllowedFact
from app.services.coach.luna import FakeTextAuthor
from app.services.coach.prompts import AuthorRequest, build_prompt
from app.services.coach.validation import validate, voice_block
from app.services.coach.voice import Delivery, FishVoiceAdapter, VoiceStreamer, fish_markup
from app.tests.test_coach_e08_voice import PRICE as VOICE_PRICE
from app.tests.test_coach_e10_live import HYBRID, event, make_coach, seed, settle

TEXT = "Двенадцать повторений. Чат, это было мощно!"


def raw_segment(**kw):
    return {"emotion": "excited", "intensity": "very", "tone": "none", "direction": "like a stream host",
            "soundBefore": "none", "pauseAfter": "none", "tags": [], **kw}


def test_segment_parsing_is_strict():
    assert expressive.segment_from(raw_segment(tags=[{"words": "мощно", "tag": "emphasis"}])).tags == (("мощно", "emphasis"),)
    for bad in (raw_segment(emotion="sad"), raw_segment(soundBefore="sobbing"), raw_segment(tone="screaming"),
                raw_segment(direction="кричи"), raw_segment(direction="[shout]"), raw_segment(direction="x" * 41),
                raw_segment(tags=[{"words": "<b>", "tag": "emphasis"}]), raw_segment(tags=[{"words": "a", "tag": "loud"}])):
        assert expressive.segment_from(bad) is None


def test_palette_follows_the_moment():
    joke = Segment("sarcastic", tone="shouting", sound="crowd laughing", tags=(("мощно", "forceful"),))
    plain = expressive.allowed(joke, VoiceContext(humor=False, mood="focus", crowd=False))
    assert (plain.emotion, plain.tone, plain.sound) == ("none", "emphasis", "none")
    show = expressive.allowed(joke, VoiceContext(humor=True, mood="triumph", crowd=True))
    assert (show.emotion, show.tone, show.sound) == ("sarcastic", "shouting", "crowd laughing")
    gentle = expressive.allowed(Segment("excited", sound="laughing", tags=(("x", "forceful"),)), VoiceContext(mood="recover"))
    assert gentle.sound == "none" and gentle.tags == ()
    assert expressive.allowed(Segment(sound="sighing"), VoiceContext(sounds=False)).sound == "none"


def test_render_keeps_words_and_places_markup_per_sentence():
    segments = (Segment("confident", sound="breath", pause="break"),
                Segment("excited", "very", tone="shouting", tags=(("мощно", "emphasis"),)))
    markup = expressive.render(TEXT, segments)
    assert markup == "[breath] [confident] Двенадцать повторений. [break] [very excited, shouting] Чат, это было <emphasis>мощно</emphasis>!"
    assert expressive.strip_markup(markup) == expressive.strip_markup(TEXT)


def test_markup_budget_trims_secondary_marks_first():
    heavy = (Segment("excited", "extremely", "shouting", "like a hyped stream host", "laughing", "long-break",
                     (("Двенадцать", "emphasis"), ("повторений", "stress"))),)
    trimmed = expressive.within_budget("Двенадцать повторений.", heavy)
    markup = expressive.render("Двенадцать повторений.", trimmed)
    plain = len("Двенадцать повторений.".encode())
    assert (len(markup.encode()) - plain) / len(markup.encode()) <= expressive.MARKUP_SHARE
    assert trimmed[0].emotion == "excited"  # the sentence emotion survives longest


def test_curve_contrast_repeats_crowd_and_extremely():
    history = VoiceHistory()
    loud = (Segment("excited", tone="shouting", sound="laughing"),)
    history.note(history.shape(loud, now_ms=0, exercise="e1"), now_ms=0, exercise="e1")
    second = history.shape((Segment("proud", tone="shouting", sound="laughing", tags=(("да", "forceful"),)),),
                           now_ms=1000, exercise="e1")
    assert second[0].tone == "emphasis" and second[0].sound == "none" and second[0].tags == (("да", "emphasis"),)
    history.note((Segment(sound="crowd laughing"),), now_ms=2000, exercise="e1")
    assert history.shape((Segment(sound="crowd laughing"),), now_ms=200_000, exercise="e1")[0].sound == "none"
    history.note((Segment(intensity="extremely"),), now_ms=3000, exercise="e1")
    assert history.shape((Segment(intensity="extremely"),), now_ms=4000, exercise="e1")[0].intensity == "very"
    assert history.shape((Segment(intensity="extremely"),), now_ms=4000, exercise="e2")[0].intensity == "extremely"


def test_synthesis_parameters_by_profile_mood_and_phase():
    assert expressive.synthesis("support", "grind", "active") == {
        "temperature": 0.7, "prosody": {"speed": 1.25, "volume": 2.0}, "language": "ru", "latency": "low"}
    assert expressive.synthesis("safety", "triumph", "rest")["prosody"] == {"speed": 1.0, "volume": 0.0}
    assert expressive.synthesis("result", "triumph", "rest")["temperature"] == 0.8


def test_fish_markup_new_path_fixed_tone_and_levels():
    partial = fish_markup(TEXT, Delivery(profile="partial", mood="recover", segments=(Segment("excited", sound="laughing"),)),
                          "expressive")
    assert partial.startswith("[empathetic, soft tone] ") and "laughing" not in partial
    merged = fish_markup(TEXT, Delivery(profile="result", mood="triumph",
                                        segments=(Segment(sound="gasping"), Segment(tags=(("мощно", "emphasis"),)))),
                         "expressive")
    # The mood fills the first emotion; on this short line the 35% budget already trims «very».
    assert merged.startswith("[gasping] [excited] ") and "<emphasis>мощно</emphasis>" in merged
    subtle = fish_markup(TEXT, Delivery(profile="result", mood="triumph", segments=(Segment(sound="gasping", pause="break"),)),
                         "subtle")
    assert "[gasping]" not in subtle and "[break]" not in subtle and subtle.startswith("[very excited] ")
    # The legacy path (no mood, no segments) is unchanged.
    assert fish_markup("Записал.", Delivery(profile="result"), "expressive").endswith("] Записал.")


def test_validator_accepts_segments_and_drops_foreign_tags():
    saved = AllowedFact("saved-set", "Выполнено двенадцать повторений", "confirmed", 12, "reps", numbers=(12,),
                        scope_epoch=1, valid_until_ms=10**13)
    request = AuthorRequest("T36", "rest", "rest/full-feedback", ("motivation", "humor"), "t", 30, facts=(saved,),
                            voice_markup=True, humor="often", mood={"name": "triumph", "intensity": 3})
    assert "segments" in build_prompt(request).schema["properties"]["voice"]["properties"]
    voice = {"direction": "", "sound": "none", "stress": "none", "segments": [
        raw_segment(tags=[{"words": "двенадцать", "tag": "emphasis"}, {"words": "не из текста", "tag": "stress"}]),
        raw_segment(emotion="sarcastic", tone="shouting")]}
    output = {"action": "speak", "intent": "motivation", "topicKey": "t", "usedFactIds": ["saved-set"],
              "silenceReason": None, "delivery": {"energy": "bright", "pace": "normal", "emphasis": "result"},
              "text": "Было двенадцать повторений. Чат в восторге!", "voice": voice}
    verdict = validate(output, request)
    assert verdict.ok, verdict.reason
    first, second = verdict.delivery["segments"]
    assert first.tags == (("двенадцать", "emphasis"),)
    assert second.emotion == "none" and second.tone == "shouting"  # sarcasm needs a humor line; triumph may shout
    assert voice_block({**voice, "segments": [raw_segment(emotion="angry")]}) is None
    assert voice_block({"direction": "", "sound": "none", "stress": "none"}) == {"direction": "", "sound": "none",
                                                                                 "stress": "none"}


async def test_live_fish_request_carries_mood_voice_and_parameters(session_factory):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=bytes(4800), headers={"content-type": "audio/pcm"})

    def script(body):
        data = json.loads(body["input"][0]["content"])
        key = "framingText" if data["mode"] == "locked_fact" else "text"
        return {"action": "speak", "intent": data["intent"][0], "topicKey": data["topicKey"],
                "usedFactIds": list(data["lockedFactIds"]), "silenceReason": None,
                "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}, key: "Записали честно, отдышись.",
                "voice": {"direction": "", "sound": "none", "stress": "none", "segments": []}}

    coach, sink, run_id = make_coach(session_factory, CoachPreferences(**HYBRID), fake_text=FakeTextAuthor(script))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fish = FishVoiceAdapter(client, "k", model="drama-3")
        fish.test_only = True
        coach.voice = VoiceStreamer(session_factory, fish, VOICE_PRICE.model_copy(update={"model": "drama-3"}))
        with session_factory() as db:
            _, _, set_id = seed(db, actual=6, planned=10, status="partial")
        await coach.handle(event("set_persisted", run_id, set_ordinal=1, phase="rest", refs={"backendSetId": set_id},
                                 context={"restMs": 90_000}))
        await settle(coach)
    assert bodies, sink.of("decision")
    body = bodies[-1]
    assert body["text"].startswith("[empathetic, soft tone] ") and body["language"] == "ru"
    assert body["prosody"] == {"speed": 1.05, "volume": -2.0} and body["latency"] == "balanced"
    await coach.close()


@pytest.mark.parametrize("mood", sorted(expressive.MOOD_VOICE))
def test_every_mood_has_a_palette_voice(mood):
    base = expressive.base_segment(mood)
    assert base.emotion in expressive.ALWAYS and base.emotion not in expressive.FORBIDDEN


def test_an_in_set_line_is_one_breath_at_most_two_colours_and_no_pauses():
    from app.services.coach.voice import Delivery, fish_markup

    text = "Стыковочный манёвр! Финальный виток миссии! Жим от груди! Эфиру пора показать класс!"
    colours = tuple(Segment(e, pause="short pause") for e in ("excited", "determined", "proud", "confident"))
    in_set = fish_markup(text, Delivery(mood="grind", phase="active", segments=colours), "expressive")
    assert in_set.count("[") == 2 and "pause" not in in_set and expressive.strip_markup(in_set) == text
    rest = fish_markup(text, Delivery(mood="triumph", phase="rest", segments=colours), "expressive")
    assert rest.count("short pause") >= 2 and rest.count("[") >= 4  # between sets the author's staging stays
