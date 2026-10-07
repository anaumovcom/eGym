"""E08: voice prompts, tagged PCM framing, adapters (mocked transport), transcript checks, ledger-bound streaming."""

import asyncio
import base64
import json
import re
import struct
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachCredential
from app.schemas.coach import CoachAudio, CoachScope
from app.schemas.coach_control import Pricing, ReportedUsage
from app.services.coach import ledger
from app.services.coach.ports import AudioChunk
from app.services.coach.voice import (
    COUNT_INSTRUCTIONS,
    FRAME_MAGIC,
    MAX_STREAM_BYTES,
    REALTIME_INSTRUCTIONS,
    TTS_TEMPLATE,
    Delivery,
    FakeVoiceStream,
    PcmFramer,
    RealtimeVoiceAdapter,
    TtsVoiceAdapter,
    VoiceCapability,
    VoiceError,
    VoiceOutcome,
    VoiceStreamer,
    decode_frame,
    encode_frame,
    parse_realtime_usage,
    parse_tts_usage,
    route_voice,
    tts_instructions,
    verify_transcript,
    voice_bounds,
    voice_hashes,
    voice_pricing,
)

DOC = Path(__file__).resolve().parents[3] / "plan" / "13-live-ai-coach-behavior-prompts.md"
SCOPE = CoachScope(user_id="alexey", run_id="run-1", exercise_id="chest-press", set_ordinal=2, scope_epoch=3)
PRICE = Pricing(version="synthetic-voice-1", model="fake-voice", input_rate=600_000, cached_rate=60_000,
                output_rate=2_400_000, audio_input_rate=10_000_000, audio_cached_rate=300_000,
                audio_output_rate=20_000_000, verified=True, enforceable_bounds=True)


def _quote_after(heading: str, label: str) -> str:
    text = DOC.read_text()
    section = text[text.index(heading):]
    section = section[section.index(label):]
    lines = []
    for line in section.splitlines()[1:]:
        if line.startswith("> "):
            lines.append(line[2:])
        elif lines:
            break
    return "\n".join(lines)


def test_voice_prompts_are_verbatim_from_document_and_hashed():
    assert _quote_after("### Live voice instructions", "TTS:") == TTS_TEMPLATE
    assert _quote_after("### Live voice instructions", "Realtime:") == REALTIME_INSTRUCTIONS
    assert _quote_after("### Числа и микроклипы", "### Числа и микроклипы") == COUNT_INSTRUCTIONS
    filled = tts_instructions(Delivery("bright", "brisk", "result"))
    assert "Энергия: bright; темп: brisk; акцент результата: result." in filled and "{" not in filled
    with pytest.raises(ValueError):
        Delivery("shout")
    hashes = voice_hashes()
    assert hashes["version"] == "coach-voice-0.3" and all(len(v) == 64 for k, v in hashes.items() if k != "version")


def chunk(data: bytes, *, sequence=0, final=False, rate=24_000, **meta) -> AudioChunk:
    fields = dict(utterance_id="u-1", generation_id="g-1", scope=SCOPE, sequence=sequence, source="tts",
                  codec="pcm_s16le", sample_rate=rate, byte_length=len(data), duration_ms=len(data) / 2 / rate * 1000,
                  final=final)
    return AudioChunk(CoachAudio(**{**fields, **meta}), data)


GOLDEN_PCM = struct.pack("<4h", 0, 16384, -16384, 32767)
GOLDEN = ("RUNBMUABAAB7InNjaGVtYVZlcnNpb24iOjEsInV0dGVyYW5jZUlkIjoidS0xIiwiZ2VuZXJhdGlvbklk"
          "IjoiZy0xIiwic2NvcGUiOnsic2NoZW1hVmVyc2lvbiI6MSwidXNlcklkIjoiYWxleGV5IiwicnVuSWQi"
          "OiJydW4tMSIsImV4ZXJjaXNlSWQiOiJjaGVzdC1wcmVzcyIsInNldE9yZGluYWwiOjIsInNjb3BlRXBv"
          "Y2giOjN9LCJzZXF1ZW5jZSI6MCwic291cmNlIjoidHRzIiwiY29kZWMiOiJwY21fczE2bGUiLCJzYW1w"
          "bGVSYXRlIjoyNDAwMCwiY2hhbm5lbHMiOjEsImJ5dGVMZW5ndGgiOjgsImR1cmF0aW9uTXMiOjAuMTY2"
          "NjY2NjY2NjY2NjY2NjYsImZpbmFsIjp0cnVlfQAAAEAAwP9/")  # shared with frontend coach-frames.test.ts


