"""E09 voice packs: editorial catalog, dry-run plan, verified artifacts, atomic manifests, resumable capped jobs.

Artifacts are content-addressed by generation fingerprint in a private directory (never the public media mount).
Paid generation is fail-closed in the ledger unless the operator enabled paid voice. No hardware/motor imports.
"""

import array
import asyncio
import contextlib
import io
import json
import math
import os
import re
import sys
import tempfile
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.coach import CoachAttempt, CoachJob
from app.schemas.coach import CoachScope
from app.schemas.coach_control import Pricing, ReportedUsage, UsageBounds
from app.services.coach import ledger
from app.services.coach.facts import number_words
from app.services.coach.voice import (
    AUDIO_INPUT_ALLOWANCE,
    COUNT_INSTRUCTIONS,
    REALTIME_INSTRUCTIONS,
    REASONING_ALLOWANCE,
    SAMPLE_RATE,
    Delivery,
    VoiceAdapter,
    tts_instructions,
    verify_transcript,
)

CATALOG_VERSION = "coach-pack-catalog-0.1"
STYLE_VERSION = "coach-pack-style-0.1"
LOCALE = "ru-RU"
SCHEMA_VERSION = 1
SLOTS = ("female", "male")
Slot = Literal["female", "male"]
Group = Literal["count", "countdown", "lifecycle", "time", "outcome", "rest", "safety"]
REQUIRED_COUNT = 30
MAX_COUNT = 100
MAX_CLIP_SECONDS = 6.0
PEAK_LIMIT = 0.99  # Above this the clip is treated as clipped.
LOUDNESS_DBFS = (-35.0, -10.0)  # RMS window over the non-silent part.
SILENCE_DBFS = -50.0
MAX_EDGE_SILENCE_S = 0.5
PACK_VERSION_RE = re.compile(r"^[a-f0-9]{16}$")
FINGERPRINT_RE = re.compile(r"^[a-f0-9]{64}$")


class PackError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ClipSpec:
    id: str
    text: str
    group: Group
    required: bool
    max_seconds: float = 3.0
    # Safety texts are released only after a human listened (approval of the catalog version).
    needs_approval: bool = False


def _catalog() -> dict[str, ClipSpec]:
    clips = [ClipSpec(f"count-{n}", "Раз." if n == 1 else f"{number_words(n).capitalize()}.", "count", n <= REQUIRED_COUNT,
                      max_seconds=1.5 if n <= 20 else 2.5) for n in range(1, MAX_COUNT + 1)]
    clips += [ClipSpec(f"countdown-{n}", f"{number_words(n).capitalize()}.", "countdown", True, max_seconds=1.2) for n in (1, 2, 3)]
    rows: list[tuple[str, str, Group]] = [
        ("set-start", "Начинаем подход.", "lifecycle"),
        ("hold-start", "Держим позицию.", "lifecycle"),
        ("set-pause", "Пауза.", "lifecycle"),
        ("set-resume", "Продолжаем.", "lifecycle"),
        ("rep-half", "Половина позади.", "time"),
        ("rep-three-left", "Ещё три.", "time"),
        ("rep-target", "Есть цель.", "time"),
        ("time-half", "Половина времени.", "time"),
        ("time-ten-left", "Десять секунд.", "time"),
        ("set-end", "Подход завершён.", "outcome"),
        ("set-partial", "Подход засчитан частично.", "outcome"),
        ("set-skipped", "Подход пропущен.", "outcome"),
        ("last-set-next", "Остался последний подход.", "outcome"),
        ("rest-ten", "Через десять секунд продолжаем.", "rest"),
        ("rest-five", "Пять секунд.", "rest"),
        ("rest-ready", "Готовимся к подходу.", "rest"),
        ("exercise-done", "Упражнение выполнено.", "outcome"),
        ("exercise-partial", "Упражнение выполнено частично.", "outcome"),
        ("exercise-skipped", "Упражнение пропущено.", "outcome"),
        ("workout-done", "Тренировка завершена. Хорошая работа.", "outcome"),
        ("workout-partial", "Тренировка завершена частично.", "outcome"),
    ]
    clips += [ClipSpec(clip_id, text, group, True, max_seconds=3.5) for clip_id, text, group in rows]
    clips += [
        ClipSpec("safety-stop", "Стоп. Остановись.", "safety", True, max_seconds=3.0, needs_approval=True),
        ClipSpec("pain-stop", "Остановись. Если больно — не продолжай.", "safety", True, max_seconds=4.0, needs_approval=True),
    ]
    return {clip.id: clip for clip in clips}


