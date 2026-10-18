"""Export folder names and original muscles from every exercise JSON.

Run from any directory; paths default to this script's directory.
Source files are never modified. Invalid input aborts before writing the export.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def collect_exercise_muscles(directory: Path) -> list[dict[str, object]]:
    if not directory.is_dir():
        raise ValueError(f"Exercise directory does not exist: {directory}")

    paths = sorted(directory.rglob("*.json"))
    if not paths:
        raise ValueError(f"No exercise JSON files found: {directory}")

    records: list[dict[str, object]] = []
    folders: set[str] = set()
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        muscles = data.get("muscles") if isinstance(data, dict) else None
        if not isinstance(muscles, list) or not all(
            isinstance(muscle, str) and muscle.strip() for muscle in muscles
        ):
            raise ValueError(f"Expected a list of nonempty muscle strings: {path}")

        folder = path.parent.relative_to(directory).as_posix()
        if folder in folders:
            raise ValueError(f"Multiple JSON files in exercise folder: {folder}")
        folders.add(folder)
        records.append({"folder": folder, "muscles": muscles})

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercises", type=Path, default=ROOT / "exercises")
    parser.add_argument("--output", type=Path, default=ROOT / "exercise_muscles.json")
    args = parser.parse_args()
    directory = args.exercises.resolve()
    output = args.output.resolve()
    if output.is_relative_to(directory):
        parser.error("Output must be outside the exercise directory")

    records = collect_exercise_muscles(directory)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = Counter(muscle for record in records for muscle in set(record["muscles"]))
    print(f"Exported {len(records)} exercises to {output}")
    print(f"Empty muscle lists: {sum(not record['muscles'] for record in records)}")
    print(f"Unique muscles: {len(counts)}")
    print(json.dumps(dict(sorted(counts.items())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()