def test_golden_frame_matches_shared_fixture():
    frame = encode_frame(chunk(GOLDEN_PCM, final=True))
    assert frame[:4] == FRAME_MAGIC and base64.b64encode(frame).decode() == GOLDEN
    decoded = decode_frame(base64.b64decode(GOLDEN))
    assert decoded.data == GOLDEN_PCM and decoded.metadata.final and decoded.metadata.scope == SCOPE


def test_frame_roundtrip_and_bounds():
    original = chunk(bytes(range(256)) * 10, sequence=4)
    decoded = decode_frame(encode_frame(original))
    assert decoded == original
    frame = encode_frame(original)
    for broken, reason in [(b"XXXX" + frame[4:], "frame_magic"), (frame[:6], "frame_magic"),
                           (frame[:4] + struct.pack("<I", 9999) + frame[8:], "frame_header"),
                           (frame[:-1], "frame_length"), (frame + b"\x00\x00", "frame_length"),
                           (frame[:8] + b"{" * (len(frame) - 8), "frame_header")]:
        with pytest.raises(VoiceError) as error:
            decode_frame(broken)
        assert error.value.reason == reason
    with pytest.raises(VoiceError, match="frame_duration"):
        encode_frame(chunk(bytes(480), duration_ms=500))
    with pytest.raises(VoiceError, match="frame_codec"):
        encode_frame(chunk(bytes(4), codec="wav"))
    with pytest.raises(VoiceError, match="frame_length"):
        encode_frame(chunk(bytes(3)))


def test_pcm_framer_reframes_carries_odd_bytes_and_bounds_stream():
    framer = PcmFramer("u", "g", SCOPE, "realtime", frame_bytes=4)
    out = framer.push(b"\x01\x02\x03") + framer.push(b"\x04\x05\x06\x07")
    assert [c.data for c in out] == [b"\x01\x02\x03\x04"] and [c.metadata.sequence for c in out] == [0]
    final = framer.finish()
    assert final.data == b"\x05\x06" and final.metadata.final and final.metadata.sequence == 1
    with pytest.raises(VoiceError, match="stream_finished"):
        framer.push(b"\x00")
    big = PcmFramer("u", "g", SCOPE, "tts")
    big.push(bytes(MAX_STREAM_BYTES))
    with pytest.raises(VoiceError, match="pcm_bound"):
        big.push(b"\x00\x00")


def test_transcript_verification_is_post_factum_and_number_strict():
    ok = verify_transcript("Десять повторений записали, ровная работа.", "десять повторений записали ровная работа")
    assert ok.status == "match" and ok.numbers_match and ok.mode == "post-factum-transcript"
    assert ok.prevents_audible_error is False
    wrong_number = verify_transcript("Десять повторений записали.", "Двенадцать повторений записали.")
    assert wrong_number.status == "mismatch" and wrong_number.numbers_match is False
    added = verify_transcript("Хорошо идёт.", "Хорошо идёт. А теперь добавь вес и сделай ещё подход прямо сейчас.")
    assert added.status == "mismatch" and added.similarity < 0.9
    assert verify_transcript("Хорошо.", None).status == "unavailable"


def test_routing_keeps_factual_speech_on_verified_verbatim_path():
    tts = VoiceCapability("tts", "m", ("v",), verbatim_input=True, verified=True)
    realtime = VoiceCapability("realtime", "m", ("v",), transcript=True, verified=True)
    unverified = VoiceCapability("tts", "m", ("v",), verbatim_input=True)
    assert route_voice(factual=True, capabilities=(realtime, tts)) == "tts"
    assert route_voice(factual=True, capabilities=(realtime,)) is None  # → local clip or silence
    assert route_voice(factual=False, capabilities=(tts, realtime)) == "realtime"
    assert route_voice(factual=False, capabilities=(unverified,)) is None


