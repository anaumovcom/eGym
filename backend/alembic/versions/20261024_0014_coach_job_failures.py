"""Repair older Coach job tables missing the failure counter (preserve all job receipts)."""

from alembic import op
from app.services.coach.schema import ensure_job_failure_counter

revision = "20261024_0014"
down_revision = "20261018_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_job_failure_counter(op.get_bind())


def downgrade() -> None:
    op.drop_column("coach_jobs", "failures")