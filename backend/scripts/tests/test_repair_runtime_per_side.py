"""Standalone DB-only tests; run without app/tests' application conftest."""

import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.base import Base
from scripts.repair_runtime_per_side import repair, snapshot


@pytest.fixture()
def engine(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'repair.db'}")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('20260928_0006')")
        connection.exec_driver_sql("ALTER TABLE exercise_sessions DROP COLUMN planned_total")
        connection.exec_driver_sql("ALTER TABLE exercise_sessions DROP COLUMN per_side")
        connection.exec_driver_sql("""INSERT INTO exercise_sessions
            (user_id, exercise_slug, exercise_name, kind, order_index, status, started_at, target_sets, muscle_targets)
            VALUES ('legacy', 'legacy', 'Legacy', 'machine', 1, 'skipped', CURRENT_TIMESTAMP, 2, '[]')""")
    yield engine
    engine.dispose()


@pytest.mark.parametrize("existing", [None, "per_side", "planned_total", "both"])
def test_scoped_upgrade_preserves_data_and_version_and_is_repeatable(engine, existing):
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        if existing in {"per_side", "both"}:
            connection.exec_driver_sql("ALTER TABLE exercise_sessions ADD COLUMN per_side BOOLEAN NOT NULL DEFAULT 0")
            connection.exec_driver_sql("UPDATE exercise_sessions SET per_side=1")
        if existing in {"planned_total", "both"}:
            connection.exec_driver_sql("ALTER TABLE exercise_sessions ADD COLUMN planned_total FLOAT")
            connection.exec_driver_sql("UPDATE exercise_sessions SET planned_total=40")
        before = snapshot(connection)
        statements = []
        sa.event.listen(connection, "before_cursor_execute", lambda conn, cursor, stmt, params, ctx, many: statements.append(stmt))
        result = repair(connection)
        assert result["alembic_version_unchanged"] == ["20260928_0006"]
        assert result["orm_exercise_sessions"] == 1
        assert snapshot(connection) == before
        assert connection.exec_driver_sql("SELECT per_side, planned_total FROM exercise_sessions").one() == (
            1 if existing in {"per_side", "both"} else 0,
            40 if existing in {"planned_total", "both"} else None,
        )
        assert repair(connection)["added"] == []
        changes = [stmt for stmt in statements if stmt.lstrip().upper().startswith(("ALTER", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP"))]
        assert len(changes) == len(result["added"])
        assert all(stmt.startswith("ALTER TABLE exercise_sessions ADD COLUMN") for stmt in changes)
        connection.commit()


def test_incompatible_existing_column_fails_before_any_ddl(engine):
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        connection.exec_driver_sql("ALTER TABLE exercise_sessions ADD COLUMN planned_total TEXT")
        with pytest.raises(RuntimeError, match="incompatible"):
            repair(connection)
        assert "per_side" not in {c["name"] for c in sa.inspect(connection).get_columns("exercise_sessions")}
        connection.rollback()


def test_validation_failure_rolls_back_added_columns(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE exercise_sessions SET kind='invalid_enum'")
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        with pytest.raises(LookupError):
            repair(connection)
        connection.rollback()
    with engine.connect() as connection:
        assert not {"per_side", "planned_total"} & {
            c["name"] for c in sa.inspect(connection).get_columns("exercise_sessions")
        }
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260928_0006"