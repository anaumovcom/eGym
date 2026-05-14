from pathlib import Path

from scripts.export_openapi import export_openapi


def test_export_openapi_writes_schema(tmp_path: Path) -> None:
    output = export_openapi(tmp_path / "openapi.json")
    content = output.read_text(encoding="utf-8")

    assert output.exists()
    assert '"/api/users"' in content
    assert '"/api/dashboard"' in content
    assert '"/api/exercises"' in content
    assert '"/api/quick-start"' in content
    assert '"/api/today"' in content
