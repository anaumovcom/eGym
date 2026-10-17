"""U07 candidate preparation only; socket/serial/paid access prohibited by the safe runner."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.services.coach import voice
from app.services.coach.voice import Delivery

FIXTURE = json.loads((Path(__file__).parent / "fixtures/coach_u07_delivery.json").read_text())
CASES = FIXTURE["cases"]


def test_baseline_defaults_and_separate_candidate_version():
    assert Settings.model_fields["coach_situational_delivery_enabled"].default is False
    assert Delivery().profile == "legacy"
    assert voice.VOICE_PROMPT_VERSION == FIXTURE["baselineVersion"] == "coach-voice-0.5"
    assert voice.CANDIDATE_DELIVERY_VERSION == FIXTURE["candidateVersion"]
    from app.services.coach.packs import STYLE_VERSION
    assert STYLE_VERSION == FIXTURE["packStyleVersion"] == "coach-pack-style-0.3"
    with pytest.raises(ValueError):
        Delivery(profile="invented")
    with pytest.raises(ValueError):
        voice.candidate_instructions(Delivery())


@pytest.mark.parametrize(("flag", "accepted", "expected"), [
    (False, False, False), (True, False, False), (False, True, False), (True, True, True),
])
def test_runtime_requires_flag_and_future_acceptance(monkeypatch, flag, accepted, expected):
    assert voice.SITUATIONAL_DELIVERY_ACCEPTED is False
    monkeypatch.setenv("COACH_SITUATIONAL_DELIVERY_ENABLED", str(flag).lower())
    monkeypatch.setattr(voice, "SITUATIONAL_DELIVERY_ACCEPTED", accepted)
    get_settings.cache_clear()
    try:
        assert voice.situational_delivery_enabled() is expected
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_offline_same_text_profile_invariants_and_explicit_selection(case):
    args = dict(intent=case["intent"], action=case["action"], outcome=case["outcome"])
    assert voice.select_delivery(Delivery(), **args).profile == "legacy"
    delivery = voice.select_delivery(Delivery(), **args, enabled=True)
    assert delivery.profile == case["profile"]
    instructions = voice.candidate_instructions(delivery)
    assert voice.CANDIDATE_TIMBRE in instructions and voice.CANDIDATE_READING in instructions
    assert voice.PROFILE_PRESENTATION[case["profile"]] in instructions
    assert "искусственного смеха" in instructions and "не добавляй слова" in instructions
    assert "Без улыбки в голосе" not in instructions
    assert voice.delivery_instructions(delivery) == voice.REALTIME_INSTRUCTIONS
    assert voice.delivery_instructions(delivery, realtime=False) == voice.tts_instructions(delivery)
    assert voice.delivery_instructions(delivery, enabled=True) == instructions


@pytest.mark.parametrize(("intent", "action", "outcome", "profile"), [
    ("motivation", "playful", None, "support"),  # Offered humor slot is not actual humor.
    ("humor", "support", None, "playful"),  # Actual intent, not broad trigger.
    ("humor", "result", "partial", "partial"),
    ("humor", "summary", "limited", "partial"),
    ("factual-feedback", "result", None, "partial"),
    ("factual-feedback", "summary", "unknown", "partial"),
    ("motivation", "result", "full", "result"),
    ("humor", "safety", "full", "safety"),
    ("humor", "count", None, "count"),
])
def test_actual_intent_action_and_result_precedence(intent, action, outcome, profile):
    delivery = voice.select_delivery(Delivery(), intent=intent, action=action, outcome=outcome, enabled=True)
    assert delivery.profile == profile


@pytest.mark.parametrize("profile", voice.DELIVERY_PROFILES)
def test_manual_energy_pace_override_including_legacy_and_strict_profiles(profile):
    base = Delivery("bright", "brisk", "result", profile)
    action = profile if profile in {"count", "safety"} else "support"
    delivery = voice.select_delivery(base, intent="motivation", action=action, outcome=None,
                                     enabled=profile != "legacy", energy="calm", pace="normal")
    assert (delivery.energy, delivery.pace, delivery.emphasis) == ("calm", "normal", "result")
    auto = voice.select_delivery(base, intent="motivation", action=action, outcome=None, enabled=True)
    assert (auto.energy, auto.pace) == ("bright", "brisk")


async def no_connect(*args, **kwargs):
    raise AssertionError("Preparation must never connect")


@pytest.mark.parametrize("enabled", [False, True])
def test_realtime_request_only_reading_payload_no_workout_context(enabled):
    adapter = voice.RealtimeVoiceAdapter(no_connect, "synthetic-not-a-key", model="fake-model", voice="ash",
                                         situational_enabled=enabled)
    delivery = Delivery(profile="playful")
    req = adapter.request("У отдыха тоже есть рабочее место.", delivery)["response"]
    payload = json.loads(req["input"][0]["content"][0]["text"])
    assert payload == {"speechText": "У отдыха тоже есть рабочее место.",
                       "delivery": {"energy": "warm", "pace": "normal", "emphasis": "none"}}
    assert req["conversation"] == "none" and "tools" not in req
    assert req["instructions"] == voice.delivery_instructions(delivery, enabled=enabled)
    if enabled:
        assert "Без улыбки в голосе" not in req["instructions"]
    else:
        assert req["instructions"] == voice.REALTIME_INSTRUCTIONS
    assert req["audio"]["output"]["voice"] == "ash"
    legacy = adapter.request("Работа идёт, без спешки.", Delivery())["response"]
    assert legacy["instructions"] == voice.REALTIME_INSTRUCTIONS


@pytest.mark.parametrize("enabled", [False, True])
async def test_tts_mock_transport_selects_candidate_only_when_explicit(enabled):
    seen = []
    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, text='data: {"type":"speech.audio.done","usage":{"input_tokens":10,"output_tokens":20}}\n\n')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = voice.TtsVoiceAdapter(client, "synthetic-not-a-key", model="fake", voice="ash",
                                       situational_enabled=enabled)
        delivery = Delivery(profile="support")
        from app.tests.test_coach_e08_voice import SCOPE
        assert [chunk async for chunk in adapter.stream("Работа идёт, без спешки.", SCOPE, "g", delivery)]
    assert seen[0]["instructions"] == voice.delivery_instructions(delivery, enabled=enabled, realtime=False)
    assert seen[0]["input"] == "Работа идёт, без спешки." and seen[0]["voice"] == "ash"


def test_reserve_conservatively_includes_candidate_instruction_bytes():
    text = "Работа идёт, без спешки."
    baseline = voice.voice_bounds(text, audio_tokens_per_s=50)
    candidate = voice.voice_bounds(text, audio_tokens_per_s=50,
                                   instructions=voice.candidate_instructions(Delivery(profile="support")))
    assert candidate.input_tokens > baseline.input_tokens
    assert candidate.audio_output_tokens == baseline.audio_output_tokens


def preparation_module():
    path = Path(__file__).resolve().parents[2] / "scripts/coach_delivery_pilot.py"
    spec = importlib.util.spec_from_file_location("offline_delivery_plan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_plan_no_settings_secrets_or_provider_access(monkeypatch, capsys):
    monkeypatch.setattr(voice, "get_settings", lambda: pytest.fail("No settings access"))
    module = preparation_module()
    assert module.main(["plan"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["paidUsd"] == "0.00" and plan["approvedCapUsd"] is None
    assert not plan["proposalIsApproval"] and not plan["generationAvailable"] and plan["providerRequests"] == 0
    assert 8 <= len(plan["pairs"]) <= 12 and plan["futureNonLocalRequestCeiling"] == 14
    for pair in plan["pairs"]:
        assert pair["a"]["speechText"] == pair["b"]["speechText"]
        assert pair["a"]["delivery"] == pair["b"]["delivery"]
        assert pair["a"]["pronunciation"] == pair["b"]["pronunciation"] == []
        if pair["localOnly"]:
            assert pair["generation"] == "forbidden-current-recordings-only"
    for args in [["generate"], ["plan", "--confirm-paid", "--cap-usd", "0.10"]]:
        with pytest.raises(SystemExit) as error:
            module.main(args)
        assert error.value.code == 2


@pytest.fixture
def enabled_coach(use_test_emulator, monkeypatch):
    monkeypatch.setenv("COACH_ENABLED", "true")
    monkeypatch.setenv("COACH_SITUATIONAL_DELIVERY_ENABLED", "true")
    get_settings.cache_clear()


async def test_live_flag_without_listening_keeps_legacy_and_user_overrides(session_factory, enabled_coach):
    from app.schemas.coach_control import CoachPreferences
    from app.tests.test_coach_e10_live import HYBRID, event, make_coach, settle
    prefs = CoachPreferences(**{**HYBRID, "voiceEnergy": "calm", "voicePace": "brisk"})
    coach, sink, run = make_coach(session_factory, prefs=prefs)
    deliveries = []
    original = coach.voice.adapter.stream
    async def capture(text, scope, gid, delivery, **kwargs):
        deliveries.append(delivery)
        async for chunk in original(text, scope, gid, delivery, **kwargs):
            yield chunk
    coach.voice.adapter.stream = capture
    await coach.handle(event("workout_started", run))
    await settle(coach)
    assert sink.of("speech_start") and deliveries
    assert deliveries == [Delivery("calm", "brisk", deliveries[0].emphasis)]
    await coach.close()


@pytest.mark.parametrize(("actual", "status", "expected"), [(10, "completed", "result"), (7, "partial", "partial")])
async def test_live_future_explicit_opt_in_uses_actual_result_not_trigger(
        session_factory, enabled_coach, monkeypatch, actual, status, expected):
    from app.services.coach.luna import FakeTextAuthor
    from app.tests.test_coach_e10_live import event, make_coach, seed, settle
    from app.tests.test_coach_u03_completion import count_script
    # Explicit synthetic acceptance for this test only; the shipped marker stays False.
    monkeypatch.setattr(voice, "SITUATIONAL_DELIVERY_ACCEPTED", True)
    with session_factory() as db:
        _, _, sid = seed(db, actual=actual, planned=10, status=status)
    text = "Выполнено десять повторов." if actual == 10 else "Выполнено семь повторов."
    coach, sink, run = make_coach(session_factory, fake_text=FakeTextAuthor(count_script(text)))
    deliveries = []
    original = coach.voice.adapter.stream
    async def capture(text, scope, gid, delivery, **kwargs):
        deliveries.append(delivery)
        async for chunk in original(text, scope, gid, delivery, **kwargs):
            yield chunk
    coach.voice.adapter.stream = capture
    await coach.handle(event("set_persisted", run, set_ordinal=1, phase="rest", refs={"backendSetId": sid},
                             context={"restMs": 90_000}))
    await settle(coach)
    assert sink.of("speech_start") and [d.profile for d in deliveries] == [expected]
    await coach.close()
