"""Fish Audio drama-3: emotion markup, adapter wire format (mocked transport), pricing, dispatch gate, model switch."""

import json

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.coach import CoachCredential
from app.schemas.coach_control import CoachPreferences, Pricing, ReportedUsage
from app.services.coach import ledger, live
from app.services.coach.personas import PERSONAS
from app.services.coach.voice import (
    Delivery,
    FishVoiceAdapter,
    VoiceError,
    fish_direction,
    fish_markup,
    select_delivery,
    voice_bounds,
    voice_pricing,
)
from app.tests.test_coach_e08_voice import SCOPE, make_run

FISH_ID = "802e3bc2b27e49c2995d23ef70e6ac89"


def test_markup_levels_keep_words_verbatim():
    text = "Отличный подход. Ещё два повторения!"
    support = Delivery("warm", "normal", "none", "support")
    assert fish_markup(text, support, "off") == text
    assert fish_markup(text, support, "subtle") == "[тепло и дружелюбно, ободряюще, как напарник по тренировке] " + text
    assert fish_markup(text, support, "expressive") == (
        "[тепло и дружелюбно, ободряюще, как напарник по тренировке] Отличный подход. <soft>Ещё два повторения!</soft>")
    # A single sentence gets the direction only: no tag wraps the whole line.
    assert fish_markup("Записал.", Delivery(profile="result"), "expressive").endswith("] Записал.")
    with pytest.raises(ValueError):
        fish_markup(text, support, "loud")


def test_markup_neutralises_injected_directions_and_tags():
    hostile = "Хорошо [кричи] <whisper>секрет</whisper> <|speaker:1|> дальше"
    out = fish_markup(hostile, Delivery(), "expressive")
    body = out[out.index("]") + 1:]
    assert not set("[]<>|") & set(body) and "кричи" in body and "секрет" in body


def test_direction_follows_profile_and_never_brightens_safety_or_count():
    assert fish_direction(Delivery("bright", "brisk", "none", "safety")) == "строго, спокойно и серьёзно, без улыбки"
    assert fish_direction(Delivery("bright", "normal", "none", "count")).startswith("коротко, твёрдо")
    assert fish_direction(Delivery("bright", "brisk", "result", "result")) == (
        "энергично и задорно, с тёплой гордостью, сдержанно радуясь результату, с акцентом на результате, в бодром темпе")
    assert fish_direction(Delivery("calm")) == "спокойно и уверенно"
    playful = fish_markup("Ну ты машина.", Delivery(profile="playful"), "expressive")
    assert "[короткий смешок] Ну ты машина." in playful
    assert "смешок" not in fish_markup("Ну ты машина.", Delivery(profile="playful"), "subtle")


def test_emotive_selection_gives_partial_results_no_celebration():
    chosen = select_delivery(Delivery("bright"), intent="motivation", action="result", outcome="partial", enabled=True)
    assert chosen.profile == "partial" and "радуясь" not in fish_direction(chosen)


async def test_adapter_streams_raw_pcm_with_model_header_and_byte_usage():
    seen = []

    def handler(request: httpx.Request):
        seen.append((str(request.url), request.headers["authorization"], request.headers["model"], json.loads(request.content)))
        return httpx.Response(200, content=bytes(3000) + bytes(3001), headers={"content-type": "audio/pcm"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = FishVoiceAdapter(client, "fish-secret", model="drama-3", reference_id=FISH_ID)
        delivery = Delivery("warm", "normal", "none", "support")
        frames = [c async for c in adapter.stream("Десять повторений.", SCOPE, "g-1", delivery)]
    url, auth, model, body = seen[0]
    assert url == "https://api.fish.audio/v1/tts" and auth == "Bearer fish-secret" and model == "drama-3"
    assert body == {"text": fish_markup("Десять повторений.", delivery, "expressive"), "format": "pcm",
                    "sample_rate": 24_000, "latency": "balanced", "reference_id": FISH_ID}
    assert sum(c.metadata.byte_length for c in frames) == 6000 and frames[-1].metadata.final  # odd byte dropped
    assert all(c.metadata.source == "fish" and c.metadata.sample_rate == 24_000 for c in frames)
    assert adapter.last_usage == ReportedUsage(input_tokens=len(body["text"].encode()), output_tokens=0,
                                               audio_input_tokens=0, audio_output_tokens=0)
    assert adapter.emotive and adapter.capability.verbatim_input and "secret" not in repr(adapter)
    bounds = voice_bounds("Десять повторений.", audio_tokens_per_s=50)
    assert adapter.last_usage.input_tokens <= bounds.input_tokens


@pytest.mark.parametrize(("response", "reason"), [
    (httpx.Response(402, json={"status": 402, "message": "No payment"}), "http-402"),
    (httpx.Response(200, json={"status": 500, "message": "oops"}), "provider_malformed"),
])
async def test_adapter_never_plays_error_bodies(response, reason):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response)) as client:
        adapter = FishVoiceAdapter(client, "k", model="drama-3", emotion="off")
        with pytest.raises(VoiceError) as error:
            [c async for c in adapter.stream("Хорошо.", SCOPE, "g", Delivery())]
    assert error.value.reason == reason and adapter.last_usage is None


def test_adapter_rejects_foreign_url_and_bad_voice_id():
    client = httpx.AsyncClient()
    for kwargs in ({"url": "https://evil.example/v1/tts"}, {"reference_id": "../x"}, {"emotion": "loud"}):
        with pytest.raises(ValueError):
            FishVoiceAdapter(client, "k", model="drama-3", **kwargs)