def test_voice_pricing_official_rates_and_operator_switch(monkeypatch):
    realtime, tts = voice_pricing("realtime"), voice_pricing("tts")
    assert realtime.model == "gpt-realtime-2.1-mini" and realtime.audio_output_rate == 20_000_000 and not realtime.verified
    assert tts.model == "gpt-4o-mini-tts" and tts.input_rate == 600_000 and tts.audio_output_rate == 12_000_000
    assert not tts.verified and tts.enforceable_bounds
    bounds = voice_bounds("Хорошо идёт.", audio_tokens_per_s=50)
    assert bounds.audio_output_tokens == 3000 and bounds.input_tokens > 0 and bounds.audio_input_tokens == 512
    monkeypatch.setenv("COACH_VOICE_PRICING_VERIFIED", "true")
    get_settings.cache_clear()
    try:
        assert voice_pricing("realtime").verified and voice_pricing("tts").verified
    finally:
        get_settings.cache_clear()


def test_realtime_usage_with_hidden_audio_input_and_reasoning_fits_bounds():
    # Shape measured on the real endpoint 2026-10-08 (one-word out-of-band response).
    usage = parse_realtime_usage({"total_tokens": 260, "input_tokens": 195, "output_tokens": 65, "input_token_details": {
        "text_tokens": 35, "audio_tokens": 160, "image_tokens": 0, "cached_tokens": 128,
        "cached_tokens_details": {"text_tokens": 0, "audio_tokens": 128, "image_tokens": 0}},
        "output_token_details": {"text_tokens": 47, "audio_tokens": 18, "reasoning_tokens": 32}})
    assert usage == ReportedUsage(input_tokens=35, output_tokens=47, audio_input_tokens=160, audio_output_tokens=18,
                                  cached_audio_input_tokens=128, reasoning_tokens=32)
    bounds = voice_bounds("Двенадцать.", audio_tokens_per_s=50)
    assert all(getattr(usage, f) <= getattr(bounds, f) for f in ("input_tokens", "output_tokens", "audio_input_tokens", "audio_output_tokens"))
    assert parse_tts_usage({"input_tokens": 12, "output_tokens": 37, "total_tokens": 49}) == ReportedUsage(
        input_tokens=12, output_tokens=0, audio_input_tokens=0, audio_output_tokens=37)


def sse(*events, done=True) -> bytes:
    lines = [f"data: {json.dumps(e)}\n\n" for e in events] + (["data: [DONE]\n\n"] if done else [])
    return "".join(lines).encode()


async def test_tts_adapter_streams_sse_pcm_frames_with_documented_body():
    seen = []
    parts = [base64.b64encode(p).decode() for p in (bytes(3000), bytes(3001), b"\x07")]
    payload = sse(*({"type": "speech.audio.delta", "audio": p} for p in parts),
                  {"type": "speech.audio.done", "usage": {"input_tokens": 12, "output_tokens": 37, "total_tokens": 49}})

    def handler(request: httpx.Request):
        seen.append((str(request.url), request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(200, content=payload, headers={"x-request-id": "req-1", "content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = TtsVoiceAdapter(client, "sk-test-secret", model="gpt-4o-mini-tts", voice="marin")
        frames = [c async for c in adapter.stream("Десять повторений.", SCOPE, "g-7", Delivery())]
        url, auth, sent = seen[0]
        assert url == "https://api.openai.com/v1/audio/speech" and auth == "Bearer sk-test-secret"
        assert sent == {"model": "gpt-4o-mini-tts", "input": "Десять повторений.", "voice": "marin",
                        "instructions": tts_instructions(Delivery()), "response_format": "pcm", "stream_format": "sse"}
        assert sum(c.metadata.byte_length for c in frames) == 6002 and frames[-1].metadata.final
        assert all(c.metadata.source == "tts" and c.metadata.generation_id == "g-7" for c in frames)
        assert [c.metadata.sequence for c in frames] == list(range(len(frames)))
        assert "secret" not in repr(adapter) and adapter.last_response_id == "req-1"
        assert adapter.last_usage == ReportedUsage(input_tokens=12, output_tokens=0, audio_input_tokens=0, audio_output_tokens=37)
        [c async for c in adapter.stream("Раз.", SCOPE, "g-8", Delivery(), instructions=COUNT_INSTRUCTIONS)]
        assert seen[1][2]["instructions"] == COUNT_INSTRUCTIONS
    with pytest.raises(ValueError):
        TtsVoiceAdapter(client, "k", model="m", voice="v", url="http://evil.example/")


@pytest.mark.parametrize(("payload", "reason"), [
    (sse({"type": "speech.audio.delta", "audio": "AAAA"}), "provider_incomplete"),  # no usage event
    (b"data: {not json\n\n", "provider_malformed"),
    (sse({"type": "speech.audio.delta", "audio": "@@@"}), "provider_malformed"),
    (sse({"type": "error", "error": {}}), "provider_error"),
])
async def test_tts_adapter_sse_failures(payload, reason):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload))) as client:
        adapter = TtsVoiceAdapter(client, "k", model="m", voice="v")
        with pytest.raises(VoiceError) as error:
            [c async for c in adapter.stream("Хорошо.", SCOPE, "g", Delivery())]
    assert error.value.reason == reason


async def test_tts_adapter_http_error_and_empty_text():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429))) as client:
        adapter = TtsVoiceAdapter(client, "k", model="m", voice="v")
        with pytest.raises(VoiceError, match="http-429"):
            [c async for c in adapter.stream("Хорошо.", SCOPE, "g", Delivery())]
        with pytest.raises(VoiceError, match="invalid_text"):
            [c async for c in adapter.stream("  ", SCOPE, "g", Delivery())]


