"""Upgrade an isolated SQLite database, never the working trainer database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_direction_column_defaults_down_and_migration_is_reversible(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'direction.db'}")
    command.upgrade(config, "20261014_0009")
    command.upgrade(config, "20261016_0010")
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    try:
        column = next(c for c in inspect(engine).get_columns("exercise_calibrations") if c["name"] == "load_direction")
        assert column["nullable"] is False
        assert "down" in str(column["default"])
        # All legacy rows, if any, must retain the old direction, not opt into upward force.
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM exercise_calibrations WHERE load_direction != 'down'")).scalar_one() == 0
        command.downgrade(config, "20261014_0009")
        assert "load_direction" not in {c["name"] for c in inspect(engine).get_columns("exercise_calibrations")}
    finally:
        engine.dispose()