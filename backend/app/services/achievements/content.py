"""Canonical editorial catalog and strict offline validation/Markdown export."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, cast

from app.services.achievements.generation import durable_bytes, durable_json
from app.services.achievements.rules import CATALOG_VERSION, CONTENT_VERSION, GROUPS, RULES, TIER_NAMES, rarity_for
from app.services.achievements.version import ASSET_VERSION

CONTENT_ROOT = Path(__file__).resolve().parent / "content" / ASSET_VERSION
CATALOG_PATH = CONTENT_ROOT / "catalog.json"
RARITY_LABELS = {"common": "Обычная", "rare": "Редкая", "epic": "Эпичная", "legendary": "Легендарная"}
FISH_DIRECTIONS = {
    "common": "[proud, warm, with a playful smile]",
    "rare": "[excited, delighted, playful, confident]",
    "epic": "[very excited, cinematic, triumphant, playful]",
    "legendary": "[extremely proud, delighted, legendary celebration, warm]",
}


def empty_catalog() -> dict[str, Any]:
    # Resolve the current art direction locally; never concatenate legacy image prompts.
    from app.services.achievements.visual_style import image_prompt

    lines = []
    for rule in RULES:
        rarity = rarity_for(rule["id"])
        tier_count = len(rule["thresholds"])
        tiers = []
        for index, threshold in enumerate(rule["thresholds"], 1):
            tier_id = f"{rule['id']}:t{index}"
            required_days = rule['minimumEvidenceDays'][min(index - 1, len(rule['minimumEvidenceDays']) - 1)]
            fallback_phrase = (f"Цель {tier_id}: {threshold} {rule['unit']} "
                               f"и {required_days} разных дней подтверждённой практики.")
            tier = {
                "id": tier_id,
                "tier": index,
                "tierName": TIER_NAMES[index - 1],
                "tierCount": tier_count,
                "isFinal": index == tier_count,
                "threshold": threshold,
                "minimumEvidenceDays": required_days,
                "title": f"{rule['id']} · {TIER_NAMES[index - 1]}"[:80],
                "phrase": fallback_phrase,
                "rarity": rarity,
                "fishMarkup": f"{FISH_DIRECTIONS[rarity]} {fallback_phrase}",
                "audioText": fallback_phrase,
                "contentOrigin": "offline-fallback",
            }
            tier["imagePrompt"] = image_prompt({**tier, "description": rule["description"], "unit": rule["unit"]})
            tiers.append(tier)
        lines.append({**rule, "groupName": GROUPS[rule["group"]], "tiers": tiers})
    return {"schemaVersion": 1, "assetVersion": ASSET_VERSION, "rulesVersion": CATALOG_VERSION, "contentVersion": CONTENT_VERSION,
            "locale": "ru-RU", "textModel": None, "lines": lines}


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    if not path.is_file():
        return empty_catalog()
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def save_catalog(catalog: dict[str, Any], path: Path = CATALOG_PATH) -> None:
    durable_json(path, catalog)


def reconcile_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Rules own metadata; paid editorial fields survive append-only expansion/rebalance."""
    from copy import deepcopy

    result = empty_catalog()
    old = {tier['id']: tier for line in catalog.get('lines', []) for tier in line.get('tiers', [])}
    fields = ('title', 'phrase', 'imagePrompt', 'fishMarkup', 'audioText', 'contentOrigin', 'editorialStyle')
    for line in result['lines']:
        for tier in line['tiers']:
            source = old.get(tier['id'], {})
            if source.get('contentOrigin') != 'gpt-6.1-sol':
                continue
            for key in fields:
                if key in source:
                    tier[key] = deepcopy(source[key])
    result['textModel'] = catalog.get('textModel')
    return result


def _plain_fish(markup: str) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", markup)
    text = re.sub(r"</?[A-Za-z]+>", "", text)
    return " ".join(text.split())


