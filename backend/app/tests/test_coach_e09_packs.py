import asyncio
import dataclasses
import json
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachJob
from app.schemas.coach_control import Pricing, ReportedUsage
from app.services.coach import ledger, packs
from app.services.coach.packs import (
    CATALOG,
    FakePackVoice,
    PackError,
    PackJobRunner,
    PackStore,
    ProviderPackVoice,
    pcm_to_wav,
    verify_wav,
)
from app.services.coach.voice import COUNT_INSTRUCTIONS, FakeVoiceStream, PcmFramer, VoiceCapability
from app.tests.test_coach_control_plane import ORIGIN, auth, make_run, secured  # noqa: F401

PRICE = Pricing(version="synthetic-voice-1", model="fake-tts", input_rate=600_000, cached_rate=60_000, output_rate=2_400_000,
                audio_output_rate=12_000_000, verified=True, enforceable_bounds=True)
LOCAL_CUES = Path(__file__).resolve().parents[3] / "frontend/src/features/coach/interpreter/local-cues.ts"


@pytest.fixture
def pack_env(monkeypatch, tmp_path):
    monkeypatch.setenv("COACH_PACK_ROOT", str(tmp_path / "packs"))
    monkeypatch.setenv("COACH_PACK_VOICE_FEMALE", "synthetic-female")
    monkeypatch.delenv("COACH_PACK_VOICE_MALE", raising=False)
    get_settings.cache_clear()
    yield PackStore(tmp_path / "packs")
    get_settings.cache_clear()


def tone(seconds=0.4, amplitude=0.2, lead=0.0, rate=24_000, channels=1):
    audio = asyncio.run(FakePackVoice(seconds=seconds, amplitude=amplitude).synthesize("x", "v", "i"))
    pcm = b"\0\0" * int(lead * rate) + audio.pcm
    return pcm_to_wav(pcm, rate)


def required_ids():
    return [spec.id for spec in CATALOG.values() if spec.required]


def test_catalog_covers_local_cues_and_speaks_words():
    source = LOCAL_CUES.read_text()
    cue_clips = set(re.findall(r"clip: '([a-z-]+)'", source))
    required = set(required_ids())
    assert cue_clips <= required
    assert {f"count-{n}" for n in range(1, 31)} | {"countdown-1", "countdown-2", "countdown-3"} <= required
    assert CATALOG["count-31"].required is False and CATALOG["count-100"].text == "Сто."
    assert CATALOG["count-1"].text == "Раз." and CATALOG["count-21"].text == "Двадцать один."
    assert all(not re.search(r"\d", spec.text) for spec in CATALOG.values())
    safety = [spec for spec in CATALOG.values() if spec.group == "safety"]
    assert {spec.id for spec in safety} == {"safety-stop", "pain-stop"} and all(spec.needs_approval for spec in safety)
    assert packs.APPROVED_SAFETY_CATALOG is None


def test_fingerprint_is_per_clip_and_voice_specific():
    spec = CATALOG["set-start"]
    base = packs.fingerprint(spec, "voice-a", "model-a")
    assert re.fullmatch(r"[a-f0-9]{64}", base)
    assert packs.fingerprint(spec, "voice-b", "model-a") != base
    assert packs.fingerprint(spec, "voice-a", "model-b") != base
    edited = packs.ClipSpec(spec.id, "Начинаем.", spec.group, spec.required)
    assert packs.fingerprint(edited, "voice-a", "model-a") != base
    # Editing one text leaves other clips untouched.
    assert packs.fingerprint(CATALOG["set-end"], "voice-a", "model-a") == packs.fingerprint(CATALOG["set-end"], "voice-a", "model-a")


def test_verify_wav_accepts_clean_and_rejects_bad_audio():
    check = verify_wav(tone())
    assert check.sample_rate == 24_000 and 390 <= check.duration_ms <= 410 and -20 < check.rms_dbfs < -10
    for data, reason in [
        (tone(amplitude=1.0), "wav_clipping"),
        (tone(amplitude=0.001), "wav_silent"),
        (tone(amplitude=0.01), "wav_loudness"),
        (tone(seconds=0.05), "wav_duration"),
        (tone(lead=0.8), "wav_edge_silence"),
        (b"RIFF" + b"\0" * 60, "wav_format"),
    ]:
        with pytest.raises(PackError, match=reason):
            verify_wav(data)
    with pytest.raises(PackError, match="wav_duration"):
        verify_wav(tone(seconds=2.0), max_seconds=1.5)
    stereo = bytearray(tone())
    stereo[22] = 2  # channel count in the RIFF header
    with pytest.raises(PackError):
        verify_wav(bytes(stereo))
    truncated = tone()[:-100]
    with pytest.raises(PackError, match="wav_length|wav_format"):
        verify_wav(truncated)