class FakeSocket:
    def __init__(self, events):
        self.events, self.sent, self.closed = list(events), [], False

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def recv(self):
        return json.dumps(self.events.pop(0))

    async def close(self):
        self.closed = True


def realtime_events(status="completed"):
    audio = base64.b64encode(bytes(6000)).decode()
    return [{"type": "response.created"},
            {"type": "response.output_audio.delta", "delta": audio},
            {"type": "response.output_audio_transcript.delta", "delta": "Хорошо "},
            {"type": "response.output_audio_transcript.delta", "delta": "идёт."},
            {"type": "response.done", "response": {"id": "resp_1", "status": status, "usage": {
                "input_token_details": {"text_tokens": 120, "audio_tokens": 0, "cached_tokens_details": {"text_tokens": 64}},
                "output_token_details": {"text_tokens": 8, "audio_tokens": 40}}}}]


async def test_realtime_adapter_out_of_band_response_usage_and_transcript():
    sockets = []

    async def connect(url, headers):
        sockets.append((url, headers))
        sockets.append(FakeSocket(realtime_events()))
        return sockets[-1]

    adapter = RealtimeVoiceAdapter(connect, "sk-rt", model="gpt-realtime-2.1-mini", voice="marin")
    frames = [c async for c in adapter.stream("Хорошо идёт.", SCOPE, "g-r", Delivery("calm"))]
    url, headers = sockets[0]
    socket = sockets[1]
    assert url == "wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1-mini" and headers["Authorization"] == "Bearer sk-rt"
    request = socket.sent[0]["response"]
    assert socket.sent[0]["type"] == "response.create" and request["conversation"] == "none"
    assert request["output_modalities"] == ["audio"] and request["instructions"] == REALTIME_INSTRUCTIONS
    payload = json.loads(request["input"][0]["content"][0]["text"])
    assert payload == {"speechText": "Хорошо идёт.", "delivery": {"energy": "calm", "pace": "normal", "emphasis": "none"}}
    assert sum(c.metadata.byte_length for c in frames) == 6000 and frames[-1].metadata.final and socket.closed
    assert adapter.last_transcript == "Хорошо идёт." and adapter.last_response_id == "resp_1"
    assert adapter.last_usage == ReportedUsage(input_tokens=120, output_tokens=8, audio_input_tokens=0,
                                               audio_output_tokens=40, cached_input_tokens=64)
    assert "sk-rt" not in repr(adapter)


