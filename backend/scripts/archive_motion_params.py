"""Archive the v1 motion parameters (152 keys) and tuning presets to JSON.

Plan 16, task 1.2: v1 parameters are not migrated to v2, only kept for reference.

    cd backend && ../.venv/bin/python scripts/archive_motion_params.py [output.json]
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.settings import AppSetting

KEYS = ("hardware.tuning.parameters", "hardware.tuning.presets")


def main() -> None:
    default = Path(__file__).resolve().parents[1] / "media" / f"motion-v1-params-{datetime.now(UTC):%Y%m%d}.json"
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    with SessionLocal() as session:
        rows = session.scalars(select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key.in_(KEYS))).all()
        payload = {"archivedAt": datetime.now(UTC).isoformat(), **{row.key: row.value for row in rows}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{output}: {', '.join(k for k in KEYS if k in payload) or 'нет сохранённых параметров'}")


if __name__ == "__main__":
    main()