def test_plan_dry_run_without_voice_or_prices(pack_env, monkeypatch):
    monkeypatch.setenv("COACH_PACK_VOICE_FEMALE", "")
    get_settings.cache_clear()
    plan = packs.plan(pack_env, "female", "fake-tts")
    assert plan["voiceSelected"] is False and plan["required"]["generated"] == 0
    assert plan["estimate"]["usd"] is None and plan["estimate"]["priced"] is False
    assert len(plan["missing"]) == len(CATALOG) and plan["current"] is None
    with pytest.raises(HTTPException):
        packs.plan(pack_env, "robot", "fake-tts")


async def run_job(factory, items, adapter, store, *, key="pack-1"):
    with factory() as db:
        run_id, generation, _ = make_run(db, cap="5.00")
        job_id = ledger.submit_job(db, run_id, key, "d" * 64, items)
        ledger.job_state(db, job_id, "queued")
    runner = PackJobRunner(factory, adapter, PRICE, store, slot="female", model="fake-tts")
    return run_id, job_id, runner, await runner.run(job_id, "tab-a", generation)


@pytest.mark.asyncio
async def test_generate_required_publish_and_skip_existing(session_factory, pack_env):
    adapter = FakePackVoice()
    plan = packs.plan(pack_env, "female", "fake-tts")
    run_id, job_id, _, manifest = await run_job(session_factory, required_ids(), adapter, pack_env)
    assert manifest["complete"] and set(required_ids()) <= set(manifest["clips"])
    assert len(adapter.calls) == len(required_ids())
    assert manifest["clips"]["pain-stop"]["approved"] is False and manifest["clips"]["set-end"]["approved"] is True
    with session_factory() as db:
        assert db.get(CoachJob, job_id).state == "completed"
        assert db.scalar(select(func.count()).select_from(CoachAttempt).where(CoachAttempt.status == "settled")) == len(required_ids())
    after = packs.plan(pack_env, "female", "fake-tts")
    assert after["required"]["generated"] == after["required"]["total"] and after["planFingerprint"] == plan["planFingerprint"]
    assert after["current"]["packVersion"] == manifest["packVersion"]
    assert pack_env.manifest("female") == manifest
    # Repeat preparation never pays again: verified artifacts are reused.
    again = FakePackVoice()
    _, _, _, repeat = await run_job(session_factory, required_ids(), again, pack_env, key="pack-2")
    assert again.calls == [] and repeat["packVersion"] == manifest["packVersion"]
    default_root = Path(type(get_settings()).model_fields["coach_pack_root"].default).resolve()
    assert Path(get_settings().media_root).resolve() not in [default_root, *default_root.parents]


@pytest.mark.asyncio
async def test_failure_pauses_never_publishes_partial_and_no_blind_regeneration(session_factory, pack_env):
    adapter = FakePackVoice(fail_on={CATALOG["set-end"].text})
    with pytest.raises(PackError, match="provider_failed"):
        await run_job(session_factory, required_ids(), adapter, pack_env)
    assert pack_env.manifest("female") is None
    with session_factory() as db:
        job = db.scalar(select(CoachJob))
        assert job.state == "paused" and job.failures == 1 and "set-end" not in job.completed
        done = list(job.completed)
        assert db.scalar(select(func.count()).select_from(CoachAttempt).where(CoachAttempt.status == "unsettled")) == 1
    assert done and all(packs.PackStore.read_artifact(pack_env, CATALOG[item], packs.fingerprint(CATALOG[item], "synthetic-female", "fake-tts")) for item in done)
    plan = packs.plan(pack_env, "female", "fake-tts")
    assert plan["required"]["generated"] == len(done) and "set-end" in plan["missing"]


@pytest.mark.asyncio
async def test_rejected_audio_is_paid_but_not_stored(session_factory, pack_env):
    with pytest.raises(PackError, match="wav_clipping"):
        await run_job(session_factory, ["set-start"], FakePackVoice(amplitude=1.0), pack_env)
    with session_factory() as db:
        attempt = db.scalar(select(CoachAttempt))
        assert attempt.status == "settled" and attempt.cost_micros > 0
    assert packs.plan(pack_env, "female", "fake-tts")["required"]["generated"] == 0