@pytest.mark.parametrize(("events", "reason"), [
    (realtime_events("incomplete"), "provider_incomplete"),
    ([{"type": "error", "error": {"message": "x"}}], "provider_error"),
    ([{"type": "response.output_audio.delta", "delta": "@@@"}], "provider_malformed"),
])
async def test_realtime_adapter_failures_close_socket(events, reason):
    socket = FakeSocket(events)

    async def connect(url, headers):
        return socket

    adapter = RealtimeVoiceAdapter(connect, "k", model="m", voice="v")
    with pytest.raises(VoiceError) as error:
        [c async for c in adapter.stream("Хорошо.", SCOPE, "g", Delivery())]
    assert error.value.reason == reason and socket.closed


def make_run(session_factory):
    with session_factory() as db:
        row, _ = ledger.create_run(db, "alexey", "test", "2.00")
        run_id = row.id
        db.rollback()
        generation = ledger.lease(db, run_id, "tab-a", 0)["generation"]
    return run_id, generation


def statuses(session_factory, run_id):
    with session_factory() as db:
        return [a.status for a in db.query(CoachAttempt).filter_by(run_id=run_id).order_by(CoachAttempt.created_at)]


async def collect(streamer, run_id, generation, opportunity="v:1", text="Хорошо идёт.", **kw):
    outcome = VoiceOutcome()
    frames = [f async for f in streamer.stream(run_id=run_id, owner="tab-a", generation=generation, opportunity=opportunity,
                                               text=text, scope=SCOPE, generation_id="g-1", outcome=outcome, **kw)]
    return outcome, frames


async def test_streamer_fake_settles_and_yields_decodable_frames(session_factory):
    run_id, generation = make_run(session_factory)
    fake = FakeVoiceStream(transcript="Хорошо идёт.")
    outcome, frames = await collect(VoiceStreamer(session_factory, fake, PRICE), run_id, generation)
    decoded = [decode_frame(f) for f in frames]
    assert outcome.status == "complete" and outcome.frames == 3 and outcome.bytes == 9600
    assert [d.metadata.sequence for d in decoded] == [0, 1, 2] and decoded[-1].metadata.final
    assert outcome.transcript.mode == "verbatim-input" and outcome.first_audio_ms is not None
    assert statuses(session_factory, run_id) == ["settled"]


async def test_streamer_paid_adapter_is_refused_before_any_network_call(session_factory):
    run_id, generation = make_run(session_factory)
    calls = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200))) as client:
        adapter = TtsVoiceAdapter(client, "k", model="fake-voice", voice="v")
        outcome, frames = await collect(VoiceStreamer(session_factory, adapter, PRICE), run_id, generation)
    assert outcome.status == "refused" and outcome.reason == "paid_adapter_unavailable" and not frames and not calls
    assert statuses(session_factory, run_id) == ["cancelled"]
    outcome, _ = await collect(VoiceStreamer(session_factory, FakeVoiceStream(), voice_pricing("realtime")), run_id, generation, "v:2")
    assert outcome.status == "refused" and outcome.reason == "strict_cap_unprovable"


async def test_paid_voice_dispatch_requires_every_operator_gate(session_factory, monkeypatch):
    def attempt_for(run_id, generation, opportunity, model, ledger_name="test"):
        with session_factory() as db:
            price = PRICE.model_copy(update={"model": model})
            return ledger.reserve(db, run_id, "tab-a", generation, opportunity, "voice", price, voice_bounds("Хорошо.", audio_tokens_per_s=50))

    def try_dispatch(attempt, adapter):
        with session_factory() as db:
            try:
                ledger.dispatch(db, attempt, "tab-a", adapter=adapter)
                return "sent"
            except HTTPException as error:
                ledger.cancel_reserved(db, attempt)
                return error.detail

    run_id, generation = make_run(session_factory)
    rt = "gpt-realtime-2.1-mini"
    assert try_dispatch(attempt_for(run_id, generation, "a", rt), "realtime") == "paid_adapter_unavailable"  # flags off
    monkeypatch.setenv("COACH_PAID_VOICE_ENABLED", "true")
    monkeypatch.setenv("COACH_VOICE_PRICING_VERIFIED", "true")
    get_settings.cache_clear()
    try:
        assert try_dispatch(attempt_for(run_id, generation, "b", rt), "realtime") == "paid_adapter_unavailable"  # no vault
        with session_factory() as db:
            db.add(CoachCredential(id=1, version=1, ciphertext="synthetic-ciphertext"))
            db.commit()
        run2, gen2 = make_run(session_factory)
        assert try_dispatch(attempt_for(run2, gen2, "c", rt), "tts") == "paid_adapter_unavailable"  # model/adapter mismatch
        assert try_dispatch(attempt_for(run2, gen2, "d", rt), "luna-text") == "paid_adapter_unavailable"
        assert try_dispatch(attempt_for(run2, gen2, "e", "gpt-4o-mini-tts"), "pack-tts") == "sent"  # test ledger
        with session_factory() as db:
            ledger.mark_unsettled(db, db.query(CoachAttempt).filter_by(run_id=run2, status="sent").one().id)
        run3, gen3 = make_run(session_factory)
        assert try_dispatch(attempt_for(run3, gen3, "f", rt), "realtime") == "sent"
    finally:
        get_settings.cache_clear()


