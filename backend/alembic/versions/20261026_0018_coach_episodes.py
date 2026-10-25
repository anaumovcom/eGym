"""V11: story recap (episode) per finished workout."""

import sqlalchemy as sa

from alembic import op

revision = "20261026_0018"
down_revision = "20261025_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("coach_episodes"):
        return  # Local databases get the table from create_all at startup.
    op.create_table(
        "coach_episodes",
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workout_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(120), nullable=False, index=True),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(40), nullable=False, server_default=""),
        sa.Column("created_at", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("coach_episodes")