@pytest.mark.asyncio
async def test_corrupt_artifact_detected_and_paid_adapter_fails_closed(session_factory, pack_env):
    spec = CATALOG["set-start"]
    fp = packs.fingerprint(spec, "synthetic-female", "fake-tts")
    path = pack_env.artifact_path(fp)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a wav")
    assert "set-start" in packs.plan(pack_env, "female", "fake-tts")["corrupt"]

    class Paid(FakePackVoice):
        name = "tts"
        test_only = False

    paid = Paid()
    with pytest.raises(HTTPException, match="synthetic_dispatch_requires_test_ledger|paid_adapter_unavailable"):
        await run_job(session_factory, ["set-start"], paid, pack_env)
    assert paid.calls == [] and path.read_bytes() == b"not a wav"


@pytest.mark.asyncio
async def test_new_voice_publishes_new_version_and_keeps_old(session_factory, pack_env, monkeypatch):
    _, _, _, first = await run_job(session_factory, required_ids(), FakePackVoice(), pack_env)
    monkeypatch.setenv("COACH_PACK_VOICE_FEMALE", "synthetic-female-2")
    get_settings.cache_clear()
    assert packs.plan(pack_env, "female", "fake-tts")["required"]["generated"] == 0
    _, _, _, second = await run_job(session_factory, required_ids(), FakePackVoice(), pack_env, key="pack-2")
    assert second["packVersion"] != first["packVersion"]
    assert pack_env.manifest("female")["packVersion"] == second["packVersion"]
    assert pack_env.manifest("female", first["packVersion"]) == first
    assert pack_env.manifest("male") is None
    assert not list((pack_env.root / "packs" / "female").glob(".tmp-*"))


def test_runner_requires_selected_voice(session_factory, pack_env):
    with pytest.raises(HTTPException, match="voice_not_selected"):
        asyncio.run(PackJobRunner(session_factory, FakePackVoice(), PRICE, pack_env, slot="male", model="fake-tts").run("x", "tab-a", 0))


class ScriptedSpeaker:
    """Stands in for a provider adapter (no network): lead silence + tone, scripted transcript and usage."""

    name = "realtime"
    test_only = False

    def __init__(self, transcript):
        self.capability = VoiceCapability("realtime", "m", ("synthetic-female",), transcript=True)
        self.transcript, self.calls = transcript, []
        self.last_usage = self.last_transcript = None
        self.last_response_id = ""

    async def stream(self, text, scope, generation_id, delivery, *, instructions=None, max_output_tokens=None):
        self.calls.append((text, instructions))
        self.max_output_tokens = max_output_tokens
        pcm = b"\0\0" * 12_000
        pcm += (await FakePackVoice(seconds=0.4).synthesize("x", "v", "i")).pcm + b"\0\0" * 12_000
        framer = PcmFramer(generation_id, generation_id, scope, "realtime")
        for chunk in framer.push(pcm):
            yield chunk
        self.last_usage = ReportedUsage(input_tokens=40, output_tokens=30, audio_input_tokens=160, audio_output_tokens=20,
                                        cached_audio_input_tokens=128, reasoning_tokens=20)
        self.last_transcript, self.last_response_id = self.transcript, "resp-1"
        yield framer.finish()


@pytest.mark.asyncio
async def test_provider_pack_voice_trims_edges_and_gates_on_transcript():
    good = ProviderPackVoice(ScriptedSpeaker("Пять секунд."))
    audio = await good.synthesize("Пять секунд.", "synthetic-female", COUNT_INSTRUCTIONS, max_output_tokens=900)
    assert good.adapter.max_output_tokens == 900
    assert audio.verified and audio.response_id == "resp-1" and good.adapter.calls == [("Пять секунд.", COUNT_INSTRUCTIONS)]
    assert len(audio.pcm) < 2 * 24_000 * 0.7  # 0.5 s lead/tail silence cut to short pads
    check = verify_wav(pcm_to_wav(audio.pcm))
    assert check.duration_ms < 700
    assert ReportedUsage.model_validate(audio.usage).audio_input_tokens == 160
    bad = await ProviderPackVoice(ScriptedSpeaker("Шесть секунд.")).synthesize("Пять секунд.", "synthetic-female", "i")
    assert not bad.verified
    with pytest.raises(PackError, match="voice_mismatch"):
        await good.synthesize("Пять секунд.", "other", "i")
    with pytest.raises(ValueError):
        ProviderPackVoice(FakeVoiceStream())
    bounds = packs.clip_bounds(CATALOG["rest-five"])
    usage = ReportedUsage.model_validate(audio.usage)
    assert all(getattr(usage, f) <= getattr(bounds, f) for f in ("input_tokens", "output_tokens", "audio_input_tokens", "audio_output_tokens"))