async def test_streamer_scope_change_mid_stream_cancels_and_leaves_liability(session_factory):
    run_id, generation = make_run(session_factory)
    streamer = VoiceStreamer(session_factory, FakeVoiceStream(parts=(bytes(4800),) * 4), PRICE)
    outcome = VoiceOutcome()
    frames = []
    async for frame in streamer.stream(run_id=run_id, owner="tab-a", generation=generation, opportunity="v:3",
                                       text="Хорошо.", scope=SCOPE, generation_id="g-1", outcome=outcome):
        frames.append(frame)
        if len(frames) == 1:
            with session_factory() as db:
                ledger.cancel_run(db, run_id)  # new generation: late chunks must not be emitted
    assert outcome.status == "cancelled" and outcome.reason == "scope_changed" and len(frames) == 1
    assert statuses(session_factory, run_id) == ["unsettled"]


async def test_streamer_timeouts_errors_and_consumer_cancel_mark_unsettled(session_factory):
    run_id, generation = make_run(session_factory)
    slow = VoiceStreamer(session_factory, FakeVoiceStream(first_delay_s=0.2), PRICE, first_audio_timeout_s=0.05)
    outcome, frames = await collect(slow, run_id, generation, "v:4")
    assert outcome.status == "failed" and outcome.reason == "first_audio_timeout" and not frames
    broken = VoiceStreamer(session_factory, FakeVoiceStream(parts=(bytes(4800), bytes(4800)), error_after=1), PRICE)
    outcome, frames = await collect(broken, run_id, generation, "v:5")
    assert outcome.status == "failed" and outcome.reason == "provider_error" and len(frames) == 1
    clock = iter([0.0, 0.0, 61.0, 61.0, 61.0])
    capped = VoiceStreamer(session_factory, FakeVoiceStream(parts=(bytes(4800),) * 3), PRICE, now_s=lambda: next(clock, 61.0))
    outcome, _ = await collect(capped, run_id, generation, "v:6")
    assert outcome.status == "failed" and outcome.reason == "watchdog"  # 60 s cap is not extended by packets
    early = VoiceStreamer(session_factory, FakeVoiceStream(parts=(bytes(4800),) * 3), PRICE)
    outcome = VoiceOutcome()
    stream = early.stream(run_id=run_id, owner="tab-a", generation=generation, opportunity="v:7", text="Хорошо.",
                          scope=SCOPE, generation_id="g", outcome=outcome)
    await stream.__anext__()
    await stream.aclose()
    assert outcome.status == "cancelled"
    assert statuses(session_factory, run_id) == ["unsettled"] * 4


async def test_streamer_task_cancellation_propagates(session_factory):
    run_id, generation = make_run(session_factory)
    streamer = VoiceStreamer(session_factory, FakeVoiceStream(first_delay_s=1), PRICE)
    outcome = VoiceOutcome()

    async def consume():
        return [f async for f in streamer.stream(run_id=run_id, owner="tab-a", generation=generation, opportunity="v:8",
                                                 text="Хорошо.", scope=SCOPE, generation_id="g", outcome=outcome)]

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert outcome.status == "cancelled" and statuses(session_factory, run_id) == ["unsettled"]


def test_voice_module_has_no_hardware_imports():
    source = (Path(__file__).resolve().parents[1] / "services" / "coach" / "voice.py").read_text()
    assert not re.search(r"^(from|import) app\.(services\.(modbus|motor|hardware|device)|hardware)", source, re.M)
