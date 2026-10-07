"""Coach preferences, vault ciphertext and durable run/usage/job receipts.

Revision ID: 20261007_0007
Revises: 20260928_0006
"""

import sqlalchemy as sa

from alembic import op

revision = "20261007_0007"
down_revision = "20260928_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("coach_preferences", sa.Column("user_id", sa.String(120), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("revision", sa.Integer(), nullable=False), sa.Column("value", sa.JSON(), nullable=False))
    op.create_table("coach_credentials", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("version", sa.Integer(), nullable=False),
                    sa.Column("ciphertext", sa.Text()), sa.Column("disabled", sa.Boolean(), nullable=False), sa.Column("last_check", sa.String(40), nullable=False))
    op.create_table("coach_operator_sessions", sa.Column("digest", sa.String(64), primary_key=True), sa.Column("auth_version", sa.String(64), nullable=False),
                    sa.Column("expires_at", sa.Float(), nullable=False))
    op.create_table("coach_runs", sa.Column("id", sa.String(64), primary_key=True), sa.Column("user_id", sa.String(120), sa.ForeignKey("users.id"), nullable=False),
                    sa.Column("access_digest", sa.String(64), nullable=False), sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workout_sessions.id"), unique=True),
                    sa.Column("ledger", sa.String(16), nullable=False), sa.Column("state", sa.String(16), nullable=False), sa.Column("cap_micros", sa.Integer(), nullable=False),
                    sa.Column("pricing", sa.JSON(), nullable=False), sa.Column("owner", sa.String(120)), sa.Column("lease_until", sa.Float(), nullable=False),
                    sa.Column("generation", sa.Integer(), nullable=False), sa.Column("credential_version", sa.Integer(), nullable=False), sa.Column("created_at", sa.Float(), nullable=False))
    op.create_table("coach_attempts", sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("coach_runs.id"), nullable=False),
                    sa.Column("opportunity", sa.String(64), nullable=False), sa.Column("stage", sa.String(16), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False),
                    sa.Column("model", sa.String(80), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("reserve_micros", sa.Integer(), nullable=False),
                    sa.Column("cost_micros", sa.Integer()), sa.Column("completeness", sa.String(16), nullable=False), sa.Column("usage", sa.JSON(), nullable=False),
                    sa.Column("pricing", sa.JSON(), nullable=False), sa.Column("bounds", sa.JSON(), nullable=False), sa.Column("generation", sa.Integer(), nullable=False),
                    sa.Column("credential_version", sa.Integer(), nullable=False), sa.Column("sent_at", sa.Float()), sa.Column("created_at", sa.Float(), nullable=False),
                    sa.UniqueConstraint("run_id", "opportunity", "stage", "ordinal"))
    op.create_index("ix_coach_attempts_run_id", "coach_attempts", ["run_id"])
    op.create_table("coach_receipts", sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("coach_runs.id"), nullable=False),
                    sa.Column("canonical", sa.String(64), nullable=False), sa.Column("backend_set_id", sa.Integer()), sa.Column("state", sa.String(16), nullable=False),
                    sa.UniqueConstraint("run_id", "canonical"), sa.UniqueConstraint("run_id", "backend_set_id"))
    op.create_index("ix_coach_receipts_run_id", "coach_receipts", ["run_id"])
    op.create_table("coach_response_receipts", sa.Column("id", sa.String(64), primary_key=True), sa.Column("attempt_id", sa.String(64), sa.ForeignKey("coach_attempts.id"), nullable=False),
                    sa.Column("response_id", sa.String(120), nullable=False), sa.Column("usage", sa.JSON(), nullable=False), sa.UniqueConstraint("attempt_id", "response_id"))
    op.create_table("coach_jobs", sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("coach_runs.id"), nullable=False),
                    sa.Column("idempotency_key", sa.String(120), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False), sa.Column("items", sa.JSON(), nullable=False),
                    sa.Column("completed", sa.JSON(), nullable=False), sa.Column("state", sa.String(16), nullable=False), sa.Column("failures", sa.Integer(), nullable=False), sa.UniqueConstraint("run_id", "idempotency_key"))
    op.create_index("ix_coach_jobs_run_id", "coach_jobs", ["run_id"])


def downgrade():
    for name in ("coach_jobs", "coach_response_receipts", "coach_receipts", "coach_attempts", "coach_runs", "coach_operator_sessions", "coach_credentials", "coach_preferences"):
        op.drop_table(name)