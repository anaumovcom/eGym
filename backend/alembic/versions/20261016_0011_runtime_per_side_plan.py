"""Persist exercise-side mode and intended plan independently of saved results.

Revision ID: 20261016_0011
Revises: 20261016_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261016_0011"
down_revision: str | None = "20261016_0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # A scoped repair may run this revision on a create_all database whose
    # Alembic version lags behind its schema. Never replay unrelated revisions.
    columns = {} if op.get_context().as_sql else {
        column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("exercise_sessions")
    }
    # Validate both existing columns before issuing any DDL.
    if "per_side" in columns:
        column = columns["per_side"]
        default = str(column["default"]).strip("()'\" ").lower()
        if not isinstance(column["type"], sa.Boolean) or column["nullable"] or default not in {"0", "false"}:
            raise RuntimeError("Existing exercise_sessions.per_side is incompatible with revision 0011")
    if "planned_total" in columns:
        column = columns["planned_total"]
        if not isinstance(column["type"], sa.Float) or not column["nullable"] or column["default"] is not None:
            raise RuntimeError("Existing exercise_sessions.planned_total is incompatible with revision 0011")
    if "per_side" not in columns:
        op.add_column("exercise_sessions", sa.Column("per_side", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "planned_total" not in columns:
        op.add_column("exercise_sessions", sa.Column("planned_total", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("exercise_sessions") as batch:
        batch.drop_column("planned_total")
        batch.drop_column("per_side")