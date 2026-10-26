"""PAID integration (skipped unless COACH_PAID_TESTS=1 and FISH_API_KEY): real Fish drama-3, several emotion tags in
one text → one request → one WAV. Saves audio and a report to backend/coach_packs/pilot/drama3-tags-<time>/.

  COACH_PAID_TESTS=1 FISH_API_KEY=... .venv/Scripts/python -m pytest backend/app/tests/test_coach_fish_tags_live.py -s

≈ 900 billed UTF-8 bytes in total (≈ $0.045 at the $50/1M list price, ≈ $0.009 at the promo price before 12.11.2026).
Listen to the files: tags must change the intonation and must never be pronounced.
"""

import json
import os
import time
import wave
from pathlib import Path

import httpx
import pytest

from app.schemas.coach import CoachScope
from app.services.coach.voice import SAMPLE_RATE, Delivery, FishVoiceAdapter
from app.tests.test_coach_fish_tags import SAMPLE, SHORT

pytestmark = pytest.mark.skipif(not (os.environ.get("COACH_PAID_TESTS") == "1" and os.environ.get("FISH_API_KEY")),
                                reason="paid Fish drama-3 call: set COACH_PAID_TESTS=1 and FISH_API_KEY")
VOICE = os.environ.get("FISH_VOICE_ID", "0a690dbeb3984a9f88cd39353880775f")
OUT = Path(__file__).resolve().parents[2] / "coach_packs" / "pilot" / f"drama3-tags-{time.strftime('%Y%m%d-%H%M%S')}"
SCOPE = CoachScope(user_id="pilot", run_id="drama3-tags")


async def synthesize(text: str) -> tuple[bytes, int, float]:
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        adapter = FishVoiceAdapter(client, os.environ["FISH_API_KEY"], model="drama-3", reference_id=VOICE)
        started, first = time.monotonic(), None
        pcm = bytearray()
        async for chunk in adapter.stream(text, SCOPE, "drama3-tags", Delivery(tagged=True)):
            if chunk.data and first is None:
                first = time.monotonic() - started
            pcm += chunk.data
        return bytes(pcm), adapter.last_usage.input_tokens, round((first or 0) * 1000)


def save(name: str, pcm: bytes) -> float:
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return len(pcm) / 2 / SAMPLE_RATE


async def test_sample_and_short_phrases_with_real_drama3():
    report = {"voice": VOICE, "lines": []}
    pcm, billed, first_ms = await synthesize(SAMPLE)
    seconds = save("sample-six-emotions", pcm)
    report["lines"].append({"name": "sample", "text": SAMPLE, "seconds": round(seconds, 2), "bytes": billed,
                            "firstAudioMs": first_ms})
    assert billed == len(SAMPLE.encode())  # one request, the tagged script byte for byte
    assert 6 <= seconds <= 30, seconds
    for name, text in SHORT.items():
        pcm, billed, first_ms = await synthesize(text)
        seconds = save(f"short-{name}", pcm)
        report["lines"].append({"name": name, "text": text, "seconds": round(seconds, 2), "bytes": billed,
                                "firstAudioMs": first_ms})
        assert 1 <= seconds <= 6, (name, seconds)
    report["totalBytes"] = sum(line["bytes"] for line in report["lines"])
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(report['lines'])} files to {OUT}")
