from pathlib import Path

from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config


def test_alembic_upgrade_creates_foundation_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert {
        "users",
        "user_profiles",
        "app_settings",
        "machine_status_snapshots",
        "audit_log",
        "user_exercise_states",
        "exercise_history_records",
        "workout_programs",
        "workout_schedule_entries",
        "workout_sessions",
        "exercise_sessions",
        "set_results",
        "muscle_fatigue_events",
        "muscle_fatigue_snapshots",
        "progress_photos",
    }.issubset(table_names)
