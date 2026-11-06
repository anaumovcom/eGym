"""Offline regression tests; never call an image provider."""

import asyncio
import base64
import io
import json

import httpx
from PIL import Image

from app.services.achievements.generation import BudgetLedger, token_cost
from app.services.achievements.visual_style import STYLE_VERSION, image_prompt
from scripts import generate_achievement_media as generator


def pilot():
    return {
        "id": "start.first_set:t1", "title": "First set", "description": "Complete one set",
        "threshold": 1, "unit": "sets", "tier": 1, "rarity": "rare",
        "imagePrompt": "OBSOLETE_METAL_DONUT_PROMPT",
    }


def test_prompt_uses_hexagonal_style_not_legacy_prompt():
    prompt = image_prompt(pilot())
    assert "point-up hexagon" in prompt
    assert "cyan-to-royal-blue" in prompt
    assert "OBSOLETE_METAL_DONUT_PROMPT" not in prompt
    assert "Complete one set" in prompt


def test_image_cost_does_not_omit_reference_tokens():
    usage = {"input_tokens": 1000, "output_tokens": 100,
             "input_tokens_details": {"text_tokens": 100, "image_tokens": 900}}
    assert token_cost(generator.IMAGE_MODEL, usage) >= 10_700


def test_reserved_requests_count_toward_cap(tmp_path):
    ledger = BudgetLedger(path=tmp_path / "ledger.json", openai_cap_usd=1)
    ledger.reserve("pilot", "openai", "image", generator.IMAGE_MODEL, 750_000)
    assert ledger.committed("openai") == 750_000


def test_reference_preview_saves_512_without_publication(tmp_path, monkeypatch):
    encoded = io.BytesIO()
    Image.new("RGB", (1024, 1024), "blue").save(encoded, format="PNG")
    reference = tmp_path / "reference.png"
    reference.write_bytes(encoded.getvalue())
    monkeypatch.setattr(generator, "REFERENCE_PATHS", [reference])
    monkeypatch.setattr(generator, "IMAGE_ROOT", tmp_path / "images")
    published = []
    monkeypatch.setattr(generator, "save_asset", lambda *a, **kw: published.append(a))

    def respond(request):
        assert request.url.path == "/v1/images/edits"
        assert b'name="image[]"' in request.content
        assert b"point-up hexagon" in request.content
        assert b"OBSOLETE_METAL_DONUT_PROMPT" not in request.content
        return httpx.Response(200, json={
            "data": [{"b64_json": base64.b64encode(encoded.getvalue()).decode()}],
            "usage": {"input_tokens": 100, "output_tokens": 100},
        })

    ledger = BudgetLedger(path=tmp_path / "ledger.json")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await generator.generate_image(client, ledger, pilot(), "test-only", "medium",
                                           use_reference=True, preview=True)

    asyncio.run(run())
    result = tmp_path / "style-previews" / STYLE_VERSION / "start-first_set-t1-512.webp"
    with Image.open(result) as image:
        assert image.size == (512, 512)
    assert json.loads(result.with_suffix(".json").read_text(encoding="utf-8"))["approved"] is False
    assert published == []
    assert not (tmp_path / "images").exists()


def test_current_image_requires_new_style_and_preserves_approved_file(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "IMAGE_ROOT", tmp_path)
    path = tmp_path / "approved.webp"
    Image.new("RGB", (512, 512), "blue").save(path, format="WEBP")
    asset = {"image": {"512": path.name}, "imageMetadata": {
        "styleVersion": STYLE_VERSION, "sha256": generator.checksum(path), "approved": True,
    }}
    assert generator.current_image("start.first_set:t1", asset)
    asset["imageMetadata"]["styleVersion"] = "legacy"
    assert not generator.current_image("start.first_set:t1", asset)


def test_job_lock_rejects_second_writer(tmp_path):
    import pytest
    from filelock import Timeout

    first = BudgetLedger(path=tmp_path / "ledger.json")
    second = BudgetLedger(path=tmp_path / "ledger.json")
    with first.job_lock(), pytest.raises(Timeout), second.job_lock():
        raise AssertionError("Second writer must never acquire the job lock")


def test_run_awaits_each_image_before_starting_next(monkeypatch):
    import argparse

    rows = [dict(pilot(), id=f"start.first_set:t{tier}") for tier in (1, 2, 3)]
    events = []
    monkeypatch.setattr(generator, "validate_catalog", lambda *a, **kw: [])
    monkeypatch.setattr(generator, "tiers", lambda: rows)
    monkeypatch.setattr(generator, "load_manifest", lambda: {"assets": {}})
    monkeypatch.setattr(generator, "manifest_summary", lambda: {})
    monkeypatch.setattr(generator, "write_progress", lambda *a, **kw: None)
    monkeypatch.setattr(generator, "read_credential", lambda provider: "test-only")
    monkeypatch.setattr(generator, "BudgetLedger", lambda **kw: type("Ledger", (), {"summary": lambda self: {}})())

    async def generate(client, ledger, tier, *args):
        events.append(("start", tier["id"]))
        await asyncio.sleep(0)  # Yield only; no time delay and no provider calls.
        events.append(("finish", tier["id"]))

    monkeypatch.setattr(generator, "generate_image", generate)
    args = argparse.Namespace(preview=False, only_tier="", limit=360, kind="image", allow_partial=False,
                              force=False, quality="medium", concurrency=1, confirm_paid=True,
                              cap_openai=36, cap_fish=15, voice="test", reference=True)
    asyncio.run(generator.run(args))
    assert events == [(event, row["id"]) for row in rows for event in ("start", "finish")]