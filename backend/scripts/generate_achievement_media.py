"""Generate achievement images and Fish Drama 3 voice, publishing every file immediately.

Examples (paid, explicit):
  python scripts/generate_achievement_media.py --kind image --quality low --limit 6 --confirm-paid
  python scripts/generate_achievement_media.py --kind audio --limit 12 --confirm-paid
  python scripts/generate_achievement_media.py --kind image --quality medium --confirm-paid

No GET or workout path calls this script. Sequential by default; up to five requests on explicit opt-in.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from app.services.achievements.content import load_catalog, validate_catalog
from app.services.achievements.generation import (
    BudgetLedger,
    durable_bytes,
    durable_json,
    fish_rate_per_byte,
    micros,
    read_credential,
    token_cost,
)
from app.services.achievements.media import (
    AUDIO_ROOT,
    IMAGE_ROOT,
    checksum,
    finalize_streaming_wav,
    load_manifest,
    manifest_summary,
    mark_missing,
    media_stem,
    save_asset,
)
from app.services.achievements.visual_style import STYLE_VERSION, image_prompt
from app.services.coach.packs import PackError, verify_wav
from app.services.coach.personas import persona

IMAGE_MODEL = "gpt-image-2.5-flare"
IMAGE_URL = "https://api.openai.com/v1/images/generations"
IMAGE_EDIT_URL = "https://api.openai.com/v1/images/edits"
FISH_URL = "https://api.fish.audio/v1/tts"
ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATHS = [ROOT / "example-icons" / "icons" / name for name in (
    "icon-r2-c1.png", "icon-r3-c4.png", "icon-r4-c7.png",
)]


def tiers() -> list[dict[str, Any]]:
    return [dict(tier, lineId=line["id"], unit=line["unit"], description=line["description"])
            for line in load_catalog()["lines"] for tier in line["tiers"] if tier["contentOrigin"] == "gpt-6.1-sol"]


def audio_attempt_key(tier_id: str, voice: str, variant: str = "") -> str:
    key = f"audio:drama-3:{voice}:achievements-v2:{tier_id}"
    return f"{key}:{variant}" if variant else key


def valid_image(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def valid_audio(path: Path) -> bool:
    try:
        check = verify_wav(path.read_bytes())
        return 250 <= check.duration_ms <= 30_000 and check.rms_dbfs >= -35 and check.peak_dbfs < 0.99
    except (PackError, OSError):
        return False


def current_audio(asset: dict[str, Any]) -> bool:
    """Manifest presence alone is not evidence that a paid WAV is usable."""
    name = asset.get('audio', {}).get('file')
    if not name or Path(name).name != name:
        return False
    path = AUDIO_ROOT / name
    return valid_audio(path) and asset.get('audioMetadata', {}).get('sha256') == checksum(path)


def current_image(tier_id: str, asset: dict[str, Any]) -> bool:
    metadata = asset.get("imageMetadata", {})
    name = asset.get("image", {}).get("512")
    if not name or Path(name).name != name or metadata.get("styleVersion") != STYLE_VERSION:
        return False
    path = IMAGE_ROOT / name
    if not valid_image(path) or metadata.get("sha256") != checksum(path):
        return False
    with Image.open(path) as image:
        return image.size == (512, 512)


def write_progress(args: argparse.Namespace, status: str, processed: int, queued: int,
                   ledger: BudgetLedger, **extra: Any) -> None:
    report = {"kind": args.kind, "styleVersion": STYLE_VERSION, "status": status,
              "processed": processed, "queued": queued, "concurrency": args.concurrency,
              "updatedAt": time.time(), "budget": ledger.summary(), **extra}
    path = ledger.path.parent / "v2" / f"progress-{args.kind}-{STYLE_VERSION}.json"
    durable_json(path, report)


def save_image_variants(tier_id: str, data: bytes) -> dict[str, str]:
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGB").resize((512, 512), Image.Resampling.LANCZOS)
        name = f"{media_stem(tier_id)}-{STYLE_VERSION}-512.webp"
        path = IMAGE_ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=90, method=6)
        durable_bytes(path, output.getvalue())
        if not valid_image(path):
            raise RuntimeError(f"invalid_image:{tier_id}")
        return {"512": name}


async def generate_image(client: httpx.AsyncClient, ledger: BudgetLedger, tier: dict[str, Any], key: str,
                         quality: str, use_reference: bool = False, force: bool = False,
                         preview: bool = False) -> None:
    tier_id = tier["id"]
    expected = {"512": f"{media_stem(tier_id)}-512.webp"}
    if not force and not preview and current_image(tier_id, load_manifest().get("assets", {}).get(tier_id, {})):
        return
    reference_data = []
    if use_reference:
        # Fail before recording a sent liability if a reference is missing or corrupt.
        for path in REFERENCE_PATHS:
            if not valid_image(path):
                raise RuntimeError(f"reference_missing_or_invalid:{path.name}")
            reference_data.append((path.name, path.read_bytes()))
    mode = "preview" if preview else "publish"
    attempt_key = f"image:{quality}:{STYLE_VERSION}:{'reference' if use_reference else 'text'}:{mode}:{tier_id}"
    reserve = micros(0.25 if quality == "low" else 0.75)
    existing = ledger.find(attempt_key)
    review_root = IMAGE_ROOT.parent / "style-previews" / STYLE_VERSION
    review_path = review_root / expected["512"]
    receipt_path = review_path.with_suffix(".json")
    if existing and existing["status"] in {"sent", "unsettled", "settled"}:
        # A paid success may have been saved just before a crash/accounting failure.
        # Restore its exact bytes, never make an automatic duplicate paid request.
        if valid_image(review_path) and receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("attemptKey") == attempt_key and receipt.get("sha256") == checksum(review_path):
                usage = receipt["usage"]
                if existing["status"] != "settled":
                    ledger.settle(attempt_key, token_cost(IMAGE_MODEL, usage), usage=usage)
                if not preview:
                    files = save_image_variants(tier_id, review_path.read_bytes())
                    metadata = {**receipt, "sha256": checksum(IMAGE_ROOT / files["512"])}
                    save_asset(tier_id, "image", files, **metadata, updatedAt=time.time(), recovered=True)
                print(json.dumps({"imageRecovered": tier_id, "preview": preview}), flush=True)
                return
        raise RuntimeError(f"previous_image_outcome_needs_review:{tier_id}")
    if ledger.reserve(attempt_key, "openai", "image", IMAGE_MODEL, reserve) is None:
        return
    try:
        prompt = image_prompt(tier)
        ledger.sent(attempt_key)
        if use_reference:
            fields = [("model", (None, IMAGE_MODEL)), ("prompt", (None, prompt)), ("size", (None, "1024x1024")),
                      ("quality", (None, quality)), ("output_format", (None, "png")), ("n", (None, "1"))]
            for name, reference_bytes in reference_data:
                fields.append(("image[]", (name, reference_bytes, "image/png")))
            response = await client.post(IMAGE_EDIT_URL, files=fields, headers={"Authorization": f"Bearer {key}"})
        else:
            body = {"model": IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "quality": quality,
                    "output_format": "png", "n": 1}
            response = await client.post(IMAGE_URL, json=body, headers={"Authorization": f"Bearer {key}"})
        if response.status_code != 200:
            raise RuntimeError(f"image_http_{response.status_code}")
        payload = response.json()
        raw = payload.get("data") or []
        if not raw or not raw[0].get("b64_json"):
            raise RuntimeError("image_empty")
        data = base64.b64decode(raw[0]["b64_json"], validate=True)
        usage = payload.get("usage") or {}
        # Keep a 512px review copy before accounting/publication: never lose paid image bytes.
        review_root.mkdir(parents=True, exist_ok=True)
        review_temp = io.BytesIO()
        with Image.open(io.BytesIO(data)) as source:
            source.convert("RGB").resize((512, 512), Image.Resampling.LANCZOS).save(
                review_temp, format="WEBP", quality=90, method=6)
        durable_bytes(review_path, review_temp.getvalue())
        receipt = {
            "tierId": tier_id, "model": IMAGE_MODEL, "styleVersion": STYLE_VERSION,
            "quality": quality, "prompt": prompt, "references": [name for name, _ in reference_data],
            "usage": usage, "approved": False, "attemptKey": attempt_key,
            "sha256": checksum(review_path), "styleReference": use_reference,
        }
        durable_json(receipt_path, receipt)
        if not usage.get("output_tokens") or "input_tokens" not in usage:
            raise RuntimeError("image_usage_missing_review_saved")
        ledger.settle(attempt_key, token_cost(IMAGE_MODEL, usage), request_id=str(payload.get("id", "")), usage=usage)
        if preview:
            print(json.dumps({"imagePreview": tier_id, "path": str(review_path), "published": False}), flush=True)
            return
        files = save_image_variants(tier_id, data)
        save_asset(tier_id, "image", files, updatedAt=time.time(), model=IMAGE_MODEL, quality=quality,
                   styleReference=use_reference, styleVersion=STYLE_VERSION,
                   sha256=checksum(IMAGE_ROOT / files["512"]), usage=usage)
        print(json.dumps({"imageReady": tier_id, "quality": quality, "path": str(IMAGE_ROOT / files["512"])},
                         ensure_ascii=False), flush=True)
    except Exception:
        ledger.unsettled(attempt_key)
        raise


async def generate_audio(client: httpx.AsyncClient, ledger: BudgetLedger, tier: dict[str, Any], key: str,
                         voice: str, variant: str = "", speed: float = 1.0) -> None:
    tier_id = tier["id"]
    name = f"{media_stem(tier_id)}.wav"
    path = AUDIO_ROOT / name
    markup = tier["fishMarkup"]
    byte_count = len(markup.encode("utf-8"))
    cost = int(byte_count * fish_rate_per_byte() * 1_000_000 + 0.999999)
    attempt_key = audio_attempt_key(tier_id, voice, variant)
    receipt_suffix = f".{variant}" if variant else ""
    receipt_path = AUDIO_ROOT / "receipts" / f"{media_stem(tier_id)}{receipt_suffix}.json"
    existing = ledger.find(attempt_key)
    if valid_audio(path):
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("attemptKey") != attempt_key or receipt.get("sha256") != checksum(path):
                raise RuntimeError(f"audio_receipt_mismatch:{tier_id}")
            if existing and existing['status'] != 'settled':
                ledger.settle(attempt_key, receipt['costMicros'], request_id=receipt.get('requestId', ''),
                              usage={'utf8Bytes': receipt['utf8Bytes']})
        elif existing and existing['status'] in {'sent', 'unsettled'}:
            # Old saved WAV proves a completed dispatch; original reservation is the
            # bound for its original bytes/rate, not today's possibly edited phrase.
            ledger.settle(attempt_key, existing['reserveMicros'], usage={'recoveredLegacyWav': True})
        asset = load_manifest().get('assets', {}).get(tier_id, {})
        if not current_audio(asset):
            check = verify_wav(path.read_bytes())
            save_asset(tier_id, "audio", {"file": name}, updatedAt=time.time(), cached=True,
                       sha256=checksum(path), durationMs=check.duration_ms, model='drama-3', voice=voice)
        return
    if ledger.reserve(attempt_key, "fish", "audio", "drama-3", max(cost, 1)) is None:
        if valid_audio(path):
            save_asset(tier_id, "audio", {"file": name}, updatedAt=time.time(), cached=True)
        return
    try:
        body = {"text": markup, "format": "wav", "sample_rate": 24_000, "latency": "balanced",
                "language": "ru", "reference_id": voice,
                "prosody": {"speed": speed, "volume": 0, "normalize_loudness": True}}
        ledger.sent(attempt_key)
        response = await client.post(FISH_URL, json=body, headers={"Authorization": f"Bearer {key}", "model": "drama-3"})
        if response.status_code != 200:
            raise RuntimeError(f"fish_http_{response.status_code}")
        # Preserve provider bytes BEFORE acoustic checks or settlement, including rejects.
        raw_path = AUDIO_ROOT / "receipts" / f"{media_stem(tier_id)}.provider.wav"
        durable_bytes(raw_path, response.content)
        receipt = {'attemptKey': attempt_key, 'costMicros': max(cost, 1), 'utf8Bytes': byte_count,
               'requestId': response.headers.get('x-request-id', ''), 'voice': voice, 'model': 'drama-3',
               'speed': speed}
        durable_json(receipt_path, receipt)
        data = finalize_streaming_wav(response.content)
        check = verify_wav(data)
        if not 250 <= check.duration_ms <= 30_000 or check.rms_dbfs < -35 or check.peak_dbfs >= 0.99:
            raise RuntimeError(f"audio_acoustic_reject:{tier_id}")
        path.parent.mkdir(parents=True, exist_ok=True)
        durable_bytes(path, data)
        durable_json(receipt_path, {**receipt, 'sha256': checksum(path)})
        ledger.settle(attempt_key, max(cost, 1), request_id=response.headers.get("x-request-id", ""),
                  usage={"utf8Bytes": byte_count})
        save_asset(tier_id, "audio", {"file": name}, updatedAt=time.time(), model="drama-3", voice=voice,
                   sha256=checksum(path), durationMs=check.duration_ms, sampleRate=check.sample_rate,
                   rmsDbfs=check.rms_dbfs, peakDbfs=check.peak_dbfs)
        print(json.dumps({"audioReady": tier_id, "path": str(path), "durationMs": check.duration_ms},
                         ensure_ascii=False), flush=True)
    except Exception:
        ledger.unsettled(attempt_key)
        raise


async def run(args: argparse.Namespace) -> None:
    if args.preview and (args.kind != "image" or not args.only_tier or args.limit != 1):
        raise RuntimeError("preview_requires_image_only_tier_and_limit_1")
    errors = validate_catalog(load_catalog(), generated=True)
    if errors and not args.allow_partial:
        raise RuntimeError("catalog_not_ready:" + ";".join(errors[:8]))
    manifest = load_manifest()
    pending = []
    blocked: list[str] = []
    ledger = BudgetLedger(openai_cap_usd=args.cap_openai, fish_cap_usd=args.cap_fish)
    voice = args.voice or persona("streamer").fish_voice_id
    audio_speed = getattr(args, "audio_speed", 1.0)
    audio_variant = f"speed-{audio_speed:g}" if audio_speed != 1 else ""
    for tier in tiers():
        if args.only_tier and tier["id"] != args.only_tier:
            continue
        asset = manifest.get("assets", {}).get(tier["id"], {})
        if args.kind == 'audio':
            attempt_key = audio_attempt_key(tier['id'], voice, audio_variant)
            previous = ledger.find(attempt_key)
            if previous and previous['status'] in {'sent', 'unsettled', 'settled'}:
                stem = media_stem(tier['id'])
                receipt_suffix = f".{audio_variant}" if audio_variant else ""
                path = AUDIO_ROOT / f'{stem}.wav'
                receipt_path = AUDIO_ROOT / 'receipts' / f'{stem}{receipt_suffix}.json'
                raw_path = AUDIO_ROOT / 'receipts' / f'{stem}.provider.wav'
                if args.confirm_paid and not valid_audio(path) and receipt_path.is_file() and raw_path.is_file():
                    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                    if receipt.get('attemptKey') != attempt_key:
                        raise RuntimeError(f"audio_receipt_mismatch:{tier['id']}")
                    # The exact response is durable even when acoustically rejected.
                    if previous['status'] != 'settled':
                        ledger.settle(attempt_key, receipt['costMicros'], request_id=receipt.get('requestId', ''),
                                      usage={'utf8Bytes': receipt['utf8Bytes'], 'durableResponse': True})
                    try:
                        data = finalize_streaming_wav(raw_path.read_bytes())
                        check = verify_wav(data)
                        if 250 <= check.duration_ms <= 30_000 and check.rms_dbfs >= -35 and check.peak_dbfs < 0.99:
                            durable_bytes(path, data)
                            durable_json(receipt_path, {**receipt, 'sha256': checksum(path)})
                    except (ValueError, PackError):
                        pass
                if not valid_audio(path):
                    blocked.append(tier['id'])
                    print(json.dumps({'audioBlockedNoRepayment': tier['id'], 'status': previous['status']}), flush=True)
                    if args.confirm_paid:
                        mark_missing(tier['id'], 'audio', 'saved_response_rejected_or_unknown_outcome')
                    continue
        if args.preview or args.force or args.kind == "image" and not current_image(tier["id"], asset) or args.kind == "audio" and not current_audio(asset):
            pending.append(tier)
    pending = pending[:args.limit]
    print(json.dumps({"kind": args.kind, "pending": len(pending), "quality": args.quality,
                      "concurrency": args.concurrency,
                      "paid": args.confirm_paid, "summary": manifest_summary()}, ensure_ascii=False), flush=True)
    if not args.confirm_paid or not pending:
        if args.confirm_paid:
            write_progress(args, 'partial' if blocked else 'complete', 0, len(pending), ledger, blockedTiers=blocked)
        return
    provider = "openai" if args.kind == "image" else "fish"
    credential = read_credential(provider)
    write_progress(args, "running", 0, len(pending), ledger)
    rejected: list[str] = []
    async with httpx.AsyncClient(timeout=240, follow_redirects=False, trust_env=False) as client:
        for offset in range(0, len(pending), args.concurrency):
            batch = pending[offset:offset + args.concurrency]
            print(json.dumps({"stage": args.kind, "starting": [tier["id"] for tier in batch],
                              "processed": offset, "queued": len(pending)}, ensure_ascii=False), flush=True)
            tasks = [(generate_image(client, ledger, tier, credential, args.quality, args.reference, args.force, args.preview)
                      if args.kind == "image" else generate_audio(
                          client, ledger, tier, credential, voice, audio_variant, audio_speed)) for tier in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failures = []
            for tier, result in zip(batch, results, strict=True):
                if isinstance(result, Exception):
                    reason = str(result)[:80]
                    if not args.preview:
                        mark_missing(tier["id"], args.kind, reason)
                    failures.append((tier["id"], result))
            if failures:
                # Do not repeatedly pay for the same failed item in a long batch.
                for tier_id, error in failures:
                    print(json.dumps({"failed": tier_id, "errorType": type(error).__name__}, ensure_ascii=False), flush=True)
                if args.kind == 'audio' and all(str(error).startswith('audio_acoustic_reject:') for _, error in failures):
                    rejected.extend(tier_id for tier_id, _ in failures)
                    # Preserve/settle known paid rejects, but never retry their synthesis.
                    for tier_id, _ in failures:
                        receipt = json.loads((AUDIO_ROOT / 'receipts' / f'{media_stem(tier_id)}.json').read_text(encoding='utf-8'))
                        ledger.settle(receipt['attemptKey'], receipt['costMicros'], request_id=receipt.get('requestId', ''),
                                      usage={'utf8Bytes': receipt['utf8Bytes'], 'acousticRejected': True})
                    write_progress(args, 'running', min(offset + args.concurrency, len(pending)), len(pending), ledger,
                                   rejectedTiers=rejected)
                    continue
                write_progress(args, "stopped", offset, len(pending), ledger,
                               failedTier=failures[0][0], reason=str(failures[0][1])[:160])
                raise failures[0][1]
            write_progress(args, "running", min(offset + args.concurrency, len(pending)), len(pending), ledger)
            print(json.dumps({"processed": min(offset + args.concurrency, len(pending)),
                              "queued": len(pending), "budget": ledger.summary()}, ensure_ascii=False), flush=True)
    write_progress(args, "partial" if rejected or blocked else "complete", len(pending), len(pending), ledger,
                   rejectedTiers=rejected, blockedTiers=blocked)
    print(json.dumps({"complete": not (rejected or blocked), "rejectedTiers": rejected, 'blockedTiers': blocked,
                      "summary": manifest_summary(), "budget": ledger.summary()},
                     ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("image", "audio"), required=True)
    parser.add_argument("--quality", choices=("low", "medium"), default="medium")
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--concurrency", type=int, choices=(1, 2, 3, 4, 5), default=1)
    parser.add_argument("--voice", default="")
    parser.add_argument("--audio-speed", type=float, default=1.0, choices=(0.5, 0.75, 1.0, 1.15, 1.25, 1.5, 2.0),
                        help="Fish prosody speed multiplier; non-default values use separate paid attempts")
    parser.add_argument("--reference", action="store_true", help="Use example-icons PNGs through Images Edit API")
    parser.add_argument("--force", action="store_true", help="Replace selected existing generated assets")
    parser.add_argument("--preview", action="store_true", help="Save one 512px style preview without publishing it")
    parser.add_argument("--only-tier", default="", help="Generate only the exact tier ID")
    parser.add_argument("--cap-openai", type=float, default=36.0)
    parser.add_argument("--cap-fish", type=float, default=15.0)
    parser.add_argument("--allow-partial", action="store_true", help="Editorial pilot only; full batch stays fail-closed")
    parser.add_argument("--confirm-paid", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with BudgetLedger().job_lock():
        raise SystemExit(main())
