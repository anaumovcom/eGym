from __future__ import annotations

from csv import DictReader
from dataclasses import dataclass
from functools import lru_cache
from json import loads
from pathlib import Path
from urllib.parse import urljoin

from app.core.config import BACKEND_ROOT

REPO_ROOT = BACKEND_ROOT.parent
EXERCISES_ROOT = REPO_ROOT / "exercises"
TRANSLATIONS_PATH = REPO_ROOT / "exercise_name_translations.csv"


@dataclass(frozen=True)
class ImportedExerciseVideo:
    file_name: str
    relative_url: str
    gender: str
    view: str


@dataclass(frozen=True)
class ImportedExerciseGuide:
    setup: tuple[str, ...]
    how_to_perform: tuple[str, ...]
    technique: tuple[str, ...]
    things_to_avoid: tuple[str, ...]


@dataclass(frozen=True)
class ImportedExercise:
    slug: str
    name: str
    name_ru: str
    equipment: str
    difficulty: str
    force: str
    grips: str
    mechanic: str
    muscles: tuple[str, ...]
    steps: tuple[str, ...]
    guide: ImportedExerciseGuide
    videos: tuple[ImportedExerciseVideo, ...]


def _parse_csv() -> dict[str, tuple[str, str]]:
    if not TRANSLATIONS_PATH.exists():
        return {}

    with TRANSLATIONS_PATH.open("r", encoding="utf-8") as handle:
        reader = DictReader(handle, delimiter=";")
        return {
            row["slug"]: (row.get("name_en", "") or "", row.get("name_ru", "") or "")
            for row in reader
            if row.get("slug")
        }


def _normalize_difficulty(value: str | None) -> str:
    if value in {"Beginner", "Intermediate", "Advanced"}:
        return value
    return "Intermediate"


def _normalize_force(value: str | None) -> str:
    if value in {"Push", "Pull", "Static", "Stretch"}:
        return value
    return "Static"


def _normalize_mechanic(value: str | None) -> str:
    if value in {"Compound", "Isolation"}:
        return value
    return "Mobility"


def _to_guide_array(source: dict[str, object] | None, key: str) -> tuple[str, ...]:
    if not isinstance(source, dict):
        return ()
    raw_value = source.get(key)
    if not isinstance(raw_value, list):
        return ()
    return tuple(item for item in raw_value if isinstance(item, str) and item)


def _build_video_entries(slug: str, payload: dict[str, object], directory: Path) -> tuple[ImportedExerciseVideo, ...]:
    files = sorted(file.name for file in directory.iterdir() if file.is_file() and file.suffix.lower() == ".mp4")
    male_videos = payload.get("male_videos")
    female_videos = payload.get("female_videos")
    declared = [item for item in male_videos if isinstance(item, str)] if isinstance(male_videos, list) else []
    declared += [item for item in female_videos if isinstance(item, str)] if isinstance(female_videos, list) else []
    all_files = sorted(set(files + declared))

    return tuple(
        ImportedExerciseVideo(
            file_name=file_name,
            relative_url=f"/media/exercises/{slug}/{file_name}",
            gender="female" if file_name.startswith("female-") else "male",
            view="front" if "-front" in file_name else "side",
        )
        for file_name in all_files
    )


def _build_entry(slug: str, translations: dict[str, tuple[str, str]]) -> ImportedExercise:
    directory = EXERCISES_ROOT / slug
    json_path = directory / f"{slug}.json"
    raw_payload = loads(json_path.read_text(encoding="utf-8"))
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    translated_name, translated_name_ru = translations.get(slug, ("", ""))
    guide_source = payload.get("guide")
    guide = ImportedExerciseGuide(
        setup=_to_guide_array(guide_source, "Setup"),
        how_to_perform=_to_guide_array(guide_source, "How to Perform"),
        technique=_to_guide_array(guide_source, "Technique"),
        things_to_avoid=_to_guide_array(guide_source, "Things to Avoid"),
    )
    return ImportedExercise(
        slug=slug,
        name=str(payload.get("name") or translated_name or slug),
        name_ru=str(payload.get("name_ru") or translated_name_ru or payload.get("name") or slug),
        equipment=str(payload.get("equipment") or "Bodyweight"),
        difficulty=_normalize_difficulty(payload.get("difficulty") if isinstance(payload.get("difficulty"), str) else None),
        force=_normalize_force(payload.get("force") if isinstance(payload.get("force"), str) else None),
        grips=str(payload.get("grips") or "Neutral"),
        mechanic=_normalize_mechanic(payload.get("mechanic") if isinstance(payload.get("mechanic"), str) else None),
        muscles=tuple(item for item in (payload.get("muscles") or []) if isinstance(item, str)),
        steps=tuple(item for item in (payload.get("steps") or []) if isinstance(item, str)),
        guide=guide,
        videos=_build_video_entries(slug, payload, directory),
    )


@lru_cache(maxsize=1)
def load_imported_exercises() -> tuple[ImportedExercise, ...]:
    translations = _parse_csv()
    slugs = sorted(directory.name for directory in EXERCISES_ROOT.iterdir() if directory.is_dir())
    return tuple(_build_entry(slug, translations) for slug in slugs if (EXERCISES_ROOT / slug / f"{slug}.json").exists())


@lru_cache(maxsize=1)
def get_imported_exercise_map() -> dict[str, ImportedExercise]:
    return {exercise.slug: exercise for exercise in load_imported_exercises()}


def get_imported_exercise(slug: str) -> ImportedExercise | None:
    return get_imported_exercise_map().get(slug)


def build_asset_url(base_url: str | None, relative_url: str) -> str:
    if not base_url:
        return relative_url
    return urljoin(base_url, relative_url.lstrip("/"))