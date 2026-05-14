import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.main import create_app


def export_openapi(path: Path | None = None) -> Path:
    settings = get_settings()
    output_path = path or Path(settings.openapi_export_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    output_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    written_to = export_openapi()
    print(written_to)