@pytest.mark.asyncio
async def test_transcript_mismatch_is_paid_but_not_stored(session_factory, pack_env):
    class Mismatch(FakePackVoice):
        async def synthesize(self, text, voice, instructions, **kw):
            audio = await super().synthesize(text, voice, instructions, **kw)
            return dataclasses.replace(audio, verified=False)

    with pytest.raises(PackError, match="transcript_mismatch"):
        await run_job(session_factory, ["set-start"], Mismatch(), pack_env)
    with session_factory() as db:
        attempt = db.scalar(select(CoachAttempt))
        assert attempt.status == "settled" and attempt.cost_micros > 0
    assert packs.plan(pack_env, "female", "fake-tts")["required"]["generated"] == 0


@pytest.mark.asyncio
async def test_pack_routes_serve_whitelisted_clips(client, session_factory, pack_env):
    client.base_url = "http://localhost"
    assert client.get("/api/coach/packs/female/manifest").status_code == 404
    model = get_settings().coach_voice_tts_model
    with session_factory() as db:
        run_id, generation, _ = make_run(db, cap="5.00")
        job_id = ledger.submit_job(db, run_id, "k", "e" * 64, required_ids())
        ledger.job_state(db, job_id, "queued")
    manifest = await PackJobRunner(session_factory, FakePackVoice(), PRICE, pack_env, slot="female", model=model).run(job_id, "tab-a", generation)
    response = client.get("/api/coach/packs/female/manifest")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["packVersion"] == manifest["packVersion"]
    version = manifest["packVersion"]
    clip = client.get(f"/api/coach/packs/female/{version}/clips/count-1")
    assert clip.status_code == 200 and clip.headers["content-type"] == "audio/wav"
    assert "immutable" in clip.headers["cache-control"] and clip.headers["etag"] == f'"{manifest["clips"]["count-1"]["sha256"]}"'
    assert verify_wav(clip.content).sha256 == manifest["clips"]["count-1"]["sha256"]
    for path in [f"/api/coach/packs/female/{version}/clips/count-99", f"/api/coach/packs/female/{version}/clips/..%2Fcurrent",
                 "/api/coach/packs/female/../clips/count-1", f"/api/coach/packs/robot/{version}/clips/count-1",
                 f"/api/coach/packs/male/{version}/clips/count-1", "/api/coach/packs/female/ABCDEF0123456789/clips/count-1"]:
        assert client.get(path).status_code == 404, path
    plan = client.get("/api/coach/packs/female/plan")
    assert plan.status_code == 200 and plan.json()["required"]["generated"] == plan.json()["required"]["total"]


def test_pack_job_api_validates_plan_and_never_dispatches(client, secured, pack_env, monkeypatch):  # noqa: F811
    auth(client)
    run = client.post("/api/coach/runs", json={"userId": "alexey", "ledger": "pack"}, headers=ORIGIN).json()
    headers = {**ORIGIN, "X-Coach-Run-Token": run["runToken"]}
    plan = client.get("/api/coach/packs/female/plan").json()
    body = {"runId": run["runId"], "idempotencyKey": "pack-1", "planFingerprint": plan["planFingerprint"], "clipIds": ["count-1", "set-start"]}
    job = client.post("/api/coach/packs/female/jobs", json=body, headers=headers)
    assert job.status_code == 200 and job.json()["dispatchAvailable"] is False and job.json()["clips"] == 2
    assert client.post("/api/coach/packs/female/jobs", json=body, headers=headers).json() == job.json()
    stale = client.post("/api/coach/packs/female/jobs", json={**body, "planFingerprint": "f" * 64}, headers=headers)
    assert stale.status_code == 409 and stale.json()["detail"] == "plan_changed"
    unknown = client.post("/api/coach/packs/female/jobs", json={**body, "clipIds": ["count-1", "../etc"]}, headers=headers)
    assert unknown.status_code == 422
    male = client.post("/api/coach/packs/male/jobs", json={**body, "planFingerprint": client.get("/api/coach/packs/male/plan").json()["planFingerprint"]}, headers=headers)
    assert male.status_code == 409 and male.json()["detail"] == "voice_not_selected"
    no_token = client.post("/api/coach/packs/female/jobs", json=body, headers=ORIGIN)
    assert no_token.status_code == 404
    status = client.get(f'/api/coach/runs/{run["runId"]}/jobs/{job.json()["jobId"]}', headers=headers)
    assert status.json()["state"] == "paused" and status.json()["total"] == 2
    assert json.loads(json.dumps(plan))["estimate"]["usd"] is None
