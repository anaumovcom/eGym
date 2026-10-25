"""VD: request journal fields on Coach attempts (trigger, outcome, error, timings, preview)."""

from alembic import op
from app.services.coach.schema import ATTEMPT_JOURNAL_COLUMNS, ensure_columns

revision = "20261025_0016"
down_revision = "20261025_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_columns(op.get_bind(), ATTEMPT_JOURNAL_COLUMNS)


def downgrade() -> None:
    for _, factory in reversed(ATTEMPT_JOURNAL_COLUMNS):
        op.drop_column("coach_attempts", factory().name)