CATALOG: dict[str, ClipSpec] = _catalog()
# Set to CATALOG_VERSION only after the user listened to the safety clips of the chosen voice.
APPROVED_SAFETY_CATALOG: str | None = None


def provider_voice(slot: str) -> str:
    if slot not in SLOTS:
        raise HTTPException(404, "pack_not_found")
    cfg = get_settings()
    return (cfg.coach_pack_voice_female if slot == "female" else cfg.coach_pack_voice_male).strip()


def clip_instructions(spec: ClipSpec) -> str:
    if spec.group in {"count", "countdown"}:
        return COUNT_INSTRUCTIONS
    return tts_instructions(Delivery("calm" if spec.group == "safety" else "warm", "normal", "none"))


def fingerprint(spec: ClipSpec, voice: str, model: str) -> str:
    """Only what changes the audio: a text edit invalidates exactly that clip, not the whole pack."""
    payload = {"clip": spec.id, "text": spec.text, "locale": LOCALE, "style": STYLE_VERSION, "voice": voice, "model": model,
               "instructions": sha256(clip_instructions(spec).encode()).hexdigest(),
               "format": {"codec": "wav_s16le", "sampleRate": SAMPLE_RATE, "channels": 1}}
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


# ---------- WAV artifacts ----------

def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    if len(pcm) % 2:
        raise PackError("pcm_length")
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm)
    return out.getvalue()


def _dbfs(value: float) -> float:
    return 20 * math.log10(value) if value > 0 else -math.inf


@dataclass(frozen=True, slots=True)
class WavCheck:
    sha256: str
    bytes: int
    duration_ms: float
    sample_rate: int
    peak_dbfs: float
    rms_dbfs: float


def verify_wav(data: bytes, max_seconds: float = MAX_CLIP_SECONDS) -> WavCheck:
    """Duration comes from decoded samples, not header claims (streaming sentinel headers are rejected)."""
    if not 44 <= len(data) <= 44 + 2 * 48_000 * MAX_CLIP_SECONDS + 1024:
        raise PackError("wav_size")
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            channels, width, rate, comp = reader.getnchannels(), reader.getsampwidth(), reader.getframerate(), reader.getcomptype()
            declared = reader.getnframes()
            frames = reader.readframes(declared)
    except (wave.Error, EOFError) as error:
        raise PackError("wav_format") from error
    if channels != 1 or width != 2 or comp != "NONE" or not 8000 <= rate <= 48_000:
        raise PackError("wav_format")
    if len(frames) != declared * 2 or declared == 0:
        raise PackError("wav_length")
    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    duration = len(samples) / rate
    if not 0.1 <= duration <= max_seconds:
        raise PackError("wav_duration")
    threshold = 32768 * 10 ** (SILENCE_DBFS / 20)
    loud = [index for index, value in enumerate(samples) if abs(value) > threshold]
    if not loud:
        raise PackError("wav_silent")
    if loud[0] / rate > MAX_EDGE_SILENCE_S or (len(samples) - 1 - loud[-1]) / rate > MAX_EDGE_SILENCE_S:
        raise PackError("wav_edge_silence")
    peak = max(abs(value) for value in samples) / 32768
    if peak >= PEAK_LIMIT:
        raise PackError("wav_clipping")
    body = samples[loud[0]:loud[-1] + 1]
    rms = math.sqrt(sum(value * value for value in body) / len(body)) / 32768
    if not LOUDNESS_DBFS[0] <= _dbfs(rms) <= LOUDNESS_DBFS[1]:
        raise PackError("wav_loudness")
    return WavCheck(sha256(data).hexdigest(), len(data), round(duration * 1000, 3), rate, round(_dbfs(peak), 2), round(_dbfs(rms), 2))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)
        raise


