"""Immediate, content-addressed local media files and an atomically updated public manifest."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.achievements.content import load_catalog
from app.services.achievements.generation import durable_json
from app.services.achievements.version import ASSET_VERSION, MAX_TIERS

MEDIA_ROOT = Path(__file__).resolve().parents[3] / "media" / "achievements" / ASSET_VERSION
IMAGE_ROOT = MEDIA_ROOT / "images"
AUDIO_ROOT = MEDIA_ROOT / "audio"
MANIFEST_PATH = MEDIA_ROOT / "manifest.json"


def media_stem(tier_id: str) -> str:
    if not re.fullmatch(rf"[a-z]+\.[a-z0-9_-]+:t[1-{MAX_TIERS}]", tier_id):
        raise ValueError("invalid_tier_id")
    return tier_id.replace(".", "-").replace(":", "-")


def _write_json(path: Path, value: Any) -> None:
    durable_json(path, value)


@lru_cache(maxsize=1)
def _read_manifest(path: Path, modified_ns: int, size: int) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.is_file():
        stat = MANIFEST_PATH.stat()
        return _read_manifest(MANIFEST_PATH, stat.st_mtime_ns, stat.st_size)
    return {"schemaVersion": 1, "assetVersion": ASSET_VERSION, "assets": {}, "missing": [], "failed": {}}


def save_asset(tier_id: str, kind: str, files: dict[str, str], **metadata: Any) -> dict[str, Any]:
    """Publish one complete asset immediately; never publish a partial image variant set."""
    manifest = deepcopy(load_manifest())
    manifest["assets"][tier_id] = {**manifest["assets"].get(tier_id, {}), kind: files,
                                   f"{kind}Metadata": metadata, "updatedAt": metadata.get("updatedAt")}
    manifest["missing"] = [item for item in manifest.get("missing", []) if item != f"{kind}:{tier_id}"]
    manifest.get("failed", {}).pop(f"{kind}:{tier_id}", None)
    _write_json(MANIFEST_PATH, manifest)
    return manifest


def mark_missing(tier_id: str, kind: str, reason: str) -> dict[str, Any]:
    manifest = deepcopy(load_manifest())
    key = f"{kind}:{tier_id}"
    if key not in manifest["missing"]:
        manifest["missing"].append(key)
    manifest.setdefault("failed", {})[key] = reason[:80]
    _write_json(MANIFEST_PATH, manifest)
    return manifest


def asset_file(tier_id: str, kind: str) -> Path | None:
    """Resolve a published file strictly from the manifest, never from caller-supplied paths."""
    media_stem(tier_id)
    asset = load_manifest().get("assets", {}).get(tier_id, {})
    if kind == "image":
        name, root = (asset.get("image") or {}).get("512"), IMAGE_ROOT
    elif kind == "audio":
        name, root = (asset.get("audio") or {}).get("file"), AUDIO_ROOT
    else:
        return None
    if not isinstance(name, str) or name != Path(name).name:
        return None
    path = root / name
    return path if path.is_file() else None


def asset_urls(tier_id: str, media_prefix: str = "/media", *, user_id: str | None = None) -> dict[str, Any]:
    """Static URLs for tests/tools, or owner-checked API URLs when ``user_id`` is supplied."""
    stem = media_stem(tier_id)
    asset = load_manifest().get("assets", {}).get(tier_id, {})
    result: dict[str, Any] = {"imageUrl": None, "thumbnailUrl": None, "audioUrl": None, "imageState": "missing",
                              "audioState": "missing"}
    image = asset.get("image")
    if user_id is not None:
        from urllib.parse import quote

        from app.core.config import get_settings
        base = f"{get_settings().api_prefix}/achievements/tiers/{quote(tier_id, safe='')}"
        owner = f"?userId={quote(user_id, safe='')}"
        if image:
            result.update(imageUrl=f"{base}/image{owner}", thumbnailUrl=f"{base}/image{owner}", imageState="ready")
        if asset.get("audio"):
            result.update(audioUrl=f"{base}/audio{owner}", audioState="ready")
        result["assetKey"] = stem
        return result
    if image:
        result.update(imageUrl=f"{media_prefix}/achievements/{ASSET_VERSION}/images/{image['512']}",
                  thumbnailUrl=f"{media_prefix}/achievements/{ASSET_VERSION}/images/{image['512']}", imageState="ready")
    if asset.get("audio"):
        result.update(audioUrl=f"{media_prefix}/achievements/{ASSET_VERSION}/audio/{asset['audio']['file']}", audioState="ready")
    # Keep deterministic fallback URLs for clients that choose to render local vector placeholders.
    result["assetKey"] = stem
    return result


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize_streaming_wav(data: bytes) -> bytes:
    """Fish uses streaming sentinel lengths; decoded PCM is complete, so pin exact RIFF/data sizes."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("wav_format")
    offset = 12
    chunks = []
    pcm = None
    while offset + 8 <= len(data):
        name = data[offset:offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        payload = data[offset + 8:] if size in {0xFFFFFFFF, 0xFFFFFFFE} else data[offset + 8:offset + 8 + size]
        if name == b"data":
            pcm = payload
            break
        chunks.append((name, payload))
        offset += 8 + size + size % 2
    if pcm is None or len(pcm) % 2:
        raise ValueError("wav_length")
    body = b"".join(name + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")
                    for name, payload in chunks)
    body += b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


def manifest_summary() -> dict[str, int]:
    assets = load_manifest().get("assets", {})
    return {"lines": len(load_catalog()["lines"]),
            "tiers": sum(len(line["tiers"]) for line in load_catalog()["lines"]),
            "images": sum("image" in value for value in assets.values()),
            "audio": sum("audio" in value for value in assets.values())}
