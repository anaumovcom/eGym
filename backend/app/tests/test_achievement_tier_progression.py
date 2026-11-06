"""Offline variable-tier regressions; no catalog, media, or provider writes."""

import copy
import hashlib
import json
import socket
from collections import Counter
from itertools import pairwise
from typing import Any

import pytest

from app.services.achievements import content, rules, visual_style

EXTENDED_THRESHOLDS = {
    "rhythm.active_days": [5, 15, 30, 60, 120, 240],
    "rhythm.active_weeks": [4, 12, 26, 52, 104],
    "rhythm.months": [3, 6, 12, 18, 24],
    "practice.workouts": [5, 20, 50, 100, 200, 400],
    "practice.reps": [100, 500, 1500, 3000, 7500, 15000],
    "variety.stretch_days": [3, 10, 25, 50, 100],
    "repertoire.distinct_exercises": [3, 8, 15, 25, 40],
    "volume.weighted_days": [3, 10, 25, 50, 100],
    "plan.planned_days": [3, 10, 25, 50, 100],
    "reflection.note_weeks": [2, 6, 12, 26, 52],
    "story.archive": [5, 20, 50, 100, 200],
    "measured.verified_days": [3, 10, 25, 50, 100],
}


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Achievement tier tests must never access the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


def editorial_fixture(catalog: dict[str, Any]) -> dict[str, Any]:
    """Simulate generated text locally, not through the real catalog or a provider."""
    catalog = copy.deepcopy(catalog)
    catalog["textModel"] = "gpt-6.1-sol"
    for row in catalog["lines"]:
        for tier in row["tiers"]:
            phrase = f"Ты сохранил новую главу своей практики: {tier['id']}."
            tier.update(title=f"Глава {tier['tier']}", phrase=phrase, audioText=phrase,
                        fishMarkup=f"[warm] {phrase}", contentOrigin="gpt-6.1-sol")
    return catalog


@pytest.fixture()
def catalog() -> dict[str, Any]:
    return editorial_fixture(content.empty_catalog())


def test_rules_have_120_lines_and_387_variable_tiers() -> None:
    core = rules.RULES[:-len(rules.EXTENSION_RULES)]
    assert len(core) == len({row["id"] for row in core}) == 120
    assert Counter(len(row["thresholds"]) for row in core) == {3: 108, 5: 9, 6: 3}
    assert sum(len(row["thresholds"]) for row in core) == 387
    assert {row["id"]: row["thresholds"] for row in core if len(row["thresholds"]) > 3} == EXTENDED_THRESHOLDS
    assert all(a < b for row in rules.RULES for a, b in pairwise(row["thresholds"]))
    assert rules.CATALOG_VERSION == "achievements-rules-1.3.0"
    assert rules.CONTENT_VERSION == "achievements-content-1.1.0"


def test_all_legacy_t1_t3_ids_and_thresholds_are_preserved() -> None:
    # Captured from all 120 current rules BEFORE extending any thresholds.
    snapshot = [(row["id"], row["thresholds"][:3]) for row in rules.RULES[:-len(rules.EXTENSION_RULES)]]
    digest = hashlib.sha256(json.dumps(snapshot, separators=(",", ":")).encode()).hexdigest()
    assert digest == "0fec6eb43f96dbd298f2572f3803e7838c5a1aaa8484948aa027604871091ed9"
    catalog_rows = {row["id"]: row for row in content.empty_catalog()["lines"]}
    for definition_id, thresholds in snapshot:
        assert [(tier["id"], tier["threshold"]) for tier in catalog_rows[definition_id]["tiers"][:3]] == [
            (f"{definition_id}:t{index}", threshold) for index, threshold in enumerate(thresholds, 1)
        ]


