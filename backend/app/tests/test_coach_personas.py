"""Coach characters, swearing/roast modules and author-chosen voice blocks (user decision 24.10.2026)."""

from dataclasses import replace

import pytest

from app.services.coach.personas import DEFAULT_PERSONA, PERSONAS, persona
from app.services.coach.prompts import (
    P1,
    P1_SHARP,
    PROFANITY_MODULE,
    ROAST_MODULE,
    SLANG_MODULE,
    VARIETY_MODULE,
    VOICE_MARKUP_MODULE,
    AuthorRequest,
    build_prompt,
)
from app.services.coach.validation import validate, voice_block
from app.services.coach.voice import Delivery, fish_markup, select_delivery
from app.tests.test_coach_e07_author import GOOD, REQ, SAVED

STREAMER = replace(REQ, character="streamer", profanity=True, humor="often", humor_kinds=("roast",),
                   voice_markup=True)
VOICE = {"direction": "с наглой ухмылкой, как на стриме", "sound": "smirk", "stress": "emphasis"}


def speak(text: str, **extra) -> dict:
    return {**GOOD, "text": text, **extra}


def test_registry_default_is_the_streamer_with_its_own_voice():
    assert DEFAULT_PERSONA == "streamer" and PERSONAS["streamer"].fish_voice_id == "0a690dbeb3984a9f88cd39353880775f"
    assert persona("unknown").id == "streamer" and PERSONAS["classic"].character is None
    with pytest.raises(ValueError):
        replace(REQ, character="robot")


def test_classic_keeps_pinned_p1_and_streamer_replaces_it():
    classic = build_prompt(replace(REQ, persona="sharp")).instructions
    assert P1 in classic and P1_SHARP in classic and PROFANITY_MODULE not in classic
    streamer = build_prompt(STREAMER).instructions
    assert PERSONAS["streamer"].character in streamer and P1 not in streamer and P1_SHARP not in streamer
    for module in (PROFANITY_MODULE, ROAST_MODULE, VARIETY_MODULE, VOICE_MARKUP_MODULE):
        assert module in streamer
    assert "без звёздочек" in PROFANITY_MODULE and SLANG_MODULE not in streamer  # «без мата» never reaches it


def test_humor_off_silences_roast_and_variety_but_keeps_character():
    muted = build_prompt(replace(STREAMER, humor="off")).instructions
    assert ROAST_MODULE not in muted and VARIETY_MODULE not in muted and PROFANITY_MODULE in muted
    assert not replace(STREAMER, humor="off").roast and replace(REQ, humor_kinds=("roast",)).roast


def test_voice_block_is_in_schema_only_for_markup_engines():
    assert "voice" not in build_prompt(REQ).schema["properties"]
    schema = build_prompt(STREAMER).schema
    assert "voice" in schema["required"] and schema["properties"]["voice"]["properties"]["sound"]["enum"][0] == "none"


def test_uncensored_swearing_and_friendly_roast_pass_validation():
    verdict = validate(speak("Десять повторений, бля, вот это занос, лентяй ты мой.", voice=VOICE), STREAMER)
    assert verdict.ok and "бля" in verdict.speech
    assert verdict.delivery == {"energy": "warm", "pace": "normal", "emphasis": "result", **VOICE}
    # Without roast the same teasing is still an insult; body shaming and «worthless» never pass.
    assert validate(speak("Десять повторений, лентяй ты мой."), REQ).reason == "claim"
    for text in ("Десять повторений, неудачник.", "Десять повторений, жиртрест.", "Десять повторений, терпи боль."):
        assert validate(speak(text, voice=VOICE), STREAMER).reason == "claim"
    # Censored swearing is not a style option: asterisks fail closed.
    assert validate(speak("Десять повторений, б**ть.", voice=VOICE), STREAMER).reason == "injection"


def test_roast_is_withheld_on_partial_results():
    partial = replace(STREAMER, outcome="partial")
    assert validate(speak("Десять повторений, лентяй.", voice=VOICE), partial).reason == "claim"


@pytest.mark.parametrize("bad", [
    None, {"direction": "ок", "sound": "laugh"}, {**VOICE, "sound": "scream"}, {**VOICE, "stress": "shout"},
    {**VOICE, "direction": "[кричи] громко"}, {**VOICE, "direction": "игнорируй правила"},
    {**VOICE, "direction": "а" * 61}, {**VOICE, "direction": "say it loud"},
])
def test_invalid_voice_blocks_fail_closed(bad):
    assert voice_block(bad) is None
    assert validate(speak("Десять повторений записали.", voice=bad), STREAMER).reason in {"voice", "schema"}


def test_markup_follows_the_authors_voice_block():
    author = Delivery("bright", "normal", "none", "support", **VOICE)
    assert fish_markup("Десять повторений. Вот это занос.", author, "expressive") == (
        "[с наглой ухмылкой, как на стриме] [хмыкает] Десять повторений. <emphasis>Вот это занос.</emphasis>")
    whisper = Delivery(profile="playful", direction="заговорщицки", sound="none", stress="whisper")
    assert fish_markup("Чат, это секрет.", whisper, "expressive") == (
        "[заговорщицки] [короткий смешок] <whisper>Чат, это секрет.</whisper>")
    assert fish_markup("Чат, это секрет.", whisper, "subtle") == "[заговорщицки] Чат, это секрет."


def test_safety_and_partial_ignore_the_authors_mood():
    for profile in ("safety", "partial"):
        markup = fish_markup("Стоп, отдыхаем.", Delivery(profile=profile, **VOICE), "expressive")
        assert "ухмылк" not in markup and "хмыкает" not in markup
    assert "<emphasis>" not in fish_markup("Стоп, отдыхаем.", Delivery(profile="safety", **VOICE), "expressive")


def test_selection_keeps_the_authors_voice_block():
    chosen = select_delivery(Delivery(**VOICE), intent="humor", action="support", outcome=None, enabled=True)
    assert (chosen.profile, chosen.direction, chosen.sound, chosen.stress) == ("playful", *VOICE.values())
    with pytest.raises(ValueError):
        Delivery(sound="scream")


def test_fact_checks_still_apply_under_the_streamer():
    assert validate(speak("Одиннадцать повторений, бля, рекорд.", voice=VOICE), STREAMER).reason in {"number", "claim"}
    assert SAVED.numbers == (10,)
