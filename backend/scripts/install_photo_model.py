"""Install the pinned Apache-2.0 YOLOX-S model for offline CPU photo cropping."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.photo_crop import MODEL_SHA256, MODEL_URL


def main() -> None:
    target = Path(get_settings().photo_person_model_path)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == MODEL_SHA256:
        print(f"CPU photo model already installed: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".download")
    try:
        checksum = hashlib.sha256()
        with urlopen(MODEL_URL, timeout=120) as response, temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                checksum.update(block)
                output.write(block)
        if checksum.hexdigest() != MODEL_SHA256:
            raise RuntimeError("Photo model checksum mismatch; refusing to install.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Installed CPU photo model: {target}")


if __name__ == "__main__":
    main()