def test_tier_names_do_not_conflate_progression_and_rarity() -> None:
    assert rules.TIER_NAMES[:3] == ("Начало", "Практика", "Мастерство")
    assert len(rules.TIER_NAMES) == len(set(rules.TIER_NAMES)) == 8
    for name in rules.TIER_NAMES:
        assert not any(word in name.casefold() for word in ("обычн", "редк", "эпич", "легендар", *rules.RARITIES))
    row = rules.line("rhythm", 0, "test", "active_days", "день", "Test", (1, 2, 3, 4, 5, 6))
    assert row["thresholds"] == [1, 2, 3, 4, 5, 6]


def test_empty_catalog_has_exact_tier_metadata_and_current_prompts() -> None:
    catalog = content.empty_catalog()
    assert catalog["rulesVersion"] == rules.CATALOG_VERSION
    assert catalog["contentVersion"] == rules.CONTENT_VERSION
    assert catalog["textModel"] is None
    tiers = [tier for row in catalog["lines"] for tier in row["tiers"]]
    assert len(tiers) == len({tier["id"] for tier in tiers}) == sum(len(row['thresholds']) for row in rules.RULES)
    assert Counter(tier['rarity'] for tier in tiers) == Counter(rules.rarity_for(row['id']) for row in rules.RULES for _ in row['thresholds'])
    for row in catalog["lines"]:
        count = len(row["thresholds"])
        assert len(row["tiers"]) == count
        for index, tier in enumerate(row["tiers"], 1):
            assert tier["id"] == f"{row['id']}:t{index}"
            assert tier["tier"] == index
            assert tier["tierName"] == rules.TIER_NAMES[index - 1]
            assert tier["threshold"] == row["thresholds"][index - 1]
            assert tier["tierCount"] == count
            assert tier["isFinal"] is (index == count)
            assert tier["rarity"] == rules.rarity_for(row["id"])
            assert tier["contentOrigin"] == "offline-fallback"
            assert tier["imagePrompt"] == visual_style.image_prompt({
                **tier, "description": row["description"], "unit": row["unit"],
            })


def test_empty_catalog_resolves_visual_style_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def prompt(tier: dict[str, object]) -> str:
        assert "imagePrompt" not in tier  # No legacy framing supplied as input.
        calls.append(tier)
        return f"current-style:{tier['id']}"

    monkeypatch.setattr(visual_style, "image_prompt", prompt)
    catalog = content.empty_catalog()
    assert len(calls) == sum(len(row['thresholds']) for row in rules.RULES)
    assert {call["tierCount"] for call in calls} == {3, 4, 5, 6}
    for row in catalog["lines"]:
        for tier in row["tiers"]:
            assert tier["imagePrompt"] == f"current-style:{tier['id']}"


def test_complete_generated_catalog_validates_offline(catalog: dict[str, Any]) -> None:
    assert content.validate_catalog(catalog, generated=True) == []


@pytest.mark.parametrize(("field", "value", "error"), [
    ("id", "unrelated:t1", "tier ID changed"),
    ("tier", 2, "tier index changed"),
    ("tier", True, "tier index changed"),
    ("tier", 1.0, "tier index changed"),
    ("tierName", "Легендарная", "tier name changed"),
    ("rarity", "unknown", "tier rarity changed"),
    ("tierCount", 6, "tier count changed"),
    ("isFinal", True, "tier final flag changed"),
    ("isFinal", 0, "tier final flag changed"),
    ("threshold", 999, "thresholds changed"),
])
def test_validator_rejects_tier_metadata_tampering(
    catalog: dict[str, Any], field: str, value: Any, error: str,
) -> None:
    catalog["lines"][0]["tiers"][0][field] = value
    assert any(error in message for message in content.validate_catalog(catalog, generated=True))


def test_validator_checks_rarity_per_tier_even_when_distribution_matches(catalog: dict[str, Any]) -> None:
    common = catalog["lines"][0]["tiers"][0]
    rare = catalog["lines"][4]["tiers"][0]
    common["rarity"], rare["rarity"] = rare["rarity"], common["rarity"]
    errors = content.validate_catalog(catalog, generated=True)
    assert sum(message.startswith("tier rarity changed") for message in errors) == 2
    assert not any("distribution" in message for message in errors)


