"""Apply exercise_muscles.json to exercise JSON files, changing muscles only."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ALLOWED = set("abdominals biceps calves chest forearms front-shoulders glutes "
              "hamstrings hips lats lowerback obliques quads rear-shoulders "
              "traps traps-middle triceps".split())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    records = json.loads((ROOT / "exercise_muscles.json").read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("Expected a list of folder/muscles records")

    directory = ROOT / "exercises"
    paths: dict[str, Path] = {}
    for path in sorted(directory.rglob("*.json")):
        folder = path.parent.relative_to(directory).as_posix()
        if folder in paths:
            raise ValueError(f"Multiple JSON files in folder: {folder}")
        paths[folder] = path

    desired: dict[str, list[str]] = {}
    for record in records:
        folder, muscles = record["folder"], record["muscles"]
        if folder in desired:
            raise ValueError(f"Duplicate folder: {folder}")
        if not isinstance(muscles, list) or any(
            not isinstance(muscle, str) or muscle not in ALLOWED for muscle in muscles
        ):
            raise ValueError(f"Invalid muscle list for {folder}: {muscles!r}")
        if len(set(muscles)) != len(muscles):
            raise ValueError(f"Duplicate muscles for {folder}")
        desired[folder] = muscles
    if desired.keys() != paths.keys():
        raise ValueError(f"Folder mismatch: missing={paths.keys() - desired.keys()}, "
                         f"unknown={desired.keys() - paths.keys()}")

    changes: list[tuple[Path, bytes, bytes]] = []
    decoder = json.JSONDecoder()
    for folder, path in paths.items():
        original = path.read_bytes()
        text = original.decode("utf-8")
        data = json.loads(text.lstrip("\ufeff"))
        if data["muscles"] == desired[folder]:
            continue
        matches = list(re.finditer(r'^([ \t]*)"muscles"[ \t]*:[ \t]*', text, re.MULTILINE))
        if len(matches) != 1:
            raise ValueError(f"Cannot uniquely locate muscles field: {path}")
        match = matches[0]
        current, length = decoder.raw_decode(text[match.end():])
        if current != data["muscles"]:
            raise ValueError(f"Unexpected muscles field: {path}")
        indent = match.group(1)
        newline = "\r\n" if "\r\n" in text else "\n"
        replacement = json.dumps(desired[folder], ensure_ascii=False, indent=2)
        replacement = replacement.replace("\n", newline + indent)
        updated = text[:match.end()] + replacement + text[match.end() + length:]
        expected = {**data, "muscles": desired[folder]}
        if json.loads(updated.lstrip("\ufeff")) != expected:
            raise ValueError(f"Unexpected change to other fields: {path}")
        changes.append((path, original, updated.encode("utf-8")))

    print(f"Validated: {len(paths)} JSON files; changed: {len(changes)}; "
          f"unchanged: {len(paths) - len(changes)}")
    counts = Counter(muscle for muscles in desired.values() for muscle in muscles)
    print(json.dumps(dict(sorted(counts.items())), ensure_ascii=False))
    print(f"Empty muscle lists: {sum(not muscles for muscles in desired.values())}")
    if not args.apply:
        print("Dry run only. Use --apply to write changes.")
        return

    if changes:
        with tempfile.NamedTemporaryFile(prefix="egym-muscles-backup-", suffix=".zip", delete=False) as backup:
            backup_path = Path(backup.name)
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, original, _ in changes:
                archive.writestr(path.relative_to(ROOT).as_posix(), original)
        print(f"Backup: {backup_path}")
        for path, original, updated in changes:
            if path.read_bytes() != original:
                raise ValueError(f"File changed during execution: {path}")
            path.write_bytes(updated)

    for folder, path in paths.items():
        actual = json.loads(path.read_text(encoding="utf-8-sig"))
        if actual["muscles"] != desired[folder]:
            raise ValueError(f"Verification failed: {path}")
    print(f"Verified all {len(paths)} exercise muscle lists against exercise_muscles.json")


if __name__ == "__main__":
    main()