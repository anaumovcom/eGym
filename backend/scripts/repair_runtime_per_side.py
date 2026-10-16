"""Apply ONLY revision 0011's missing columns; never advance alembic_version.

Read-only by default. --apply requires an explicit existing SQLite database and
an existing SQLite backup. No app bootstrap, HTTP, hardware, or create_all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.models.analytics import ExerciseSession

REVISION = "20261016_0011"
NEW_COLUMNS = {"per_side", "planned_total"}


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def snapshot(connection: Connection) -> dict[str, object]:
    """Hash original row values without logging personal/credential contents."""
    result: dict[str, object] = {}
    inspector = sa.inspect(connection)
    for table in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns(table)
                   if table != "exercise_sessions" or c["name"] not in NEW_COLUMNS]
        rows = connection.exec_driver_sql(
            f"SELECT {', '.join(map(quote, columns))} FROM {quote(table)}"
        )
        hashes = sorted(hashlib.sha256(repr(tuple(row)).encode("utf-8")).digest() for row in rows)
        result[table] = {"rows": len(hashes), "sha256": hashlib.sha256(b"".join(hashes)).hexdigest()}
    return result


def schema_objects(connection: Connection) -> list[tuple[object, ...]]:
    return [tuple(row) for row in connection.exec_driver_sql(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE NOT (type = 'table' AND name = 'exercise_sessions') ORDER BY type, name"
    )]


def inspect_database(connection: Connection) -> dict[str, object]:
    inspector = sa.inspect(connection)
    if not inspector.has_table("exercise_sessions") or not inspector.has_table("alembic_version"):
        raise RuntimeError("Expected existing exercise_sessions and alembic_version tables")
    columns = inspector.get_columns("exercise_sessions")
    return {
        "version": list(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalars()),
        "missing": sorted(NEW_COLUMNS - {column["name"] for column in columns}),
        "columns": [{"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"],
                     "default": c["default"]} for c in columns],
        "tables": snapshot(connection),
        "quick_check": list(connection.exec_driver_sql("PRAGMA quick_check").scalars()),
    }


def repair(connection: Connection) -> dict[str, object]:
    """Caller must hold an explicit SQLite write transaction, including DDL."""
    if connection.dialect.name != "sqlite":
        raise RuntimeError("This narrowly scoped repair supports SQLite only")
    before = inspect_database(connection)
    if before["quick_check"] != ["ok"]:
        raise RuntimeError("SQLite quick_check failed; no repair attempted")
    objects = schema_objects(connection)
    old_columns = sa.inspect(connection).get_columns("exercise_sessions")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    revision = ScriptDirectory.from_config(config).get_revision(REVISION)
    if revision is None:
        raise RuntimeError("Revision 0011 not found")
    # No EnvironmentContext/run_migrations/stamp: execute exactly this upgrade.
    with Operations.context(MigrationContext.configure(connection)):
        revision.module.upgrade()
    after = inspect_database(connection)
    new_columns = sa.inspect(connection).get_columns("exercise_sessions")
    retained_columns = [c for c in new_columns if c["name"] not in NEW_COLUMNS]
    original_columns = [c for c in old_columns if c["name"] not in NEW_COLUMNS]
    # Reflected type instances are distinct; compare their rendered signatures.
    original_signature = [{**c, "type": str(c["type"])} for c in original_columns]
    retained_signature = [{**c, "type": str(c["type"])} for c in retained_columns]
    if (before["tables"] != after["tables"] or before["version"] != after["version"]
            or objects != schema_objects(connection) or original_signature != retained_signature
            or after["missing"] or after["quick_check"] != ["ok"]):
        raise RuntimeError("Preservation verification failed; transaction must roll back")
    # Real mapped entity SELECT: no API/app lifespan or hardware service imports.
    with Session(bind=connection, autoflush=False) as session:
        orm_rows = len(session.scalars(sa.select(ExerciseSession)).all())
    return {"revision_operations": REVISION, "added": before["missing"],
            "alembic_version_unchanged": after["version"], "tables": after["tables"],
            "quick_check": after["quick_check"], "orm_exercise_sessions": orm_rows,
            "original_data_hashes_unchanged": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    database = args.database.resolve(strict=True)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    configured = sa.engine.make_url(config.get_main_option("sqlalchemy.url") or get_settings().database_url)
    if configured.get_backend_name() != "sqlite" or configured.database is None:
        parser.error("Configured database must be SQLite")
    if Path(configured.database).resolve() != database:
        parser.error("Explicit database does not match the effective Alembic/settings URL")
    if args.apply:
        if args.backup is None:
            parser.error("--apply requires an existing --backup (no automatic restore)")
        backup = args.backup.resolve(strict=True)
        if backup == database:
            parser.error("Backup must not be the live database")
        with closing(sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)) as conn:
            if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                parser.error("Backup quick_check failed")
    # mode=rw forbids accidentally creating a database; timeout fails fast if busy.
    mode = "rw" if args.apply else "ro"
    engine = sa.create_engine("sqlite://", poolclass=NullPool, creator=lambda: sqlite3.connect(
        database.as_uri() + f"?mode={mode}", uri=True, timeout=1.0,
    ))
    try:
        with engine.connect() as connection:
            if not args.apply:
                connection.exec_driver_sql("PRAGMA query_only=ON")
            # Explicit BEGIN ensures SQLite DDL is truly transactional. IMMEDIATE
            # prevents concurrent writers from invalidating preservation checks.
            connection.exec_driver_sql("BEGIN IMMEDIATE" if args.apply else "BEGIN")
            try:
                report = repair(connection) if args.apply else inspect_database(connection)
                if args.apply:
                    connection.commit()
                else:
                    connection.rollback()
            except BaseException:
                connection.rollback()
                raise
        print(json.dumps({"database": str(database), "applied": args.apply, **report}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()