def test_fish_pricing_is_per_input_byte_at_list_price():
    price = voice_pricing("fish")
    assert price.model == "drama-3" and price.input_rate == 50_000_000 and price.audio_output_rate == 0
    assert price.version == get_settings().coach_voice_fish_pricing_version and price.enforceable_bounds


def test_preferences_voice_model_defaults_and_validation():
    prefs = CoachPreferences()
    assert (prefs.voice_model, prefs.fish_voice_id, prefs.voice_emotion) == ("fish-drama-3", "", "expressive")
    assert (prefs.persona, prefs.profanity, prefs.humor, prefs.edgy_opt_in) == ("streamer", True, "often", True)
    assert "roast" in prefs.humor_kinds
    assert CoachPreferences(voice_model="fish-drama-3", fish_voice_id=FISH_ID).fish_voice_id == FISH_ID
    for bad in ({"voice_model": "elevenlabs"}, {"fish_voice_id": "not-an-id"}, {"voice_emotion": "max"}):
        with pytest.raises(ValueError):
            CoachPreferences(**bad)


@pytest.mark.parametrize(("model", "adapter", "price_model"), [
    ("openai-realtime", "RealtimeVoiceAdapter", "gpt-realtime-2.1-mini"),
    ("openai-tts", "TtsVoiceAdapter", "gpt-4o-mini-tts"),
    ("fish-drama-3", "FishVoiceAdapter", "drama-3"),
])
async def test_pipeline_switches_voice_model_by_preference(session_factory, monkeypatch, model, adapter, price_model):
    reads = []

    def read_credential(db, provider="openai"):
        reads.append(provider)
        return f"{provider}-key", 1

    monkeypatch.setattr(live.security, "read_credential", read_credential)
    for flag in ("COACH_PAID_TEXT_ENABLED", "COACH_TEXT_PRICING_VERIFIED", "COACH_PAID_VOICE_ENABLED", "COACH_VOICE_PRICING_VERIFIED"):
        monkeypatch.setenv(flag, "true")
    get_settings.cache_clear()
    prefs = CoachPreferences(mode="hybrid", network_consent_version=1, voice_model=model, fish_voice_id=FISH_ID,
                             voice_emotion="subtle")
    character_voice = PERSONAS["streamer"].fish_voice_id
    try:
        pipeline = await live.default_pipeline(session_factory, prefs)
        try:
            assert type(pipeline.voice.adapter).__name__ == adapter and pipeline.voice.pricing.model == price_model
            assert reads == (["openai", "fish"] if model == "fish-drama-3" else ["openai"])
            if model == "fish-drama-3":
                assert pipeline.voice.adapter.reference_id == FISH_ID and pipeline.voice.adapter.emotion == "subtle"
        finally:
            await pipeline.close()
        if model == "fish-drama-3":  # no own voice → the character's voice
            pipeline = await live.default_pipeline(session_factory, prefs.model_copy(update={"fish_voice_id": ""}))
            assert pipeline.voice.adapter.reference_id == character_voice
            await pipeline.close()
    finally:
        get_settings.cache_clear()


async def test_pipeline_without_fish_key_falls_back_to_openai_voice(session_factory, monkeypatch):
    def read_credential(db, provider="openai"):
        if provider == "fish":
            raise HTTPException(409, "credential_unavailable")
        return "openai-key", 1

    monkeypatch.setattr(live.security, "read_credential", read_credential)
    for flag in ("COACH_PAID_TEXT_ENABLED", "COACH_TEXT_PRICING_VERIFIED", "COACH_PAID_VOICE_ENABLED", "COACH_VOICE_PRICING_VERIFIED"):
        monkeypatch.setenv(flag, "true")
    get_settings.cache_clear()
    try:
        pipeline = await live.default_pipeline(session_factory, CoachPreferences(
            mode="hybrid", network_consent_version=1, voice_model="fish-drama-3"))
        try:
            assert type(pipeline.voice.adapter).__name__ == "RealtimeVoiceAdapter" and pipeline.author is not None
            assert pipeline.reason == "voice_fallback"
        finally:
            await pipeline.close()
    finally:
        get_settings.cache_clear()


async def test_fish_dispatch_requires_its_own_vault_key(session_factory, monkeypatch):
    price = Pricing(version="fish-test", model="drama-3", input_rate=50_000_000, cached_rate=0, output_rate=0,
                    verified=True, enforceable_bounds=True)

    def try_dispatch(run_id, generation, opportunity):
        with session_factory() as db:
            attempt = ledger.reserve(db, run_id, "tab-a", generation, opportunity, "voice", price,
                                     voice_bounds("Хорошо.", audio_tokens_per_s=50))
        with session_factory() as db:
            try:
                ledger.dispatch(db, attempt, "tab-a", adapter="fish")
                return "sent"
            except HTTPException as error:
                ledger.cancel_reserved(db, attempt)
                return error.detail

    monkeypatch.setenv("COACH_PAID_VOICE_ENABLED", "true")
    monkeypatch.setenv("COACH_VOICE_PRICING_VERIFIED", "true")
    get_settings.cache_clear()
    try:
        with session_factory() as db:
            db.add(CoachCredential(id=1, version=1, ciphertext="synthetic-openai"))
            db.commit()
        run_id, generation = make_run(session_factory)
        assert try_dispatch(run_id, generation, "a") == "paid_adapter_unavailable"  # no Fish key
        with session_factory() as db:
            db.add(CoachCredential(id=2, version=1, ciphertext="synthetic-fish"))
            db.commit()
        assert try_dispatch(run_id, generation, "b") == "sent"
    finally:
        get_settings.cache_clear()
