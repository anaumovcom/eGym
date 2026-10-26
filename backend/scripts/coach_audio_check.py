"""Operator check of generated coach audio: speech-to-text (OpenAI) and loudness per second. Paid (transcription).

  .venv/Scripts/python backend/scripts/coach_audio_check.py backend/coach_packs/pilot/<dir> [--expected report.json]

Reads OPENAI_API_KEY from the environment or backend/.env.local (never printed). Writes audio-check.json next to
the WAVs: transcript, words that look like spoken stage directions, duration, RMS dBFS per second (loud vs whisper).
"""

import argparse
import asyncio
import json
import math
import re
import struct
import sys
import wave
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))
TAG_WORDS = re.compile(r"(?i)\b(excited|calm|shouting|chuckling|whispering|proud|very|break|laughing|sighing|gasping|"
                       r"panting|confident|determined|empathetic|delighted|soft tone|emphasis|forceful|whisper|"
                       r"эксайтед|шаутинг|виспер|чаклинг)\b")


def loudness(path: Path) -> tuple[float, list[float]]:
    with wave.open(str(path)) as wav:
        rate, frames = wav.getframerate(), wav.readframes(wav.getnframes())
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    per_second = []
    for start in range(0, len(samples), rate):
        chunk = samples[start:start + rate]
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) if chunk else 0
        per_second.append(round(20 * math.log10(rms / 32768), 1) if rms > 0 else -99.0)
    return len(samples) / rate, per_second


async def transcribe(client: httpx.AsyncClient, key: str, path: Path) -> str:
    for model in ("gpt-4o-transcribe", "whisper-1"):
        response = await client.post("https://api.openai.com/v1/audio/transcriptions",
                                     headers={"Authorization": f"Bearer {key}"},
                                     data={"model": model, "language": "ru"},
                                     files={"file": (path.name, path.read_bytes(), "audio/wav")})
        if response.status_code == 200:
            return response.json().get("text", "")
    return f"<transcription failed: HTTP {response.status_code}>"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    from coach_pilot import read_api_key

    key = read_api_key("openai")
    folder = Path(args.directory)
    rows = []
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        for path in sorted(folder.glob("*.wav")):
            seconds, levels = loudness(path)
            text = await transcribe(client, key, path)
            rows.append({"file": path.name, "seconds": round(seconds, 2), "transcript": text,
                         "spokenTags": sorted(set(m.lower() for m in TAG_WORDS.findall(text))), "dbfsPerSecond": levels})
            print(f"{path.name:32} {seconds:5.1f}s tags={rows[-1]['spokenTags'] or '-'}  «{text}»")
    (folder / "audio-check.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