class PackStore:
    """<root>/artifacts/<fingerprint>.wav, <root>/packs/<slot>/<packVersion>.json, <root>/packs/<slot>/current.json."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def artifact_path(self, fp: str) -> Path:
        if not FINGERPRINT_RE.match(fp):
            raise PackError("fingerprint")
        return self.root / "artifacts" / f"{fp}.wav"

    def read_artifact(self, spec: ClipSpec, fp: str) -> WavCheck | None:
        path = self.artifact_path(fp)
        if not path.is_file():
            return None
        return verify_wav(path.read_bytes(), spec.max_seconds)

    def save_artifact(self, spec: ClipSpec, fp: str, data: bytes) -> WavCheck:
        check = verify_wav(data, spec.max_seconds)  # Verify before publish; a bad file never becomes an artifact.
        _atomic_write(self.artifact_path(fp), data)
        return check

    def manifest(self, slot: str, version: str | None = None) -> dict | None:
        if slot not in SLOTS:
            raise HTTPException(404, "pack_not_found")
        base = self.root / "packs" / slot
        if version is None:
            pointer = base / "current.json"
            if not pointer.is_file():
                return None
            version = json.loads(pointer.read_text())["packVersion"]
        if not PACK_VERSION_RE.match(str(version)):
            return None
        path = base / f"{version}.json"
        return json.loads(path.read_text()) if path.is_file() else None

    def publish(self, slot: str, voice: str, model: str) -> dict | None:
        """Publishes only a complete, verified pack; a partial result never replaces the current pointer."""
        clips = {}
        for spec in CATALOG.values():
            fp = fingerprint(spec, voice, model)
            try:
                check = self.read_artifact(spec, fp)
            except PackError:
                check = None
            if check is None:
                if spec.required:
                    return None
                continue
            clips[spec.id] = {"fingerprint": fp, "sha256": check.sha256, "bytes": check.bytes, "durationMs": check.duration_ms,
                              "sampleRate": check.sample_rate, "peakDbfs": check.peak_dbfs, "rmsDbfs": check.rms_dbfs,
                              "required": spec.required, "group": spec.group,
                              "approved": not spec.needs_approval or APPROVED_SAFETY_CATALOG == CATALOG_VERSION}
        version = sha256(json.dumps(clips, sort_keys=True).encode()).hexdigest()[:16]
        manifest = {"schemaVersion": SCHEMA_VERSION, "slot": slot, "packVersion": version, "complete": True,
                    "catalogVersion": CATALOG_VERSION, "styleVersion": STYLE_VERSION, "locale": LOCALE, "model": model,
                    "voice": voice, "createdAt": time.time(), "clips": clips}
        base = self.root / "packs" / slot
        if not (base / f"{version}.json").is_file():
            _atomic_write(base / f"{version}.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode())
        else:
            manifest = json.loads((base / f"{version}.json").read_text())
        # Older manifests stay on disk: a pinned run keeps its compatible pack until the next run.
        _atomic_write(base / "current.json", json.dumps({"packVersion": version}).encode())
        return manifest


# ---------- Dry-run plan ----------

def plan(store: PackStore, slot: str, model: str) -> dict:
    voice = provider_voice(slot)
    rows, missing, corrupt = [], [], []
    ready_required = ready_optional = ready_bytes = chars = 0
    for spec in CATALOG.values():
        fp = fingerprint(spec, voice, model) if voice else None
        status = "unselected"
        if fp:
            try:
                check = store.read_artifact(spec, fp)
                status = "ready" if check else "missing"
                ready_bytes += check.bytes if check else 0
            except PackError:
                status = "corrupt"
        if status == "ready":
            ready_required += spec.required
            ready_optional += not spec.required
        elif status in {"missing", "corrupt", "unselected"}:
            (corrupt if status == "corrupt" else missing).append(spec.id)
            chars += len(spec.text)
        rows.append({"clipId": spec.id, "required": spec.required, "group": spec.group, "status": status, "fingerprint": fp})
    required_total = sum(spec.required for spec in CATALOG.values())
    current = store.manifest(slot)
    plan_fp = sha256(json.dumps([[row["clipId"], row["fingerprint"]] for row in rows]).encode()).hexdigest()
    return {"schemaVersion": SCHEMA_VERSION, "slot": slot, "voiceSelected": bool(voice), "model": model,
            "catalogVersion": CATALOG_VERSION, "planFingerprint": plan_fp,
            "required": {"total": required_total, "generated": ready_required},
            "optional": {"total": len(CATALOG) - required_total, "generated": ready_optional},
            "missing": missing, "corrupt": corrupt, "generatedBytes": ready_bytes,
            # Pricing is unverified until E08.1: no fake estimate in dollars.
            "estimate": {"clips": len(missing) + len(corrupt), "characters": chars, "usd": None, "priced": False},
            "safetyApproved": APPROVED_SAFETY_CATALOG == CATALOG_VERSION,
            "current": {"packVersion": current["packVersion"], "complete": current["complete"]} if current else None,
            "clips": rows}


# ---------- Resumable capped generation ----------

@dataclass(frozen=True, slots=True)
class PackAudio:
    pcm: bytes
    sample_rate: int
    usage: dict
    response_id: str
    # False when a generative speaker's transcript does not match the clip text: paid, but never saved.
    verified: bool = True


class PackVoice(Protocol):
    name: str
    test_only: bool

    async def synthesize(self, text: str, voice: str, instructions: str) -> PackAudio: ...


def trim_edges(pcm: bytes, sample_rate: int = SAMPLE_RATE, keep_s: float = 0.08) -> bytes:
    """Cuts provider lead-in/tail silence to a short pad so pack clips start on the word."""
    samples = array.array("h")
    samples.frombytes(pcm[:len(pcm) - len(pcm) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    threshold = 32768 * 10 ** (SILENCE_DBFS / 20)
    loud = [index for index, value in enumerate(samples) if abs(value) > threshold]
    if not loud:
        return pcm
    pad = int(keep_s * sample_rate)
    body = samples[max(0, loud[0] - pad):min(len(samples), loud[-1] + 1 + pad)]
    if sys.byteorder == "big":
        body.byteswap()
    return body.tobytes()


class ProviderPackVoice:
    """Wraps a real streaming adapter (TTS or Realtime) for one-off clip synthesis.

    Realtime is a generative speaker: its transcript must match the clip text before the artifact is saved.
    """

    test_only = False

    def __init__(self, adapter: VoiceAdapter):
        if adapter.test_only or adapter.name not in {"tts", "realtime"}:
            raise ValueError("Provider adapter required")
        self.adapter, self.name = adapter, adapter.name
        self.last_transcript: str | None = None

    async def synthesize(self, text: str, voice: str, instructions: str) -> PackAudio:
        if voice not in self.adapter.capability.voices:
            raise PackError("voice_mismatch")
        scope = CoachScope(user_id="pack", run_id="pack")
        parts = [chunk.data async for chunk in self.adapter.stream(text, scope, f"pack-{time.time_ns()}", Delivery(),
                                                                   instructions=instructions)]
        usage = self.adapter.last_usage
        if not isinstance(usage, ReportedUsage):
            raise PackError("usage_unavailable")
        verified = True
        if self.adapter.capability.transcript:
            self.last_transcript = self.adapter.last_transcript
            verified = verify_transcript(text, self.adapter.last_transcript).status == "match"
        return PackAudio(trim_edges(b"".join(parts)), SAMPLE_RATE, usage.model_dump(by_alias=True),
                         self.adapter.last_response_id, verified)


def clip_bounds(spec: ClipSpec) -> UsageBounds:
    size = len(spec.text.encode()) + len(clip_instructions(spec).encode()) + len(REALTIME_INSTRUCTIONS.encode()) + 256
    return UsageBounds(input_tokens=2 * size + 64, output_tokens=2 * len(spec.text.encode()) + REASONING_ALLOWANCE,
                       audio_input_tokens=AUDIO_INPUT_ALLOWANCE, audio_output_tokens=50 * math.ceil(spec.max_seconds) + 50)


class PackJobRunner:
    """One voice request at a time; DB transactions never span provider awaits.

    Order per clip: verified artifact on disk → skip without paying (crash recovery, repeated prepare);
    otherwise reserve → dispatch → synthesize → verify+atomic write → settle → progress receipt.
    """

    def __init__(self, sessions: Callable[[], Session], adapter: PackVoice, pricing: Pricing, store: PackStore,
                 *, slot: str, model: str, timeout_s: float = 30):
        if not 0 < timeout_s <= 60:
            raise ValueError("Invalid bounded timeout")
        self.sessions, self.adapter, self.pricing, self.store = sessions, adapter, pricing, store
        self.slot, self.model, self.timeout_s = slot, model, timeout_s
        self.voice = provider_voice(slot)
        self.tasks: dict[str, asyncio.Task] = {}

    async def cancel(self, job_id: str) -> None:
        with self.sessions() as db:
            ledger.job_state(db, job_id, "cancelled")
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _complete(self, job_id: str, item: str) -> bool:
        with self.sessions() as db:
            job = db.get(CoachJob, job_id, populate_existing=True)
            if job.state != "queued":
                return False
            job.completed = [*job.completed, item]
            db.commit()
            return True

    async def run(self, job_id: str, owner: str, generation: int) -> dict | None:
        if not self.voice:
            raise HTTPException(409, "voice_not_selected")
        if job_id in self.tasks:
            raise HTTPException(409, "pipeline_busy")
        self.tasks[job_id] = asyncio.current_task()
        attempt_id = None
        try:
            with self.sessions() as db:
                job = db.get(CoachJob, job_id)
                if not job or job.state != "queued":
                    return None
                if job.failures >= 3:
                    raise HTTPException(409, "provider_circuit")
                items, done, run_id = job.items[:], set(job.completed), job.run_id
            for item in items:
                spec = CATALOG.get(item)
                if spec is None:
                    raise PackError("unknown_clip")
                if item in done:
                    continue
                fp = fingerprint(spec, self.voice, self.model)
                try:
                    existing = self.store.read_artifact(spec, fp)
                except PackError:
                    existing = None  # Corrupt artifact: an explicit item in a paid job may replace it.
                if existing is None:
                    with self.sessions() as db:
                        if db.get(CoachJob, job_id, populate_existing=True).state != "queued":
                            return None
                        # Long jobs outlive one 15 s lease: renew per clip; a lost lease pauses instead of paying.
                        if ledger.lease(db, run_id, owner, generation)["generation"] != generation:
                            raise PackError("lease_lost")
                        attempt_id = ledger.reserve(db, run_id, owner, generation, f"pack:{fp}", "voice", self.pricing, clip_bounds(spec))
                        ledger.dispatch(db, attempt_id, owner, test_only=self.adapter.test_only, adapter=f"pack-{self.adapter.name}")
                    audio = await asyncio.wait_for(self.adapter.synthesize(spec.text, self.voice, clip_instructions(spec)), self.timeout_s)
                    usage = ReportedUsage.model_validate(audio.usage)
                    try:
                        if not audio.verified:
                            raise PackError("transcript_mismatch")
                        self.store.save_artifact(spec, fp, pcm_to_wav(audio.pcm, audio.sample_rate))
                    finally:
                        # Paid even when verification rejects the audio; the cost is always recorded.
                        with self.sessions() as db:
                            ledger.settle(db, attempt_id, audio.response_id, usage, terminal=True)
                        settled_id, attempt_id = attempt_id, None
                    with self.sessions() as db:
                        if db.get(CoachAttempt, settled_id).status != "settled" or ledger.get_run(db, run_id).generation != generation:
                            return None
                if not self._complete(job_id, item):
                    return None
            with self.sessions() as db:
                job = db.get(CoachJob, job_id, populate_existing=True)
                if job.state != "queued":
                    return None
                job.state = "completed"
                db.commit()
            return self.store.publish(self.slot, self.voice, self.model)
        except (Exception, asyncio.CancelledError):
            if attempt_id:
                with self.sessions() as db:
                    ledger.mark_unsettled(db, attempt_id)
            with self.sessions() as db:
                job = db.get(CoachJob, job_id, populate_existing=True)
                if job:
                    job.failures += 1
                    if job.state == "queued":
                        job.state = "failed" if job.failures >= 3 else "paused"
                    db.commit()
            raise
        finally:
            self.tasks.pop(job_id, None)


class FakePackVoice:
    """Test-only synthetic voice: a tone of the clip's length. Never a provider."""

    name = "fake"
    test_only = True

    def __init__(self, *, seconds: float = 0.4, amplitude: float = 0.2, fail_on: set[str] | None = None):
        self.seconds, self.amplitude, self.fail_on = seconds, amplitude, fail_on or set()
        self.calls: list[str] = []

    async def synthesize(self, text: str, voice: str, instructions: str) -> PackAudio:
        self.calls.append(text)
        if text in self.fail_on:
            raise PackError("provider_failed")
        count = int(self.seconds * SAMPLE_RATE)
        samples = array.array("h", (int(32767 * self.amplitude * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)) for i in range(count)))
        if sys.byteorder == "big":
            samples.byteswap()
        usage = {"inputTokens": len(text), "outputTokens": 0, "audioInputTokens": 0, "audioOutputTokens": 20}
        return PackAudio(samples.tobytes(), SAMPLE_RATE, usage, f"fake-{len(self.calls)}")
