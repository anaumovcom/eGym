"""V1: chosen workout scenario per Coach ledger run."""

import sqlalchemy as sa

from alembic import op

revision = "20261025_0017"
down_revision = "20261025_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("coach_scenarios"):
        return  # Local databases get the table from create_all at startup.
    op.create_table(
        "coach_scenarios",
        sa.Column("run_id", sa.String(64), sa.ForeignKey("coach_runs.id"), primary_key=True),
        sa.Column("user_id", sa.String(120), nullable=False, index=True),
        sa.Column("archetype", sa.String(24), nullable=False),
        sa.Column("title", sa.String(60), nullable=False),
        sa.Column("card", sa.JSON(), nullable=False),
        sa.Column("bible", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(40), nullable=False, server_default=""),
        sa.Column("created_at", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("coach_scenarios")
