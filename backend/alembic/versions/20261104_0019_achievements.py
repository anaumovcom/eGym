"""Persistent achievement catalog, progress, grants, evidence and outbox."""

import sqlalchemy as sa

from alembic import op

revision = "20261104_0019"
down_revision = "20261026_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("achievement_definitions"):
        return
    op.create_table(
        "achievement_definitions",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("rules_version", sa.String(80), nullable=False),
        sa.Column("content_version", sa.String(80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "achievement_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("definition_id", sa.String(80), nullable=False, index=True),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("highest_tier", sa.Integer(), nullable=False),
        sa.Column("data_state", sa.String(32), nullable=False),
        sa.Column("computed_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "definition_id", "scope_key", name="uq_achievement_progress_scope"),
    )
    op.create_table(
        "achievement_grants",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("definition_id", sa.String(80), nullable=False, index=True),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_workout_id", sa.Integer(), sa.ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "definition_id", "tier", "scope_key", name="uq_achievement_grant"),
    )
    op.create_table(
        "achievement_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("grant_id", sa.Integer(), sa.ForeignKey("achievement_grants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.UniqueConstraint("grant_id", "source_type", "source_id", name="uq_achievement_evidence"),
    )
    op.create_table(
        "achievement_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, index=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "source_type", "source_id", "source_revision", name="uq_achievement_outbox"),
    )
    op.create_table(
        "achievement_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("grant_id", sa.Integer(), sa.ForeignKey("achievement_grants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("surface", sa.String(32), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "grant_id", "surface", name="uq_achievement_receipt"),
    )


def downgrade() -> None:
    for table in ("achievement_receipts", "achievement_outbox", "achievement_evidence", "achievement_grants",
                  "achievement_progress", "achievement_definitions"):
        op.drop_table(table)
