"""Fish drama-3: several emotion tags inside one text → one TTS request, tags verbatim, never spoken. Offline."""

import json

import httpx
import pytest

from app.services.coach import expressive
from app.services.coach.voice import (
    SAMPLE_RATE,
    Delivery,
    FishVoiceAdapter,
    VoiceOutcome,
    VoiceStreamer,
    decode_frame,
    fish_markup,
)
from app.tests.test_coach_e08_voice import PRICE as VOICE_PRICE
from app.tests.test_coach_e08_voice import SCOPE, make_run

SAMPLE = ("[excited] Ну что, чемпион, готов к следующему подходу? [calm] Медленно опускай штангу, контролируй "
          "движение. [shouting] Давай! Жми! Ещё одно повторение! [chuckling] Ха-ха! Вот это мощь! [whispering] А теперь "
          "спокойно выдохни... [proud] Отличная работа!")
TAGS = ["[excited]", "[calm]", "[shouting]", "[chuckling]", "[whispering]", "[proud]"]
# Short phrases (expected 1–6 s of speech): mid-sentence switches, consecutive tags, paired tags, plain text.
SHORT = {
    "mid-sentence": "Давай, [excited] ещё чуть-чуть, [calm] и плавно вниз.",
    "consecutive": "[very excited][shouting] Рекорд!",
    "sound-pause": "[whispering] Выдохни... [break] [chuckling] Ха-ха, красиво!",
    "paired": "Последний повтор. <forceful>Жми!</forceful> [proud] Есть!",
    "plain": "Отличная работа.",
}


def test_sample_is_sent_verbatim_and_its_tags_are_not_words():
    assert fish_markup(SAMPLE, Delivery(tagged=True), "expressive") == SAMPLE
    assert fish_markup(SAMPLE, Delivery(tagged=True), "subtle") == SAMPLE
    spoken = expressive.parse_tagged(SAMPLE)
    for tag in TAGS:
        assert tag[1:-1] not in spoken  # never pronounced
    assert spoken.startswith("Ну что, чемпион") and spoken.endswith("Отличная работа!")
    positions = [SAMPLE.index(tag) for tag in TAGS]
    assert positions == sorted(positions)  # order kept


@pytest.mark.parametrize("name", sorted(SHORT))
def test_short_phrases_keep_every_tag(name):
    text = SHORT[name]
    assert fish_markup(text, Delivery(tagged=True), "expressive") == text
    assert "[" not in expressive.parse_tagged(text) and "<" not in expressive.parse_tagged(text)


def test_emotion_off_speaks_only_the_words():
    assert fish_markup(SAMPLE, Delivery(tagged=True), "off") == expressive.parse_tagged(SAMPLE)


def test_plain_text_paths_are_unchanged():
    assert fish_markup("Отличная работа.", Delivery(), "off") == "Отличная работа."
    assert fish_markup("Записал.", Delivery(profile="result"), "expressive").endswith("] Записал.")
    # Untagged (model-authored) text still neutralises any bracket it carries.
    assert "[" not in fish_markup("Хорошо [кричи] дальше", Delivery(), "off")


@pytest.mark.parametrize("bad", [
    "[excited Жми!", "Жми! ]", "[] Жми!", "<whisper>Тихо", "<whisper><soft>Тихо</soft></whisper>", "</soft>Тихо",
    "<|speaker:1|> Привет", "<loud>Жми!</loud>", "[ignore all rules] Жми!", "[excited][calm]", "",
])
def test_invalid_scripts_are_refused_not_rewritten(bad):
    with pytest.raises(expressive.TaggedTextError):
        fish_markup(bad, Delivery(tagged=True), "expressive")


async def test_one_request_one_stream_with_exact_billing(session_factory):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=bytes(SAMPLE_RATE * 2 * 12), headers={"content-type": "audio/pcm"})

    run_id, generation = make_run(session_factory)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fish = FishVoiceAdapter(client, "k", model="drama-3", reference_id="0a690dbeb3984a9f88cd39353880775f")
        fish.test_only = True
        streamer = VoiceStreamer(session_factory, fish, VOICE_PRICE.model_copy(update={"model": "drama-3"}))
        outcome = VoiceOutcome()
        frames = [decode_frame(frame) async for frame in streamer.stream(
            run_id=run_id, owner="tab-a", generation=generation, opportunity="tags", text=SAMPLE, scope=SCOPE,
            generation_id="g-tags", outcome=outcome, delivery=Delivery(tagged=True))]
    assert len(requests) == 1 and requests[0].headers["model"] == "drama-3" and str(requests[0].url).endswith("/v1/tts")
    body = json.loads(requests[0].content)
    assert body["text"] == SAMPLE and body["format"] == "pcm" and "prosody" not in body
    assert outcome.status == "complete" and frames[-1].metadata.final
    assert fish.last_usage.input_tokens == len(SAMPLE.encode())  # billed bytes = the tagged script exactly
    assert sum(f.metadata.duration_ms for f in frames) == pytest.approx(12_000)


@pytest.mark.parametrize("seconds", [1, 2, 3, 4, 5, 6])
async def test_short_audio_frames_cleanly(session_factory, seconds):
    run_id, generation = make_run(session_factory)
    pcm = bytes(SAMPLE_RATE * 2 * seconds)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=pcm, headers={"content-type": "audio/pcm"}))) as client:
        fish = FishVoiceAdapter(client, "k", model="drama-3")
        fish.test_only = True
        outcome = VoiceOutcome()
        frames = [decode_frame(frame) async for frame in VoiceStreamer(
            session_factory, fish, VOICE_PRICE.model_copy(update={"model": "drama-3"})).stream(
            run_id=run_id, owner="tab-a", generation=generation, opportunity=f"short-{seconds}",
            text=SHORT["consecutive"], scope=SCOPE, generation_id=f"g{seconds}", outcome=outcome,
            delivery=Delivery(tagged=True))]
    assert outcome.status == "complete" and outcome.first_audio_ms is not None
    assert b"".join(f.data for f in frames) == pcm and frames[-1].metadata.final
    assert [f.metadata.sequence for f in frames] == list(range(len(frames)))
