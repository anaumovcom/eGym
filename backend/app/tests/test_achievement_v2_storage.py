"""Version boundaries must not replace paid v1 media or reset shared spending."""

import pytest

from app.services.achievements import content, media
from app.services.achievements.visual_style import STYLE_VERSION, image_prompt
from scripts import generate_achievement_content as text_generator


def test_outputs_are_isolated_in_v2():
    assert content.CATALOG_PATH.parent.name == "v2"
    assert media.MEDIA_ROOT.name == "v2"
    assert text_generator.MD_PATH.parent.name == "v2"
    assert STYLE_VERSION == "hexagonal-v2"
    assert content.empty_catalog()["assetVersion"] == "v2"


def test_urls_and_extended_tier_ids(monkeypatch):
    monkeypatch.setattr(media, "load_manifest", lambda: {"assets": {
        "practice.workouts:t6": {"image": {"512": "icon.webp"}, "audio": {"file": "voice.wav"}},
    }})
    urls = media.asset_urls("practice.workouts:t6")
    assert urls["imageUrl"] == "/media/achievements/v2/images/icon.webp"
    assert urls["audioUrl"] == "/media/achievements/v2/audio/voice.wav"
    with pytest.raises(ValueError):
        media.media_stem("practice.workouts:t9")
    assert media.media_stem("practice.workouts:t8") == "practice-workouts-t8"
    assert text_generator.schema()["properties"]["lines"]["items"]["properties"]["tiers"]["maxItems"] == 8


@pytest.mark.parametrize("count", [3, 5, 6, 7, 8])
def test_final_is_relative_and_bottom_is_clean(count):
    row = {"tier": 1, "tierCount": count, "rarity": "common"}
    opening = image_prompt(row)
    final = image_prompt({**row, "tier": count})
    assert "45%" in opening and "90%" in final
    assert "FINAL TIER:" not in opening
    assert "FINAL TIER:" in final
    assert "NO rank marker" in final
    assert "small pale-blue faceted diamond" not in final


def test_more_than_eight_tiers_rejected():
    with pytest.raises(ValueError, match="invalid_tier_progression"):
        image_prompt({"tier": 9, "tierCount": 9, "rarity": "common"})


def test_five_media_requests_are_in_flight(monkeypatch):
    import argparse
    import asyncio

    from scripts import generate_achievement_media as generator

    rows = [{"id": f"practice.workouts:t{index}", "tier": index} for index in range(1, 6)]
    active = 0
    peak = 0
    monkeypatch.setattr(generator, "validate_catalog", lambda *a, **kw: [])
    monkeypatch.setattr(generator, "tiers", lambda: rows)
    monkeypatch.setattr(generator, "load_manifest", lambda: {"assets": {}})
    monkeypatch.setattr(generator, "manifest_summary", lambda: {})
    monkeypatch.setattr(generator, "write_progress", lambda *a, **kw: None)
    monkeypatch.setattr(generator, "read_credential", lambda provider: "test-only")
    monkeypatch.setattr(generator, "BudgetLedger", lambda **kw: type("Ledger", (), {"summary": lambda self: {}})())

    async def generate(*args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1

    monkeypatch.setattr(generator, "generate_image", generate)
    args = argparse.Namespace(preview=False, only_tier="", limit=387, kind="image", allow_partial=False,
                              force=False, quality="medium", concurrency=5, confirm_paid=True,
                              cap_openai=36, cap_fish=15, voice="test", reference=True)
    asyncio.run(generator.run(args))
    assert peak == 5