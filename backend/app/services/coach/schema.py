"""Additive repair for local databases bootstrapped before the job failure counter existed."""

from sqlalchemy import Column, Integer, inspect
from sqlalchemy.engine import Connection

from alembic.migration import MigrationContext
from alembic.operations import Operations


def ensure_job_failure_counter(connection: Connection) -> None:
    schema = inspect(connection)
    if schema.has_table("coach_jobs") and "failures" not in {col["name"] for col in schema.get_columns("coach_jobs")}:
        Operations(MigrationContext.configure(connection)).add_column(
            "coach_jobs", Column("failures", Integer(), nullable=False, server_default="0"))