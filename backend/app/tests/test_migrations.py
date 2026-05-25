from pathlib import Path

from sqlalchemy import create_engine, inspect, text

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
        "user_hidden_workout_programs",
        "workout_programs",
        "workout_schedule_entries",
        "workout_sessions",
        "exercise_sessions",
        "set_results",
        "muscle_fatigue_events",
        "muscle_fatigue_snapshots",
        "progress_photos",
        "exercise_calibrations",
        "hardware_diagnostic_records",
    }.issubset(table_names)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    actor_user_id,
                    action,
                    target_type,
                    target_id,
                    severity,
                    details,
                    created_at
                ) VALUES (
                    NULL,
                    'hardware_command',
                    'hardware',
                    '1',
                    'info',
                    '{}',
                    CURRENT_TIMESTAMP
                )
                """
            )
        )
