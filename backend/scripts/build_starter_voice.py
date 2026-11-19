"""Build the shipped offline voice asset from the editorial catalogue. No database, credentials or provider."""

import json
import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.coach import packs
from app.services.coach import starter_voice as voice
from app.services.coach.workout_guidance import browser_index


def build(bundle: Path) -> tuple[str, int]:
    bundle.parent.mkdir(parents=True, exist_ok=True)
    temp = bundle.with_suffix(".tmp")
    clips = {}
    synthesized = 0
    try:
        with ExitStack() as stack:
            old = stack.enter_context(ZipFile(bundle)) if bundle.is_file() else None
            prior = json.loads(old.read("manifest.json")) if old else {}
            archive = stack.enter_context(ZipFile(temp, "w", compression=ZIP_DEFLATED))
            if old:
                for name in old.namelist():
                    if name != "manifest.json":
                        archive.writestr(name, old.read(name))
            for spec in packs.CATALOG.values():
                fp = packs.fingerprint(spec, voice.VOICE, voice.MODEL)
                name = f"{fp}.wav"
                if old and name in old.NameToInfo:
                    data = old.read(name)
                    entry = prior["clips"].get(spec.id, {})
                    if entry.get("fingerprint") == fp and sha256(data).hexdigest() != entry["sha256"]:
                        raise ValueError(f"Invalid shipped recording: {spec.id}")
                else:
                    pcm, rate = voice.synthesize(spec.text)
                    data = packs.pcm_to_wav(packs.trim_edges(pcm, rate), rate)
                    archive.writestr(name, data)
                    synthesized += 1
                clips[spec.id] = packs.PackStore.entry(spec, fp, packs.verify_wav(data))
            version = sha256(json.dumps(clips, sort_keys=True).encode()).hexdigest()[:16]
            if old and prior["packVersion"] != version:
                name = voice.history_member(prior["packVersion"])
                if name not in old.NameToInfo:
                    archive.writestr(name, old.read("manifest.json"))
            archive.writestr("manifest.json", json.dumps({"schemaVersion": 1, "catalogVersion": packs.CATALOG_VERSION,
                "styleVersion": packs.STYLE_VERSION, "slot": voice.SLOT, "voice": voice.VOICE, "model": voice.MODEL,
                "locale": packs.LOCALE, "complete": True, "packVersion": version, "clips": clips}, ensure_ascii=False))
        if prior.get("packVersion") != version or prior.get("catalogVersion") != packs.CATALOG_VERSION:
            temp.replace(bundle)
        return version, synthesized
    finally:
        temp.unlink(missing_ok=True)


def main() -> None:
    version, synthesized = build(voice.BUNDLE)
    index = Path(__file__).resolve().parents[2] / "frontend/src/features/coach/interpreter/workout-guidance.generated.json"
    data = (json.dumps(browser_index(), ensure_ascii=False, indent=2) + "\n").encode()
    if not index.is_file() or index.read_bytes() != data:
        index.write_bytes(data)
    print(f"Published {len(packs.CATALOG)} Russian recordings ({synthesized} new), version {version}, {voice.BUNDLE.stat().st_size} bytes")


if __name__ == "__main__":
    main()