def test_validator_checks_unique_but_swapped_ids(catalog: dict[str, Any]) -> None:
    first, second = catalog["lines"][0]["tiers"][:2]
    first["id"], second["id"] = second["id"], first["id"]
    assert sum(message.startswith("tier ID changed") for message in content.validate_catalog(catalog)) == 2


@pytest.mark.parametrize("remove", [True, False])
def test_validator_rejects_missing_or_extra_tiers_without_crashing(catalog: dict[str, Any], remove: bool) -> None:
    row = next(row for row in catalog["lines"] if row["id"] == "rhythm.active_days")
    if remove:
        row["tiers"].pop()
    else:
        row["tiers"].append(copy.deepcopy(row["tiers"][-1]))
    errors = content.validate_catalog(catalog, generated=True)
    assert any(message.startswith(f"expected {sum(len(row['thresholds']) for row in rules.RULES)} tiers") for message in errors)
    assert any(message.startswith("thresholds changed") for message in errors)


@pytest.mark.parametrize("origin", [None, "offline-fallback", "other-model"])
def test_generated_validation_requires_sol_origin(catalog: dict[str, Any], origin: str | None) -> None:
    tier = catalog["lines"][-1]["tiers"][-1]
    if origin is None:
        tier.pop("contentOrigin")
    else:
        tier["contentOrigin"] = origin
    assert content.validate_catalog(catalog, generated=True) == [
        f"content origin must be gpt-6.1-sol: {tier['id']}",
    ]
    assert content.validate_catalog(catalog) == []


def test_validator_derives_counts_and_distribution_from_current_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    row = copy.deepcopy(rules.RULES[0])
    row["thresholds"].append(40)  # Four tiers also work; not just the current 3/5/6 lengths.
    monkeypatch.setattr(content, "RULES", (row,))
    catalog = editorial_fixture(content.empty_catalog())
    assert len(catalog["lines"][0]["tiers"]) == 4
    assert content.validate_catalog(catalog, generated=True) == []


def test_validator_preserves_text_and_rule_checks(catalog: dict[str, Any]) -> None:
    row = catalog["lines"][0]
    row["metric"] = "unrelated"
    first, second = row["tiers"][:2]
    first["phrase"] = second["phrase"]
    first["imagePrompt"] = "short"
    errors = content.validate_catalog(catalog, generated=True)
    assert "duplicate phrases" in errors
    assert any(message.startswith("rule changed") for message in errors)
    assert any(message.startswith("image prompt too short") for message in errors)
    assert any(message.startswith("audio text differs from phrase") for message in errors)
    first["fishMarkup"] = "[warm] different spoken text"
    assert any(message.startswith("Fish markup changes spoken text") for message in content.validate_catalog(catalog))


def test_markdown_renders_variable_tiers_and_updated_palettes(catalog: dict[str, Any]) -> None:
    markdown = content.render_markdown(catalog)
    assert markdown.startswith(f"# Достижения Forma: {len(rules.RULES)} линий и {sum(len(row['thresholds']) for row in rules.RULES)} наград\n")
    assert "от 3 до 6 ступеней" in markdown
    assert "три ступени" not in markdown
    assert markdown.count("- **ID:**") == sum(len(row['thresholds']) for row in rules.RULES)
    for color in ("steel-blue", "cyan", "violet", "amber-gold"):
        assert color in markdown
    assert "без нижних ромбов, корон и декоративных украшений" in markdown
    for row in catalog["lines"]:
        for tier in row["tiers"]:
            assert f"- **ID:** `{tier['id']}`" in markdown
            assert f"- **Порог:** {tier['threshold']} {row['unit']}" in markdown
    subset = {**catalog, "lines": [catalog["lines"][0]]}
    assert content.render_markdown(subset).startswith("# Достижения Forma: 1 линий и 3 наград\n")
    assert content.render_markdown({**catalog, "lines": []}).startswith("# Достижения Forma: 0 линий и 0 наград\n")