def validate_catalog(catalog: dict[str, Any], *, generated: bool = False) -> list[str]:
    errors: list[str] = []
    lines = catalog.get("lines", [])
    expected = {rule["id"]: rule for rule in RULES}
    if len(lines) != len(expected):
        errors.append(f"expected {len(expected)} lines, got {len(lines)}")
    if {line.get("id") for line in lines} != set(expected):
        errors.append("line IDs differ from deterministic rules")
    tiers = [tier for line in lines for tier in line.get("tiers", [])]
    expected_tiers = sum(len(rule["thresholds"]) for rule in RULES)
    if len(tiers) != expected_tiers:
        errors.append(f"expected {expected_tiers} tiers, got {len(tiers)}")
    if len({tier.get("id") for tier in tiers}) != len(tiers):
        errors.append("duplicate tier IDs")
    phrases = [str(tier.get("phrase", "")).strip().casefold() for tier in tiers]
    if len(set(phrases)) != len(phrases):
        errors.append("duplicate phrases")
    rarities = Counter(tier.get("rarity") for tier in tiers)
    expected_rarities = Counter(rarity_for(rule["id"]) for rule in RULES for _ in rule["thresholds"])
    if rarities != expected_rarities:
        errors.append(f"unexpected rarity distribution: {dict(rarities)}")
    for line in lines:
        rule = expected.get(str(line.get("id")))
        if rule is None:
            continue
        for key in ("group", "metric", "unit", "description", "thresholds", "applicability", "evidenceMetric", "minimumEvidenceDays"):
            if line.get(key) != rule[key]:
                errors.append(f"rule changed: {rule['id']}:{key}")
        if [tier.get("threshold") for tier in line.get("tiers", [])] != rule["thresholds"]:
            errors.append(f"thresholds changed: {rule['id']}")
        tier_count = len(rule["thresholds"])
        for index, tier in enumerate(line.get("tiers", []), 1):
            tier_id = f"{rule['id']}:t{index}"
            if tier.get("id") != tier_id:
                errors.append(f"tier ID changed: {tier_id}")
            if type(tier.get("tier")) is not int or tier["tier"] != index:
                errors.append(f"tier index changed: {tier_id}")
            if index > tier_count or tier.get("tierName") != TIER_NAMES[index - 1]:
                errors.append(f"tier name changed: {tier_id}")
            if tier.get("rarity") != rarity_for(rule["id"]):
                errors.append(f"tier rarity changed: {tier_id}")
            if type(tier.get("tierCount")) is not int or tier["tierCount"] != tier_count:
                errors.append(f"tier count changed: {tier_id}")
            if type(tier.get("isFinal")) is not bool or tier["isFinal"] != (index == tier_count):
                errors.append(f"tier final flag changed: {tier_id}")
            required_days = rule['minimumEvidenceDays'][min(index - 1, len(rule['minimumEvidenceDays']) - 1)]
            if tier.get('minimumEvidenceDays') != required_days:
                errors.append(f"tier evidence days changed: {tier_id}")
            if generated and tier.get("contentOrigin") != "gpt-6.1-sol":
                errors.append(f"content origin must be gpt-6.1-sol: {tier_id}")
            title = str(tier.get("title", "")).strip()
            phrase = str(tier.get("phrase", "")).strip()
            prompt = str(tier.get("imagePrompt", "")).strip()
            markup = str(tier.get("fishMarkup", "")).strip()
            if not 2 <= len(title) <= 80:
                errors.append(f"bad title length: {tier.get('id')}")
            if generated and not 20 <= len(phrase) <= 240:
                errors.append(f"bad phrase length: {tier.get('id')}")
            if generated and len(prompt) < 120:
                errors.append(f"image prompt too short: {tier.get('id')}")
            if _plain_fish(markup) != " ".join(str(tier.get("audioText", "")).split()):
                errors.append(f"Fish markup changes spoken text: {tier.get('id')}")
            if generated and phrase != str(tier.get("audioText", "")).strip():
                errors.append(f"audio text differs from phrase: {tier.get('id')}")
    return errors


def render_markdown(catalog: dict[str, Any]) -> str:
    catalog_lines = catalog["lines"]
    tier_counts = [len(line["tiers"]) for line in catalog_lines]
    tier_range = f"от {min(tier_counts)} до {max(tier_counts)}" if tier_counts else "0"
    lines = [
        f"# Достижения Forma: {len(catalog_lines)} линий и {sum(tier_counts)} наград",
        "",
        f"Версия правил: `{catalog['rulesVersion']}`. Версия контента: `{catalog['contentVersion']}`.",
        "",
        f"Каждая линия имеет независимое условие и {tier_range} ступеней. Ступени не считаются отдельными линиями.",
        "Фразы создаются заранее; условия и прогресс всегда вычисляет детерминированный backend.",
        "",
        "Редкость: **обычная** — стальной синий (steel-blue), **редкая** — циан (cyan), "
        "**эпичная** — фиолетовый (violet), **легендарная** — янтарное золото (amber-gold).",
        "Шестиугольные значки с чистым нижним краем: без нижних ромбов, корон и декоративных украшений.",
        "",
    ]
    for group, group_name in GROUPS.items():
        lines.extend([f"## {group_name}", ""])
        for line in (item for item in catalog["lines"] if item["group"] == group):
            lines.extend([
                f"### `{line['id']}`",
                "",
                f"**Правило:** {line['description']} **Единица:** {line['unit']}. **Источник:** `{line['applicability']}`.",
                "",
            ])
            for tier in line["tiers"]:
                lines.extend([
                    f"#### {tier['tier']}. {tier['title']}",
                    "",
                    f"- **ID:** `{tier['id']}`",
                    f"- **Порог:** {tier['threshold']} {line['unit']}",
                    f"- **Подтверждённая практика:** минимум {tier['minimumEvidenceDays']} разных дней; оба условия обязательны.",
                    f"- **Ступень:** {tier['tierName']}",
                    f"- **Редкость:** {RARITY_LABELS[tier['rarity']]} (`{tier['rarity']}`)",
                    f"- **Фраза:** {tier['phrase']}",
                    f"- **Fish Drama 3:** `{tier['fishMarkup']}`",
                    f"- **Image prompt:** {tier['imagePrompt']}",
                    "",
                ])
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(catalog: dict[str, Any], path: Path) -> None:
    durable_bytes(path, render_markdown(catalog).encode('utf-8'))
