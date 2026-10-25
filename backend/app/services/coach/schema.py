"""Additive repair for local databases bootstrapped before newer Coach columns existed.

`create_all` creates missing tables but never alters existing ones; each stage lists its added columns here,
and the matching Alembic revision calls the same helper. Columns are nullable or server-defaulted only.
"""

from sqlalchemy import Column, Float, Integer, String, inspect
from sqlalchemy.engine import Connection

from alembic.migration import MigrationContext
from alembic.operations import Operations

# (table, column factory). Factories, because a Column object can be attached to one table only.
JOB_COLUMNS = (("coach_jobs", lambda: Column("failures", Integer(), nullable=False, server_default="0")),)
ATTEMPT_BUDGET_COLUMNS = (("coach_attempts", lambda: Column("purpose", String(16), nullable=False, server_default="live")),)
ATTEMPT_JOURNAL_COLUMNS = tuple(("coach_attempts", factory) for factory in (
    lambda: Column("trigger_id", String(8), nullable=True),
    lambda: Column("task", String(40), nullable=True),
    lambda: Column("exercise_label", String(80), nullable=True),
    lambda: Column("set_ordinal", Integer(), nullable=True),
    lambda: Column("outcome", String(24), nullable=True),
    lambda: Column("error_code", String(64), nullable=True),
    lambda: Column("error_detail", String(300), nullable=True),
    lambda: Column("http_status", Integer(), nullable=True),
    lambda: Column("first_byte_ms", Float(), nullable=True),
    lambda: Column("duration_ms", Float(), nullable=True),
    lambda: Column("finished_at", Float(), nullable=True),
    lambda: Column("text_preview", String(300), nullable=True),
    lambda: Column("markup_bytes", Integer(), nullable=True),
    lambda: Column("text_bytes", Integer(), nullable=True),
))
ADDITIVE_COLUMNS = (*JOB_COLUMNS, *ATTEMPT_BUDGET_COLUMNS, *ATTEMPT_JOURNAL_COLUMNS)


def ensure_columns(connection: Connection, columns=ADDITIVE_COLUMNS) -> None:
    schema = inspect(connection)
    operations = Operations(MigrationContext.configure(connection))
    existing: dict[str, set[str]] = {}
    for table, factory in columns:
        if not schema.has_table(table):
            continue
        names = existing.setdefault(table, {col["name"] for col in schema.get_columns(table)})
        column = factory()
        if column.name not in names:
            operations.add_column(table, column)
            names.add(column.name)


def ensure_job_failure_counter(connection: Connection) -> None:
    ensure_columns(connection, JOB_COLUMNS)
